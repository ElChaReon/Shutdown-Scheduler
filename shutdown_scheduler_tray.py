import customtkinter as ctk
from tkcalendar import Calendar
import tkinter as tk
from tkinter import messagebox
from datetime import datetime, timedelta
import threading
import uuid
import json
import os
import sys
import subprocess
import shutil
from PIL import Image, ImageDraw
import pystray
import time

# ---------- Config ----------
SAVE_PATH = os.path.join(os.getenv("APPDATA") or os.path.expanduser("~"), "ShutdownScheduler", "scheduled_shutdowns.json")
os.makedirs(os.path.dirname(SAVE_PATH), exist_ok=True)
# Use the per-user SAVE_PATH (avoids hard-coded user paths)
STORAGE_FILE = SAVE_PATH
CONFIG_FILE = os.path.join(os.path.dirname(SAVE_PATH), "config.json")
SIMULATE_SHUTDOWN = False  # Set to False for real shutdowns (⚠️)
# ----------------------------

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

class SchedulerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.withdraw()  # Start minimized

        self.title("Shutdown Scheduler")
        self.geometry("800x480")
        self.resizable(False, False)

        self.protocol("WM_DELETE_WINDOW", self.hide_window)

        # Internal data
        self.schedules = {}
        self.timers = {}
        self.config = {}
        self.start_with_windows = False
        self.icon = None

        # Build UI
        self.create_ui()

        # Load config and schedules
        self.load_config()
        # Check if startup shortcut exists and sync checkbox
        startup_dir = os.path.join(os.getenv('APPDATA'), 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
        lnk_path = os.path.join(startup_dir, "ShutdownScheduler.lnk")
        self.start_with_windows = os.path.exists(lnk_path)
        self.startup_var.set(self.start_with_windows)
        self.save_config()  # Sync config with actual state
        self.load_schedules()
        self.restore_timers()
        self.refresh_list_for_selected_day()

        # Create tray icon
        self.create_tray_icon()

    def create_ui(self):
        # Frames
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        left_frame = ctk.CTkFrame(self, corner_radius=8)
        left_frame.grid(row=0, column=0, padx=12, pady=12, sticky="nsew")

        lbl = ctk.CTkLabel(left_frame, text="Pick date", font=ctk.CTkFont(size=16, weight="bold"))
        lbl.grid(row=0, column=0, pady=(10,6))

        self.calendar = Calendar(left_frame, selectmode="day", date_pattern="yyyy-mm-dd")
        self.calendar.grid(row=1, column=0, padx=10, pady=6)

        btn_add = ctk.CTkButton(left_frame, text="Add shutdown for selected day", command=self.open_time_popup)
        btn_add.grid(row=2, column=0, pady=10)

        self.startup_var = tk.BooleanVar(value=self.start_with_windows)
        self.startup_checkbox = ctk.CTkCheckBox(left_frame, text="Start with Windows", variable=self.startup_var, command=self.toggle_startup)
        self.startup_checkbox.grid(row=3, column=0, pady=10)

        right_frame = ctk.CTkFrame(self, corner_radius=8)
        right_frame.grid(row=0, column=1, padx=12, pady=12, sticky="nsew")

        lbl2 = ctk.CTkLabel(right_frame, text="Scheduled shutdowns", font=ctk.CTkFont(size=16, weight="bold"))
        lbl2.grid(row=0, column=0, pady=(10,6), sticky="w", padx=10)

        self.listbox = tk.Listbox(right_frame, height=14, activestyle="none", selectmode=tk.SINGLE)
        self.listbox.grid(row=1, column=0, padx=(10,0), pady=6, sticky="nsew")

        scrollbar = tk.Scrollbar(right_frame, command=self.listbox.yview)
        scrollbar.grid(row=1, column=1, sticky="ns", padx=(0,10), pady=6)
        self.listbox.config(yscrollcommand=scrollbar.set)

        btn_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
        btn_frame.grid(row=2, column=0, pady=8, padx=10, sticky="ew")
        btn_frame.grid_columnconfigure((0,1,2), weight=1)

        ctk.CTkButton(btn_frame, text="Enable/Disable", command=self.toggle_selected).grid(row=0, column=0, padx=4)
        ctk.CTkButton(btn_frame, text="Remove", fg_color="#b22222", hover_color="#ff3333", command=self.remove_selected).grid(row=0, column=1, padx=4)
        ctk.CTkButton(btn_frame, text="Run Now", command=self.run_now_selected).grid(row=0, column=2, padx=4)

        self.status = ctk.CTkLabel(self, text="Ready", anchor="w")
        self.status.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0,8))

        self.calendar.bind("<<CalendarSelected>>", lambda e: self.refresh_list_for_selected_day())

    # ---------- Persistence ----------
    def load_schedules(self):
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
                        self.schedules[sid] = {
                            "id": sid,
                            "when": dt.isoformat(),
                            "label": item.get("label", ""),
                            "enabled": item.get("enabled", True)
                        }
                self.status.configure(text=f"Loaded {len(self.schedules)} scheduled shutdown(s).")
            except Exception as e:
                messagebox.showwarning("Load error", f"Failed to load schedules: {e}")
        else:
            self.schedules = {}

    def save_schedules(self):
        try:
            to_save = list(self.schedules.values())
            with open(STORAGE_FILE, "w", encoding="utf-8") as f:
                json.dump(to_save, f, indent=2, ensure_ascii=False)
            self.status.configure(text="Schedules saved.")
        except Exception as e:
            messagebox.showwarning("Save error", f"Failed to save schedules: {e}")

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
            except Exception:
                self.config = {}
        else:
            self.config = {}
        self.start_with_windows = self.config.get("start_with_windows", False)
        self.startup_var.set(self.start_with_windows)

    def save_config(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            messagebox.showwarning("Save error", f"Failed to save config: {e}")

    def toggle_startup(self):
        self.start_with_windows = self.startup_var.get()
        self.config["start_with_windows"] = self.start_with_windows
        self.save_config()
        if self.start_with_windows:
            self.enable_startup()
        else:
            self.disable_startup()

    def enable_startup(self):
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
                self.startup_var.set(False)
                self.start_with_windows = False
                self.save_config()
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

    def disable_startup(self):
        startup_dir = os.path.join(os.getenv('APPDATA'), 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
        lnk_path = os.path.join(startup_dir, "ShutdownScheduler.lnk")
        try:
            if os.path.exists(lnk_path):
                os.remove(lnk_path)
        except Exception as e:
            messagebox.showwarning("Error", f"Failed to disable startup: {e}")

    # ---------- UI helpers ----------
    def refresh_list_for_selected_day(self):
        selected = self.calendar.get_date()  # yyyy-mm-dd
        # compile items for that day
        date_start = datetime.fromisoformat(selected + "T00:00:00")
        date_end = date_start + timedelta(days=1)
        items = []
        for sid, info in self.schedules.items():
            dt = datetime.fromisoformat(info["when"])
            if date_start <= dt < date_end:
                items.append((dt, sid, info))
        # sort by time
        items.sort(key=lambda x: x[0])
        # refresh listbox
        self.listbox.delete(0, tk.END)
        for dt, sid, info in items:
            enabled_mark = "✅" if info.get("enabled", True) else "⛔"
            label = info.get("label", "")
            display = f"{enabled_mark} {dt.strftime('%H:%M:%S')}  — {label}  (id={sid[:8]})"
            self.listbox.insert(tk.END, display)

    def get_selected_schedule_id(self):
        sel = self.listbox.curselection()
        if not sel:
            return None
        display = self.listbox.get(sel[0])
        # parse id from display (id=xxxx)
        try:
            sid_short = display.split("id=")[1].strip(")")
            # find schedule that startswith sid_short
            for sid in self.schedules:
                if sid.startswith(sid_short):
                    return sid
        except Exception:
            return None
        return None
    # ----------- Tray Integration ------------
    def create_tray_icon(self):
        # create icon image
        image = Image.new("RGB", (64, 64), (0, 0, 0))
        d = ImageDraw.Draw(image)
        d.rectangle((16, 16, 48, 48), fill=(0, 150, 255))
        menu = (
            pystray.MenuItem("Show Window", self.show_window, default=True),
            pystray.MenuItem("Exit", self.exit_app)
        )
        self.icon = pystray.Icon("Shutdown Scheduler", image, "Shutdown Scheduler", menu)
        threading.Thread(target=self.icon.run, daemon=True).start()

    def hide_window(self):
        self.withdraw()

    def show_window(self):
        self.deiconify()
        self.after(100, self.lift)

    def exit_app(self):
        if messagebox.askyesno("Exit", "Exit the Shutdown Scheduler?"):
            if self.icon:
                self.icon.stop()
            self.destroy()
            os._exit(0)
    # ---------- Time popup ----------
    def open_time_popup(self):
        date_str = self.calendar.get_date()  # yyyy-mm-dd
        popup = TimePopup(self, date_str, self.add_shutdown)
        popup.grab_set()

    def add_shutdown(self, iso_when, label="Scheduled shutdown"):
        sid = str(uuid.uuid4())
        self.schedules[sid] = {
            "id": sid,
            "when": iso_when,
            "label": label,
            "enabled": True
        }
        self.save_schedules()
        self.schedule_timer_for(sid)
        self.refresh_list_for_selected_day()

    # ---------- Scheduling ----------
    def schedule_timer_for(self, sid):
        # cancel existing timer if present
        if sid in self.timers:
            try:
                self.timers[sid].cancel()
            except Exception:
                pass
            del self.timers[sid]

        info = self.schedules.get(sid)
        if not info:
            return

        if not info.get("enabled", True):
            return

        dt = datetime.fromisoformat(info["when"])
        now = datetime.now()
        delay = (dt - now).total_seconds()
        if delay <= 0:
            # past time: run immediately (simulate) or skip? We'll run immediately.
            delay = 0.1

        timer = threading.Timer(delay, self._timer_fired, args=(sid,))
        timer.daemon = True
        timer.start()
        self.timers[sid] = timer
        print(f"[Scheduler] Scheduled {sid} at {dt} (in {delay:.1f}s)")

    def _timer_fired(self, sid):
        # called in background thread
        info = self.schedules.get(sid)
        if not info:
            return
        if not info.get("enabled", True):
            return

        when = info.get("when")
        label = info.get("label", "")
        msg = f"Executing shutdown {sid[:8]} scheduled for {when} — {label}"
        print(msg)
        # update UI from main thread
        self.after(0, lambda: self.status.configure(text=msg))

        # perform (simulate by default)
        if SIMULATE_SHUTDOWN:
            # simulation: sleep briefly then log
            print("[Shutdown simulated] device would shut down now (simulation).")
            self.after(0, lambda: messagebox.showinfo("Simulated shutdown", f"Simulated shutdown executed:\n{label}\n{when}"))
        else:
            # real shutdown command for Windows. (Modify for other OS as desired.)
            try:
                if sys.platform.startswith("win"):
                    # immediate shutdown
                    subprocess.run(["shutdown", "/s", "/t", "0"], check=False)
                elif sys.platform.startswith("linux") or sys.platform.startswith("darwin"):
                    # requires sudo privileges; user will need to adjust
                    subprocess.run(["shutdown", "-h", "now"], check=False)
                else:
                    print("Unsupported OS for auto-shutdown.")
            except Exception as e:
                print("Failed to execute shutdown:", e)

        # After running, we remove the schedule automatically.
        try:
            del self.schedules[sid]
        except KeyError:
            pass
        try:
            del self.timers[sid]
        except KeyError:
            pass
        self.save_schedules()
        self.after(0, self.refresh_list_for_selected_day)

    def restore_timers(self):
        # restore active timers on startup for enabled schedules in the future
        count = 0
        for sid, info in list(self.schedules.items()):
            dt = datetime.fromisoformat(info["when"])
            if info.get("enabled", True):
                if dt > datetime.now() - timedelta(seconds=1):
                    self.schedule_timer_for(sid)
                    count += 1
                else:
                    # past items: remove or keep? We'll remove past items by default.
                    try:
                        del self.schedules[sid]
                    except KeyError:
                        pass
        self.save_schedules()
        print(f"[Scheduler] Restored {count} timers.")

    # ---------- Controls for selected ----------
    def toggle_selected(self):
        sid = self.get_selected_schedule_id()
        if not sid:
            messagebox.showinfo("Select", "Please select a shutdown item from the list.")
            return
        info = self.schedules.get(sid)
        if not info:
            return
        info["enabled"] = not info.get("enabled", True)
        if info["enabled"]:
            self.schedule_timer_for(sid)
        else:
            # cancel timer
            if sid in self.timers:
                try:
                    self.timers[sid].cancel()
                except Exception:
                    pass
                del self.timers[sid]
        self.save_schedules()
        self.refresh_list_for_selected_day()

    def remove_selected(self):
        sid = self.get_selected_schedule_id()
        if not sid:
            messagebox.showinfo("Select", "Please select a shutdown item from the list.")
            return
        if messagebox.askyesno("Confirm", "Remove the selected scheduled shutdown?"):
            # cancel timer
            if sid in self.timers:
                try:
                    self.timers[sid].cancel()
                except Exception:
                    pass
                del self.timers[sid]
            try:
                del self.schedules[sid]
            except KeyError:
                pass
            self.save_schedules()
            self.refresh_list_for_selected_day()

    def run_now_selected(self):
        sid = self.get_selected_schedule_id()
        if not sid:
            messagebox.showinfo("Select", "Select an item to run now.")
            return
        # run the same code as fired timer (but from main thread)
        if messagebox.askyesno("Run now", "Execute the selected shutdown now (simulated if SIMULATE_SHUTDOWN=True)?"):
            # perform simulation directly
            info = self.schedules.get(sid)
            when = info.get("when")
            label = info.get("label", "")
            if SIMULATE_SHUTDOWN:
                messagebox.showinfo("Simulated", f"Simulated shutdown executed:\n{label}\n{when}")
            else:
                try:
                    if sys.platform.startswith("win"):
                        subprocess.run(["shutdown","/s","/t","0"], check=False)
                    elif sys.platform.startswith("linux") or sys.platform.startswith("darwin"):
                        subprocess.run(["shutdown", "-h", "now"], check=False)
                except Exception as e:
                    messagebox.showwarning("Error", f"Failed to run shutdown: {e}")


class TimePopup(tk.Toplevel):
    def __init__(self, parent, date_str, callback):
        super().__init__(parent)
        self.parent = parent
        self.callback = callback
        self.date_str = date_str  # yyyy-mm-dd
        self.title(f"Pick time for {date_str}")
        self.geometry("300x200")
        self.resizable(False, False)

        lbl = ctk.CTkLabel(self, text=f"Select time for {date_str}")
        lbl.pack(pady=(10,8))

        frame = ctk.CTkFrame(self, corner_radius=6)
        frame.pack(padx=12, pady=6, fill="x")

        # Hours/Minutes/Seconds spinboxes
        inner = tk.Frame(frame)
        inner.pack(pady=8)

        tk.Label(inner, text="Hour").grid(row=0, column=0, padx=6)
        tk.Label(inner, text="Min").grid(row=0, column=1, padx=6)
        tk.Label(inner, text="Sec").grid(row=0, column=2, padx=6)

        self.hour_var = tk.StringVar(value="12")
        self.min_var = tk.StringVar(value="00")
        self.sec_var = tk.StringVar(value="00")

        self.hour_sb = tk.Spinbox(inner, from_=0, to=23, wrap=True, width=4, textvariable=self.hour_var, format="%02.0f")
        self.hour_sb.grid(row=1, column=0, padx=6)
        self.min_sb = tk.Spinbox(inner, from_=0, to=59, wrap=True, width=4, textvariable=self.min_var, format="%02.0f")
        self.min_sb.grid(row=1, column=1, padx=6)
        self.sec_sb = tk.Spinbox(inner, from_=0, to=59, wrap=True, width=4, textvariable=self.sec_var, format="%02.0f")
        self.sec_sb.grid(row=1, column=2, padx=6)

        # Label input
        self.label_entry = ctk.CTkEntry(self, placeholder_text="Label (optional)")
        self.label_entry.pack(fill="x", padx=12, pady=(6,8))

        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=6)
        ok = ctk.CTkButton(btn_frame, text="Add", command=self.on_add)
        ok.grid(row=0, column=0, padx=6)
        cancel = ctk.CTkButton(btn_frame, text="Cancel", command=self.destroy)
        cancel.grid(row=0, column=1, padx=6)

    def on_add(self):
        try:
            hh = int(self.hour_var.get())
            mm = int(self.min_var.get())
            ss = int(self.sec_var.get())
            dt = datetime.fromisoformat(self.date_str + "T00:00:00").replace(hour=hh, minute=mm, second=ss)
            if dt < datetime.now():
                if not messagebox.askyesno("Past time", "Selected time is in the past. Add anyway (it will run immediately)?"):
                    return
            iso = dt.isoformat()
            label = self.label_entry.get().strip() or "Scheduled shutdown"
            self.callback(iso, label)
            self.destroy()
        except Exception as e:
            messagebox.showwarning("Invalid", f"Invalid time: {e}")

if __name__ == "__main__":
    app = SchedulerApp()
    app.mainloop()
