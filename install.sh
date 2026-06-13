#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.local/bin"
APPLICATIONS_DIR="$HOME/.local/share/applications"
MACOS_LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
MACOS_LABEL="com.prompt-click.middle"
MACOS_PLIST="$MACOS_LAUNCH_AGENTS_DIR/$MACOS_LABEL.plist"
MACOS_DAEMON_APP="$HOME/Applications/Prompt Click Daemon.app"
MACOS_DAEMON="$MACOS_DAEMON_APP/Contents/MacOS/prompt_click_macos_daemon"
MACOS_DAEMON_CLI="$INSTALL_DIR/prompt_click_macos_daemon"
MACOS_EDITOR="$HOME/Applications/Prompt Click Editor.command"
MACOS_SESSION_PID_FILE="$HOME/Library/Logs/prompt-click-middle-session.pid"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}[+]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[-]${NC} $1"
}

require_command() {
    if ! command -v "$1" &> /dev/null; then
        print_error "Missing dependency: $1"
        return 1
    fi
}

python_tk_formula() {
    python3 - <<'PY'
import sys
print(f"python-tk@{sys.version_info.major}.{sys.version_info.minor}")
PY
}

# Linux uninstall function
uninstall_linux() {
    print_status "Uninstalling Prompt Click..."

    pkill xbindkeys 2>/dev/null || true
    rm -f "$INSTALL_DIR/prompt_click"
    rm -f "$APPLICATIONS_DIR/prompt-click.desktop"
    rm -f "$HOME/.xbindkeysrc"

    print_status "Uninstalled. Config at ~/.config/prompt_click/ preserved."
    print_warning "Run 'rm -rf ~/.config/prompt_click' to remove saved snippets."
    exit 0
}

uninstall_macos() {
    print_status "Uninstalling Prompt Click for macOS..."

    launchctl bootout "gui/$(id -u)" "$MACOS_PLIST" 2>/dev/null || true
    rm -f "$INSTALL_DIR/prompt_click"
    rm -f "$MACOS_DAEMON_CLI"
    rm -rf "$MACOS_DAEMON_APP"
    rm -f "$MACOS_PLIST"
    rm -f "$MACOS_EDITOR"
    if [[ -f "$MACOS_SESSION_PID_FILE" ]]; then
        kill "$(cat "$MACOS_SESSION_PID_FILE")" 2>/dev/null || true
        rm -f "$MACOS_SESSION_PID_FILE"
    fi

    print_status "Uninstalled. Config at ~/.config/prompt_click/ preserved."
    print_warning "Run 'rm -rf ~/.config/prompt_click' to remove saved snippets."
    exit 0
}

uninstall() {
    if [[ "$(uname -s)" == "Darwin" ]]; then
        uninstall_macos
    fi
    uninstall_linux
}

# Check for uninstall flag
if [[ "$1" == "--uninstall" ]] || [[ "$1" == "-u" ]]; then
    uninstall
fi

