"""GUI window for FS-HDR Monitor with menu bar and log output."""

import tkinter as tk
from tkinter import scrolledtext, messagebox
import threading
import sys
import webbrowser
from pathlib import Path

from gui_dialogs import LicenseDialog, PortSettingsDialog

try:
    from version import __version__, __build__
except ImportError:
    __version__ = "dev"
    __build__ = "local"


class LogRedirector:
    """Redirect stdout/stderr to GUI text widget."""

    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.buffer = []
        self.enabled = True

    def write(self, message):
        # Skip if disabled or widget destroyed
        if not self.enabled:
            return

        # Add to buffer
        self.buffer.append(message)

        # Update GUI (must be done in main thread)
        try:
            if self.text_widget.winfo_exists():
                self.text_widget.after(0, self._update_text, message)
        except:
            pass  # Widget might be destroyed

    def _update_text(self, message):
        try:
            if self.enabled and self.text_widget.winfo_exists():
                self.text_widget.insert(tk.END, message)
                self.text_widget.see(tk.END)
        except:
            pass  # Widget destroyed

    def disable(self):
        """Disable logging to prevent crashes during shutdown."""
        self.enabled = False

    def flush(self):
        pass  # Required for file-like object


class FSHDRMonitorGUI:
    """Main GUI window for FS-HDR Monitor."""

    def __init__(self, host, port, config_file, on_quit_callback=None):
        self.host = host
        self.port = port
        self.config_file = config_file
        self.on_quit_callback = on_quit_callback

        # Save original stdout/stderr
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr

        # Create main window
        self.root = tk.Tk()
        self.root.title("FS-HDR Monitor")
        self.root.geometry("800x600")
        self.root.configure(bg="#1e1e1e")

        # Create menu bar
        self._create_menu()

        # Create main content area
        self._create_content()

        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Redirect stdout/stderr to GUI
        self.log_redirector = LogRedirector(self.log_text)
        sys.stdout = self.log_redirector
        sys.stderr = self.log_redirector

    def _create_menu(self):
        """Create menu bar with File and Help menus."""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Open Web Interface", command=self._open_browser)
        file_menu.add_separator()
        file_menu.add_command(label="Settings...", command=self._show_settings_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="License...", command=self._show_license_dialog)
        help_menu.add_separator()
        help_menu.add_command(label="About", command=self._show_about)

    def _create_content(self):
        """Create main content area with logs and controls."""
        # Header frame
        header_frame = tk.Frame(self.root, bg="#1e1e1e", pady=10)
        header_frame.pack(fill=tk.X, padx=10)

        # Title
        title = tk.Label(
            header_frame,
            text="FS-HDR Monitor Server",
            font=("Arial", 16, "bold"),
            bg="#1e1e1e",
            fg="white"
        )
        title.pack(side=tk.LEFT)

        # Open browser button
        open_btn = tk.Button(
            header_frame,
            text="Open Web Interface",
            command=self._open_browser,
            bg="#4CAF50",
            fg="white",
            padx=20,
            pady=8,
            relief=tk.FLAT,
            cursor="hand2"
        )
        open_btn.pack(side=tk.RIGHT)

        # Server info frame
        info_frame = tk.Frame(self.root, bg="#2c2f33", pady=8, padx=10)
        info_frame.pack(fill=tk.X, padx=10)

        server_label = tk.Label(
            info_frame,
            text=f"Server running at: http://{self.host}:{self.port}",
            bg="#2c2f33",
            fg="#4CAF50",
            font=("Courier", 10)
        )
        server_label.pack()

        # Log area label
        log_label = tk.Label(
            self.root,
            text="Server Logs:",
            bg="#1e1e1e",
            fg="white",
            font=("Arial", 10, "bold"),
            anchor="w"
        )
        log_label.pack(fill=tk.X, padx=10, pady=(10, 5))

        # Scrolled text widget for logs
        self.log_text = scrolledtext.ScrolledText(
            self.root,
            wrap=tk.WORD,
            bg="#23272b",
            fg="#f8f8f8",
            insertbackground="white",
            font=("Courier", 9),
            relief=tk.FLAT
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        # Status bar
        status_frame = tk.Frame(self.root, bg="#2c2f33", pady=4)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self.status_label = tk.Label(
            status_frame,
            text="Ready",
            bg="#2c2f33",
            fg="#888",
            font=("Arial", 8),
            anchor="w"
        )
        self.status_label.pack(side=tk.LEFT, padx=10)

    def _open_browser(self):
        """Open the web interface in default browser."""
        url = f"http://{self.host}:{self.port}"
        webbrowser.open(url)
        self.update_status(f"Opened {url} in browser")

    def _show_license_dialog(self):
        """Show license management dialog."""
        # Create a temporary hidden root for the dialog
        temp_root = tk.Toplevel(self.root)
        temp_root.withdraw()

        license_dialog = LicenseDialog(temp_root, self.config_file)
        license_dialog.is_valid = True  # Don't block since we're already running
        license_dialog.show_dialog()

    def _show_settings_dialog(self):
        """Show settings dialog for port configuration."""
        # Create a temporary hidden root for the dialog
        temp_root = tk.Toplevel(self.root)
        temp_root.withdraw()

        port_dialog = PortSettingsDialog(temp_root, self.config_file)

        # Get current port from config
        import json
        with open(self.config_file, 'r') as f:
            config = json.load(f)
        current_port = config["settings"]["port"]

        port_dialog.prompt_for_port(current_port)

        messagebox.showinfo(
            "Restart Required",
            "Port settings have been saved. Please restart FS-HDR Monitor for changes to take effect."
        )

    def _show_about(self):
        """Show about dialog."""
        about_text = f"""FS-HDR Monitor
Version {__version__}
Build {__build__}

Web-based monitoring and control dashboard for AJA FS-HDR, FS4, and FS2 framestore units.

© 2025 Broadcast Software Repo"""
        messagebox.showinfo("About FS-HDR Monitor", about_text)

    def _on_close(self):
        """Handle window close event."""
        if messagebox.askokcancel("Quit", "Stop the server and quit?"):
            # Disable log redirector first
            self.log_redirector.disable()

            # Restore original stdout/stderr
            sys.stdout = self.original_stdout
            sys.stderr = self.original_stderr

            # Call quit callback if provided
            if self.on_quit_callback:
                self.on_quit_callback()

            # Clean up tkinter
            self.root.quit()
            self.root.destroy()

    def update_status(self, message):
        """Update status bar message."""
        self.status_label.config(text=message)

    def run(self):
        """Start the GUI main loop."""
        self.root.mainloop()
