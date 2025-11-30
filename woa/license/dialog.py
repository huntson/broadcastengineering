"""Tk dialogs for license entry and management."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import tkinter as tk
from tkinter import messagebox

from . import storage, verification


@dataclass
class LicenseStatus:
    ok: bool
    reason: str
    name: str = ""
    key: str = ""


StatusCallback = Callable[[LicenseStatus], None]


class LicenseManager:
    """Manage license verification, persistence, and dialog presentation."""

    def __init__(
        self,
        root: tk.Tk,
        on_status_change: Optional[StatusCallback] = None,
        *,
        storage_path: Optional[Path] = None,
    ) -> None:
        self.root = root
        self._on_status_change = on_status_change
        self._storage_path = storage_path
        self._dialog: Optional[tk.Toplevel] = None
        self._status_widget: Optional[tk.Label] = None
        self._name_var = tk.StringVar()
        self._key_var = tk.StringVar()
        self._status_var = tk.StringVar(value="License required")
        self._status_color = "#ff5555"
        self.status = LicenseStatus(ok=False, reason="License required")
        self._load_cached_license()

    def _load_cached_license(self) -> None:
        cached = storage.load_cached_license(self._storage_path)
        if not cached:
            self._emit_status()
            return
        name = cached.get("name", "")
        key = cached.get("key", "")
        if name:
            self._name_var.set(name)
        if key:
            self._key_var.set(key)
        ok, reason = verification.verify_name_key(name, key)
        self.status = LicenseStatus(ok=ok, reason=reason, name=name, key=key)
        if ok:
            self._status_var.set("License validated")
            self._status_color = "#4CAF50"
        else:
            self._status_var.set(reason)
            self._status_color = "#ff5555"
        self._emit_status()

    def ensure_dialog(self) -> None:
        if not self.status.ok:
            self.show_dialog()
        else:
            self._emit_status()

    def show_dialog(self) -> None:
        if self._dialog and self._dialog.winfo_exists():
            self._dialog.deiconify()
            self._dialog.lift()
            self._dialog.focus_set()
            return
        self._dialog = tk.Toplevel(self.root)
        self._dialog.title("Application License")
        self._dialog.configure(bg="#1e1e1e")
        self._dialog.resizable(False, False)
        self._dialog.protocol("WM_DELETE_WINDOW", self._on_close)
        self._dialog.transient(self.root)

        container = tk.Frame(self._dialog, bg="#1e1e1e", padx=16, pady=16)
        container.pack(fill=tk.BOTH, expand=True)

        title = tk.Label(
            container,
            text="Enter your license information",
            bg="#1e1e1e",
            fg="white",
            font=("Arial", 12, "bold"),
        )
        title.pack(anchor="w")

        name_label = tk.Label(container, text="Licensed To", bg="#1e1e1e", fg="white")
        name_label.pack(anchor="w", pady=(12, 4))
        name_entry = tk.Entry(
            container,
            textvariable=self._name_var,
            width=36,
            bg="#3c3c3c",
            fg="white",
            insertbackground="white",
        )
        name_entry.pack(fill=tk.X)

        key_label = tk.Label(container, text="License Key", bg="#1e1e1e", fg="white")
        key_label.pack(anchor="w", pady=(12, 4))
        key_entry = tk.Entry(
            container,
            textvariable=self._key_var,
            width=36,
            bg="#3c3c3c",
            fg="white",
            insertbackground="white",
        )
        key_entry.pack(fill=tk.X)

        status_label = tk.Label(
            container,
            textvariable=self._status_var,
            bg="#1e1e1e",
            fg=self._status_color,
            wraplength=320,
            justify="left",
        )
        status_label.pack(fill=tk.X, pady=(12, 12))
        self._status_widget = status_label

        button_row = tk.Frame(container, bg="#1e1e1e")
        button_row.pack(fill=tk.X)

        verify_btn = tk.Button(
            button_row,
            text="VERIFY",
            command=self._on_verify,
            bg="#4CAF50",
            fg="white",
            padx=12,
            pady=6,
            width=10,
        )
        verify_btn.pack(side=tk.LEFT)

        clear_btn = tk.Button(
            button_row,
            text="CLEAR",
            command=self._on_clear,
            bg="#555555",
            fg="white",
            padx=12,
            pady=6,
            width=10,
        )
        clear_btn.pack(side=tk.LEFT, padx=8)

        close_btn = tk.Button(
            button_row,
            text="CLOSE",
            command=self._on_close,
            bg="#3c3c3c",
            fg="white",
            padx=12,
            pady=6,
            width=10,
        )
        close_btn.pack(side=tk.RIGHT)

        self._dialog.bind("<Return>", lambda _event: self._on_verify())
        self._dialog.bind("<Escape>", lambda _event: self._on_close())
        self._dialog.after(10, name_entry.focus_set)

        self._status_var.set(self.status.reason if not self.status.ok else "License validated")
        self._update_status_color("#4CAF50" if self.status.ok else self._status_color)

    def _emit_status(self) -> None:
        if self._on_status_change:
            self._on_status_change(self.status)

    def _update_status_color(self, color: str) -> None:
        self._status_color = color
        if self._status_widget and self._status_widget.winfo_exists():
            self._status_widget.config(fg=color)

    def _set_status(self, ok: bool, reason: str, name: Optional[str] = None, key: Optional[str] = None) -> None:
        if name is not None:
            self._name_var.set(name)
        if key is not None:
            self._key_var.set(key)
        self.status = LicenseStatus(ok=ok, reason=reason, name=self._name_var.get(), key=self._key_var.get())
        self._status_var.set(reason)
        self._update_status_color("#4CAF50" if ok else "#ff5555")
        self._emit_status()

    def _on_verify(self) -> None:
        name = self._name_var.get().strip()
        key = self._key_var.get().strip()
        if not name or not key:
            messagebox.showerror("License", "Enter both a name and license key")
            return
        ok, reason = verification.verify_name_key(name, key)
        self._set_status(ok, reason, name, key)
        if ok:
            storage.save_license(name, key, self._storage_path)
            self._status_var.set("License validated")
            self._update_status_color("#4CAF50")
            if self._dialog and self._dialog.winfo_exists():
                self._dialog.after(400, self._dialog.destroy)

    def _on_clear(self) -> None:
        storage.clear_license(self._storage_path)
        self._set_status(False, "License cleared")

    def _on_close(self) -> None:
        if self._dialog and self._dialog.winfo_exists():
            self._dialog.withdraw()

