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


def load_strings():
    """Load strings from config file."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return ["Example string 1", "Example string 2"]


def save_strings(strings):
    """Save strings to config file."""
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(strings, f, ensure_ascii=False, indent=2)


def truncate(text, max_len=30):
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


class EditDialog(Gtk.Dialog):
    """Dialog for editing the list of strings."""

    def __init__(self, parent, strings):
        super().__init__(title="Edit Strings", parent=parent, modal=True)
        self.set_default_size(450, 350)
        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                         Gtk.STOCK_OK, Gtk.ResponseType.OK)

        self.strings = strings.copy()

        box = self.get_content_area()
        box.set_spacing(10)
        box.set_margin_start(10)
        box.set_margin_end(10)
        box.set_margin_top(10)
        box.set_margin_bottom(10)

        # List store: display text, full text
        self.store = Gtk.ListStore(str, str)
        for s in self.strings:
            self.store.append([truncate(s), s])

        self.tree = Gtk.TreeView(model=self.store)
        self.tree.set_reorderable(True)
        self.tree.connect("row-activated", self.on_row_activated)

        renderer = Gtk.CellRendererText()
        column = Gtk.TreeViewColumn("Strings (double-click to edit)", renderer, text=0)
        self.tree.append_column(column)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self.tree)
        scroll.set_vexpand(True)
        box.pack_start(scroll, True, True, 0)

        # Buttons
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)

        add_btn = Gtk.Button(label="Add")
        add_btn.connect("clicked", self.on_add)
        btn_box.pack_start(add_btn, False, False, 0)

        edit_btn = Gtk.Button(label="Edit")
        edit_btn.connect("clicked", self.on_edit)
        btn_box.pack_start(edit_btn, False, False, 0)

        remove_btn = Gtk.Button(label="Remove")
        remove_btn.connect("clicked", self.on_remove)
        btn_box.pack_start(remove_btn, False, False, 0)

        up_btn = Gtk.Button(label="Up")
        up_btn.connect("clicked", self.on_move_up)
        btn_box.pack_start(up_btn, False, False, 0)

        down_btn = Gtk.Button(label="Down")
        down_btn.connect("clicked", self.on_move_down)
        btn_box.pack_start(down_btn, False, False, 0)

        box.pack_start(btn_box, False, False, 0)

        self.show_all()

    def on_row_activated(self, tree, path, column):
        """Double-click to edit."""
        self.edit_selected()

    def on_edit(self, button):
        """Edit button clicked."""
        self.edit_selected()

    def edit_selected(self):
        """Open textbox dialog for selected item."""
        selection = self.tree.get_selection()
        model, iter = selection.get_selected()
        if iter:
            full_text = model[iter][1]
            dialog = StringEditDialog(self, full_text)
            response = dialog.run()
            if response == Gtk.ResponseType.OK:
                new_text = dialog.get_text()
                model[iter][0] = truncate(new_text)
                model[iter][1] = new_text
            dialog.destroy()

    def on_add(self, button):
        dialog = StringEditDialog(self, "")
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            new_text = dialog.get_text()
            if new_text.strip():
                self.store.append([truncate(new_text), new_text])
        dialog.destroy()

    def on_remove(self, button):
        selection = self.tree.get_selection()
        model, iter = selection.get_selected()
        if iter:
            model.remove(iter)

    def on_move_up(self, button):
        selection = self.tree.get_selection()
        model, iter = selection.get_selected()
        if iter:
            path = model.get_path(iter)
            if path.get_indices()[0] > 0:
                prev_iter = model.get_iter(Gtk.TreePath.new_from_indices([path.get_indices()[0] - 1]))
                model.swap(iter, prev_iter)

    def on_move_down(self, button):
        selection = self.tree.get_selection()
        model, iter = selection.get_selected()
        if iter:
            path = model.get_path(iter)
            if path.get_indices()[0] < len(model) - 1:
                next_iter = model.get_iter(Gtk.TreePath.new_from_indices([path.get_indices()[0] + 1]))
                model.swap(iter, next_iter)

    def get_strings(self):
        return [row[1] for row in self.store]


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

        self.strings = load_strings()
        self.checkboxes = []

        # Main container with border
        frame = Gtk.Frame()
        frame.set_shadow_type(Gtk.ShadowType.OUT)
        self.add(frame)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        main_box.set_margin_start(10)
        main_box.set_margin_end(10)
        main_box.set_margin_top(10)
        main_box.set_margin_bottom(10)
        frame.add(main_box)

        # Title
        title = Gtk.Label(label="Select strings to paste:")
        title.set_xalign(0)
        main_box.pack_start(title, False, False, 0)

        # Scrolled window for checkboxes
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_max_content_height(300)
        scroll.set_propagate_natural_height(True)

        self.checkbox_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        scroll.add(self.checkbox_box)
        main_box.pack_start(scroll, True, True, 0)

        self.rebuild_checkboxes()

        # Separator
        main_box.pack_start(Gtk.Separator(), False, False, 5)

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

        main_box.pack_start(btn_box, False, False, 0)

        # Handle Escape key
        self.connect("key-press-event", self.on_key_press)
        # Close on focus out
        self.connect("focus-out-event", self.on_focus_out)

        self.show_all()
        self.position_at_cursor()

    def rebuild_checkboxes(self):
        """Rebuild checkbox list from strings."""
        for child in self.checkbox_box.get_children():
            self.checkbox_box.remove(child)

        self.checkboxes = []
        for s in self.strings:
            cb = Gtk.CheckButton(label=truncate(s))
            cb.full_text = s  # Store full text as attribute
            self.checkboxes.append(cb)
            self.checkbox_box.pack_start(cb, False, False, 0)

        self.checkbox_box.show_all()

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
        selected = [cb.full_text for cb in self.checkboxes if cb.get_active()]
        if selected:
            text = ", ".join(selected)
            # Use xclip for reliable clipboard (survives app exit)
            # Copy to CLIPBOARD
            p = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE)
            p.communicate(text.encode("utf-8"))
            # Copy to PRIMARY
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
        dialog = EditDialog(self, self.strings)
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            self.strings = dialog.get_strings()
            save_strings(self.strings)
            self.rebuild_checkboxes()

        dialog.destroy()

    def on_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.destroy()
            Gtk.main_quit()
            return True
        return False

    def on_focus_out(self, widget, event):
        # Don't close if edit dialog is open
        if any(isinstance(w, (EditDialog, StringEditDialog)) for w in Gtk.Window.list_toplevels()):
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
