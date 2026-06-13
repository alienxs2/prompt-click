import ApplicationServices
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

    func start() -> Bool {
        let options = [
            kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true
        ] as CFDictionary

        guard AXIsProcessTrustedWithOptions(options) else {
            fputs("\(label): Accessibility permission is required.\n", stderr)
            fputs("Enable the installed daemon in System Settings > Privacy & Security > Accessibility.\n", stderr)
            return false
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

        let process = Process()
        process.executableURL = URL(fileURLWithPath: binary)
        process.arguments = ["--paste-mode", "auto"]
        var environment = ProcessInfo.processInfo.environment
        if let path = environment["PATH"], !path.isEmpty {
            environment["PATH"] = "\(defaultPath):\(path)"
        } else {
            environment["PATH"] = defaultPath
        }
        process.environment = environment
        process.terminationHandler = { [weak self] _ in
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
