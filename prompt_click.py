#!/usr/bin/env python3
import gi
import json
import os
import subprocess
import time

gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib

CONFIG_FILE = os.path.expanduser("~/.config/prompt_click/strings.json")

DEFAULT_CONFIG = {
    "settings": {
        "truncate_length": 30
    },
    "sections": [
        {
            "name": "General",
            "strings": ["Example string 1", "Example string 2"]
        }
    ]
}


def load_config():
    """Load config from file with migration support."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)

                # Migration: old format (just a list)
                if isinstance(data, list):
                    return {
                        "settings": DEFAULT_CONFIG["settings"].copy(),
                        "sections": [{"name": "General", "strings": data}]
                    }

                # Migration: old format with "strings" key
                if "strings" in data and "sections" not in data:
                    return {
                        "settings": data.get("settings", DEFAULT_CONFIG["settings"].copy()),
                        "sections": [{"name": "General", "strings": data["strings"]}]
                    }

                return data
        except:
            pass
    return DEFAULT_CONFIG.copy()


def save_config(config):
    """Save config to file."""
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def truncate(text, max_len):
    """Truncate text to max_len characters with ellipsis."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


class StringEditDialog(Gtk.Dialog):
    """Dialog for editing a single string with a textbox."""

    def __init__(self, parent, text=""):
        super().__init__(title="Edit String", parent=parent, modal=True)
        self.set_default_size(500, 200)
        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                         Gtk.STOCK_OK, Gtk.ResponseType.OK)

        box = self.get_content_area()
        box.set_spacing(10)
        box.set_margin_start(10)
        box.set_margin_end(10)
        box.set_margin_top(10)
        box.set_margin_bottom(10)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        self.textview = Gtk.TextView()
        self.textview.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.textview.get_buffer().set_text(text)
        scroll.add(self.textview)
        box.pack_start(scroll, True, True, 0)

        self.show_all()

    def get_text(self):
        buf = self.textview.get_buffer()
        return buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)


class SectionNameDialog(Gtk.Dialog):
    """Dialog for entering section name."""

    def __init__(self, parent, title="Section Name", current_name=""):
        super().__init__(title=title, parent=parent, modal=True)
        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                         Gtk.STOCK_OK, Gtk.ResponseType.OK)

        box = self.get_content_area()
        box.set_spacing(10)
        box.set_margin_start(10)
        box.set_margin_end(10)
        box.set_margin_top(10)
        box.set_margin_bottom(10)

        label = Gtk.Label(label="Section name:")
        label.set_xalign(0)
        box.pack_start(label, False, False, 0)

        self.entry = Gtk.Entry()
        self.entry.set_text(current_name)
        self.entry.connect("activate", lambda w: self.response(Gtk.ResponseType.OK))
        box.pack_start(self.entry, False, False, 0)

        self.show_all()

    def get_name(self):
        return self.entry.get_text().strip()


class MoveToSectionDialog(Gtk.Dialog):
    """Dialog for selecting target section to move string to."""

    def __init__(self, parent, sections, current_section_idx):
        super().__init__(title="Move to Section", parent=parent, modal=True)
        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                         Gtk.STOCK_OK, Gtk.ResponseType.OK)

        box = self.get_content_area()
        box.set_spacing(10)
        box.set_margin_start(10)
        box.set_margin_end(10)
        box.set_margin_top(10)
        box.set_margin_bottom(10)

        label = Gtk.Label(label="Select target section:")
        label.set_xalign(0)
        box.pack_start(label, False, False, 0)

        self.combo = Gtk.ComboBoxText()
        for i, section in enumerate(sections):
            if i != current_section_idx:
                self.combo.append(str(i), section["name"])
        self.combo.set_active(0)
        box.pack_start(self.combo, False, False, 0)

        self.show_all()

    def get_section_index(self):
        active_id = self.combo.get_active_id()
        return int(active_id) if active_id else None


