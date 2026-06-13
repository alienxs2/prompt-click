#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


CONFIG_FILE = Path(os.environ.get(
    "PROMPT_CLICK_CONFIG",
    os.path.expanduser("~/.config/prompt_click/strings.json"),
))
DEFAULT_TRUNCATE_LENGTH = 100
PASTE_MODE_AUTO = "auto"
PASTE_MODE_COPY = "copy"
AUTOPASTE_TRIGGER_PATH = os.environ.get("PROMPT_CLICK_AUTOPASTE_TRIGGER")
AUTOPASTE_TRIGGER_TOKEN = os.environ.get("PROMPT_CLICK_AUTOPASTE_TOKEN")

DEFAULT_CONFIG = {
    "settings": {
        "truncate_length": DEFAULT_TRUNCATE_LENGTH
    },
    "sections": [
        {
            "name": "General",
            "strings": ["Example string 1", "Example string 2"]
        }
    ]
}


def apply_config_migrations(config):
    settings = config.setdefault("settings", {})
    truncate_len = settings.get("truncate_length")

    if truncate_len in (None, 30):
        settings["truncate_length"] = DEFAULT_TRUNCATE_LENGTH

    sections = config.setdefault("sections", [])
    if not sections:
        config["sections"] = [{"name": "General", "strings": []}]

    for idx, section in enumerate(config["sections"], start=1):
        section.setdefault("name", f"Section {idx}")
        section.setdefault("strings", [])

    return config


def load_config():
    if CONFIG_FILE.exists():
        try:
            with CONFIG_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, list):
                return apply_config_migrations({
                    "settings": DEFAULT_CONFIG["settings"].copy(),
                    "sections": [{"name": "General", "strings": data}]
                })

            if "strings" in data and "sections" not in data:
                return apply_config_migrations({
                    "settings": data.get("settings", DEFAULT_CONFIG["settings"].copy()),
                    "sections": [{"name": "General", "strings": data["strings"]}]
                })

            return apply_config_migrations(data)
        except (OSError, json.JSONDecodeError):
            pass

    return apply_config_migrations({
        "settings": DEFAULT_CONFIG["settings"].copy(),
        "sections": [
            {
                "name": section["name"],
                "strings": section["strings"].copy(),
            }
            for section in DEFAULT_CONFIG["sections"]
        ],
    })


def save_config(config):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_FILE.open("w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def truncate(text, max_len):
    single_line = " ".join(
        text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ").split()
    )
    if len(single_line) <= max_len:
        return single_line
    return single_line[:max_len] + "..."


def run_osascript(script):
    return subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        check=False,
    )


def get_frontmost_app():
    script = """
tell application "System Events"
    set frontApp to first application process whose frontmost is true
    set appName to name of frontApp
    try
        set bundleId to bundle identifier of frontApp
    on error
        set bundleId to ""
    end try
end tell
return bundleId & linefeed & appName
"""
    result = run_osascript(script)
    if result.returncode != 0:
        return None

    lines = result.stdout.splitlines()
    if len(lines) < 2:
        return None

    return {
        "bundle_id": lines[0].strip(),
        "name": lines[1].strip(),
    }


def copy_text_to_clipboard(text):
    subprocess.run(["pbcopy"], input=text, text=True, check=True)


def request_autopaste(text):
    if not AUTOPASTE_TRIGGER_PATH or not AUTOPASTE_TRIGGER_TOKEN:
        return False

    try:
        with open(AUTOPASTE_TRIGGER_PATH, "w", encoding="utf-8") as f:
            json.dump({
                "token": AUTOPASTE_TRIGGER_TOKEN,
                "text": text,
            }, f, ensure_ascii=False)
        return True
    except OSError:
        return False


def paste_to_frontmost_app(frontmost_app):
    if not frontmost_app:
        activate = ""
    elif frontmost_app.get("bundle_id"):
        bundle_id = frontmost_app["bundle_id"].replace("\\", "\\\\").replace('"', '\\"')
        activate = f'tell application id "{bundle_id}" to activate\n'
    else:
        app_name = frontmost_app.get("name", "").replace("\\", "\\\\").replace('"', '\\"')
        activate = f'tell application "{app_name}" to activate\n' if app_name else ""

    script = f"""
{activate}delay 0.08
tell application "System Events"
    keystroke "v" using command down
end tell
"""
    result = run_osascript(script)
    return result.returncode == 0


