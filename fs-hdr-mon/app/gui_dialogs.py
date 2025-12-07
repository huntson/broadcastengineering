"""Tkinter GUI dialogs for FS-HDR Monitor settings."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import tkinter as tk
from tkinter import messagebox


class PortSettingsDialog:
    """GUI dialog for port configuration."""

    def __init__(self, root: tk.Tk, config_file: Path):
        self.root = root
        self.config_file = config_file
        self.dialog: Optional[tk.Toplevel] = None
        self.port_var = tk.StringVar()
        self.selected_port: Optional[int] = None

    def prompt_for_port(self, current_port: int) -> Optional[int]:
        """Show port configuration dialog. Return selected port or None."""
        self.port_var.set(str(current_port))
        self.selected_port = current_port  # Default to current

        self.show_dialog()
        self.root.wait_window(self.dialog)

        return self.selected_port

    def show_dialog(self):
        """Show the port settings dialog."""
        self.dialog = tk.Toplevel(self.root)
        self.dialog.title("FS-HDR Monitor - Port Configuration")
        self.dialog.configure(bg="#1e1e1e")
        self.dialog.resizable(False, False)
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_use_current)
        self.dialog.attributes('-topmost', True)
        self.dialog.after(100, lambda: self.dialog.attributes('-topmost', False))

        container = tk.Frame(self.dialog, bg="#1e1e1e", padx=20, pady=20)
        container.pack(fill=tk.BOTH, expand=True)

        # Title
        title = tk.Label(
            container,
            text="Server Port Configuration",
            bg="#1e1e1e",
            fg="white",
            font=("Arial", 12, "bold")
        )
        title.pack(anchor="w", pady=(0, 15))

        # Port setting
        port_frame = tk.Frame(container, bg="#1e1e1e")
        port_frame.pack(fill=tk.X, pady=5)

        port_label = tk.Label(
            port_frame,
            text="Server Port:",
            bg="#1e1e1e",
            fg="white",
            width=12,
            anchor="w"
        )
        port_label.pack(side=tk.LEFT)

        port_entry = tk.Entry(
            port_frame,
            textvariable=self.port_var,
            width=10,
            bg="#3c3c3c",
            fg="white",
            insertbackground="white"
        )
        port_entry.pack(side=tk.LEFT, padx=10)

        # Info text
        info_label = tk.Label(
            container,
            text="Default port is 5070. Press Enter or click Save to use the specified port.",
            bg="#1e1e1e",
            fg="#888",
            wraplength=300,
            justify="left"
        )
        info_label.pack(fill=tk.X, pady=(10, 10))

        # Buttons
        button_frame = tk.Frame(container, bg="#1e1e1e")
        button_frame.pack(fill=tk.X, pady=(10, 0))

        save_btn = tk.Button(
            button_frame,
            text="Save",
            command=self._on_save,
            bg="#4CAF50",
            fg="white",
            padx=12,
            pady=6,
            width=10
        )
        save_btn.pack(side=tk.LEFT)

        cancel_btn = tk.Button(
            button_frame,
            text="Cancel",
            command=self._on_use_current,
            bg="#3c3c3c",
            fg="white",
            padx=12,
            pady=6,
            width=10
        )
        cancel_btn.pack(side=tk.RIGHT)

        self.dialog.bind("<Return>", lambda _event: self._on_save())
        self.dialog.bind("<Escape>", lambda _event: self._on_use_current())

        # Focus on entry
        self.dialog.deiconify()
        self.dialog.lift()
        self.dialog.focus_force()
        self.dialog.after(10, port_entry.focus_set)
        port_entry.selection_range(0, tk.END)

    def _on_save(self):
        """Save the port setting."""
        try:
            new_port = int(self.port_var.get())
            if new_port < 1 or new_port > 65535:
                messagebox.showerror("Invalid Port", "Port must be between 1 and 65535")
                return

            self.selected_port = new_port

            # Update config file
            with open(self.config_file, 'r') as f:
                config = json.load(f)

            config["settings"]["port"] = new_port

            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)

            print(f"[config] Port changed to {new_port} and saved to config.json")

            if self.dialog and self.dialog.winfo_exists():
                self.dialog.destroy()

        except ValueError:
            messagebox.showerror("Invalid Port", "Please enter a valid port number")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save port: {e}")

    def _on_use_current(self):
        """Close dialog and use current port."""
        if self.dialog and self.dialog.winfo_exists():
            self.dialog.destroy()
