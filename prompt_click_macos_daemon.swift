import ApplicationServices
import AppKit
import Foundation

private let label = "Prompt Click macOS middle-click daemon"
private let middleButtonNumber: Int64 = 2
private let launchCooldown: TimeInterval = 0.5
private let defaultPath = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

func writeLine(_ message: String, to handle: FileHandle = .standardOutput) {
    if let data = "\(message)\n".data(using: .utf8) {
        try? handle.write(contentsOf: data)
    }
}

struct AutoPastePayload: Decodable {
    let token: String
    let text: String
}

final class PromptClickDaemon {
    private var eventTap: CFMachPort?
    private var runLoopSource: CFRunLoopSource?
    private var lastLaunch = Date.distantPast
    private var launchInProgress = false
    private let lock = NSLock()

    private var promptBinary: String {
        if let configured = ProcessInfo.processInfo.environment["PROMPT_CLICK_BIN"], !configured.isEmpty {
            return configured
        }

        let home = FileManager.default.homeDirectoryForCurrentUser.path
        return "\(home)/.local/bin/prompt_click"
    }

    private var triggerDirectory: URL {
        let base = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first
            ?? FileManager.default.temporaryDirectory
        return base.appendingPathComponent("PromptClick", isDirectory: true)
    }

    func start() -> Bool {
        let options = [
            kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true
        ] as CFDictionary

        if !AXIsProcessTrustedWithOptions(options) {
            fputs("\(label): Accessibility permission check returned false; trying to create event tap anyway.\n", stderr)
        }

        let mask =
            (1 << CGEventType.otherMouseDown.rawValue) |
            (1 << CGEventType.otherMouseUp.rawValue)

        let callback: CGEventTapCallBack = { proxy, type, event, refcon in
            guard let refcon else {
                return Unmanaged.passUnretained(event)
            }

            let daemon = Unmanaged<PromptClickDaemon>.fromOpaque(refcon).takeUnretainedValue()
            return daemon.handleEvent(proxy: proxy, type: type, event: event)
        }

        let refcon = UnsafeMutableRawPointer(Unmanaged.passUnretained(self).toOpaque())
        guard let tap = CGEvent.tapCreate(
            tap: .cgSessionEventTap,
            place: .headInsertEventTap,
            options: .defaultTap,
            eventsOfInterest: CGEventMask(mask),
            callback: callback,
            userInfo: refcon
        ) else {
            fputs("\(label): failed to create event tap.\n", stderr)
            fputs("Enable Prompt Click in System Settings > Privacy & Security > Accessibility.\n", stderr)
            return false
        }

        eventTap = tap
        guard let source = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, tap, 0) else {
            fputs("\(label): failed to create run loop source.\n", stderr)
            return false
        }