def notify_user(message):
    safe = message.replace("\\", "\\\\").replace('"', '\\"')
    run_osascript(f'display notification "{safe}" with title "Prompt Click"')


def import_tk():
    try:
        import tkinter as tk
        from tkinter import messagebox, simpledialog, ttk
    except ModuleNotFoundError as error:
        print(
            "Prompt Click for macOS requires tkinter. Install it with: "
            "brew install python-tk@3.14",
            file=sys.stderr,
        )
        raise SystemExit(2) from error

    return tk, ttk, messagebox, simpledialog


class MultilineTextDialog:
    def __init__(self, parent, title, initial_text=""):
        tk, ttk, _, _ = import_tk()
        self.result = None
        self.top = tk.Toplevel(parent)
        self.top.title(title)
        self.top.transient(parent)
        self.top.grab_set()
        self.top.minsize(520, 240)

        frame = ttk.Frame(self.top, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        self.text = tk.Text(frame, wrap=tk.WORD, width=70, height=12)
        self.text.insert("1.0", initial_text)
        self.text.pack(fill=tk.BOTH, expand=True)
        self.text.focus_set()

        buttons = ttk.Frame(frame)
        buttons.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(buttons, text="Cancel", command=self.cancel).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="OK", command=self.ok).pack(side=tk.RIGHT, padx=(0, 6))

        self.top.bind("<Escape>", lambda _event: self.cancel())
        self.top.protocol("WM_DELETE_WINDOW", self.cancel)
        parent.wait_window(self.top)

    def ok(self):
        self.result = self.text.get("1.0", "end-1c")
        self.top.destroy()

    def cancel(self):
        self.top.destroy()


