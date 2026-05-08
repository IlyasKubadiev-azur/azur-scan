"""Azur-Scan Agent — setup wizard (tokenless).

GUI installer that bundles agent.exe + WinSW + service.xml as a single
self-extracting executable. End user enters only the backend URL; the agent
auto-enrolls against that URL on first run.

Built into `azur-scan-agent-setup.exe` via `installer.spec` (windowed app
with UAC elevation manifest).
"""
from __future__ import annotations

import ctypes
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

# ── paths ───────────────────────────────────────────────────────────────────
INSTALL_DIR = Path("C:/Program Files/AzurScan")
DATA_DIR    = Path("C:/ProgramData/AzurScan")
LOGS_DIR    = DATA_DIR / "logs"
AGENT_EXE   = INSTALL_DIR / "azurscan-agent.exe"
WINSW_EXE   = INSTALL_DIR / "azurscan-service.exe"

BUNDLED = ["azurscan-agent.exe", "azurscan-service.exe", "azurscan-service.xml"]

# Pre-filled default — change for your office before shipping
DEFAULT_SERVER = "http://10.0.20.143:8000"


# ── elevation ───────────────────────────────────────────────────────────────
def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _elevate():
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, None, None, 1)
    sys.exit(0)


# ── embedded files ──────────────────────────────────────────────────────────
def _embedded(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


# ── installation worker (background thread) ────────────────────────────────
def _worker(server: str, log, finish):
    """Install + enroll. `log(msg)` and `finish(ok, msg)` are thread-safe
    callbacks scheduled onto the Tk main loop."""
    try:
        log("Creating directories...")
        for d in (INSTALL_DIR, DATA_DIR, LOGS_DIR):
            d.mkdir(parents=True, exist_ok=True)

        log("Stopping existing service (if any)...")
        subprocess.run(["sc", "stop", "AzurScanAgent"], capture_output=True)
        time.sleep(1)
        if WINSW_EXE.exists():
            subprocess.run([str(WINSW_EXE), "uninstall"], capture_output=True)
            time.sleep(1)

        log("Copying files...")
        for fname in BUNDLED:
            shutil.copy2(_embedded(fname), INSTALL_DIR / fname)
            log(f"  + {fname}")

        log("Registering Windows service...")
        r = subprocess.run([str(WINSW_EXE), "install"], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"Service install failed: {(r.stderr or r.stdout).strip()}")

        # Restart on failure: 30s -> 60s -> 5min, reset counter daily
        subprocess.run([
            "sc", "failure", "AzurScanAgent",
            "reset=", "86400", "actions=", "restart/30000/restart/60000/restart/300000",
        ], capture_output=True)

        log(f"Enrolling with {server} ...")
        r = subprocess.run(
            [str(AGENT_EXE), "enroll", "--server", server],
            capture_output=True, text=True,
        )
        out = (r.stdout + r.stderr).strip()
        if r.returncode != 0:
            raise RuntimeError(f"Enrollment failed:\n{out}")
        log(out)

        log("Starting service...")
        subprocess.run(["sc", "start", "AzurScanAgent"], capture_output=True)
        time.sleep(3)

        r = subprocess.run(["sc", "query", "AzurScanAgent"], capture_output=True, text=True)
        log("Service: " + ("Running" if "RUNNING" in r.stdout else "check manually"))

        finish(True, "Installation complete.\n\nThe device will appear in the admin panel "
                     "within ~60 seconds.")
    except Exception as exc:
        finish(False, str(exc))


# ── main window ─────────────────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Azur-Scan Agent Setup")
        self.resizable(False, False)
        w, h = 480, 380
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
        self._build()

    def _build(self):
        tk.Label(self, text="Azur-Scan Agent Setup",
                 font=("Segoe UI", 14, "bold")).pack(pady=(18, 2))
        tk.Label(self, text="Installs the service and enrolls this device automatically.",
                 font=("Segoe UI", 9)).pack()

        # Server URL — only required input
        tk.Label(self, text="Backend Server URL:", font=("Segoe UI", 9),
                 anchor="w").pack(fill="x", padx=20, pady=(18, 0))
        self._server_var = tk.StringVar(value=DEFAULT_SERVER)
        tk.Entry(self, textvariable=self._server_var,
                 font=("Segoe UI", 10)).pack(fill="x", padx=20, ipady=5)
        tk.Label(self, text="Example:  http://10.0.20.143:8000",
                 font=("Segoe UI", 8), fg="gray").pack(anchor="w", padx=20, pady=(2, 0))

        # Install button
        self._btn = tk.Button(
            self, text="Install & Enroll",
            font=("Segoe UI", 10, "bold"),
            command=self._run,
        )
        self._btn.pack(fill="x", padx=20, pady=18, ipady=8)

        # Status label
        self._status_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self._status_var,
                 font=("Segoe UI", 9), fg="navy").pack(padx=20)

        # Log area
        frame = tk.Frame(self)
        frame.pack(fill="both", expand=True, padx=20, pady=(4, 18))
        self._log = tk.Text(frame, font=("Consolas", 9),
                            state="disabled", wrap="word", relief="sunken", bd=1, height=8)
        sb = tk.Scrollbar(frame, command=self._log.yview)
        self._log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._log.pack(side="left", fill="both", expand=True)

    def _log_line(self, msg: str):
        self._log.configure(state="normal")
        self._log.insert("end", msg.rstrip() + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _run(self):
        server = self._server_var.get().strip().rstrip("/")
        if not server:
            messagebox.showwarning("Missing", "Enter the backend URL.", parent=self)
            return
        if not (server.startswith("http://") or server.startswith("https://")):
            messagebox.showwarning(
                "Invalid URL",
                "URL must start with http:// or https://",
                parent=self,
            )
            return
        self._btn.config(state="disabled")
        self._status_var.set("Installing, please wait...")
        self._log_line(f"Starting... server={server}")
        threading.Thread(
            target=_worker,
            args=(server,
                  lambda m: self.after(0, self._log_line, m),
                  lambda ok, msg: self.after(0, self._done, ok, msg)),
            daemon=True,
        ).start()

    def _done(self, ok: bool, msg: str):
        self._status_var.set("")
        self._btn.config(state="normal")
        self._log_line(("\n[OK] " if ok else "\n[FAIL] ") + msg)
        if ok:
            messagebox.showinfo("Done", msg, parent=self)
        else:
            messagebox.showerror("Failed", msg, parent=self)


# ── entry point ─────────────────────────────────────────────────────────────
def main():
    if not _is_admin():
        _elevate()
    App().mainloop()


if __name__ == "__main__":
    main()