class EditDialog(Gtk.Dialog):
    """Dialog for editing sections and strings with tabs."""

    def __init__(self, parent, config):
        super().__init__(title="Edit Strings", parent=parent, modal=True)
        self.set_default_size(550, 450)
        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                         Gtk.STOCK_OK, Gtk.ResponseType.OK)

        # Deep copy config
        self.config = {
            "settings": config["settings"].copy(),
            "sections": [{"name": s["name"], "strings": s["strings"].copy()}
                         for s in config["sections"]]
        }
        self.truncate_len = self.config["settings"].get("truncate_length", 30)

        box = self.get_content_area()
        box.set_spacing(10)
        box.set_margin_start(10)
        box.set_margin_end(10)
        box.set_margin_top(10)
        box.set_margin_bottom(10)

        # Settings section
        settings_frame = Gtk.Frame(label="Settings")
        settings_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        settings_box.set_margin_start(10)
        settings_box.set_margin_end(10)
        settings_box.set_margin_top(5)
        settings_box.set_margin_bottom(5)

        label = Gtk.Label(label="Display characters:")
        settings_box.pack_start(label, False, False, 0)

        self.truncate_spin = Gtk.SpinButton.new_with_range(10, 200, 5)
        self.truncate_spin.set_value(self.truncate_len)
        settings_box.pack_start(self.truncate_spin, False, False, 0)

        settings_frame.add(settings_box)
        box.pack_start(settings_frame, False, False, 0)

        # Section management buttons
        section_btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)

        add_section_btn = Gtk.Button(label="+ Section")
        add_section_btn.connect("clicked", self.on_add_section)
        section_btn_box.pack_start(add_section_btn, False, False, 0)

        rename_section_btn = Gtk.Button(label="Rename")
        rename_section_btn.connect("clicked", self.on_rename_section)
        section_btn_box.pack_start(rename_section_btn, False, False, 0)

        remove_section_btn = Gtk.Button(label="- Section")
        remove_section_btn.connect("clicked", self.on_remove_section)
        section_btn_box.pack_start(remove_section_btn, False, False, 0)

        box.pack_start(section_btn_box, False, False, 0)

        # Notebook (tabs) for sections
        self.notebook = Gtk.Notebook()
        self.notebook.set_scrollable(True)
        box.pack_start(self.notebook, True, True, 0)

        # Store references to tree views and stores
        self.section_stores = []
        self.section_trees = []

        self.rebuild_tabs()

        self.show_all()

    def rebuild_tabs(self):
        """Rebuild all tabs from config."""
        # Clear existing tabs
        while self.notebook.get_n_pages() > 0:
            self.notebook.remove_page(0)

        self.section_stores = []
        self.section_trees = []

        for idx, section in enumerate(self.config["sections"]):
            self.add_section_tab(section, idx)

    def add_section_tab(self, section, idx):
        """Add a tab for a section."""
        # Create store and tree
        store = Gtk.ListStore(str, str)
        for s in section["strings"]:
            store.append([truncate(s, self.truncate_len), s])

        tree = Gtk.TreeView(model=store)
        tree.set_reorderable(True)
        tree.connect("row-activated", self.on_row_activated)

        renderer = Gtk.CellRendererText()
        column = Gtk.TreeViewColumn("Strings (double-click to edit)", renderer, text=0)
        tree.append_column(column)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.add(tree)

        # Tab content box
        tab_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        tab_box.set_margin_start(5)
        tab_box.set_margin_end(5)
        tab_box.set_margin_top(5)
        tab_box.set_margin_bottom(5)
        tab_box.pack_start(scroll, True, True, 0)

        # String management buttons
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)

        add_btn = Gtk.Button(label="Add")
        add_btn.connect("clicked", self.on_add_string)
        btn_box.pack_start(add_btn, False, False, 0)

        edit_btn = Gtk.Button(label="Edit")
        edit_btn.connect("clicked", self.on_edit_string)
        btn_box.pack_start(edit_btn, False, False, 0)

        remove_btn = Gtk.Button(label="Remove")
        remove_btn.connect("clicked", self.on_remove_string)
        btn_box.pack_start(remove_btn, False, False, 0)

        up_btn = Gtk.Button(label="Up")
        up_btn.connect("clicked", self.on_move_up)
        btn_box.pack_start(up_btn, False, False, 0)

        down_btn = Gtk.Button(label="Down")
        down_btn.connect("clicked", self.on_move_down)
        btn_box.pack_start(down_btn, False, False, 0)

        move_btn = Gtk.Button(label="Move to...")
        move_btn.connect("clicked", self.on_move_to_section)
        btn_box.pack_start(move_btn, False, False, 0)

        tab_box.pack_start(btn_box, False, False, 0)

        # Add tab
        label = Gtk.Label(label=section["name"])
        self.notebook.append_page(tab_box, label)

        self.section_stores.append(store)
        self.section_trees.append(tree)

    def get_current_section_idx(self):
        return self.notebook.get_current_page()

    def get_current_store(self):
        idx = self.get_current_section_idx()
        return self.section_stores[idx] if idx >= 0 else None

    def get_current_tree(self):
        idx = self.get_current_section_idx()
        return self.section_trees[idx] if idx >= 0 else None

    def on_add_section(self, button):
        dialog = SectionNameDialog(self, "New Section")
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            name = dialog.get_name()
            if name:
                self.config["sections"].append({"name": name, "strings": []})
                self.add_section_tab(self.config["sections"][-1], len(self.config["sections"]) - 1)
                self.notebook.show_all()
                self.notebook.set_current_page(len(self.config["sections"]) - 1)
        dialog.destroy()

    def on_rename_section(self, button):
        idx = self.get_current_section_idx()
        if idx < 0:
            return
        current_name = self.config["sections"][idx]["name"]
        dialog = SectionNameDialog(self, "Rename Section", current_name)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            name = dialog.get_name()
            if name:
                self.config["sections"][idx]["name"] = name
                self.notebook.get_tab_label(self.notebook.get_nth_page(idx)).set_text(name)
        dialog.destroy()

    def on_remove_section(self, button):
        idx = self.get_current_section_idx()
        if idx < 0 or len(self.config["sections"]) <= 1:
            return  # Keep at least one section

        dialog = Gtk.MessageDialog(
            parent=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Delete section '{self.config['sections'][idx]['name']}'?"
        )
        dialog.format_secondary_text("All strings in this section will be deleted.")
        response = dialog.run()
        dialog.destroy()

        if response == Gtk.ResponseType.YES:
            del self.config["sections"][idx]
            del self.section_stores[idx]
            del self.section_trees[idx]
            self.notebook.remove_page(idx)

    def on_row_activated(self, tree, path, column):
        self.edit_selected_string()

    def on_edit_string(self, button):
        self.edit_selected_string()

    def edit_selected_string(self):
        tree = self.get_current_tree()
        if not tree:
            return
        selection = tree.get_selection()
        model, iter = selection.get_selected()
        if iter:
            full_text = model[iter][1]
            dialog = StringEditDialog(self, full_text)
            response = dialog.run()
            if response == Gtk.ResponseType.OK:
                new_text = dialog.get_text()
                model[iter][0] = truncate(new_text, self.truncate_len)
                model[iter][1] = new_text
            dialog.destroy()

    def on_add_string(self, button):
        dialog = StringEditDialog(self, "")
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            new_text = dialog.get_text()
            if new_text.strip():
                store = self.get_current_store()
                if store:
                    store.append([truncate(new_text, self.truncate_len), new_text])
        dialog.destroy()

    def on_remove_string(self, button):
        tree = self.get_current_tree()
        if not tree:
            return
        selection = tree.get_selection()
        model, iter = selection.get_selected()
        if iter:
            model.remove(iter)

    def on_move_up(self, button):
        tree = self.get_current_tree()
        if not tree:
            return
        selection = tree.get_selection()
        model, iter = selection.get_selected()
        if iter:
            path = model.get_path(iter)
            if path.get_indices()[0] > 0:
                prev_iter = model.get_iter(Gtk.TreePath.new_from_indices([path.get_indices()[0] - 1]))
                model.swap(iter, prev_iter)

    def on_move_down(self, button):
        tree = self.get_current_tree()
        if not tree:
            return
        selection = tree.get_selection()
        model, iter = selection.get_selected()
        if iter:
            path = model.get_path(iter)
            if path.get_indices()[0] < len(model) - 1:
                next_iter = model.get_iter(Gtk.TreePath.new_from_indices([path.get_indices()[0] + 1]))
                model.swap(iter, next_iter)

    def on_move_to_section(self, button):
        if len(self.config["sections"]) < 2:
            return

        tree = self.get_current_tree()
        if not tree:
            return

        selection = tree.get_selection()
        model, iter = selection.get_selected()
        if not iter:
            return

        current_idx = self.get_current_section_idx()
        dialog = MoveToSectionDialog(self, self.config["sections"], current_idx)
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            target_idx = dialog.get_section_index()
            if target_idx is not None:
                # Get the string
                full_text = model[iter][1]
                # Remove from current
                model.remove(iter)
                # Add to target
                self.section_stores[target_idx].append([truncate(full_text, self.truncate_len), full_text])

        dialog.destroy()

    def get_config(self):
        """Build config from current state."""
        sections = []
        for i, store in enumerate(self.section_stores):
            sections.append({
                "name": self.config["sections"][i]["name"],
                "strings": [row[1] for row in store]
            })
        return {
            "settings": {
                "truncate_length": int(self.truncate_spin.get_value())
            },
            "sections": sections
        }