class ConfigEditor:
    def __init__(self, parent, config):
        tk, ttk, messagebox, simpledialog = import_tk()
        self.tk = tk
        self.ttk = ttk
        self.messagebox = messagebox
        self.simpledialog = simpledialog
        self.saved = False
        self.config = {
            "settings": config.get("settings", {}).copy(),
            "sections": [
                {
                    "name": section.get("name", f"Section {idx + 1}"),
                    "strings": section.get("strings", []).copy(),
                }
                for idx, section in enumerate(config.get("sections", []))
            ],
        }

        self.top = tk.Toplevel(parent)
        self.top.title("Edit Prompt Click")
        self.top.transient(parent)
        self.top.grab_set()
        self.top.minsize(640, 420)

        outer = ttk.Frame(self.top, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)

        settings = ttk.Frame(outer)
        settings.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(settings, text="Display characters:").pack(side=tk.LEFT)
        self.truncate_var = tk.IntVar(
            value=int(self.config.get("settings", {}).get(
                "truncate_length",
                DEFAULT_TRUNCATE_LENGTH,
            ))
        )
        ttk.Spinbox(
            settings,
            from_=10,
            to=400,
            increment=5,
            width=6,
            textvariable=self.truncate_var,
        ).pack(side=tk.LEFT, padx=(6, 0))

        section_buttons = ttk.Frame(outer)
        section_buttons.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(section_buttons, text="+ Section", command=self.add_section).pack(side=tk.LEFT)
        ttk.Button(section_buttons, text="Rename", command=self.rename_section).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(section_buttons, text="- Section", command=self.remove_section).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(section_buttons, text="Section Up", command=lambda: self.move_section(-1)).pack(side=tk.LEFT, padx=(18, 0))
        ttk.Button(section_buttons, text="Section Down", command=lambda: self.move_section(1)).pack(side=tk.LEFT, padx=(6, 0))

        self.notebook = ttk.Notebook(outer)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        self.listboxes = []
        self.rebuild_tabs()

        bottom = ttk.Frame(outer)
        bottom.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(bottom, text="Cancel", command=self.cancel).pack(side=tk.RIGHT)
        ttk.Button(bottom, text="Save", command=self.save).pack(side=tk.RIGHT, padx=(0, 6))

        self.top.bind("<Escape>", lambda _event: self.cancel())
        self.top.protocol("WM_DELETE_WINDOW", self.cancel)
        parent.wait_window(self.top)

    def current_section_index(self):
        selected = self.notebook.select()
        if not selected:
            return -1
        return self.notebook.index(selected)

    def current_listbox(self):
        idx = self.current_section_index()
        if idx < 0 or idx >= len(self.listboxes):
            return None
        return self.listboxes[idx]

    def selected_string_index(self):
        listbox = self.current_listbox()
        if not listbox:
            return None
        selection = listbox.curselection()
        return selection[0] if selection else None

    def rebuild_tabs(self):
        for tab_id in self.notebook.tabs():
            self.notebook.forget(tab_id)
        self.listboxes = []

        truncate_len = int(self.truncate_var.get() or DEFAULT_TRUNCATE_LENGTH)
        for idx, section in enumerate(self.config["sections"]):
            frame = self.ttk.Frame(self.notebook, padding=8)
            listbox = self.tk.Listbox(frame, activestyle="dotbox")
            listbox.pack(fill=self.tk.BOTH, expand=True)
            listbox.bind("<Double-Button-1>", lambda _event: self.edit_string())

            for value in section["strings"]:
                listbox.insert(self.tk.END, truncate(value, truncate_len))

            buttons = self.ttk.Frame(frame)
            buttons.pack(fill=self.tk.X, pady=(8, 0))
            self.ttk.Button(buttons, text="Add", command=self.add_string).pack(side=self.tk.LEFT)
            self.ttk.Button(buttons, text="Edit", command=self.edit_string).pack(side=self.tk.LEFT, padx=(6, 0))
            self.ttk.Button(buttons, text="Remove", command=self.remove_string).pack(side=self.tk.LEFT, padx=(6, 0))
            self.ttk.Button(buttons, text="Up", command=lambda: self.move_string(-1)).pack(side=self.tk.LEFT, padx=(18, 0))
            self.ttk.Button(buttons, text="Down", command=lambda: self.move_string(1)).pack(side=self.tk.LEFT, padx=(6, 0))
            self.ttk.Button(buttons, text="Move To...", command=self.move_string_to_section).pack(side=self.tk.LEFT, padx=(18, 0))

            self.notebook.add(frame, text=section["name"])
            self.listboxes.append(listbox)

        if self.config["sections"]:
            self.notebook.select(min(0, len(self.config["sections"]) - 1))

    def refresh_current_listbox(self):
        idx = self.current_section_index()
        if idx < 0:
            return
        listbox = self.listboxes[idx]
        listbox.delete(0, self.tk.END)
        truncate_len = int(self.truncate_var.get() or DEFAULT_TRUNCATE_LENGTH)
        for value in self.config["sections"][idx]["strings"]:
            listbox.insert(self.tk.END, truncate(value, truncate_len))

    def add_section(self):
        name = self.simpledialog.askstring("New Section", "Section name:", parent=self.top)
        if not name:
            return
        self.config["sections"].append({"name": name.strip(), "strings": []})
        self.rebuild_tabs()
        self.notebook.select(len(self.config["sections"]) - 1)

    def rename_section(self):
        idx = self.current_section_index()
        if idx < 0:
            return
        current = self.config["sections"][idx]["name"]
        name = self.simpledialog.askstring(
            "Rename Section",
            "Section name:",
            initialvalue=current,
            parent=self.top,
        )
        if not name:
            return
        self.config["sections"][idx]["name"] = name.strip()
        self.notebook.tab(idx, text=name.strip())

    def remove_section(self):
        idx = self.current_section_index()
        if idx < 0:
            return
        if len(self.config["sections"]) <= 1:
            self.messagebox.showinfo("Prompt Click", "Keep at least one section.", parent=self.top)
            return
        name = self.config["sections"][idx]["name"]
        if not self.messagebox.askyesno(
            "Delete Section",
            f"Delete section '{name}' and all strings in it?",
            parent=self.top,
        ):
            return
        del self.config["sections"][idx]
        self.rebuild_tabs()

    def move_section(self, delta):
        idx = self.current_section_index()
        target = idx + delta
        if idx < 0 or target < 0 or target >= len(self.config["sections"]):
            return
        self.config["sections"][idx], self.config["sections"][target] = (
            self.config["sections"][target],
            self.config["sections"][idx],
        )
        self.rebuild_tabs()
        self.notebook.select(target)

    def add_string(self):
        idx = self.current_section_index()
        if idx < 0:
            return
        dialog = MultilineTextDialog(self.top, "Add String")
        if dialog.result is None or not dialog.result.strip():
            return
        self.config["sections"][idx]["strings"].append(dialog.result)
        self.refresh_current_listbox()

    def edit_string(self):
        section_idx = self.current_section_index()
        string_idx = self.selected_string_index()
        if section_idx < 0 or string_idx is None:
            return
        current = self.config["sections"][section_idx]["strings"][string_idx]
        dialog = MultilineTextDialog(self.top, "Edit String", current)
        if dialog.result is None:
            return
        self.config["sections"][section_idx]["strings"][string_idx] = dialog.result
        self.refresh_current_listbox()
        self.current_listbox().selection_set(string_idx)

    def remove_string(self):
        section_idx = self.current_section_index()
        string_idx = self.selected_string_index()
        if section_idx < 0 or string_idx is None:
            return
        del self.config["sections"][section_idx]["strings"][string_idx]
        self.refresh_current_listbox()

    def move_string(self, delta):
        section_idx = self.current_section_index()
        string_idx = self.selected_string_index()
        if section_idx < 0 or string_idx is None:
            return
        target = string_idx + delta
        strings = self.config["sections"][section_idx]["strings"]
        if target < 0 or target >= len(strings):
            return
        strings[string_idx], strings[target] = strings[target], strings[string_idx]
        self.refresh_current_listbox()
        self.current_listbox().selection_set(target)

    def move_string_to_section(self):
        section_idx = self.current_section_index()
        string_idx = self.selected_string_index()
        if section_idx < 0 or string_idx is None or len(self.config["sections"]) < 2:
            return

        choices = [
            f"{idx + 1}. {section['name']}"
            for idx, section in enumerate(self.config["sections"])
            if idx != section_idx
        ]
        choice = self.simpledialog.askstring(
            "Move To Section",
            "Target section number:\n" + "\n".join(choices),
            parent=self.top,
        )
        if not choice:
            return
        try:
            target = int(choice.split(".", 1)[0]) - 1
        except ValueError:
            return
        if target < 0 or target >= len(self.config["sections"]) or target == section_idx:
            return

        value = self.config["sections"][section_idx]["strings"].pop(string_idx)
        self.config["sections"][target]["strings"].append(value)
        self.refresh_current_listbox()

    def save(self):
        self.config["settings"] = {
            "truncate_length": int(self.truncate_var.get() or DEFAULT_TRUNCATE_LENGTH)
        }
        save_config(self.config)
        self.saved = True
        self.top.destroy()

    def cancel(self):
        self.top.destroy()


