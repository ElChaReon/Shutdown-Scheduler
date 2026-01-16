import pystray
from PIL import Image, ImageDraw
import threading
import os
from tkinter import messagebox

def create_tray_icon(app):
    # create icon image
    image = Image.new("RGB", (64, 64), (0, 0, 0))
    d = ImageDraw.Draw(image)
    d.rectangle((16, 16, 48, 48), fill=(0, 150, 255))
    menu = (
        pystray.MenuItem("Show Window", lambda: show_window(app), default=True),
        pystray.MenuItem("Exit", lambda: exit_app(app))
    )
    app.icon = pystray.Icon("Shutdown Scheduler", image, "Shutdown Scheduler", menu)
    threading.Thread(target=app.icon.run, daemon=True).start()

def hide_window(app):
    app.withdraw()

def show_window(app):
    app.deiconify()
    app.after(100, app.lift)

def exit_app(app):
    if messagebox.askyesno("Exit", "Exit the Shutdown Scheduler?"):
        if app.icon:
            app.icon.stop()
        app.destroy()
        os._exit(0)