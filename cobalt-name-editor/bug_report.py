"""Bug report dialog and proxy-based email delivery.

The app sends bug reports to a server-side proxy endpoint which holds
the SMTP2GO API key and forwards the email.  No secrets are embedded
in the client binary.
"""

from __future__ import annotations

import base64
import json
import platform
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

import tkinter as tk
from tkinter import scrolledtext, messagebox

import http_logger

# ---------------------------------------------------------------------------
# Bug-report proxy endpoint (TBD — replace with your deployed URL)
# ---------------------------------------------------------------------------
_PROXY_ENDPOINT = "https://bugreport.broadcastglue.com:4080/bugreport"
_SEND_TIMEOUT = 15


def _read_version() -> str:
    version_file = Path(__file__).parent / "VERSION"
    try:
        return version_file.read_text().strip()
    except OSError:
        return "unknown"


def send_bug_report(
    description: str,
    user_email: str,
    log_text: str,
    http_log_text: str,
    app_version: str,
) -> Tuple[bool, str]:
    """Send a bug report to the proxy endpoint. Returns (success, message).

    The proxy is responsible for holding the SMTP2GO API key, building
    the email, and forwarding it.  This client just sends a simple JSON
    payload with the report data and base64-encoded log attachments.
    """

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    payload = {
        "app": "cobalt-name-editor",
        "version": app_version,
        "timestamp": now,
        "platform": platform.platform(),
        "python": sys.version,
        "reporter_email": user_email or "",
        "description": description,
        "attachments": [],
    }

    if log_text:
        payload["attachments"].append({
            "filename": "console_log.txt",
            "content_base64": base64.b64encode(
                log_text.encode("utf-8")
            ).decode("ascii"),
        })
    if http_log_text:
        payload["attachments"].append({
            "filename": "http_log.txt",
            "content_base64": base64.b64encode(
                http_log_text.encode("utf-8")
            ).decode("ascii"),
        })

    try:
        resp = http_logger.unlogged_post(
            _PROXY_ENDPOINT,
            json=payload,
            headers={"User-Agent": f"CobaltNameEditor/{app_version}"},
            timeout=_SEND_TIMEOUT,
        )
    except Exception as exc:
        type_name = type(exc).__name__
        if "ConnectionError" in type_name or "connection" in str(exc).lower():
            return False, "Could not reach bug report server. Check your internet connection."
        if "Timeout" in type_name:
            return False, "Request timed out. Please try again."
        return False, f"Network error: {exc}"

    if resp.status_code == 200:
        try:
            data = resp.json()
            msg = data.get("message", "Report sent successfully!")
            return True, msg
        except (ValueError, json.JSONDecodeError):
            return True, "Report sent successfully!"

    # Error responses
    try:
        data = resp.json()
        error_msg = data.get("error", f"Server returned HTTP {resp.status_code}")
    except (ValueError, json.JSONDecodeError):
        error_msg = f"Server returned HTTP {resp.status_code}"
    return False, error_msg


# ---------------------------------------------------------------------------
# Tkinter dialog
# ---------------------------------------------------------------------------

