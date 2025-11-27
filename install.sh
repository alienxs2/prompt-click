#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.local/bin"
AUTOSTART_DIR="$HOME/.config/autostart"

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
    rm -f "$AUTOSTART_DIR/prompt-click.desktop"
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

# Check for X11
if [[ "$XDG_SESSION_TYPE" != "x11" ]]; then
    print_warning "This tool requires X11. You appear to be running $XDG_SESSION_TYPE."
    print_warning "It may not work correctly on Wayland."
fi

# Check dependencies
DEPS=(python3 xbindkeys xdotool xclip)
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
mkdir -p "$AUTOSTART_DIR"

# Copy script
cp "$SCRIPT_DIR/prompt_click.py" "$INSTALL_DIR/prompt_click"
chmod +x "$INSTALL_DIR/prompt_click"
print_status "Installed script to $INSTALL_DIR/prompt_click"

# Configure xbindkeys
cat > "$HOME/.xbindkeysrc" << EOF
# Prompt Click - middle mouse button
"$INSTALL_DIR/prompt_click"
  b:2 + Release
EOF
print_status "Created ~/.xbindkeysrc"

# Create autostart entry
cat > "$AUTOSTART_DIR/prompt-click.desktop" << EOF
[Desktop Entry]
Type=Application
Name=Prompt Click
Comment=Middle click popup for text snippets
Exec=sh -c "sleep 2 && xbindkeys"
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
EOF
print_status "Created autostart entry"

# Start xbindkeys
pkill xbindkeys 2>/dev/null || true
xbindkeys
print_status "Started xbindkeys"

echo ""
print_status "Installation complete!"
echo ""
echo "Usage: Click middle mouse button to open the snippet selector."
echo "       Edit snippets via the Edit... button in the popup."
echo ""
print_warning "To uninstall: $SCRIPT_DIR/install.sh --uninstall"
