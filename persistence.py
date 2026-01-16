import json
import os
import sys
import subprocess
import shutil
from tkinter import messagebox
from datetime import datetime
import uuid
from config import CONFIG_FILE

def load_schedules(app):
    from config import STORAGE_FILE
    if os.path.exists(STORAGE_FILE):
        try:
            with open(STORAGE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # validate and load
                for item in data:
                    sid = item.get("id") or str(uuid.uuid4())
                    when = item.get("when")
                    try:
                        dt = datetime.fromisoformat(when)
                    except Exception:
                        continue
                    app.schedules[sid] = {
                        "id": sid,
                        "when": dt.isoformat(),
                        "label": item.get("label", ""),
                        "enabled": item.get("enabled", True)
                    }
            app.status.configure(text=f"Loaded {len(app.schedules)} scheduled shutdown(s).")
        except Exception as e:
            messagebox.showwarning("Load error", f"Failed to load schedules: {e}")
    else:
        app.schedules = {}

def save_schedules(app):
    from config import STORAGE_FILE
    try:
        to_save = list(app.schedules.values())
        with open(STORAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(to_save, f, indent=2, ensure_ascii=False)
        app.status.configure(text="Schedules saved.")
    except Exception as e:
        messagebox.showwarning("Save error", f"Failed to save schedules: {e}")

def load_config(app):
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                app.config = json.load(f)
        except Exception:
            app.config = {}
    else:
        app.config = {}
    app.start_with_windows = app.config.get("start_with_windows", False)
    app.startup_var.set(app.start_with_windows)

def save_config(app):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(app.config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        messagebox.showwarning("Save error", f"Failed to save config: {e}")

def toggle_startup(app):
    app.start_with_windows = app.startup_var.get()
    app.config["start_with_windows"] = app.start_with_windows
    save_config(app)
    if app.start_with_windows:
        enable_startup(app)
    else:
        disable_startup(app)

def enable_startup(app):
    startup_dir = os.path.join(os.getenv('APPDATA'), 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
    lnk_path = os.path.join(startup_dir, "ShutdownScheduler.lnk")
    if getattr(sys, 'frozen', False):
        target = sys.executable
        args = ""
    else:
        exe_path = os.path.join(os.path.dirname(__file__), 'dist', 'shutdown_scheduler_tray.exe')
        if os.path.exists(exe_path):
            target = exe_path
            args = ""
        else:
            messagebox.showwarning("Error", "Executable not found. Please build the .exe first using PyInstaller.")
            app.startup_var.set(False)
            app.start_with_windows = False
            save_config(app)
            return
    # Use PowerShell to create shortcut
    ps_command = f"$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('{lnk_path}'); $Shortcut.TargetPath = '{target}'; $Shortcut.Arguments = '{args}'; $Shortcut.WorkingDirectory = '{os.path.dirname(os.path.abspath(__file__))}'; $Shortcut.WindowStyle = 7; $Shortcut.Save()"
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    try:
        result = subprocess.run(["powershell", "-Command", ps_command], capture_output=True, text=True, check=True, startupinfo=startupinfo)
    except subprocess.CalledProcessError as e:
        messagebox.showwarning("Error", f"Failed to enable startup: {e.stderr}")

def disable_startup(app):
    startup_dir = os.path.join(os.getenv('APPDATA'), 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
    lnk_path = os.path.join(startup_dir, "ShutdownScheduler.lnk")
    try:
        if os.path.exists(lnk_path):
            os.remove(lnk_path)
    except Exception as e:
        messagebox.showwarning("Error", f"Failed to disable startup: {e}")