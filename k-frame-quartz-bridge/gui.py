"""GUI window for K-Frame Quartz Bridge with menu bar and log output."""

import tkinter as tk
from tkinter import scrolledtext, messagebox, ttk
import sys
import webbrowser
from pathlib import Path
import configparser
from license import LicenseManager, LicenseStatus, storage


SUITES = [
    "suite1a", "suite1b",
    "suite2a", "suite2b",
    "suite3a", "suite3b",
    "suite4a", "suite4b",
]

PROTOCOLS = ["auto", "tcp", "udp"]


class LogRedirector:
    """Redirect stdout/stderr to GUI text widget."""

    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.enabled = True

    def write(self, message):
        if not self.enabled:
            return
        try:
            if self.text_widget.winfo_exists():
                self.text_widget.after(0, self._update_text, message)
        except Exception:
            pass

    def _update_text(self, message):
        try:
            if self.enabled and self.text_widget.winfo_exists():
                self.text_widget.insert(tk.END, message)
                self.text_widget.see(tk.END)
        except Exception:
            pass

    def disable(self):
        """Disable logging to prevent crashes during shutdown."""
        self.enabled = False

    def flush(self):
        pass


class BridgeGUI:
    """Main GUI window for K-Frame Quartz Bridge."""

    def __init__(self, gv_host, gv_suite, quartz_port, http_port, on_quit_callback=None):
        self.gv_host = gv_host
        self.gv_suite = gv_suite
        self.quartz_port = quartz_port
        self.http_port = http_port
        self.on_quit_callback = on_quit_callback

        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr

        self.root = tk.Tk()
        self.root.title("K-Frame Quartz Bridge")
        self.root.geometry("900x600")
        self.root.configure(bg="#1e1e1e")

        icon_path = Path(__file__).parent / "icon.ico"
        if icon_path.exists():
            try:
                self.root.iconbitmap(str(icon_path))
            except Exception:
                pass

        self.license_manager = LicenseManager(self.root, self._on_license_status_changed)
        self.license_manager.ensure_dialog()

        self._create_menu()
        self._create_content()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.log_redirector = LogRedirector(self.log_text)
        sys.stdout = self.log_redirector
        sys.stderr = self.log_redirector

    def _create_menu(self):
        """Create menu bar."""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Open Status Page", command=self._open_browser)
        file_menu.add_separator()
        file_menu.add_command(label="Settings...", command=self._show_settings_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)

        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="License...", command=self._show_license_dialog)
        help_menu.add_separator()
        help_menu.add_command(label="About", command=self._show_about)

    def _create_content(self):
        """Create main content area with logs and controls."""
        # Header
        header_frame = tk.Frame(self.root, bg="#1e1e1e", pady=10)
        header_frame.pack(fill=tk.X, padx=10)

        title = tk.Label(
            header_frame,
            text="K-Frame Quartz Bridge",
            font=("Arial", 16, "bold"),
            bg="#1e1e1e",
            fg="white",
        )
        title.pack(side=tk.LEFT)

        open_btn = tk.Button(
            header_frame,
            text="Open Status Page",
            command=self._open_browser,
            bg="#4CAF50",
            fg="white",
            padx=20,
            pady=8,
            relief=tk.FLAT,
            cursor="hand2",
        )
        open_btn.pack(side=tk.RIGHT)

        # Server info
        info_frame = tk.Frame(self.root, bg="#2c2f33", pady=8, padx=10)
        info_frame.pack(fill=tk.X, padx=10)

        info_text = (
            f"GV: {self.gv_host} ({self.gv_suite})  |  "
            f"Quartz: port {self.quartz_port}  |  "
            f"Status UI: http://localhost:{self.http_port}"
        )
        server_label = tk.Label(
            info_frame,
            text=info_text,
            bg="#2c2f33",
            fg="#4CAF50",
            font=("Courier", 10),
        )
        server_label.pack()

        # Log label
        log_label = tk.Label(
            self.root,
            text="Bridge Logs:",
            bg="#1e1e1e",
            fg="white",
            font=("Arial", 10, "bold"),
            anchor="w",
        )
        log_label.pack(fill=tk.X, padx=10, pady=(10, 5))

        # Log area
        self.log_text = scrolledtext.ScrolledText(
            self.root,
            wrap=tk.WORD,
            bg="#23272b",
            fg="#f8f8f8",
            insertbackground="white",
            font=("Courier", 9),
            relief=tk.FLAT,
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
            anchor="w",
        )
        self.status_label.pack(side=tk.LEFT, padx=10)

    def _open_browser(self):
        """Open the status page in default browser."""
        url = f"http://localhost:{self.http_port}"
        webbrowser.open(url)
        self.update_status(f"Opened {url} in browser")

    def _show_settings_dialog(self):
        """Show settings dialog."""
        config = configparser.ConfigParser()
        config_path = Path(__file__).parent / "config.ini"
        config.read(config_path)

        dialog = tk.Toplevel(self.root)
        dialog.title("K-Frame Quartz Bridge - Settings")
        dialog.configure(bg="#1e1e1e")
        dialog.resizable(False, False)
        dialog.attributes("-topmost", True)
        dialog.after(100, lambda: dialog.attributes("-topmost", False))

        container = tk.Frame(dialog, bg="#1e1e1e", padx=20, pady=20)
        container.pack(fill=tk.BOTH, expand=True)

        title = tk.Label(
            container,
            text="Bridge Settings",
            bg="#1e1e1e",
            fg="white",
            font=("Arial", 12, "bold"),
        )
        title.pack(anchor="w", pady=(0, 15))

        # --- Setting rows ---
        fields = {}

        def add_field(parent, label_text, current_value, widget_type="entry", options=None):
            frame = tk.Frame(parent, bg="#1e1e1e")
            frame.pack(fill=tk.X, pady=4)

            label = tk.Label(
                frame, text=label_text, bg="#1e1e1e", fg="white",
                width=20, anchor="w",
            )
            label.pack(side=tk.LEFT)

            var = tk.StringVar(value=str(current_value))

            if widget_type == "combo" and options:
                widget = ttk.Combobox(
                    frame, textvariable=var, values=options,
                    state="readonly", width=18,
                )
            else:
                widget = tk.Entry(
                    frame, textvariable=var, width=20,
                    bg="#3c3c3c", fg="white", insertbackground="white",
                )

            widget.pack(side=tk.LEFT, padx=10)
            fields[label_text] = var
            return var

        add_field(container, "GV Host:",
                  config.get("gv", "host", fallback="127.0.0.1"))
        add_field(container, "GV Suite:",
                  config.get("gv", "suite", fallback="suite1a"),
                  widget_type="combo", options=SUITES)
        add_field(container, "GV Protocol:",
                  config.get("gv", "protocol", fallback="auto"),
                  widget_type="combo", options=PROTOCOLS)
        add_field(container, "Quartz Listen Port:",
                  config.get("quartz", "listen_port", fallback="4000"))
        add_field(container, "HTTP Listen Port:",
                  config.get("http", "listen_port", fallback="4001"))
        add_field(container, "Router Sources:",
                  config.get("router", "sources", fallback="809"))
        add_field(container, "Router Destinations:",
                  config.get("router", "destinations", fallback="96"))

        # Status message
        status_var = tk.StringVar(value="")
        status_label = tk.Label(
            container, textvariable=status_var, bg="#1e1e1e", fg="#888",
            wraplength=400, justify="left",
        )
        status_label.pack(fill=tk.X, pady=(10, 10))

        # Buttons
        button_frame = tk.Frame(container, bg="#1e1e1e")
        button_frame.pack(fill=tk.X, pady=(10, 0))

        def save_settings():
            try:
                port_q = int(fields["Quartz Listen Port:"].get())
                port_h = int(fields["HTTP Listen Port:"].get())
                sources = int(fields["Router Sources:"].get())
                dests = int(fields["Router Destinations:"].get())
                for port in (port_q, port_h):
                    if port < 1 or port > 65535:
                        messagebox.showerror("Invalid Port", "Ports must be between 1 and 65535")
                        return
                if sources < 1 or dests < 1:
                    messagebox.showerror("Invalid Value", "Sources and destinations must be at least 1")
                    return
            except ValueError:
                messagebox.showerror("Invalid Value", "Please enter valid numbers for ports, sources, and destinations")
                return

            for section in ("gv", "quartz", "http", "router"):
                if not config.has_section(section):
                    config.add_section(section)

            config.set("gv", "host", fields["GV Host:"].get())
            config.set("gv", "suite", fields["GV Suite:"].get())
            config.set("gv", "protocol", fields["GV Protocol:"].get())
            config.set("quartz", "listen_port", fields["Quartz Listen Port:"].get())
            config.set("http", "listen_port", fields["HTTP Listen Port:"].get())
            config.set("router", "sources", fields["Router Sources:"].get())
            config.set("router", "destinations", fields["Router Destinations:"].get())

            with open(config_path, "w") as f:
                config.write(f)

            messagebox.showinfo(
                "Settings Saved",
                "Settings have been saved.\n\nPlease restart the application for changes to take effect.",
            )
            dialog.destroy()

        save_btn = tk.Button(
            button_frame, text="Save", command=save_settings,
            bg="#4CAF50", fg="white", padx=12, pady=6, width=10,
        )
        save_btn.pack(side=tk.LEFT)

        cancel_btn = tk.Button(
            button_frame, text="Cancel", command=dialog.destroy,
            bg="#3c3c3c", fg="white", padx=12, pady=6, width=10,
        )
        cancel_btn.pack(side=tk.RIGHT)

        dialog.bind("<Return>", lambda e: save_settings())
        dialog.bind("<Escape>", lambda e: dialog.destroy())

        dialog.transient(self.root)
        dialog.grab_set()

    def _show_license_dialog(self):
        """Show license dialog."""
        if self.license_manager:
            self.license_manager.show_dialog()

    def _on_license_status_changed(self, status: LicenseStatus) -> None:
        """Handle license status changes."""
        if status.ok:
            self.update_status(f"Licensed to: {status.name}")
        else:
            self.update_status(f"License: {status.reason}")

    def _show_about(self):
        """Show about dialog."""
        version = "1.0.0"
        version_file = Path(__file__).parent / "VERSION"
        if version_file.exists():
            version = version_file.read_text().strip()

        about_text = (
            f"K-Frame Quartz Bridge\n"
            f"Version {version}\n\n"
            f"Bridges Grass Valley K-Frame AUX buses to\n"
            f"Evertz/Quartz router control clients."
        )
        messagebox.showinfo("About K-Frame Quartz Bridge", about_text)

    def _on_close(self):
        """Handle window close."""
        if messagebox.askokcancel("Quit", "Stop the bridge and quit?"):
            self.log_redirector.disable()
            sys.stdout = self.original_stdout
            sys.stderr = self.original_stderr

            if self.on_quit_callback:
                self.on_quit_callback()

            self.root.quit()
            self.root.destroy()

    def update_status(self, message):
        """Update status bar message."""
        self.status_label.config(text=message)

    def run(self):
        """Start the GUI main loop."""
        self.root.mainloop()
