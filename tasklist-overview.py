#!/usr/bin/env python3
"""
Crude overview/exposé-like kludge tested on labwc 0.91 to visually
display the current tasks and make them active/focused. It aims to 
be a makeshift replacement for skippy-xd on X/openbox. It might 
end up working on other wayland compositors, as well. 

No window previews, at the moment: just big (beautiful) buttons that
get the job done...

- make sure to install: wlrctl
- make sure to install the required python dependencies
- chmod +x tasklist-overview.py
- bind it to a convenient key combo / mouse button (rc.xml on labwc)
"""

author = "alpha6z"
license = "GPLv3"
version = "0.0.3"

import gi
import subprocess
import threading
import os

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GObject, GdkX11, GLib, Pango

class TaskWidget(Gtk.Button):
    def __init__(self, task_name, on_click_callback):
        super().__init__()
        self.task_name = task_name
        self.set_size_request(140, 70)  # rectangle
        self.set_label(task_name)
        self.connect("clicked", self.on_click)
        self.on_click_callback = on_click_callback
        self.set_relief(Gtk.ReliefStyle.NONE)
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
        Gtk.StyleContext.add_provider(self.get_style_context(), style_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)

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

        # load tasks
        GLib.idle_add(self.refresh_tasks)

        # settings to ensure the background is transparent
        self.connect("draw", self.on_draw)

        # intercept button-press events on the background to consume them (the window blocks clicks), buttons on top will still receive them because they are children and have their own handling
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
        self.connect("button-press-event", self.on_background_click)
        
        # sllow the window to receive keyboard events and connect Esc to close
        self.add_events(Gdk.EventMask.KEY_PRESS_MASK)
        self.connect("key-press-event", self.on_key_press)
        
    def on_draw(self, widget, cr):
        # don't draw anything: transparent background
        cr.set_source_rgba(0, 0, 0, 0.75)
        #cr.set_operator(cr.OPERATOR_SOURCE)
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
            result = subprocess.run(["wlrctl", "toplevel", "list"], capture_output=True, text=True, check=True)
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
            line = line.strip()
            # do not show itself among the tasks
            if line and not line.startswith(os.path.basename(__file__)):
                tasks.append(line)
        return tasks

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
            # maximum width per cell and maximum height per cell
            cell_w = avail_w / cols
            cell_h = avail_h / rows
            # adapt button size to 4:3 ratio
            # try to maximize width while keeping ratio
            btn_w = min(cell_w, cell_h * (ratio_w / ratio_h))
            btn_h = btn_w * (ratio_h / ratio_w)
            # if for some reason btn_h > cell_h, resize
            if btn_h > cell_h:
                btn_h = cell_h
                btn_w = btn_h * (ratio_w / ratio_h)
            if btn_w < min_btn_w or btn_h < min_btn_h:
                # if too small, ignore this configuration
                continue
            area = btn_w * btn_h
            if best is None or area > best[0] * best[1]:
                best = (btn_w, btn_h, cols, rows)

        if best is None:
            # fallback: force at least one column with minimum size
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

        # shared CSS
        css = b"""
        button { background-color: rgba(52,152,219,0.9); color: white; border-radius: 6px; border: 0px; font-weight: bold; }
        """
        style_provider = Gtk.CssProvider()
        style_provider.load_from_data(css)

        for idx, task_name in enumerate(tasks):
            r = idx // cols
            c = idx % cols
            x = start_x + spacing_x + c * (btn_w + spacing_x)
            y = start_y + spacing_y + r * (btn_h + spacing_y)

            btn = Gtk.Button()
            btn.set_relief(Gtk.ReliefStyle.NONE)
            btn.set_size_request(btn_w, btn_h)
            Gtk.StyleContext.add_provider(btn.get_style_context(), style_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)

            lbl = Gtk.Label(label=task_name)
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
            lbl.set_xalign(0.5)
            lbl.set_yalign(0.5)
            lbl.set_single_line_mode(True)
            lbl.set_margin_start(6)
            lbl.set_margin_end(6)

            btn.add(lbl)
            btn.connect("clicked", lambda b, name=task_name: self.on_task_click(name))

            self.fixed.put(btn, x, y)
            btn.show_all()
            self.task_widgets.append(btn)


    def on_task_click(self, task_name):
        #print(f"Task: {task_name}")
        # wlrctl output formatted as "<window>: <title>"
        win = task_name.split(":", 1)[0]
        try:
            subprocess.Popen(["wlrctl", "toplevel", "focus", win])
        except Exception as e:
            print("Error focusing:", e)
        self.destroy()
        Gtk.main_quit()

    def on_key_press(self, widget, event):
        # exit on ESC press
        if event.keyval == Gdk.KEY_Escape:
            self.destroy()
            Gtk.main_quit()
            return True
        return False        

def main():
    print("Simple tasklist overview")
    win = MainWindow()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()

if __name__ == "__main__":
    main()
