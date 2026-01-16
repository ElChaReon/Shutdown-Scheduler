import threading
import time
import sys
import subprocess
from datetime import datetime, timedelta
from tkinter import messagebox
from config import SIMULATE_SHUTDOWN

def schedule_timer_for(app, sid):
    # cancel existing timer if present
    if sid in app.timers:
        try:
            app.timers[sid].cancel()
        except Exception:
            pass
        del app.timers[sid]

    info = app.schedules.get(sid)
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

    timer = threading.Timer(delay, _timer_fired, args=(app, sid))
    timer.daemon = True
    timer.start()
    app.timers[sid] = timer
    print(f"[Scheduler] Scheduled {sid} at {dt} (in {delay:.1f}s)")

def _timer_fired(app, sid):
    # called in background thread
    info = app.schedules.get(sid)
    if not info:
        return
    if not info.get("enabled", True):
        return

    when = info.get("when")
    label = info.get("label", "")
    msg = f"Executing shutdown {sid[:8]} scheduled for {when} — {label}"
    print(msg)
    # update UI from main thread
    app.after(0, lambda: app.status.configure(text=msg))

    # perform (simulate by default)
    if SIMULATE_SHUTDOWN:
        # simulation: sleep briefly then log
        print("[Shutdown simulated] device would shut down now (simulation).")
        app.after(0, lambda: messagebox.showinfo("Simulated shutdown", f"Simulated shutdown executed:\n{label}\n{when}"))
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
        del app.schedules[sid]
    except KeyError:
        pass
    try:
        del app.timers[sid]
    except KeyError:
        pass
    from persistence import save_schedules
    save_schedules(app)
    app.after(0, app.refresh_list_for_selected_day)

def restore_timers(app):
    # restore active timers on startup for enabled schedules in the future
    count = 0
    for sid, info in list(app.schedules.items()):
        dt = datetime.fromisoformat(info["when"])
        if info.get("enabled", True):
            if dt > datetime.now() - timedelta(seconds=1):
                schedule_timer_for(app, sid)
                count += 1
            else:
                # past items: remove or keep? We'll remove past items by default.
                try:
                    del app.schedules[sid]
                except KeyError:
                    pass
    from persistence import save_schedules
    save_schedules(app)
    print(f"[Scheduler] Restored {count} timers.")