class PickerApp:
    def __init__(self, paste_mode):
        tk, ttk, messagebox, _ = import_tk()
        self.tk = tk
        self.ttk = ttk
        self.messagebox = messagebox
        self.paste_mode = paste_mode
        self.external_autopaste = bool(AUTOPASTE_TRIGGER_PATH and AUTOPASTE_TRIGGER_TOKEN)
        self.config = load_config()
        self.frontmost_app = (
            get_frontmost_app()
            if paste_mode == PASTE_MODE_AUTO and not self.external_autopaste
            else None
        )
        self.root = tk.Tk()
        self.root.title("Prompt Click")
        self.root.minsize(420, 320)
        self.root.attributes("-topmost", True)
        self.root.protocol("WM_DELETE_WINDOW", self.cancel)

        self.listboxes = []
        self.build_ui()
        self.position_near_pointer()

    def position_near_pointer(self):
        self.root.update_idletasks()
        width = max(self.root.winfo_width(), 420)
        height = max(self.root.winfo_height(), 320)
        pointer_x = self.root.winfo_pointerx()
        pointer_y = self.root.winfo_pointery()
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = min(pointer_x + 12, max(0, screen_width - width - 24))
        y = min(pointer_y + 12, max(0, screen_height - height - 48))
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def build_ui(self):
        for child in self.root.winfo_children():
            child.destroy()

        outer = self.ttk.Frame(self.root, padding=10)
        outer.pack(fill=self.tk.BOTH, expand=True)

        self.notebook = self.ttk.Notebook(outer)
        self.notebook.pack(fill=self.tk.BOTH, expand=True)
        self.listboxes = []
        truncate_len = int(self.config.get("settings", {}).get(
            "truncate_length",
            DEFAULT_TRUNCATE_LENGTH,
        ))

        for section in self.config["sections"]:
            frame = self.ttk.Frame(self.notebook, padding=8)
            listbox = self.tk.Listbox(frame, selectmode=self.tk.MULTIPLE, activestyle="dotbox")
            listbox.pack(fill=self.tk.BOTH, expand=True)
            listbox.bind("<Double-Button-1>", lambda _event: self.accept())
            for value in section.get("strings", []):
                listbox.insert(self.tk.END, truncate(value, truncate_len))
            self.notebook.add(frame, text=section.get("name", "Section"))
            self.listboxes.append(listbox)

        buttons = self.ttk.Frame(outer)
        buttons.pack(fill=self.tk.X, pady=(10, 0))
        self.ttk.Button(buttons, text="Cancel", command=self.cancel).pack(side=self.tk.RIGHT)
        self.ttk.Button(buttons, text="Edit...", command=self.open_editor).pack(side=self.tk.RIGHT, padx=(0, 6))
        self.ttk.Button(buttons, text="Copy", command=self.copy_only).pack(side=self.tk.RIGHT, padx=(0, 6))
        self.ttk.Button(buttons, text="Paste", command=self.accept).pack(side=self.tk.RIGHT, padx=(0, 6))

        self.root.bind("<Escape>", lambda _event: self.cancel())
        self.root.bind("<Return>", lambda _event: self.accept())

    def selected_strings(self):
        selected = []
        for section_idx, listbox in enumerate(self.listboxes):
            strings = self.config["sections"][section_idx].get("strings", [])
            for row_idx in listbox.curselection():
                if row_idx < len(strings):
                    selected.append(strings[row_idx])
        return selected

    def selected_text(self):
        return ", ".join(self.selected_strings())

    def open_editor(self):
        editor = ConfigEditor(self.root, self.config)
        if editor.saved:
            self.config = load_config()
            self.build_ui()

    def copy_only(self):
        text = self.selected_text()
        if not text:
            self.messagebox.showinfo("Prompt Click", "Select at least one string.", parent=self.root)
            return
        copy_text_to_clipboard(text)
        notify_user("Copied selected text")
        self.root.destroy()

    def accept(self):
        text = self.selected_text()
        if not text:
            self.messagebox.showinfo("Prompt Click", "Select at least one string.", parent=self.root)
            return
        copy_text_to_clipboard(text)
        if self.paste_mode == PASTE_MODE_AUTO and self.external_autopaste:
            if not request_autopaste(text):
                notify_user("Copied selected text. Auto-paste trigger failed.")
            self.root.destroy()
            return

        self.root.destroy()
        if self.paste_mode == PASTE_MODE_AUTO:
            if not paste_to_frontmost_app(self.frontmost_app):
                notify_user("Copied selected text. Auto-paste needs Accessibility permission.")
        else:
            notify_user("Copied selected text")

    def cancel(self):
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def run_editor():
    tk, _, _, _ = import_tk()
    root = tk.Tk()
    root.withdraw()
    ConfigEditor(root, load_config())
    root.destroy()


def run_self_test():
    tk, _, _, _ = import_tk()
    config = load_config()
    if not config["sections"]:
        raise SystemExit("self-test failed: no sections after migration")
    root = tk.Tk()
    root.withdraw()
    root.update_idletasks()
    root.destroy()
    print("prompt_click_macos self-test ok")


def main():
    parser = argparse.ArgumentParser(description="Prompt Click for macOS")
    parser.add_argument(
        "--paste-mode",
        choices=[PASTE_MODE_AUTO, PASTE_MODE_COPY],
        default=PASTE_MODE_AUTO,
        help="Copy only or copy and paste into the previously focused app.",
    )
    parser.add_argument("--edit", action="store_true", help="Open the snippet editor.")
    parser.add_argument("--self-test", action="store_true", help="Run a non-interactive smoke test.")
    args = parser.parse_args()

    if args.self_test:
        run_self_test()
        return 0

    if args.edit:
        run_editor()
        return 0

    app = PickerApp(args.paste_mode)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
