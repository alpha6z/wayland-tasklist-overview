#!/usr/bin/env python3
"""
Overview/Exposé-like script tested on labwc 0.91+ to display the current
tasks and make them active/focused. Other wlroots compositors may work, as well. It aims to be a wayland replacement for skippy-xd.

No thumbnails: version 0.5 adds proper icons for each task and a few css
styles to match your preferences.

- make sure to install: wlrctl
- make sure to install the required python dependencies
- chmod +x tasklist-overview.py
- bind it to a convenient key combo / mouse button (rc.xml on labwc)
- enjoy!
"""

author = "alpha6z"
license = "GPLv3"
version = "0.5.3"

import gi
import subprocess
import threading
import os

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GObject, GLib, Pango


class TaskWidget(Gtk.Button):
    def __init__(self, task_name, on_click_callback, icon_pixbuf=None):
        super().__init__()
        self.task_name = task_name
        self.connect("clicked", self.on_click)
        self.on_click_callback = on_click_callback
        self.set_relief(Gtk.ReliefStyle.NONE)

        # build content: vbox with icon (image) centered and label below
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        vbox.set_homogeneous(False)
        vbox.set_margin_top(6)
        vbox.set_margin_bottom(6)
        vbox.set_margin_start(6)
        vbox.set_margin_end(6)

        if icon_pixbuf:
            img = Gtk.Image.new_from_pixbuf(icon_pixbuf)
        else:
            img = Gtk.Image.new()  # empty placeholder

        img.set_halign(Gtk.Align.CENTER)
        img.set_valign(Gtk.Align.CENTER)

        lbl = Gtk.Label(label=task_name)
        lbl.set_ellipsize(Pango.EllipsizeMode.END)
        lbl.set_xalign(0.5)
        lbl.set_yalign(0.5)
        lbl.set_single_line_mode(True)

        vbox.pack_start(img, True, True, 0)
        vbox.pack_start(lbl, False, False, 0)

        self.add(vbox)

        css = b"""
        button {
            background-color: rgba(52,152,219,0.9);
            color: white;
            border-radius: 6px;
            border: 0px;
            font-weight: bold;
        }
        """
        style_provider = Gtk.CssProvider()
        style_provider.load_from_data(css)
        Gtk.StyleContext.add_provider(
            self.get_style_context(), style_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER
        )

    def on_click(self, widget):
        self.on_click_callback(self.task_name)


class MainWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Tasklist Overview")
        self.set_decorated(False)
        self.set_default_size(800, 600)
        self.fullscreen()
        self.set_keep_above(True)
        self.set_app_paintable(True)

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual and self.is_composited():
            self.set_visual(visual)

        # root transparent box + Fixed for absolute positioning
        self.fixed = Gtk.Fixed()
        self.add(self.fixed)

        # list of widgets for positioning
        self.task_widgets = []

        # icon theme
        self.icon_theme = Gtk.IconTheme.get_default()

        # load tasks
        GLib.idle_add(self.refresh_tasks)

        # settings to ensure the background is transparent
        self.connect("draw", self.on_draw)

        # intercept button-press events on the background to consume them
        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )
        self.connect("button-press-event", self.on_background_click)

        # allow the window to receive keyboard events and connect Esc to close
        self.add_events(Gdk.EventMask.KEY_PRESS_MASK)
        self.connect("key-press-event", self.on_key_press)

    def on_draw(self, widget, cr):
        # overlay alpha to play with transparency
        cr.set_source_rgba(0, 0, 0, 0.85)
        cr.paint()
        return False

    def on_background_click(self, widget, event):
        # consume the event on the background window (do not propagate)
        return True

    def refresh_tasks(self):
        for w in self.task_widgets:
            self.fixed.remove(w)
        self.task_widgets = []
        threading.Thread(target=self.load_tasks, daemon=True).start()

    def load_tasks(self):
        try:
            result = subprocess.run(
                ["wlrctl", "toplevel", "list"],
                capture_output=True,
                text=True,
                check=True,
            )
            output = result.stdout
        except Exception as e:
            print("Error retrieving tasks:", e)
            output = ""
        tasks = self.parse_tasks(output)
        if len(tasks) == 0:
            self.destroy()
            Gtk.main_quit()
        GObject.idle_add(self.display_tasks, tasks)

    def parse_tasks(self, output):
        tasks = []
        for line in output.splitlines():
            # do not show itself among the tasks
            if line and not line.startswith(os.path.basename(__file__)):
                tasks.append(line)
        return tasks

    def get_icon_for_task(self, task_name, size):
        # try to infer an icon name from the window "app_id" or title
        icon = None
        try:
            win = task_name.split(":", 1)[0]
            candidate_names = []
            candidate_names.append(win)
            title = task_name.split(": ", 1)[1] if ": " in task_name else ""
            for word in title.split():
                if len(word) > 2:
                    candidate_names.append(word.lower())
            seen = set()
            candidate_names = [
                n for n in candidate_names if not (n in seen or seen.add(n))
            ]
            for name in candidate_names:
                try:
                    if self.icon_theme.has_icon(name):
                        icon = self.icon_theme.load_icon(name, size, 0)
                        break
                except Exception:
                    continue
        except Exception:
            pass

        # fallback to generic application icon
        if icon is None:
            try:
                if self.icon_theme.has_icon("application-x-executable"):
                    icon = self.icon_theme.load_icon("application-x-executable", size, 0)
                elif self.icon_theme.has_icon("application-default-icon"):
                    icon = self.icon_theme.load_icon("application-default-icon", size, 0)
            except Exception:
                icon = None
        return icon

    def display_tasks(self, tasks):
        # calculate window dimensions
        win_w, win_h = self.get_size()
        if win_w <= 0 or win_h <= 0:
            win_w, win_h = 800, 600

        n = len(tasks)
        if n == 0:
            return

        spacing_x = 40
        spacing_y = 40
        ratio_w, ratio_h = 4, 3
        min_btn_w = 60
        min_btn_h = 45  # keeps 4:3 ratio -> 60x45

        best = None  # (btn_w, btn_h, cols, rows)
        for cols in range(1, n + 1):
            rows = (n + cols - 1) // cols
            avail_w = win_w - (cols + 1) * spacing_x
            avail_h = win_h - (rows + 1) * spacing_y
            if avail_w <= 0 or avail_h <= 0:
                continue
            cell_w = avail_w / cols
            cell_h = avail_h / rows
            btn_w = min(cell_w, cell_h * (ratio_w / ratio_h))
            btn_h = btn_w * (ratio_h / ratio_w)
            if btn_h > cell_h:
                btn_h = cell_h
                btn_w = btn_h * (ratio_w / ratio_h)
            if btn_w < min_btn_w or btn_h < min_btn_h:
                continue
            area = btn_w * btn_h
            if best is None or area > best[0] * best[1]:
                best = (btn_w, btn_h, cols, rows)

        if best is None:
            cols = 1
            rows = n
            btn_w = max(min_btn_w, int((win_w - 2 * spacing_x) / cols))
            btn_h = int(btn_w * (ratio_h / ratio_w))
            best = (btn_w, btn_h, cols, rows)

        btn_w, btn_h, cols, rows = best
        btn_w = int(btn_w)
        btn_h = int(btn_h)

        total_w = cols * btn_w + (cols + 1) * spacing_x
        total_h = rows * btn_h + (rows + 1) * spacing_y
        start_x = max(10, (win_w - total_w) // 2)
        start_y = max(10, (win_h - total_h) // 2)

        # remove any existing widgets
        for w in self.task_widgets:
            try:
                self.fixed.remove(w)
            except Exception:
                pass
        self.task_widgets = []

        # shared CSS: change this part to match your theme/preferences
        css_skyblue = b"""
        button { background-color: rgba(52,152,219,0.9); color: white; border-radius: 6px; border: 0px; font-weight: bold; } button:hover { background-color: rgba(41,128,185,0.95); box-shadow: 0 6px 18px rgba(0,0,0,0.45); }
        """
        
        css_gray = b"""
        button { background-color: rgba(120,120,120,0.9); color: white; border-radius: 6px; border: 0px; font-weight: bold; } button:hover { background-color: rgba(90,90,90,0.95); box-shadow: 0 6px 18px rgba(0,0,0,0.45); }
        """
        
        css_darkgray = b"""button { background-color: rgba(70,70,70,0.92); color: white; border-radius: 6px; border: 0px; font-weight: bold; } button:hover { background-color: rgba(40,40,40,0.98); box-shadow: 0 6px 18px rgba(0,0,0,0.55); }"""
        
        css_nordic = b"""button { background-color: rgba(76,86,100,0.98); color: #ECEFF4; border-radius: 6px; border: 1px solid rgba(255,255,255,0.06); font-weight: bold; } button:hover { background-color: rgba(96,120,140,1.0); box-shadow: 0 6px 18px rgba(2,6,23,0.55); }"""
        
        css = css_nordic
        style_provider = Gtk.CssProvider()
        style_provider.load_from_data(css)

        # icon size relative to button height (%)
        icon_size = max(16, int(btn_h * 0.30))

        for idx, task_name in enumerate(tasks):
            r = idx // cols
            c = idx % cols
            x = start_x + spacing_x + c * (btn_w + spacing_x)
            y = start_y + spacing_y + r * (btn_h + spacing_y)

            # load icon pixbuf for this task (may be None)
            pixbuf = self.get_icon_for_task(task_name, icon_size)

            # create TaskWidget which already contains an image+label vertically centered
            tw = TaskWidget(task_name, self.on_task_click, icon_pixbuf=pixbuf)
            tw.set_size_request(btn_w, btn_h)
            Gtk.StyleContext.add_provider(
                tw.get_style_context(), style_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER
            )

            tw.connect("clicked", lambda b, name=task_name: self.on_task_click(name))

            self.fixed.put(tw, x, y)
            tw.show_all()
            self.task_widgets.append(tw)

    def on_task_click(self, task_name):
        try:
            win = task_name.split(":", 1)[0]
            title = task_name.split(": ", 1)[1] if ": " in task_name else ""
            subprocess.Popen(
                ["wlrctl", "toplevel", "focus", f"app_id:{win}", f"title:{title}"]
            )
            print("Selected:", f"[{win}] [{title}]")
        except Exception as e:
            print("Error focusing:", e)
        self.destroy()
        Gtk.main_quit()

    def on_key_press(self, widget, event):
        # exit on ESC press
        if event.keyval == Gdk.KEY_Escape:
            self.close()


def main():
    print("Simple tasklist overview")
    win = MainWindow()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    try:
        Gtk.main()
    except:
        pass


if __name__ == "__main__":
    main()