class BugReportDialog:
    """Dark-themed bug report dialog for the Tkinter GUI."""

    def __init__(
        self,
        parent: tk.Tk,
        log_redirector,
        http_log: Optional[http_logger.HttpLogger],
    ) -> None:
        self._parent = parent
        self._log_redirector = log_redirector
        self._http_logger = http_log
        self._dialog: Optional[tk.Toplevel] = None

    def show(self) -> None:
        if self._dialog and self._dialog.winfo_exists():
            self._dialog.deiconify()
            self._dialog.lift()
            self._dialog.focus_force()
            return
        self._build_dialog()

    def _build_dialog(self) -> None:
        dlg = tk.Toplevel(self._parent)
        dlg.title("Cobalt Name Editor - Report a Bug")
        dlg.configure(bg="#1e1e1e")
        dlg.resizable(False, False)
        dlg.attributes("-topmost", True)
        dlg.after(100, lambda: dlg.attributes("-topmost", False))

        self._dialog = dlg

        container = tk.Frame(dlg, bg="#1e1e1e", padx=20, pady=20)
        container.pack(fill=tk.BOTH, expand=True)

        # Title
        tk.Label(
            container,
            text="Report a Bug",
            bg="#1e1e1e",
            fg="white",
            font=("Arial", 12, "bold"),
        ).pack(anchor="w", pady=(0, 12))

        # Description
        tk.Label(
            container,
            text="Describe the issue:",
            bg="#1e1e1e",
            fg="white",
        ).pack(anchor="w", pady=(0, 4))

        self._desc_text = scrolledtext.ScrolledText(
            container,
            wrap=tk.WORD,
            height=8,
            bg="#23272b",
            fg="#f8f8f8",
            insertbackground="white",
            font=("Courier", 9),
            relief=tk.FLAT,
        )
        self._desc_text.pack(fill=tk.X, pady=(0, 10))

        # Email
        tk.Label(
            container,
            text="Your email (optional, for follow-up):",
            bg="#1e1e1e",
            fg="white",
        ).pack(anchor="w", pady=(0, 4))

        self._email_var = tk.StringVar()
        email_entry = tk.Entry(
            container,
            textvariable=self._email_var,
            bg="#3c3c3c",
            fg="white",
            insertbackground="white",
        )
        email_entry.pack(fill=tk.X, pady=(0, 12))

        # Attachment info
        tk.Label(
            container,
            text="Attachments:",
            bg="#1e1e1e",
            fg="white",
            font=("Arial", 9, "bold"),
        ).pack(anchor="w")

        console_lines = len(self._log_redirector.buffer) if self._log_redirector else 0
        http_entries = self._http_logger.entry_count() if self._http_logger else 0

        tk.Label(
            container,
            text=f"  Console log ({console_lines} lines)",
            bg="#1e1e1e",
            fg="#888",
        ).pack(anchor="w")

        tk.Label(
            container,
            text=f"  HTTP request log ({http_entries} entries)",
            bg="#1e1e1e",
            fg="#888",
        ).pack(anchor="w")

        # Status
        self._status_var = tk.StringVar(value="")
        self._status_label = tk.Label(
            container,
            textvariable=self._status_var,
            bg="#1e1e1e",
            fg="#888",
            wraplength=400,
            justify="left",
        )
        self._status_label.pack(fill=tk.X, pady=(10, 10))

        # Buttons
        btn_frame = tk.Frame(container, bg="#1e1e1e")
        btn_frame.pack(fill=tk.X, pady=(4, 0))

        self._send_btn = tk.Button(
            btn_frame,
            text="Send Report",
            command=self._on_send,
            bg="#4CAF50",
            fg="white",
            padx=12,
            pady=6,
            width=12,
        )
        self._send_btn.pack(side=tk.LEFT)

        tk.Button(
            btn_frame,
            text="Cancel",
            command=self._on_close,
            bg="#3c3c3c",
            fg="white",
            padx=12,
            pady=6,
            width=10,
        ).pack(side=tk.RIGHT)

        # Key bindings
        dlg.bind("<Escape>", lambda _: self._on_close())

        dlg.transient(self._parent)
        dlg.grab_set()
        self._desc_text.focus_set()

    # ------------------------------------------------------------------
    # Send logic
    # ------------------------------------------------------------------

    def _on_send(self) -> None:
        description = self._desc_text.get("1.0", tk.END).strip()
        if not description:
            messagebox.showerror(
                "Bug Report",
                "Please describe the issue before sending.",
                parent=self._dialog,
            )
            return

        user_email = self._email_var.get().strip()

        # Collect logs at send time
        log_text = "".join(self._log_redirector.buffer) if self._log_redirector else ""
        http_log_text = self._http_logger.get_text() if self._http_logger else ""
        app_version = _read_version()

        # Disable button and update status
        self._send_btn.config(state=tk.DISABLED)
        self._status_var.set("Sending report...")
        self._status_label.config(fg="#888")

        thread = threading.Thread(
            target=self._send_in_background,
            args=(description, user_email, log_text, http_log_text, app_version),
            daemon=True,
        )
        thread.start()

    def _send_in_background(
        self,
        description: str,
        user_email: str,
        log_text: str,
        http_log_text: str,
        app_version: str,
    ) -> None:
        success, message = send_bug_report(
            description, user_email, log_text, http_log_text, app_version,
        )
        try:
            if self._dialog and self._dialog.winfo_exists():
                self._dialog.after(0, self._on_send_complete, success, message)
        except Exception:
            pass

    def _on_send_complete(self, success: bool, message: str) -> None:
        self._send_btn.config(state=tk.NORMAL)
        self._status_var.set(message)
        self._status_label.config(fg="#4CAF50" if success else "#ff5555")
        if success:
            self._dialog.after(1500, self._on_close)

    def _on_close(self) -> None:
        if self._dialog and self._dialog.winfo_exists():
            self._dialog.destroy()
            self._dialog = None
