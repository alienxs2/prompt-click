#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.local/bin"
APPLICATIONS_DIR="$HOME/.local/share/applications"

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

# Uninstall function
uninstall() {
    print_status "Uninstalling Prompt Click..."

    pkill xbindkeys 2>/dev/null || true
    rm -f "$INSTALL_DIR/prompt_click"
    rm -f "$APPLICATIONS_DIR/prompt-click.desktop"
    rm -f "$HOME/.xbindkeysrc"

    print_status "Uninstalled. Config at ~/.config/prompt_click/ preserved."
    print_warning "Run 'rm -rf ~/.config/prompt_click' to remove saved snippets."
    exit 0
}

# Check for uninstall flag
if [[ "$1" == "--uninstall" ]] || [[ "$1" == "-u" ]]; then
    uninstall
fi

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
