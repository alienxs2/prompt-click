# Prompt Click

A Linux utility that replaces the default middle-click paste with a customizable text snippet selector.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Platform](https://img.shields.io/badge/platform-Linux%20(X11)-lightgrey.svg)

## Features

- **Middle-click popup menu** - Select from predefined text snippets
- **Multi-select** - Choose multiple snippets to paste (joined with ", ")
- **Easy editing** - Add, edit, remove, and reorder snippets via GUI with multi-line text editor
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

- Linux with X11 (not Wayland)
- Python 3
- GTK 3 (python3-gi)
- xbindkeys
- xdotool
- xclip

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
sudo apt install python3 python3-gi xbindkeys xdotool xclip
```

2. Copy the script:
```bash
mkdir -p ~/.local/bin
cp prompt_click.py ~/.local/bin/prompt_click
chmod +x ~/.local/bin/prompt_click
```

3. Configure xbindkeys:
```bash
echo '"$HOME/.local/bin/prompt_click"
  b:2 + Release' > ~/.xbindkeysrc
```

4. Add to autostart:
```bash
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/prompt-click.desktop << EOF
[Desktop Entry]
Type=Application
Name=Prompt Click
Exec=sh -c "sleep 2 && xbindkeys"
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
EOF
```

5. Start xbindkeys:
```bash
xbindkeys
```

## Usage

1. **Click middle mouse button** anywhere to open the popup
2. **Check the snippets** you want to paste
3. **Click OK** - text is copied to clipboard and pasted automatically
4. **Click Edit...** to manage your snippets:
   - Double-click or select + Edit button to modify a snippet (opens multi-line editor)
   - Use Add/Remove to manage the list
   - Use Up/Down to reorder
   - Adjust "Display characters" to change how many characters are shown in the popup

## Configuration

Settings and snippets are stored in `~/.config/prompt_click/strings.json`

Example:
```json
{
  "settings": {
    "truncate_length": 30
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
| `truncate_length` | 30 | Number of characters to display in the popup menu |

## Uninstallation

```bash
./install.sh --uninstall
```

Or manually:
```bash
rm ~/.local/bin/prompt_click
rm ~/.config/autostart/prompt-click.desktop
rm -rf ~/.config/prompt_click
pkill xbindkeys
```

## License

MIT License - see [LICENSE](LICENSE) file.

## Contributing

Pull requests are welcome! Feel free to open issues for bugs or feature requests.
