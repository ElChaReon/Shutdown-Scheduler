import threading
import sys
import subprocess
from datetime import datetime, timedelta
from tkinter import messagebox
from config import SIMULATE_SHUTDOWN

def _calculate_next_occurrence(current_dt, repeat_days):
    """
    Calculate the next occurrence based on repeat_days.
    repeat_days: list of weekday ints (0=Mon, 6=Sun)
    If empty, repeat daily.
    """
    if not repeat_days:
        # Repeat daily
        next_dt = current_dt + timedelta(days=1)
        return next_dt

    # Find next day that matches repeat_days
    current_weekday = current_dt.weekday()  # 0=Mon, 6=Sun
    days_ahead = []
    for day in repeat_days:
        if day > current_weekday:
            days_ahead.append(day - current_weekday)
        elif day == current_weekday:
            # Same day, but time has passed, so next week
            days_ahead.append(7)
        else:
            days_ahead.append(7 + day - current_weekday)

    if days_ahead:
        min_days = min(days_ahead)
        next_dt = current_dt + timedelta(days=min_days)
        return next_dt
    return None

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

    # After running, check if repeat
    if info.get("repeat", False):
        # Reschedule for next occurrence
        dt = datetime.fromisoformat(when)
        next_dt = _calculate_next_occurrence(dt, info.get("repeat_days", []))
        if next_dt:
            info["when"] = next_dt.isoformat()
            from persistence import save_schedules
            save_schedules(app)
            schedule_timer_for(app, sid)
            app.after(0, lambda: app.status.configure(text=f"Rescheduled {sid[:8]} for {next_dt}"))
            return  # Don't remove the schedule

    # If not repeating, remove the schedule
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
                # past items: if repeating, reschedule; else remove
                if info.get("repeat", False):
                    next_dt = _calculate_next_occurrence(dt, info.get("repeat_days", []))
                    if next_dt:
                        info["when"] = next_dt.isoformat()
                        schedule_timer_for(app, sid)
                        count += 1
                    else:
                        # No next occurrence, remove
                        try:
                            del app.schedules[sid]
                        except KeyError:
                            pass
                else:
                    # Not repeating, remove past items
                    try:
                        del app.schedules[sid]
                    except KeyError:
                        pass
    from persistence import save_schedules
    save_schedules(app)
    print(f"[Scheduler] Restored {count} timers.")