install_macos() {
    print_status "Installing Prompt Click for macOS..."

    local missing=0
    for dep in python3 osascript pbcopy pbpaste launchctl swiftc; do
        require_command "$dep" || missing=1
    done
    if [[ "$missing" -ne 0 ]]; then
        exit 1
    fi

    if ! python3 - <<'PY' 2>/dev/null
import tkinter
PY
    then
        local formula
        formula="$(python_tk_formula)"
        if [[ "${PROMPT_CLICK_INSTALL_DEPS:-0}" == "1" ]] && command -v brew &> /dev/null; then
            print_status "Installing $formula with Homebrew..."
            brew install "$formula"
        else
            print_error "Missing tkinter for the active python3."
            print_status "Install it with: brew install $formula"
            print_status "Or rerun with: PROMPT_CLICK_INSTALL_DEPS=1 $SCRIPT_DIR/install.sh"
            exit 1
        fi
    fi

    mkdir -p "$INSTALL_DIR"
    mkdir -p "$MACOS_LAUNCH_AGENTS_DIR"
    mkdir -p "$HOME/Library/Logs"
    mkdir -p "$HOME/Applications"
    launchctl bootout "gui/$(id -u)" "$MACOS_PLIST" 2>/dev/null || true
    if [[ -f "$MACOS_SESSION_PID_FILE" ]]; then
        kill "$(cat "$MACOS_SESSION_PID_FILE")" 2>/dev/null || true
        rm -f "$MACOS_SESSION_PID_FILE"
    fi
    pkill -f "$MACOS_DAEMON" 2>/dev/null || true
    pkill -f "$MACOS_DAEMON_CLI" 2>/dev/null || true
    rm -rf "$MACOS_DAEMON_APP"
    mkdir -p "$MACOS_DAEMON_APP/Contents/MacOS"
    mkdir -p "$MACOS_DAEMON_APP/Contents/Resources"

    cp "$SCRIPT_DIR/prompt_click_macos.py" "$INSTALL_DIR/prompt_click"
    chmod +x "$INSTALL_DIR/prompt_click"
    print_status "Installed macOS app to $INSTALL_DIR/prompt_click"

    swiftc "$SCRIPT_DIR/prompt_click_macos_daemon.swift" -o "$MACOS_DAEMON"
    chmod +x "$MACOS_DAEMON"
    ln -sf "$MACOS_DAEMON" "$MACOS_DAEMON_CLI"
    cat > "$MACOS_DAEMON_APP/Contents/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>prompt_click_macos_daemon</string>
    <key>CFBundleIdentifier</key>
    <string>$MACOS_LABEL</string>
    <key>CFBundleName</key>
    <string>Prompt Click Daemon</string>
    <key>CFBundleDisplayName</key>
    <string>Prompt Click Daemon</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSUIElement</key>
    <true/>
</dict>
</plist>
EOF
    if command -v codesign &> /dev/null; then
        codesign --force --deep --sign - "$MACOS_DAEMON_APP" >/dev/null 2>&1 || true
    fi
    print_status "Built middle-click daemon at $MACOS_DAEMON_APP"

    cat > "$MACOS_EDITOR" << EOF
#!/bin/bash
"$INSTALL_DIR/prompt_click" --edit
EOF
    chmod +x "$MACOS_EDITOR"
    print_status "Created editor launcher at $MACOS_EDITOR"

    cat > "$MACOS_PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$MACOS_LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$MACOS_DAEMON</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PROMPT_CLICK_BIN</key>
        <string>$INSTALL_DIR/prompt_click</string>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$HOME/Library/Logs/prompt-click-middle.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/Library/Logs/prompt-click-middle.err.log</string>
</dict>
</plist>
EOF

    "$MACOS_DAEMON" --check-permissions || {
        print_warning "Accessibility permission is not granted yet."
        print_warning "Enable Prompt Click in System Settings > Privacy & Security > Accessibility, then rerun this installer."
    }

    launchctl bootstrap "gui/$(id -u)" "$MACOS_PLIST"
    launchctl enable "gui/$(id -u)/$MACOS_LABEL" 2>/dev/null || true
    launchctl kickstart -k "gui/$(id -u)/$MACOS_LABEL" 2>/dev/null || true
    print_status "Loaded LaunchAgent $MACOS_LABEL"

    sleep 1
    if ! launchctl print "gui/$(id -u)/$MACOS_LABEL" 2>/dev/null | grep -q "state = running"; then
        print_warning "LaunchAgent is installed but not running yet, likely due to macOS Accessibility trust."
        print_warning "Starting a session daemon from the current trusted shell so Prompt Click works now."
        nohup "$MACOS_DAEMON" >> "$HOME/Library/Logs/prompt-click-middle.log" 2>> "$HOME/Library/Logs/prompt-click-middle.err.log" &
        echo "$!" > "$MACOS_SESSION_PID_FILE"
        sleep 1
        if kill -0 "$(cat "$MACOS_SESSION_PID_FILE")" 2>/dev/null; then
            print_status "Started session daemon pid $(cat "$MACOS_SESSION_PID_FILE")"
        else
            print_warning "Session daemon did not stay running. Check $HOME/Library/Logs/prompt-click-middle.err.log"
        fi
    fi

    "$INSTALL_DIR/prompt_click" --self-test

    echo ""
    print_status "Installation complete!"
    echo ""
    echo "Usage: middle-click to open Prompt Click, or run:"
    echo "       $INSTALL_DIR/prompt_click --edit"
    echo "       open '$MACOS_EDITOR'"
    echo ""
    print_warning "To uninstall: $SCRIPT_DIR/install.sh --uninstall"
    exit 0
}

install_linux() {
print_status "Installing Prompt Click..."

# Check session type
SESSION_TYPE="${XDG_SESSION_TYPE:-unknown}"
if [[ "$SESSION_TYPE" == "wayland" ]]; then
    print_warning "Wayland session detected."
    print_warning "This installer sets up the Prompt Click app; global middle-click auto-paste on GNOME Wayland also requires the system daemon in prompt_click_middle_daemon.py."
fi

# Check dependencies
DEPS=(python3 xclip)
MISSING=()

for dep in "${DEPS[@]}"; do
    if ! command -v "$dep" &> /dev/null; then
        MISSING+=("$dep")
    fi
done

if [[ ${#MISSING[@]} -gt 0 ]]; then
    print_error "Missing dependencies: ${MISSING[*]}"
    print_status "Install them with:"
    echo "    sudo apt install ${MISSING[*]} python3-gi"
    exit 1
fi

# Check for python3-gi
if ! python3 -c "import gi" 2>/dev/null; then
    print_error "Missing python3-gi (GTK bindings)"
    print_status "Install with: sudo apt install python3-gi"
    exit 1
fi

# Create directories
mkdir -p "$INSTALL_DIR"
mkdir -p "$APPLICATIONS_DIR"

# Copy script
cp "$SCRIPT_DIR/prompt_click.py" "$INSTALL_DIR/prompt_click"
chmod +x "$INSTALL_DIR/prompt_click"
print_status "Installed script to $INSTALL_DIR/prompt_click"

# Create desktop entry for manual launch/editing
cat > "$APPLICATIONS_DIR/prompt-click.desktop" << EOF
[Desktop Entry]
Type=Application
Name=Prompt Click
Comment=Snippet picker and editor
Exec=$INSTALL_DIR/prompt_click --paste-mode auto
Terminal=false
Categories=Utility;
EOF
print_status "Created desktop entry"

echo ""
print_status "Installation complete!"
echo ""
echo "Usage: Launch Prompt Click from the desktop entry to edit and test snippets."
echo "       For GNOME X11/Wayland middle-click integration, install the system daemon from prompt_click_middle_daemon.py and systemd/prompt-click-middle.service."
echo ""
print_warning "To uninstall: $SCRIPT_DIR/install.sh --uninstall"
}

if [[ "$(uname -s)" == "Darwin" ]]; then
    install_macos
fi

install_linux
