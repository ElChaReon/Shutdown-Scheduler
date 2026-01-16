import os

# ---------- Config ----------
SAVE_PATH = os.path.join(os.getenv("APPDATA") or os.path.expanduser("~"), "ShutdownScheduler", "scheduled_shutdowns.json")
os.makedirs(os.path.dirname(SAVE_PATH), exist_ok=True)
# Use the per-user SAVE_PATH (avoids hard-coded user paths)
STORAGE_FILE = SAVE_PATH
CONFIG_FILE = os.path.join(os.path.dirname(SAVE_PATH), "config.json")
SIMULATE_SHUTDOWN = False  # Set to False for real shutdowns (⚠️)
# ----------------------------