class PopupWindow(Gtk.Window):
    """Main popup window for selecting strings."""

    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)

        # Remember active window before popup
        try:
            result = subprocess.run(["xdotool", "getactivewindow"],
                                    capture_output=True, text=True, check=True)
            self.previous_window_id = result.stdout.strip()
        except:
            self.previous_window_id = None

        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.set_type_hint(Gdk.WindowTypeHint.POPUP_MENU)
        self.set_resizable(False)

        self.config = load_config()
        self.truncate_len = self.config["settings"].get("truncate_length", 30)
        self.current_section_idx = 0
        self.section_checkboxes = {}  # {section_idx: [checkboxes]}

        # Main container with border
        frame = Gtk.Frame()
        frame.set_shadow_type(Gtk.ShadowType.OUT)
        self.add(frame)

        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.main_box.set_margin_start(10)
        self.main_box.set_margin_end(10)
        self.main_box.set_margin_top(10)
        self.main_box.set_margin_bottom(10)
        frame.add(self.main_box)

        # Section header with navigation
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)

        self.section_label = Gtk.Label()
        self.section_label.set_xalign(0)
        self.section_label.set_markup(self.get_section_header())
        header_box.pack_start(self.section_label, True, True, 0)

        # Navigation hint
        if len(self.config["sections"]) > 1:
            nav_label = Gtk.Label(label="(scroll to switch)")
            nav_label.get_style_context().add_class("dim-label")
            header_box.pack_end(nav_label, False, False, 0)

        self.main_box.pack_start(header_box, False, False, 0)

        # Scrolled window for checkboxes
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_max_content_height(300)
        scroll.set_propagate_natural_height(True)

        # Event box for scroll events
        self.event_box = Gtk.EventBox()
        self.event_box.connect("scroll-event", self.on_scroll)

        self.checkbox_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.event_box.add(self.checkbox_box)
        scroll.add(self.event_box)
        self.main_box.pack_start(scroll, True, True, 0)

        # Initialize checkboxes for all sections
        for i in range(len(self.config["sections"])):
            self.section_checkboxes[i] = []

        self.rebuild_checkboxes()

        # Separator
        self.main_box.pack_start(Gtk.Separator(), False, False, 5)

        # Selected counter
        self.counter_label = Gtk.Label(label="Selected: 0")
        self.counter_label.set_xalign(0)
        self.main_box.pack_start(self.counter_label, False, False, 0)

        # Buttons
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)

        ok_btn = Gtk.Button(label="OK")
        ok_btn.connect("clicked", self.on_ok)
        ok_btn.get_style_context().add_class("suggested-action")
        btn_box.pack_start(ok_btn, True, True, 0)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", self.on_cancel)
        btn_box.pack_start(cancel_btn, True, True, 0)

        edit_btn = Gtk.Button(label="Edit...")
        edit_btn.connect("clicked", self.on_edit)
        btn_box.pack_start(edit_btn, True, True, 0)

        self.main_box.pack_start(btn_box, False, False, 0)

        # Handle Escape key and scroll
        self.connect("key-press-event", self.on_key_press)
        self.connect("scroll-event", self.on_scroll)
        # Close on focus out
        self.connect("focus-out-event", self.on_focus_out)

        self.show_all()
        self.position_at_cursor()

    def get_section_header(self):
        """Get formatted section header."""
        section = self.config["sections"][self.current_section_idx]
        total = len(self.config["sections"])
        if total > 1:
            return f"<b>{section['name']}</b> ({self.current_section_idx + 1}/{total})"
        return f"<b>{section['name']}</b>"

    def rebuild_checkboxes(self):
        """Rebuild checkbox list for current section."""
        for child in self.checkbox_box.get_children():
            self.checkbox_box.remove(child)

        section = self.config["sections"][self.current_section_idx]

        # Create checkboxes if not exist for this section
        if not self.section_checkboxes[self.current_section_idx]:
            for s in section["strings"]:
                cb = Gtk.CheckButton(label=truncate(s, self.truncate_len))
                cb.full_text = s
                cb.connect("toggled", self.on_checkbox_toggled)
                self.section_checkboxes[self.current_section_idx].append(cb)

        # Add checkboxes to box
        for cb in self.section_checkboxes[self.current_section_idx]:
            self.checkbox_box.pack_start(cb, False, False, 0)

        self.checkbox_box.show_all()
        self.section_label.set_markup(self.get_section_header())

    def on_checkbox_toggled(self, checkbox):
        """Update counter when checkbox is toggled."""
        self.update_counter()

    def update_counter(self):
        """Update the selected counter."""
        total = sum(
            sum(1 for cb in cbs if cb.get_active())
            for cbs in self.section_checkboxes.values()
        )
        self.counter_label.set_text(f"Selected: {total}")

    def on_scroll(self, widget, event):
        """Handle mouse scroll to switch sections."""
        if len(self.config["sections"]) <= 1:
            return False

        if event.direction == Gdk.ScrollDirection.UP:
            self.current_section_idx = (self.current_section_idx - 1) % len(self.config["sections"])
            self.rebuild_checkboxes()
            return True
        elif event.direction == Gdk.ScrollDirection.DOWN:
            self.current_section_idx = (self.current_section_idx + 1) % len(self.config["sections"])
            self.rebuild_checkboxes()
            return True
        elif event.direction == Gdk.ScrollDirection.SMOOTH:
            # Handle smooth scrolling (touchpad)
            _, dy = event.get_scroll_deltas()
            if dy < -0.5:
                self.current_section_idx = (self.current_section_idx - 1) % len(self.config["sections"])
                self.rebuild_checkboxes()
                return True
            elif dy > 0.5:
                self.current_section_idx = (self.current_section_idx + 1) % len(self.config["sections"])
                self.rebuild_checkboxes()
                return True

        return False

    def position_at_cursor(self):
        """Position window at mouse cursor."""
        display = Gdk.Display.get_default()
        seat = display.get_default_seat()
        pointer = seat.get_pointer()
        _, x, y = pointer.get_position()

        # Get window size
        self.realize()
        width, height = self.get_size()

        # Get screen size
        screen = self.get_screen()
        monitor = screen.get_monitor_at_point(x, y)
        geometry = screen.get_monitor_geometry(monitor)

        # Adjust position to keep window on screen
        if x + width > geometry.x + geometry.width:
            x = geometry.x + geometry.width - width
        if y + height > geometry.y + geometry.height:
            y = geometry.y + geometry.height - height

        self.move(x, y)

    def on_ok(self, button):
        """Copy selected strings to clipboard and paste."""
        selected = []
        for cbs in self.section_checkboxes.values():
            for cb in cbs:
                if cb.get_active():
                    selected.append(cb.full_text)

        if selected:
            text = ", ".join(selected)
            # Use xclip for reliable clipboard (survives app exit)
            p = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE)
            p.communicate(text.encode("utf-8"))
            p = subprocess.Popen(["xclip", "-selection", "primary"], stdin=subprocess.PIPE)
            p.communicate(text.encode("utf-8"))

            # Close window first
            self.destroy()

            # Restore focus and paste
            if self.previous_window_id:
                time.sleep(0.1)
                subprocess.run(["xdotool", "windowactivate", self.previous_window_id], check=False)
                time.sleep(0.1)
                subprocess.run(["xdotool", "key", "shift+Insert"], check=False)
        else:
            self.destroy()
        Gtk.main_quit()

    def on_cancel(self, button):
        self.destroy()
        Gtk.main_quit()

    def on_edit(self, button):
        """Open edit dialog."""
        dialog = EditDialog(self, self.config)
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            self.config = dialog.get_config()
            self.truncate_len = self.config["settings"].get("truncate_length", 30)
            save_config(self.config)
            # Reset checkboxes
            self.section_checkboxes = {i: [] for i in range(len(self.config["sections"]))}
            self.current_section_idx = min(self.current_section_idx, len(self.config["sections"]) - 1)
            self.rebuild_checkboxes()
            self.update_counter()

        dialog.destroy()

    def on_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.destroy()
            Gtk.main_quit()
            return True
        return False

    def on_focus_out(self, widget, event):
        # Don't close if edit dialog is open
        if any(isinstance(w, (EditDialog, StringEditDialog, SectionNameDialog, MoveToSectionDialog))
               for w in Gtk.Window.list_toplevels()):
            return False
        self.destroy()
        Gtk.main_quit()
        return False


def main():
    win = PopupWindow()
    win.connect("destroy", Gtk.main_quit)
    Gtk.main()


if __name__ == "__main__":
    main()
