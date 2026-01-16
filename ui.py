import customtkinter as ctk
from tkcalendar import Calendar
import tkinter as tk
from tkinter import messagebox
from datetime import datetime, timedelta
import uuid
import os
from persistence import load_schedules, save_schedules, load_config, save_config, toggle_startup
from scheduler import schedule_timer_for, restore_timers
from tray import create_tray_icon, hide_window, show_window, exit_app

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

class SchedulerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.withdraw()  # Start minimized

        self.title("Shutdown Scheduler")
        self.geometry("800x480")
        self.resizable(False, False)

        self.protocol("WM_DELETE_WINDOW", lambda: hide_window(self))

        # Internal data
        self.schedules = {}
        self.timers = {}
        self.config = {}
        self.start_with_windows = False
        self.icon = None

        # Build UI
        self.create_ui()

        # Load config and schedules
        load_config(self)
        # Check if startup shortcut exists and sync checkbox
        startup_dir = os.path.join(os.getenv('APPDATA'), 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
        lnk_path = os.path.join(startup_dir, "ShutdownScheduler.lnk")
        self.start_with_windows = os.path.exists(lnk_path)
        self.startup_var.set(self.start_with_windows)
        save_config(self)  # Sync config with actual state
        load_schedules(self)
        restore_timers(self)
        self.refresh_list_for_selected_day()

        # Create tray icon
        create_tray_icon(self)

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
        self.startup_checkbox = ctk.CTkCheckBox(left_frame, text="Start with Windows", variable=self.startup_var, command=lambda: toggle_startup(self))
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
        save_schedules(self)
        schedule_timer_for(self, sid)
        self.refresh_list_for_selected_day()

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
            schedule_timer_for(self, sid)
        else:
            # cancel timer
            if sid in self.timers:
                try:
                    self.timers[sid].cancel()
                except Exception:
                    pass
                del self.timers[sid]
        save_schedules(self)
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
            save_schedules(self)
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
            from config import SIMULATE_SHUTDOWN
            if SIMULATE_SHUTDOWN:
                messagebox.showinfo("Simulated", f"Simulated shutdown executed:\n{label}\n{when}")
            else:
                import sys
                import subprocess
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