        runLoopSource = source
        CFRunLoopAddSource(CFRunLoopGetCurrent(), source, .commonModes)
        CGEvent.tapEnable(tap: tap, enable: true)
        writeLine("\(label): listening for middle mouse clicks")
        return true
    }

    private func handleEvent(proxy: CGEventTapProxy, type: CGEventType, event: CGEvent) -> Unmanaged<CGEvent>? {
        if type == .tapDisabledByTimeout || type == .tapDisabledByUserInput {
            if let eventTap {
                CGEvent.tapEnable(tap: eventTap, enable: true)
            }
            return nil
        }

        guard type == .otherMouseDown || type == .otherMouseUp else {
            return Unmanaged.passUnretained(event)
        }

        let buttonNumber = event.getIntegerValueField(.mouseEventButtonNumber)
        guard buttonNumber == middleButtonNumber else {
            return Unmanaged.passUnretained(event)
        }

        if type == .otherMouseUp {
            launchPromptClick()
        }

        return nil
    }

    private func launchPromptClick() {
        lock.lock()
        defer { lock.unlock() }

        let now = Date()
        guard now.timeIntervalSince(lastLaunch) >= launchCooldown else {
            return
        }
        guard !launchInProgress else {
            return
        }
        lastLaunch = now
        launchInProgress = true

        let binary = promptBinary
        guard FileManager.default.isExecutableFile(atPath: binary) else {
            fputs("\(label): prompt binary is not executable at \(binary)\n", stderr)
            launchInProgress = false
            return
        }

        writeLine("\(label): launching \(binary)")

        let previousApp = NSWorkspace.shared.frontmostApplication
        let token = UUID().uuidString
        let triggerURL = triggerDirectory.appendingPathComponent("autopaste-\(token).json")
        do {
            try FileManager.default.createDirectory(
                at: triggerDirectory,
                withIntermediateDirectories: true
            )
            try? FileManager.default.removeItem(at: triggerURL)
        } catch {
            fputs("\(label): failed to prepare trigger directory: \(error)\n", stderr)
        }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: binary)
        process.arguments = ["--paste-mode", "auto"]
        var environment = ProcessInfo.processInfo.environment
        if let path = environment["PATH"], !path.isEmpty {
            environment["PATH"] = "\(defaultPath):\(path)"
        } else {
            environment["PATH"] = defaultPath
        }
        environment["PROMPT_CLICK_AUTOPASTE_TOKEN"] = token
        environment["PROMPT_CLICK_AUTOPASTE_TRIGGER"] = triggerURL.path
        process.environment = environment
        process.terminationHandler = { [weak self] _ in
            self?.handlePromptExit(triggerURL: triggerURL, token: token, previousApp: previousApp)
            self?.lock.lock()
            self?.launchInProgress = false
            self?.lock.unlock()
            writeLine("\(label): prompt process exited")
        }

        do {
            try process.run()
        } catch {
            fputs("\(label): failed to launch \(binary): \(error)\n", stderr)
            launchInProgress = false
        }
    }

    private func handlePromptExit(triggerURL: URL, token: String, previousApp: NSRunningApplication?) {
        defer {
            try? FileManager.default.removeItem(at: triggerURL)
        }

        guard
            let data = try? Data(contentsOf: triggerURL),
            let payload = try? JSONDecoder().decode(AutoPastePayload.self, from: data),
            payload.token == token
        else {
            writeLine("\(label): prompt closed without paste request")
            return
        }

        setClipboard(payload.text)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.12) {
            previousApp?.activate(options: [])
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.12) {
                self.emitPaste()
                writeLine("\(label): pasted selected text")
            }
        }
    }

    private func setClipboard(_ text: String) {
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        pasteboard.setString(text, forType: .string)
    }

    private func emitPaste() {
        let source = CGEventSource(stateID: .hidSystemState)
        let keyCodeV = CGKeyCode(9)

        guard
            let keyDown = CGEvent(keyboardEventSource: source, virtualKey: keyCodeV, keyDown: true),
            let keyUp = CGEvent(keyboardEventSource: source, virtualKey: keyCodeV, keyDown: false)
        else {
            fputs("\(label): failed to create Cmd+V events\n", stderr)
            return
        }

        keyDown.flags = .maskCommand
        keyUp.flags = .maskCommand
        keyDown.post(tap: .cghidEventTap)
        keyUp.post(tap: .cghidEventTap)
    }
}

func checkPermissions(prompt: Bool) -> Int32 {
    let options = [
        kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: prompt
    ] as CFDictionary
    let trusted = AXIsProcessTrustedWithOptions(options)
    print(trusted ? "accessibility: trusted" : "accessibility: not trusted")
    return trusted ? 0 : 2
}

if CommandLine.arguments.contains("--check-permissions") {
    exit(checkPermissions(prompt: true))
}

if CommandLine.arguments.contains("--version") {
    print("prompt_click_macos_daemon 1.0")
    exit(0)
}

let daemon = PromptClickDaemon()
guard daemon.start() else {
    exit(2)
}

RunLoop.current.run()
