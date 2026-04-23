# Prompt Click

A Linux utility that replaces the default middle-click paste with a customizable text snippet selector.

The recommended target is Ubuntu GNOME 22.04/24.04 on both X11 and GNOME Wayland.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Platform](https://img.shields.io/badge/platform-Ubuntu%20GNOME%20(X11%20%2B%20Wayland)-lightgrey.svg)

## Features

- **Middle-click popup menu** - Select from predefined text snippets
- **Multi-select** - Choose multiple snippets to paste (joined with ", ")
- **Easy editing** - Add, edit, remove, and reorder snippets via GUI with multi-line text editor
- **Section drag-and-drop** - Reorder top-level sections in Edit mode by dragging tabs
- **One-line previews** - Multi-line strings are shown as one line in lists and popup
- **Auto-paste** - Automatically pastes selected text to the previous window
- **Configurable display** - Adjust the number of characters shown in the popup menu
- **Persistent storage** - Snippets and settings saved to `~/.config/prompt_click/strings.json`

## Screenshot

```
┌─────────────────────────────┐
│ Select strings to paste:   │
│ ☐ Example string 1         │
│ ☐ This is a longer text... │
│ ☐ Another snippet          │
│─────────────────────────────│
│  [OK]  [Cancel]  [Edit...]  │
└─────────────────────────────┘
```

## Requirements

- Ubuntu GNOME 22.04 or 24.04
- Python 3
- GTK 3 (python3-gi)
- xclip
- wl-clipboard (recommended)
- python3-evdev (for the global middle-click daemon)

## Installation

### Quick Install

```bash
git clone https://github.com/alienxs2/prompt-click.git
cd prompt-click
./install.sh
```

### Manual Installation

1. Install dependencies:
```bash
sudo apt install python3 python3-gi xclip wl-clipboard python3-evdev
```

2. Copy the app:
```bash
mkdir -p ~/.local/bin
cp prompt_click.py ~/.local/bin/prompt_click
chmod +x ~/.local/bin/prompt_click
```

3. Install the GNOME middle-click daemon:
```bash
sudo install -m 755 prompt_click_middle_daemon.py /usr/local/bin/prompt_click_middle_daemon.py
sudo install -m 644 systemd/prompt-click-middle.service /etc/systemd/system/prompt-click-middle.service
sudo systemctl daemon-reload
sudo systemctl enable --now prompt-click-middle.service
```

4. Optional desktop launcher for editing/snippet management:
```bash
mkdir -p ~/.local/share/applications
cat > ~/.local/share/applications/prompt-click.desktop << EOF
[Desktop Entry]
Type=Application
Name=Prompt Click
Exec=$HOME/.local/bin/prompt_click --paste-mode auto
Terminal=false
Categories=Utility;
EOF
```

## Usage

1. **Click middle mouse button** anywhere to open the popup
2. **Check the snippets** you want to paste
3. **Click OK** - text is copied to clipboard and pasted automatically
4. **Click Edit...** to manage your snippets:
   - Double-click or select + Edit button to modify a snippet (opens multi-line editor)
   - Use Add/Remove to manage the list
   - Use Up/Down to reorder
   - Drag section tabs (e.g., Dev/QA/Review) to reorder top-level sections
   - Adjust "Display characters" to change how many characters are shown in the popup

## Configuration

Settings and snippets are stored in `~/.config/prompt_click/strings.json`

Example:
```json
{
  "settings": {
    "truncate_length": 100
  },
  "strings": [
    "Hello, World!",
    "Best regards,\nJohn Doe",
    "https://example.com"
  ]
}
```

### Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `truncate_length` | 100 | Number of characters to display in the popup menu |

## Uninstallation

```bash
./install.sh --uninstall
```

Or manually:
```bash
rm ~/.local/bin/prompt_click
rm ~/.local/share/applications/prompt-click.desktop
sudo systemctl disable --now prompt-click-middle.service
sudo rm /etc/systemd/system/prompt-click-middle.service
sudo rm /usr/local/bin/prompt_click_middle_daemon.py
rm -rf ~/.config/prompt_click
sudo systemctl daemon-reload
```

## License

MIT License - see [LICENSE](LICENSE) file.

## Contributing

Pull requests are welcome! Feel free to open issues for bugs or feature requests.
