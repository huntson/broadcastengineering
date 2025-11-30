"""Tkinter GUI for the K-Frame Visual On-Air monitor."""

import importlib.resources as resources
import threading
import copy
from collections import OrderedDict
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

from client import SimpleKFrameClient
from window_helpers import FloatingWindowMixin
from license import LicenseManager, LicenseStatus, storage
from dialogs.aux_window import AuxWindow
from __version__ import __version__

class VisualOnAirGUI(FloatingWindowMixin):
    """Visual GUI for displaying on-air status with safe view switching"""
    BOX_CONFIGS = [
        ('pgm', 'PROGRAM', '#cc0000'),
        ('me1', 'ME 1', '#0066cc'),
        ('me2', 'ME 2', '#0066cc'),
        ('me3', 'ME 3', '#0066cc'),
        ('me4', 'ME 4', '#0066cc'),
    ]
    def __init__(self, root):
        self.root = root
        self.client = None
        self.view_mode = "1"  # "1", "2", or "4" suites
        self.aux_window_controller = AuxWindow(self)
        self.outputs_window = None
        self.outputs_canvas = None
        self.outputs_window_content = None
        self._settings_window = None
        self._output_entries = None
        self._output_entries_data = None
        self._outputs_last_width = 0
        self._outputs_resize_pending = False
        self._outputs_canvas_window_id = None
        self._logical_canvas_window_id = None
        self._app_icon_image = None
        self._engineering_canvas_window_id = None
        self.license_manager = None
        self.license_status = LicenseStatus(ok=False, reason="License required")
        self.max_outputs_to_display = 48
        self.suite_header_label_1view = None
        self.tile_height = 220
        self.tile_title_height = 40
        self.header_height = 28
        self.section_spacing = 8
        self.window_base_height = 120  # top controls + padding
        self.window_width = 960
        self._cached_state = None
        self.setup_gui()
        self.app_settings = storage.load_settings()
        last_ip = self.app_settings.get('last_ip') if self.app_settings else None
        if last_ip:
            self.ip_var.set(last_ip)
        self.root.protocol('WM_DELETE_WINDOW', self._on_root_close)
        self.license_manager = LicenseManager(self.root, self._on_license_status_changed)
        self.license_manager.ensure_dialog()
    def setup_gui(self):
        """Setup the GUI interface"""
        self.root.title("K-Frame Visual On-Air Monitor")
        self.root.geometry(f"{self.window_width}x{self._compute_window_height(1)}")
        self.root.configure(bg='#2b2b2b')
        self._apply_app_icon()
        # Fonts
        self.title_font = ('Arial', 14, 'bold')
        self.header_font = ('Arial', 14, 'bold underline')
        self.source_font = ('Arial', 12, 'bold')
        self.label_font = ('Arial', 8)
        # Top control frame
        control_frame = tk.Frame(self.root, bg='#1e1e1e', height=68)
        control_frame.pack(fill=tk.X, padx=2, pady=2)
        control_frame.pack_propagate(False)
        # BETA label in top right
        beta_label = tk.Label(control_frame, text="BETA", bg='#1e1e1e', fg='#ff6600',
                             font=('Arial', 12, 'bold'))
        beta_label.pack(side=tk.RIGHT, padx=10, pady=15)
        # IP entry
        tk.Label(control_frame, text="K-Frame IP:", bg='#1e1e1e', fg='white',
                font=self.label_font).pack(side=tk.LEFT, padx=(10, 4), pady=15)
        self.ip_var = tk.StringVar(value="localhost")
        self.ip_entry = tk.Entry(control_frame, textvariable=self.ip_var, width=15,
                                bg='#3c3c3c', fg='white', insertbackground='white')
        self.ip_entry.pack(side=tk.LEFT, padx=(4, 10), pady=10)
        connect_container = tk.Frame(control_frame, bg='#1e1e1e')
        connect_container.pack(side=tk.LEFT, padx=8, pady=(4, 8))
        # Connect button
        self.connect_btn = tk.Button(connect_container, text="CONNECT", command=self.toggle_connection,
                                    bg='#4CAF50', fg='white', font=self.label_font,
                                    padx=12, pady=4, width=10)
        self.connect_btn.pack(fill=tk.X)
        # Status indicator
        self.status_label = tk.Label(connect_container, text="DISCONNECTED", bg='#1e1e1e',
                                     fg='#ff5555', font=self.label_font, anchor='center')
        self.status_label.pack(fill=tk.X, pady=(6, 0))
        # View selection handled via the menu; keep state only.
        self.view_var = tk.StringVar(value="1 Suite")
        self.view_selector = None
        # Suite selector (only shown in single suite mode)
        self.suite_label = tk.Label(control_frame, text="Suite:", bg='#1e1e1e', fg='white',
                                   font=self.label_font)
        self.suite_label.pack(side=tk.LEFT, padx=(20, 5), pady=15)
        self.suite_var = tk.StringVar(value="Suite1")
        self.suite_selector = ttk.Combobox(control_frame, textvariable=self.suite_var,
                                          values=["Suite1", "Suite2", "Suite3", "Suite4"],
                                          width=10, state='readonly')
        self.suite_selector.bind('<<ComboboxSelected>>', self.on_suite_change)
        # Window toggles are managed through the menu only.
        self.show_aux_var = tk.BooleanVar(value=False)
        self.show_all_outputs_var = tk.BooleanVar(value=False)
        self.show_logical_var = tk.BooleanVar(value=False)
        self.show_engineering_var = tk.BooleanVar(value=False)
        self._view_menu_var = None
        self._window_menu = None
        self._view_menu = None
        self.logical_window = None
        self.logical_canvas = None
        self.logical_window_content = None
        self._logical_canvas_window_id = None
        self.engineering_window = None
        self.engineering_canvas = None
        self.engineering_window_content = None
        self._engineering_canvas_window_id = None
        self._logical_entries = None
        self._logical_entries_data = None
        self._logical_render_state = None
        self._logical_update_after_id = None
        self._logical_suite_var = tk.StringVar(value='Suite1')
        self._logical_suite_selector = None
        self._engineering_entries = None
        self._engineering_entries_data = None
        self._engineering_render_state = None
        self._engineering_update_after_id = None
        self._logical_render_job = None
        self._engineering_render_job = None
        self._logical_loading = True
        self._engineering_loading = True
        self._responsive_rows = []
        self._window_menu_items = {}
        self.suite_headers_2view = []
        self.suite_headers_4view = []
        self.aux_checkbox = None
        self.output_checkbox = None
        self.logical_checkbox = None
        self.engineering_checkbox = None
        self.settings_button = tk.Button(control_frame, text="Settings",
                                         command=self.open_settings_dialog,
                                         bg='#3c3c3c', fg='white',
                                         font=self.label_font,
                                         padx=12, pady=5)
        self.settings_button.pack(side=tk.LEFT, padx=(10, 5), pady=15)
        self._show_suite_controls()
        self._build_menu_bar()
        # Main display frame
        self.display_frame = tk.Frame(self.root, bg='#2b2b2b')
        self.display_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        # Create all layout frames (but only show one at a time)
        self.create_all_layouts()
        self.switch_to_view("1")  # Start with single suite view
        self._display_not_connected_state()
    def open_license_window(self):
        """Open the license dialog."""
        if self.license_manager:
            self.license_manager.show_dialog()

    def open_about_window(self):
        """Show the About dialog with version information."""
        messagebox.showinfo(
            "About WOA Monitor",
            f"WOA (Visual On-Air) Monitor\n\n"
            f"Version: {__version__}\n\n"
            f"Monitor Grass Valley K-Frame systems\n"
            f"Visual on-air status display\n\n"
            f"© 2025"
        )

    def _license_allows_connection(self) -> bool:
        if self.license_status and self.license_status.ok:
            return True
        reason = self.license_status.reason if self.license_status else "License required"
        if not reason.strip():
            reason = "License required to connect."
        messagebox.showinfo("License Required", reason)
        if self.license_manager:
            self.license_manager.show_dialog()
        return False

    def _on_license_status_changed(self, status: LicenseStatus) -> None:
        self.license_status = status
        if not status.ok:
            if self.client and self.client.connected:
                self.disconnect()
            if getattr(self, 'status_label', None):
                message = status.reason or "License required"
                self.status_label.config(text=message, fg='#ff5555')
            if getattr(self, 'connect_btn', None) and self.connect_btn.cget('state') == 'normal':
                self.connect_btn.config(bg='#777777')
        else:
            if getattr(self, 'connect_btn', None) and self.connect_btn.cget('state') == 'normal' and self.connect_btn.cget('text') == 'CONNECT':
                self.connect_btn.config(bg='#4CAF50')
            if (not self.client or not self.client.connected) and getattr(self, 'status_label', None):
                self.status_label.config(text="DISCONNECTED", fg='#ff5555')

    def _display_not_connected_state(self) -> None:
        """Show a centered NOT CONNECTED placeholder in every primary box."""
        if not hasattr(self, 'boxes'):
            return
        if self.suite_header_label_1view:
            self._update_single_suite_header()
        self._update_multi_suite_headers()
        message = "NOT CONNECTED"
        for view_boxes in self.boxes.values():
            for box_data in view_boxes.values():
                content_frame = box_data.get('content_frame')
                if not content_frame or not content_frame.winfo_exists():
                    continue
                for widget in content_frame.winfo_children():
                    widget.destroy()
                self._render_centered_message(
                    content_frame,
                    message,
                    bg=box_data.get('bg_color', '#2b2b2b'),
                    font=self.source_font,
                )
                box_data['current_content'] = message
        self._show_secondary_not_connected()

    def _show_secondary_not_connected(self) -> None:
        connected = self.client.connected if self.client else False
        if self.aux_window_controller.window and self.aux_window_controller.window.winfo_exists():
            self.update_aux_window([])
        if self.outputs_window_content and self.outputs_window_content.winfo_exists():
            self.update_outputs_window([])
        if self.logical_window_content and self.logical_window_content.winfo_exists():
            self.update_logical_window(self._logical_entries_data or [], False, connected)
        if self.engineering_window_content and self.engineering_window_content.winfo_exists():
            self.update_engineering_window(self._engineering_entries_data or [], False, connected)

    def _render_centered_message(self, parent, message, *, bg, fg='white', pad_x=0, pad_y=0, font=None, margin=0):
        container = tk.Frame(parent, bg=bg)
        container.pack(fill=tk.BOTH, expand=True, padx=pad_x, pady=pad_y)
        canvas = tk.Canvas(
            container,
            bg=bg,
            highlightthickness=0,
            borderwidth=0,
        )
        canvas.pack(fill=tk.BOTH, expand=True)
        text_id = canvas.create_text(
            0,
            0,
            text=message,
            fill=fg,
            font=font or self.source_font,
            anchor='center',
            justify=tk.CENTER,
        )

        def _recenter(event, cid=text_id, margin=margin):
            width = max(1, event.width)
            height = max(1, event.height)
            canvas.coords(cid, width / 2, height / 2)
            canvas.itemconfig(cid, width=max(1, width - margin))

        canvas.bind('<Configure>', _recenter, add='+')
        return container


    def _adjust_canvas_placeholder_bounds(self, canvas, window_id, window, enabled):
        if not canvas or window_id is None:
            return
        width = height = None
        if window and window.winfo_exists():
            window.update_idletasks()
            width = max(window.winfo_width() - 24, 0)
            height = max(window.winfo_height() - 48, 0)
        try:
            if enabled:
                if width is not None:
                    canvas.itemconfig(window_id, width=width)
                if height is not None:
                    canvas.itemconfig(window_id, height=height)
            else:
                canvas.itemconfig(window_id, width=0)
                canvas.itemconfig(window_id, height=0)
        except tk.TclError:
            pass
        canvas.update_idletasks()

    def _persist_app_settings(self) -> None:
        settings = dict(getattr(self, 'app_settings', {}))
        settings['last_ip'] = self.ip_var.get().strip()
        storage.save_settings(settings)
        self.app_settings = settings

    def _on_root_close(self) -> None:
        try:
            self._persist_app_settings()
        except Exception as exc:
            print(f"Error saving settings: {exc}")
        finally:
            self.root.destroy()

    def _create_suite_section(
        self,
        parent,
        view_mode: str,
        key_prefix: str,
        header_text: str,
        *,
        header_store: list | None = None,
        store_single_label: bool = False,
    ) -> tk.Frame:
        section_height = self.header_height + self.tile_height
        section = tk.Frame(parent, bg='#2b2b2b', height=section_height)
        section.pack(fill=tk.X, expand=False, pady=(0, self.section_spacing), anchor='n')
        section.pack_propagate(False)

        header_label = tk.Label(
            section,
            text=header_text,
            bg='#2b2b2b',
            fg='white',
            font=self.header_font,
        )
        header_label.pack(pady=(0, 0))

        boxes_frame = tk.Frame(section, bg='#2b2b2b', height=self.tile_height)
        boxes_frame.pack(fill=tk.X, expand=False)
        boxes_frame.pack_propagate(False)
        containers = []
        for suffix, title, bg_color in self.BOX_CONFIGS:
            key = f"{key_prefix}{suffix}"
            container = self.create_box(boxes_frame, key, title, bg_color, view_mode)
            containers.append(container)
        self._register_responsive_row(boxes_frame, containers, min_width=180)

        if header_store is not None:
            header_store.append(header_label)
        if store_single_label:
            self.suite_header_label_1view = header_label

        return section

    def create_all_layouts(self):
        """Create all layout frames upfront - safer than destroying/recreating"""
        self.layouts = {}
        self.boxes = {"1": {}, "2": {}, "4": {}}
        # Layout 1: Single Suite (5 boxes)
        self.layouts["1"] = tk.Frame(self.display_frame, bg='#2b2b2b')
        self.create_single_suite_layout(self.layouts["1"], "1")
        # Layout 2: Two Suites (2x2 boxes)
        self.layouts["2"] = tk.Frame(self.display_frame, bg='#2b2b2b')
        self.create_two_suite_layout(self.layouts["2"], "2")
        # Layout 4: Four Suites (4x1 boxes)
        self.layouts["4"] = tk.Frame(self.display_frame, bg='#2b2b2b')
        self.create_four_suite_layout(self.layouts["4"], "4")
    def create_single_suite_layout(self, parent, view_mode):
        """Create layout for single suite view (5 boxes)"""
        header_text = self._format_suite_header_text(self.suite_var.get())
        self._create_suite_section(
            parent,
            view_mode,
            key_prefix="",
            header_text=header_text,
            store_single_label=True,
        )
        self._update_single_suite_header()

    def create_two_suite_layout(self, parent, view_mode):
        """Create layout for 2 suite view using stacked sections"""
        self.suite_headers_2view = []
        for idx in range(2):
            header_text = f"SUITE {idx + 1}"
            self._create_suite_section(
                parent,
                view_mode,
                key_prefix=f"s{idx}_",
                header_text=header_text,
                header_store=self.suite_headers_2view,
            )

    def create_four_suite_layout(self, parent, view_mode):
        """Create layout for 4 suite view using stacked sections"""
        self.suite_headers_4view = []
        for idx in range(4):
            header_text = f"SUITE {idx + 1}"
            self._create_suite_section(
                parent,
                view_mode,
                key_prefix=f"s{idx}_",
                header_text=header_text,
                header_store=self.suite_headers_4view,
            )
    def create_box(self, parent, key, title, bg_color, view_mode, width=180):
        """Create a single display box that flexes with available width."""
        container = tk.Frame(parent, bg='#2b2b2b', height=self.tile_height)
        container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        container.pack_propagate(False)
        # Title bar
        title_frame = tk.Frame(container, bg='#444444', height=self.tile_title_height)
        title_frame.pack(fill=tk.X)
        title_frame.pack_propagate(False)
        title_label = tk.Label(title_frame, text=title,
                              bg='#444444', fg='white', font=self.title_font)
        title_label.pack(pady=0)
        # Main content box
        body_height = max(1, self.tile_height - self.tile_title_height)
        on_air_frame = tk.Frame(container, bg=bg_color, relief=tk.RAISED, bd=2, height=body_height)
        on_air_frame.pack(fill=tk.BOTH, expand=True)
        on_air_frame.pack_propagate(False)
        # Create a container frame for mixed-color content
        content_frame = tk.Frame(on_air_frame, bg=bg_color)
        content_frame.pack(expand=True, fill=tk.BOTH)
        self._render_centered_message(content_frame, "NOT CONNECTED", bg=bg_color)
        self.boxes[view_mode][key] = {
            'content_frame': content_frame,
            'frame': on_air_frame,
            'bg_color': bg_color,
            'container': container
        }
        return container

    def _compute_window_height(self, suite_count: int) -> int:
        section_height = self.tile_height + self.header_height + self.section_spacing
        total_height = self.window_base_height + suite_count * section_height
        return total_height

    def switch_to_view(self, mode):
        """Safely switch between views using pack_forget/pack"""
        # Hide all layouts
        for layout in self.layouts.values():
            layout.pack_forget()
        # Show selected layout
        if mode in self.layouts:
            self.layouts[mode].pack(fill=tk.BOTH, expand=True)
        self.view_mode = mode
        # Adjust window size based on view mode
        if mode == "1":
            height = self._compute_window_height(1)
            self._update_single_suite_header()
        elif mode == "2":
            height = self._compute_window_height(2)
        elif mode == "4":
            height = self._compute_window_height(4)
        else:
            height = self._compute_window_height(1)
        self.root.minsize(self.window_width, height)
        self.root.geometry(f"{self.window_width}x{height}")
    def on_view_change(self, event=None):
        """Handle view mode change and keep control order stable"""
        view_text = self.view_var.get()
        if "1" in view_text:
            mode = "1"
            self.suite_selector.config(values=["Suite1", "Suite2", "Suite3", "Suite4"])
            if self.suite_var.get() not in ["Suite1", "Suite2", "Suite3", "Suite4"]:
                self.suite_var.set("Suite1")
            self._show_suite_controls(include_aux=True)
            self._update_single_suite_header()
        elif "2" in view_text:
            mode = "2"
            self.suite_selector.config(values=["Suite1-2", "Suite3-4"])
            if self.suite_var.get() not in ["Suite1-2", "Suite3-4"]:
                self.suite_var.set("Suite1-2")
            self._show_suite_controls(include_aux=False)
            if self.show_aux_var.get():
                self.show_aux_var.set(False)
                self.close_aux_window()
        else:
            mode = "4"
            self._hide_suite_controls()
            if self.show_aux_var.get():
                self.show_aux_var.set(False)
                self.close_aux_window()
        if self._view_menu_var:
            self._view_menu_var.set(mode)
        self._update_multi_suite_headers()
        self.switch_to_view(mode)
        self.update_display()

    def _show_suite_controls(self, include_aux=True):
        """Pack suite selector controls in consistent order"""
        self.suite_label.pack_forget()
        self.suite_selector.pack_forget()
        if self.aux_checkbox:
            self.aux_checkbox.pack_forget()
        target = getattr(self, 'settings_button', None)
        pack_kwargs_label = dict(side=tk.LEFT, padx=(20, 5), pady=15)
        pack_kwargs_selector = dict(side=tk.LEFT, padx=5, pady=15)
        if target:
            pack_kwargs_label['before'] = target
            pack_kwargs_selector['before'] = target
        self.suite_label.pack(**pack_kwargs_label)
        self.suite_selector.pack(**pack_kwargs_selector)
        if include_aux and self.aux_checkbox:
            pack_kwargs_aux = dict(side=tk.LEFT, padx=(20, 5), pady=15)
            if target:
                pack_kwargs_aux['before'] = target
            self.aux_checkbox.pack(**pack_kwargs_aux)

    def _register_responsive_row(self, parent, containers, *, min_width=140):
        """Bind a resize handler that keeps tile widths responsive."""
        if not containers:
            return
        info = {
            'parent': parent,
            'containers': list(containers),
            'min_width': min_width,
        }

        def _on_config(event, row_info=info):
            self._apply_responsive_widths(row_info, event.width)

        parent.bind('<Configure>', _on_config, add='+')
        self._responsive_rows.append(info)
        parent.after_idle(lambda: self._apply_responsive_widths(info, parent.winfo_width()))

    def _apply_responsive_widths(self, info, total_width):
        containers = info.get('containers')
        if not containers:
            return
        min_width = info.get('min_width', 140)
        count = len(containers)
        if total_width is None or total_width <= 0:
            return
        padding = 10 * count
        available = max(total_width - padding, 1)
        base_target = max(1, available // max(1, count))
        if base_target >= min_width:
            target = base_target
        else:
            shrink_floor = max(60, min_width // 2)
            target = max(shrink_floor, base_target)
        stale = []
        for container in containers:
            try:
                if container and container.winfo_exists():
                    container.configure(width=target)
                else:
                    stale.append(container)
            except tk.TclError:
                stale.append(container)
        for container in stale:
            try:
                containers.remove(container)
            except ValueError:
                pass

    def _hide_suite_controls(self):
        """Hide suite selector and aux checkbox"""
        self.suite_label.pack_forget()
        self.suite_selector.pack_forget()
        if self.aux_checkbox:
            self.aux_checkbox.pack_forget()


    def _build_menu_bar(self):
        """Create the menu bar with View and Window menus."""
        menu_bar = tk.Menu(self.root)
        self.root.config(menu=menu_bar)
        self._view_menu_var = tk.StringVar(value=self.view_mode)
        view_menu = tk.Menu(menu_bar, tearoff=0)
        view_menu.add_radiobutton(label="1 Suite", variable=self._view_menu_var, value="1",
                                  command=lambda: self._select_view_mode("1"))
        view_menu.add_radiobutton(label="2 Suites", variable=self._view_menu_var, value="2",
                                  command=lambda: self._select_view_mode("2"))
        view_menu.add_radiobutton(label="4 Suites", variable=self._view_menu_var, value="4",
                                  command=lambda: self._select_view_mode("4"))
        menu_bar.add_cascade(label="View", menu=view_menu)
        window_menu = tk.Menu(menu_bar, tearoff=0)
        window_menu.add_checkbutton(label="Aux Outputs", variable=self.show_aux_var, command=self.on_aux_toggle)
        window_menu.add_checkbutton(label="All Outputs", variable=self.show_all_outputs_var, command=self.on_outputs_toggle)
        window_menu.add_checkbutton(label="Logical Sources", variable=self.show_logical_var, command=self.on_logical_toggle)
        window_menu.add_checkbutton(label="Engineering Sources", variable=self.show_engineering_var, command=self.on_engineering_toggle)
        menu_bar.add_cascade(label="Window", menu=window_menu)
        help_menu = tk.Menu(menu_bar, tearoff=0)
        help_menu.add_command(label="About...", command=self.open_about_window)
        help_menu.add_separator()
        help_menu.add_command(label="License...", command=self.open_license_window)
        menu_bar.add_cascade(label="Help", menu=help_menu)

    def _select_view_mode(self, mode: str) -> None:
        """Handle View menu selections and keep UI state synchronized."""
        valid_modes = {"1": "1 Suite", "2": "2 Suites", "4": "4 Suites"}
        label = valid_modes.get(mode)
        if not label:
            return
        if self._view_menu_var:
            self._view_menu_var.set(mode)
        if self.view_var.get() != label:
            self.view_var.set(label)
        self.on_view_change()
        if mode == "1":
            self._update_single_suite_header()
        self._update_multi_suite_headers()

    def on_aux_toggle(self):
        """Handle aux display toggle"""
        if self.show_aux_var.get():
            self.open_aux_window(bring_to_front=True)
            self.update_display()
        else:
            self.close_aux_window()
    def on_outputs_toggle(self):
        """Handle outputs window toggle"""
        if self.show_all_outputs_var.get():
            self.open_outputs_window(bring_to_front=True)
            self.update_display()
        else:
            self.close_outputs_window()

    def on_logical_toggle(self):
        """Handle logical sources window toggle"""
        if self.show_logical_var.get():
            self.open_logical_window(bring_to_front=True)
            self._logical_loading = True
            self.update_display()
        else:
            self.close_logical_window()

    def on_engineering_toggle(self):
        """Handle engineering sources window toggle"""
        if self.show_engineering_var.get():
            self.open_engineering_window(bring_to_front=True)
            self._engineering_loading = True
            self.update_display()
        else:
            self.close_engineering_window()

    def open_logical_window(self, bring_to_front=True):
        window_exists = self.logical_window and self.logical_window.winfo_exists()
        if window_exists:
            if bring_to_front:
                self.logical_window.deiconify()
                self.logical_window.lift()
            return
        window = tk.Toplevel(self.root)
        window.title("Logical Sources")
        window.configure(bg='#1e1e1e')
        window.minsize(320, 240)
        window.geometry("572x560")
        outer = tk.Frame(window, bg='#1e1e1e')
        outer.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        outer.grid_rowconfigure(0, weight=0)
        outer.grid_rowconfigure(1, weight=1)
        outer.grid_columnconfigure(0, weight=1)
        header = tk.Frame(outer, bg='#1e1e1e')
        header.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 8))
        tk.Label(header, text="Suite:", bg='#1e1e1e', fg='white', font=self.label_font).pack(side=tk.LEFT)
        self._logical_suite_selector = ttk.Combobox(
            header,
            textvariable=self._logical_suite_var,
            values=["Suite1", "Suite2", "Suite3", "Suite4"],
            state='readonly',
            width=10,
        )
        self._logical_suite_selector.pack(side=tk.LEFT, padx=(6, 0))
        self._logical_suite_selector.bind('<<ComboboxSelected>>', self._on_logical_suite_change)
        canvas = tk.Canvas(outer, bg='#1e1e1e', highlightthickness=0)
        canvas.grid(row=1, column=0, sticky='nsew')
        scrollbar = tk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        scrollbar.grid(row=1, column=1, sticky='ns')
        canvas.configure(yscrollcommand=scrollbar.set, takefocus=1)
        content = tk.Frame(canvas, bg='#1e1e1e')
        self._logical_canvas_window_id = canvas.create_window((0, 0), window=content, anchor='nw')
        content.bind('<Configure>', lambda e, cv=canvas, wid=self._logical_canvas_window_id, cont=content: self._refresh_canvas_window_height(cv, wid, cont))
        self._enable_canvas_mousewheel(canvas, content)
        window.protocol('WM_DELETE_WINDOW', self._on_logical_window_close)
        if bring_to_front:
            window.lift()
        self.logical_window = window
        self.logical_canvas = canvas
        self.logical_window_content = content
        self._logical_loading = True
        self._logical_render_state = None
        self._position_floating_window(window)
        initial_connected = self.client.connected if self.client else False
        self.update_logical_window([], False, initial_connected)

    def _on_logical_window_close(self):
        if self.show_logical_var.get():
            self.show_logical_var.set(False)
        self.close_logical_window()

    def close_logical_window(self):
        canvas = self.logical_canvas
        if self._logical_update_after_id:
            try:
                self.root.after_cancel(self._logical_update_after_id)
            except Exception:
                pass
            self._logical_update_after_id = None
        self._cancel_logical_render_job()
        state_map = getattr(self, '_canvas_scroll_state', None)
        if isinstance(state_map, dict) and canvas in state_map:
            state_map.pop(canvas, None)
        if self.logical_window and self.logical_window.winfo_exists():
            self.logical_window.destroy()
        self.logical_window = None
        self.logical_canvas = None
        self.logical_window_content = None
        self._logical_canvas_window_id = None
        self._logical_suite_selector = None
        self._logical_render_state = None
        self._logical_entries = None
        self._logical_entries_data = None

    def update_logical_window(self, entries, data_ready, connected):
        window = self.logical_window
        content = self.logical_window_content
        canvas = self.logical_canvas
        if not window or not content or not window.winfo_exists():
            return

        if canvas and self._is_canvas_scrolling(canvas):
            if self._logical_update_after_id is None:
                def _resume():
                    self._logical_update_after_id = None
                    self.update_logical_window(entries, data_ready, connected)
                self._logical_update_after_id = self.root.after(200, _resume)
            return

        if self._logical_update_after_id:
            try:
                self.root.after_cancel(self._logical_update_after_id)
            except Exception:
                pass
            self._logical_update_after_id = None

        if not entries:
            if not connected:
                message = "NOT CONNECTED"
            elif not data_ready and self._logical_loading:
                message = "Loading logical sources..."
            else:
                message = "No logical sources available."
            state = ('message', message)
            if self._logical_render_state == state:
                return
            self._logical_render_state = state
            for widget in content.winfo_children():
                widget.destroy()
            self._render_centered_message(content, message, bg='#1e1e1e', pad_x=20, pad_y=40, margin=24)
            self._adjust_canvas_placeholder_bounds(self.logical_canvas, self._logical_canvas_window_id, window, True)
            self._refresh_canvas_window_height(canvas, self._logical_canvas_window_id, content)
            return

        normalized = tuple(
            (
                entry.get('id'),
                entry.get('name'),
                entry.get('type'),
                tuple(entry.get('lines', ())),
            )
            for entry in entries
        )
        state = ('entries', normalized)
        if not self._logical_loading and self._logical_render_state == state:
            return
        self._logical_render_state = state
        self._logical_loading = False

        for widget in content.winfo_children():
            widget.destroy()
        self._adjust_canvas_placeholder_bounds(self.logical_canvas, self._logical_canvas_window_id, window, False)

        try:
            total_cols, _ = content.grid_size()
        except Exception:
            total_cols = 0
        for col in range(total_cols):
            content.grid_columnconfigure(col, weight=0)

        columns = 2 if len(entries) > 1 else 1
        for col in range(columns):
            content.grid_columnconfigure(col, weight=1)

        self._cancel_logical_render_job()
        chunk_size = max(6, columns * 6)
        self._logical_entries = normalized
        self._logical_entries_data = list(entries)
        self._logical_render_job = self.root.after_idle(lambda: self._render_logical_entries_chunk(list(entries), columns, 0, content, chunk_size))

    def open_engineering_window(self, bring_to_front=True):
        window_exists = self.engineering_window and self.engineering_window.winfo_exists()
        if window_exists:
            if bring_to_front:
                self.engineering_window.deiconify()
                self.engineering_window.lift()
            return
        window = tk.Toplevel(self.root)
        window.title("Engineering Sources")
        window.configure(bg='#1e1e1e')
        window.minsize(320, 240)
        window.geometry("572x560")
        outer = tk.Frame(window, bg='#1e1e1e')
        outer.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        outer.grid_rowconfigure(0, weight=1)
        outer.grid_columnconfigure(0, weight=1)
        canvas = tk.Canvas(outer, bg='#1e1e1e', highlightthickness=0)
        canvas.grid(row=0, column=0, sticky='nsew')
        scrollbar = tk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        canvas.configure(yscrollcommand=scrollbar.set, takefocus=1)
        content = tk.Frame(canvas, bg='#1e1e1e')
        self._engineering_canvas_window_id = canvas.create_window((0, 0), window=content, anchor='nw')
        content.bind('<Configure>', lambda e, cv=canvas, wid=self._engineering_canvas_window_id, cont=content: self._refresh_canvas_window_height(cv, wid, cont))
        self._enable_canvas_mousewheel(canvas, content)
        window.protocol('WM_DELETE_WINDOW', self._on_engineering_window_close)
        if bring_to_front:
            window.lift()
        self.engineering_window = window
        self.engineering_canvas = canvas
        self.engineering_window_content = content
        self._engineering_loading = True
        self._engineering_render_state = None
        self._position_floating_window(window)
        initial_connected = self.client.connected if self.client else False
        self.update_engineering_window([], False, initial_connected)

    def _on_engineering_window_close(self):
        if self.show_engineering_var.get():
            self.show_engineering_var.set(False)
        self.close_engineering_window()

    def close_engineering_window(self):
        canvas = self.engineering_canvas
        if self._engineering_update_after_id:
            try:
                self.root.after_cancel(self._engineering_update_after_id)
            except Exception:
                pass
            self._engineering_update_after_id = None
        self._cancel_engineering_render_job()
        state_map = getattr(self, '_canvas_scroll_state', None)
        if isinstance(state_map, dict) and canvas in state_map:
            state_map.pop(canvas, None)
        if self.engineering_window and self.engineering_window.winfo_exists():
            self.engineering_window.destroy()
        self.engineering_window = None
        self.engineering_canvas = None
        self.engineering_window_content = None
        self._engineering_canvas_window_id = None
        self._engineering_render_state = None
        self._engineering_entries = None
        self._engineering_entries_data = None

    def update_engineering_window(self, entries, data_ready, connected):
        window = self.engineering_window
        content = self.engineering_window_content
        canvas = self.engineering_canvas
        if not window or not content or not window.winfo_exists():
            return

        if canvas and self._is_canvas_scrolling(canvas):
            if self._engineering_update_after_id is None:
                def _resume():
                    self._engineering_update_after_id = None
                    self.update_engineering_window(entries, data_ready, connected)
                self._engineering_update_after_id = self.root.after(200, _resume)
            return

        if self._engineering_update_after_id:
            try:
                self.root.after_cancel(self._engineering_update_after_id)
            except Exception:
                pass
            self._engineering_update_after_id = None

        if not entries:
            if not connected:
                message = "NOT CONNECTED"
            elif not data_ready and self._engineering_loading:
                message = "Loading engineering sources..."
            else:
                message = "No engineering sources available."
            state = ('message', message)
            if self._engineering_render_state == state:
                return
            self._engineering_render_state = state
            for widget in content.winfo_children():
                widget.destroy()
            self._render_centered_message(content, message, bg='#1e1e1e', pad_x=20, pad_y=40, margin=24)
            self._adjust_canvas_placeholder_bounds(self.engineering_canvas, self._engineering_canvas_window_id, window, True)
            self._refresh_canvas_window_height(canvas, self._engineering_canvas_window_id, content)
            return

        normalized = tuple(
            (
                entry.get('id'),
                entry.get('name'),
                entry.get('type'),
                entry.get('bnc'),
            )
            for entry in entries
        )
        state = ('entries', normalized)
        if not self._engineering_loading and self._engineering_render_state == state:
            return
        self._engineering_render_state = state
        self._engineering_loading = False

        for widget in content.winfo_children():
            widget.destroy()
        self._adjust_canvas_placeholder_bounds(self.engineering_canvas, self._engineering_canvas_window_id, window, False)

        try:
            total_cols, _ = content.grid_size()
        except Exception:
            total_cols = 0
        for col in range(total_cols):
            content.grid_columnconfigure(col, weight=0)

        columns = 2 if len(entries) > 1 else 1
        for col in range(columns):
            content.grid_columnconfigure(col, weight=1)

        self._cancel_engineering_render_job()
        chunk_size = max(6, columns * 6)
        self._engineering_entries = normalized
        self._engineering_entries_data = list(entries)
        self._engineering_render_job = self.root.after_idle(lambda: self._render_engineering_entries_chunk(list(entries), columns, 0, content, chunk_size))
    def open_settings_dialog(self):
        """Prompt for output display preferences using themed modal."""
        if self._settings_window and self._settings_window.winfo_exists():
            self._settings_window.lift()
            self._settings_window.focus_set()
            return
        try:
            current_value = int(self.max_outputs_to_display)
        except (TypeError, ValueError):
            current_value = 48
        current_value = max(1, min(500, current_value))
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Output Settings")
        settings_window.configure(bg='#1e1e1e')
        settings_window.resizable(False, False)
        settings_window.transient(self.root)
        settings_window.grab_set()
        self._settings_window = settings_window
        self.root.update_idletasks()
        width, height = 320, 200
        base_x = self.root.winfo_rootx()
        base_y = self.root.winfo_rooty()
        base_width = self.root.winfo_width()
        window_x = base_x + (base_width // 2) - (width // 2)
        window_y = base_y + 120
        settings_window.geometry(f"{width}x{height}+{window_x}+{window_y}")
        container = tk.Frame(settings_window, bg='#1e1e1e')
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        prompt_label = tk.Label(
            container,
            text="Maximum outputs to display (per suite):",
            bg='#1e1e1e',
            fg='white',
            font=self.label_font,
            anchor='w',
            justify=tk.LEFT,
        )
        prompt_label.pack(anchor='w')
        control_frame = tk.Frame(container, bg='#1e1e1e')
        control_frame.pack(pady=12)
        value_var = tk.StringVar(value=str(current_value))
        def validate_value(new_value: str) -> bool:
            if not new_value:
                return True
            if not new_value.isdigit():
                return False
            return int(new_value) <= 500
        validate_command = settings_window.register(validate_value)
        value_entry = tk.Entry(
            control_frame,
            textvariable=value_var,
            width=6,
            justify='center',
            bg='#3c3c3c',
            fg='white',
            insertbackground='white',
            font=self.source_font,
            validate='key',
            validatecommand=(validate_command, '%P'),
        )
        value_entry.grid(row=0, column=0, rowspan=2, padx=10, pady=4)
        def adjust(delta: int):
            try:
                current = int(value_var.get())
            except (TypeError, ValueError):
                current = current_value
            new_value = max(1, min(500, current + delta))
            value_var.set(str(new_value))
        up_button = tk.Button(
            control_frame,
            text='\u25B2',
            command=lambda: adjust(1),
            width=3,
            bg='#3c3c3c',
            fg='white',
            activebackground='#555555',
            activeforeground='white',
            relief=tk.FLAT,
        )
        up_button.grid(row=0, column=1, sticky='nsew', pady=(0, 2))
        down_button = tk.Button(
            control_frame,
            text='\u25BC',
            command=lambda: adjust(-1),
            width=3,
            bg='#3c3c3c',
            fg='white',
            activebackground='#555555',
            activeforeground='white',
            relief=tk.FLAT,
        )
        down_button.grid(row=1, column=1, sticky='nsew', pady=(2, 0))
        control_frame.grid_columnconfigure(0, weight=1)
        control_frame.grid_columnconfigure(1, weight=0)
        info_label = tk.Label(
            container,
            text="Allowed range: 1-500",
            bg='#1e1e1e',
            fg='#cccccc',
            font=self.label_font,
        )
        info_label.pack()
        button_frame = tk.Frame(container, bg='#1e1e1e')
        button_frame.pack(fill=tk.X, pady=(20, 0))
        def close_settings(event=None):
            window = self._settings_window
            if window and window.winfo_exists():
                try:
                    window.grab_release()
                except tk.TclError:
                    pass
                window.destroy()
            self._settings_window = None
        def apply_settings(event=None):
            try:
                new_value = int(value_var.get())
            except (TypeError, ValueError):
                messagebox.showerror(
                    "Invalid Value",
                    "Please enter a number between 1 and 500.",
                    parent=settings_window,
                )
                value_var.set(str(current_value))
                value_entry.focus_set()
                return
            if not (1 <= new_value <= 500):
                messagebox.showerror(
                    "Invalid Value",
                    "Please enter a number between 1 and 500.",
                    parent=settings_window,
                )
                value_var.set(str(max(1, min(500, new_value))))
                value_entry.focus_set()
                return
            self.max_outputs_to_display = new_value
            if self.show_aux_var.get() or self.show_all_outputs_var.get():
                self.update_display()
            close_settings()
        cancel_button = tk.Button(
            button_frame,
            text='Cancel',
            command=close_settings,
            bg='#3c3c3c',
            fg='white',
            activebackground='#555555',
            activeforeground='white',
            relief=tk.FLAT,
            padx=18,
            pady=6,
        )
        cancel_button.pack(side=tk.RIGHT, padx=(8, 0))
        save_button = tk.Button(
            button_frame,
            text='Save',
            command=apply_settings,
            bg='#4CAF50',
            fg='white',
            activebackground='#66bb6a',
            activeforeground='white',
            relief=tk.FLAT,
            padx=18,
            pady=6,
        )
        save_button.pack(side=tk.RIGHT)
        settings_window.protocol('WM_DELETE_WINDOW', close_settings)
        settings_window.bind('<Return>', apply_settings)
        settings_window.bind('<Escape>', close_settings)
        value_entry.focus_set()
        self.root.wait_window(settings_window)
    def _position_floating_window(self, window, *, align_to_aux=False):
        self.root.update_idletasks()
        window.update_idletasks()
        base_x = self.root.winfo_rootx()
        base_y = self.root.winfo_rooty()
        base_width = self.root.winfo_width()
        win_w = window.winfo_width() or window.winfo_reqwidth()
        win_h = window.winfo_height() or window.winfo_reqheight()
        x = base_x + base_width + 20
        y = base_y
        if align_to_aux:
            aux_window = getattr(self.aux_window_controller, 'window', None)
            if aux_window and aux_window.winfo_exists():
                aux_x = aux_window.winfo_rootx()
                aux_w = aux_window.winfo_width()
                x = max(x, aux_x + aux_w + 16)

        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = max(0, min(x, screen_w - win_w - 20))
        y = max(0, min(y, screen_h - win_h - 20))
        window.geometry(f"{win_w}x{win_h}+{x}+{y}")
    def open_aux_window(self, bring_to_front=True):
        self.aux_window_controller.open(bring_to_front=bring_to_front)




    def close_aux_window(self):
        self.aux_window_controller.close()

    def update_aux_window(self, entries):
        self.aux_window_controller.render(AuxWindow.from_raw(entries or []))

    def open_outputs_window(self, bring_to_front=True):
        window_exists = self.outputs_window and self.outputs_window.winfo_exists()
        should_lift = bring_to_front or not window_exists
        if window_exists:
            if should_lift:
                self.outputs_window.deiconify()
                self.outputs_window.lift()
            return

        window = tk.Toplevel(self.root)
        window.title("All Outputs")
        window.configure(bg='#1e1e1e')
        window.minsize(360, 260)
        window.geometry("572x560")

        outer = tk.Frame(window, bg='#1e1e1e')
        outer.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        outer.grid_rowconfigure(0, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        canvas = tk.Canvas(outer, bg='#1e1e1e', highlightthickness=0)
        canvas.grid(row=0, column=0, sticky='nsew')

        scrollbar = tk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        canvas.configure(yscrollcommand=scrollbar.set, takefocus=1)

        content = tk.Frame(canvas, bg='#1e1e1e')
        self._outputs_canvas_window_id = canvas.create_window((0, 0), window=content, anchor='nw')
        content.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
        self._enable_canvas_mousewheel(canvas, content)

        window.protocol('WM_DELETE_WINDOW', self._on_outputs_window_close)
        window.bind('<Configure>', self._on_outputs_window_configure)

        self.outputs_window = window
        self.outputs_canvas = canvas
        if should_lift:
            window.lift()
        self.outputs_window_content = content
        self._output_entries = None
        self._output_entries_data = []
        self._outputs_resize_pending = False
        window.update_idletasks()
        self._outputs_last_width = window.winfo_width()

        self._position_floating_window(window, align_to_aux=True)
        self.update_outputs_window([])

    def _on_outputs_window_close(self):
        if self.show_all_outputs_var.get():
            self.show_all_outputs_var.set(False)
        self.close_outputs_window()

    def close_outputs_window(self):
        if self.outputs_window and self.outputs_window.winfo_exists():
            self.outputs_window.destroy()
        self.outputs_window = None
        self.outputs_canvas = None
        self.outputs_window_content = None
        self._output_entries = None
        self._output_entries_data = None
        self._outputs_last_width = 0
        self._outputs_resize_pending = False
        self._outputs_canvas_window_id = None

    def _fit_outputs_canvas_width(self):
        min_width = 220
        width = self._measure_canvas_width(
            self.outputs_canvas,
            self.outputs_window,
            self.outputs_window_content,
            self._outputs_last_width,
            min_width,
        )
        if self.outputs_canvas and self._outputs_canvas_window_id is not None:
            self.outputs_canvas.itemconfig(self._outputs_canvas_window_id, width=width)
        return width

    def _on_outputs_window_configure(self, event):
        if not self.outputs_window or event.widget is not self.outputs_window:
            return
        new_width = event.width
        if new_width <= 0:
            return
        if abs(new_width - self._outputs_last_width) < 2:
            return
        self._outputs_last_width = new_width
        if self._outputs_resize_pending:
            return
        self._outputs_resize_pending = True
        self.root.after_idle(self._refresh_outputs_window)

    def _refresh_outputs_window(self):
        if not self.outputs_window or not self.outputs_window.winfo_exists():
            self._outputs_resize_pending = False
            return
        cached = self._output_entries_data
        self._output_entries = None
        if cached is None:
            self.update_outputs_window([])
        else:
            self.update_outputs_window(list(cached))
        self._outputs_resize_pending = False

    def update_outputs_window(self, entries):
        window = self.outputs_window
        content = self.outputs_window_content
        if not window or not content or not window.winfo_exists():
            return

        normalized = tuple(entries) if entries is not None else None
        self._output_entries_data = None if entries is None else list(entries)

        if not self._outputs_resize_pending and normalized == self._output_entries:
            return
        self._output_entries = normalized

        for widget in content.winfo_children():
            widget.destroy()

        for col in range(16):
            content.grid_columnconfigure(col, weight=0)

        if entries is None:
            self._render_centered_message(content, "Outputs display disabled.", bg='#1e1e1e', margin=24)
            self._adjust_canvas_placeholder_bounds(self.outputs_canvas, self._outputs_canvas_window_id, window, True)
        elif not entries:
            if not self.client or not self.client.connected:
                message = "NOT CONNECTED"
            else:
                message = "No output data received yet."
            self._render_centered_message(content, message, bg='#1e1e1e', margin=24)
            self._adjust_canvas_placeholder_bounds(self.outputs_canvas, self._outputs_canvas_window_id, window, True)
        else:
            self._adjust_canvas_placeholder_bounds(self.outputs_canvas, self._outputs_canvas_window_id, window, False)
            available_width = self._fit_outputs_canvas_width()
            window_width = 0
            if window and window.winfo_exists():
                try:
                    window.update_idletasks()
                except Exception:
                    pass
                window_width = window.winfo_width()
            if window_width and window_width > 1:
                target_width = max(window_width - 48, 140)
                if target_width > available_width and self.outputs_canvas and self._outputs_canvas_window_id is not None:
                    self.outputs_canvas.itemconfig(self._outputs_canvas_window_id, width=target_width)
                    available_width = target_width
            min_col_width = 200
            columns = self._compute_flow_columns(available_width, len(entries), min_col_width, 12)
            if columns <= 0:
                columns = 1
            for col in range(columns):
                content.grid_columnconfigure(col, weight=1)

            for idx, (_, suite_label, out_num, name, source_label) in enumerate(entries):
                row = idx // columns
                col = idx % columns
                entry_frame = tk.Frame(content, bg='#1e1e1e', bd=1, relief=tk.FLAT)
                entry_frame.grid(row=row, column=col, sticky='nsew', padx=6, pady=4)

                header = f"{suite_label} - {name}"
                header_label = tk.Label(entry_frame, text=header, bg='#1e1e1e', fg='#99ccff',
                                        font=self.label_font, anchor='w')
                header_label.pack(fill=tk.X, padx=4, pady=(4, 0))

                source_text = source_label or "No Source"
                source_label_widget = tk.Label(entry_frame, text=source_text, bg='#1e1e1e', fg='white',
                                               font=self.source_font, anchor='w', justify=tk.LEFT)
                source_label_widget.pack(fill=tk.X, padx=4, pady=(0, 4))

        self._update_canvas_scroll_region(self.outputs_canvas)
        if window and window.winfo_exists():
            self._outputs_last_width = window.winfo_width()

    def _collect_aux_entries(self, suite_indices, *, aux_assignments=None, source_names=None):
        entries = []
        if aux_assignments is None or source_names is None:
            if not self.client:
                return entries
            aux_assignments = self.client.aux_assignments
            source_names = self.client.source_names
        for suite_idx in suite_indices:
            aux_map = aux_assignments.get(suite_idx) if aux_assignments else None
            if not aux_map:
                continue
            suite_label = f"Suite {suite_idx + 1}"
            count = 0
            for out_num, data in aux_map.items():
                name = data.get('name') or f"AUX {out_num}"
                logsrc = data.get('logsrc', '')
                if logsrc and logsrc in source_names:
                    source_label = f"{source_names[logsrc]} ({logsrc})"
                elif logsrc:
                    source_label = f"Source {logsrc}"
                else:
                    source_label = "No Source"
                entries.append((suite_idx, suite_label, out_num, name, source_label))
                count += 1
                if count >= self.max_outputs_to_display:
                    break
        entries.sort(key=lambda item: (item[0], item[2]))
        return entries
    def _measure_canvas_width(self, canvas, window, content, last_known_width, minimum):
        if not canvas:
            return minimum
        try:
            canvas.update_idletasks()
        except Exception:
            pass
        width = canvas.winfo_width()
        if width <= 1 and content:
            try:
                content.update_idletasks()
            except Exception:
                pass
            width = content.winfo_width()
        if width <= 1 and window:
            try:
                window.update_idletasks()
            except Exception:
                pass
            width = canvas.winfo_width()
        if width <= 1 and last_known_width:
            width = max(last_known_width - 32, minimum)
        return max(width, minimum)
    @staticmethod
    def _compute_flow_columns(available_width, item_count, min_item_width, gutter):
        if item_count <= 0:
            return 0
        usable = max(0, available_width)
        denom = max(1, min_item_width + gutter)
        rough = int((usable + gutter) // denom)
        columns = max(1, rough)
        return min(item_count, columns)

    def _apply_app_icon(self):
        try:
            icon_path = resources.files("assets").joinpath("broadcast_software.png")
        except ModuleNotFoundError:
            icon_path = Path(__file__).resolve().parent / "assets" / "broadcast_software.png"
        try:
            if not icon_path.is_file():
                return
            self._app_icon_image = tk.PhotoImage(file=str(icon_path))
            self.root.iconphoto(False, self._app_icon_image)
        except (FileNotFoundError, tk.TclError, AttributeError):
            self._app_icon_image = None



    def _collect_output_entries(self, suite_indices, *, all_outputs=None, source_names=None):
        entries = []
        if all_outputs is None or source_names is None:
            if not self.client:
                return entries
            all_outputs = self.client.all_outputs
            source_names = self.client.source_names
        for suite_idx in suite_indices:
            outputs = all_outputs.get(suite_idx) if all_outputs else None
            if not outputs:
                continue
            suite_label = f"Suite {suite_idx + 1}"
            count = 0
            for out_num, data in outputs.items():
                name = data.get('name') or f"Output {out_num}"
                logsrc = data.get('logsrc', '')
                if logsrc and logsrc in source_names:
                    source_label = f"{source_names[logsrc]} ({logsrc})"
                elif logsrc:
                    source_label = f"Source {logsrc}"
                else:
                    source_label = "No Source"
                entries.append((suite_idx, suite_label, out_num, name, source_label))
                count += 1
                if count >= self.max_outputs_to_display:
                    break
        entries.sort(key=lambda item: (item[0], item[2]))
        return entries

    def _derive_logical_suite_index(self):
        value = self._logical_suite_var.get()
        try:
            return max(0, int(str(value).replace('Suite', '')) - 1)
        except (TypeError, ValueError):
            return 0

    def _collect_logical_entries(self, *, logical_sources=None, engineering_sources=None):
        entries = []
        if logical_sources is None or engineering_sources is None:
            if not self.client:
                return entries
            logical_sources = self.client.logical_sources
            engineering_sources = getattr(self.client, 'engineering_sources', OrderedDict())
        suite_idx = self._derive_logical_suite_index()
        logical_map = logical_sources.get(suite_idx, OrderedDict())
        engineering_map = engineering_sources or OrderedDict()
        for log_id, data in logical_map.items():
            display_name = (data.get('name') or f"Logical {log_id}").strip()
            upper_name = display_name.upper()
            if upper_name.startswith('TBD'):
                continue
            if upper_name.startswith('MVIEW'):
                continue
            eng_id = (data.get('eng_src') or '').strip()
            vs_desc = []
            for vs in data.get('vsources', []):
                eng_vs_id = (vs.get('id') or '').strip()
                label = ''
                if eng_vs_id and eng_vs_id in engineering_map:
                    info = engineering_map[eng_vs_id]
                    label = info.get('name') or f"Engineering {eng_vs_id}"
                    bnc = info.get('bnc')
                    if bnc:
                        label = f"{label} (BNC {bnc})"
                elif eng_vs_id:
                    label = f"Engineering {eng_vs_id}"
                else:
                    label = "No engineering mapping"
                stype = (vs.get('stype') or '').strip()
                if stype:
                    label = f"{stype.upper()}: {label}"
                vs_desc.append(label)
            if not vs_desc:
                if eng_id and eng_id in engineering_map:
                    info = engineering_map[eng_id]
                    desc = info.get('name') or f"Engineering {eng_id}"
                    bnc = info.get('bnc')
                    if bnc:
                        desc = f"{desc} (BNC {bnc})"
                    vs_desc.append(desc)
                elif eng_id:
                    vs_desc.append(f"Engineering {eng_id}")
                else:
                    vs_desc.append("No engineering mapping")
            entries.append({
                'id': log_id,
                'name': display_name,
                'type': data.get('type') or '',
                'lines': vs_desc,
            })
        return entries
    def _collect_engineering_entries(self, *, engineering_sources=None):
        entries = []
        if engineering_sources is None:
            if not self.client:
                return entries
            engineering_sources = getattr(self.client, 'engineering_sources', OrderedDict())
        for eng_id, data in engineering_sources.items():
            entries.append({
                'id': eng_id,
                'name': data.get('name') or f"Engineering {eng_id}",
                'type': data.get('type') or '',
                'bnc': data.get('bnc') or '',
            })
        return entries
    def _on_logical_suite_change(self, event=None):
        self._logical_loading = True
        self.update_display()
    def _format_suite_header_text(self, suite_name: str) -> str:
        try:
            number = int(str(suite_name).replace('Suite', '').strip())
        except (TypeError, ValueError):
            number = 1
        if number < 1:
            number = 1
        return f"SUITE {number}"

    def _update_single_suite_header(self) -> None:
        if self.suite_header_label_1view and self.suite_header_label_1view.winfo_exists():
            text = self._format_suite_header_text(self.suite_var.get())
            self.suite_header_label_1view.config(text=text)

    def _update_multi_suite_headers(self) -> None:
        if self.view_mode == "2":
            base_suite = 2 if self.suite_var.get() == "Suite3-4" else 0
            for idx, header in enumerate(self.suite_headers_2view):
                suite_number = base_suite + idx + 1
                if header.winfo_exists():
                    header.config(text=f"SUITE {suite_number}")
        elif self.view_mode == "4":
            for idx, header in enumerate(self.suite_headers_4view):
                suite_number = idx + 1
                if header.winfo_exists():
                    header.config(text=f"SUITE {suite_number}")

    def _collect_state_from_client(self) -> dict[str, object]:
        if not self.client:
            return {}
        client = self.client
        with client.lock:
            state = {
                'current_on_air': copy.deepcopy(client.current_on_air),
                'source_names': copy.deepcopy(client.source_names),
                'aux_assignments': copy.deepcopy(client.aux_assignments),
                'all_outputs': copy.deepcopy(client.all_outputs),
                'logical_sources': copy.deepcopy(client.logical_sources),
                'logical_suites_ready': set(client.logical_suites_ready),
                'engineering_sources': copy.deepcopy(getattr(client, 'engineering_sources', OrderedDict())),
                'engineering_sources_ready': getattr(client, 'engineering_sources_ready', False),
            }
        return state

    def _render_display_from_state(self, state: dict[str, object], *, connected: bool) -> None:
        if not state or not state.get('source_names'):
            self._display_not_connected_state()
            return
        source_names = state.get('source_names', {})
        current_on_air = state.get('current_on_air', {})

        view_mode = self.view_mode
        if view_mode == "1":
            suite_name = self.suite_var.get()
            try:
                suite_index = int(suite_name.replace('Suite', '')) - 1
            except (TypeError, ValueError):
                suite_index = 0
            self._update_single_suite_header()
            current_data = current_on_air.get(suite_index, {}) if isinstance(current_on_air, dict) else {}
            if 'pgm' in self.boxes[view_mode]:
                box_data = self.boxes[view_mode]['pgm']
                self.update_content_frame(box_data['content_frame'], current_data.get('PGM', ''), '#cc0000', box_data)
            for me_num in range(1, 5):
                key = f'me{me_num}'
                if key in self.boxes[view_mode]:
                    box_data = self.boxes[view_mode][key]
                    self.update_content_frame(box_data['content_frame'], current_data.get(f'ME{me_num}', ''), '#0066cc', box_data)
        elif view_mode == "2":
            base_suite = 2 if self.suite_var.get() == "Suite3-4" else 0
            self._update_multi_suite_headers()
            for offset in range(2):
                suite_idx = base_suite + offset
                current_data = current_on_air.get(suite_idx, {}) if isinstance(current_on_air, dict) else {}
                key = f's{offset}_pgm'
                if key in self.boxes[view_mode]:
                    box_data = self.boxes[view_mode][key]
                    self.update_content_frame(box_data['content_frame'], current_data.get('PGM', ''), '#cc0000', box_data)
                for me_num in range(1, 5):
                    key = f's{offset}_me{me_num}'
                    if key in self.boxes[view_mode]:
                        box_data = self.boxes[view_mode][key]
                        self.update_content_frame(box_data['content_frame'], current_data.get(f'ME{me_num}', ''), '#0066cc', box_data)
        else:
            self._update_multi_suite_headers()
            for suite_idx in range(4):
                current_data = current_on_air.get(suite_idx, {}) if isinstance(current_on_air, dict) else {}
                key = f's{suite_idx}_pgm'
                if key in self.boxes[view_mode]:
                    box_data = self.boxes[view_mode][key]
                    self.update_content_frame(box_data['content_frame'], current_data.get('PGM', ''), '#cc0000', box_data)
                for me_num in range(1, 5):
                    key = f's{suite_idx}_me{me_num}'
                    if key in self.boxes[view_mode]:
                        box_data = self.boxes[view_mode][key]
                        self.update_content_frame(box_data['content_frame'], current_data.get(f'ME{me_num}', ''), '#0066cc', box_data)

        suites_for_view = self._resolve_view_suites()

        aux_entries = self._collect_aux_entries(
            suites_for_view,
            aux_assignments=state.get('aux_assignments'),
            source_names=source_names,
        )
        output_entries = self._collect_output_entries(
            suites_for_view,
            all_outputs=state.get('all_outputs'),
            source_names=source_names,
        )
        logical_entries = self._collect_logical_entries(
            logical_sources=state.get('logical_sources'),
            engineering_sources=state.get('engineering_sources'),
        )
        logical_ready = self._derive_logical_suite_index() in state.get('logical_suites_ready', set())
        engineering_entries = self._collect_engineering_entries(
            engineering_sources=state.get('engineering_sources'),
        )
        engineering_ready = bool(state.get('engineering_sources_ready'))

        if self.show_aux_var.get():
            self.open_aux_window(bring_to_front=False)
            self.update_aux_window(aux_entries)
        else:
            self.close_aux_window()
        if self.show_all_outputs_var.get():
            self.open_outputs_window(bring_to_front=False)
            self.update_outputs_window(output_entries)
        else:
            self.close_outputs_window()
        if self.show_logical_var.get():
            self.open_logical_window(bring_to_front=False)
            self.update_logical_window(logical_entries, logical_ready, connected)
        else:
            self.close_logical_window()
        if self.show_engineering_var.get():
            self.open_engineering_window(bring_to_front=False)
            self.update_engineering_window(engineering_entries, engineering_ready, connected)
        else:
            self.close_engineering_window()

    def _resolve_view_suites(self):
        if self.view_mode == "1":
            suite_name = self.suite_var.get()
            try:
                return [max(0, int(suite_name.replace('Suite', '')) - 1)]
            except (TypeError, ValueError):
                return [0]
        if self.view_mode == "2":
            selection = self.suite_var.get()
            if selection == "Suite3-4":
                return [2, 3]
            return [0, 1]
        return [0, 1, 2, 3]
    def toggle_connection(self):
        """Toggle connection to K-Frame"""
        if self.client and self.client.connected:
            self.disconnect()
        else:
            self.connect()
    def connect(self):
        """Connect to K-Frame"""
        if not self._license_allows_connection():
            return
        ip = self.ip_var.get().strip()
        if not ip:
            messagebox.showerror("Error", "Please enter an IP address")
            return
        self.ip_var.set(ip)
        self._persist_app_settings()
        self.status_label.config(text="CONNECTING...", fg='yellow')
        self.connect_btn.config(state="disabled")
        threading.Thread(target=self._connect_worker, args=(ip,), daemon=True).start()
    def _connect_worker(self, ip):
        """Simple connection worker"""
        self.client = SimpleKFrameClient(ip)
        self.client.gui = self
        if self.client.start():
            self.root.after(0, self._on_connected)
        else:
            self.root.after(0, self._on_connect_failed)
    def _on_connected(self):
        """Called when connection succeeds"""
        self.status_label.config(text="CONNECTED", fg='#4CAF50')
        self.connect_btn.config(text="DISCONNECT", bg='#f44336', state="normal")
        self.ip_entry.config(state="disabled")
    def _on_connect_failed(self):
        """Called when connection fails"""
        self.status_label.config(text="CONNECTION FAILED", fg='#ff5555')
        self.connect_btn.config(state="normal")
        self._display_not_connected_state()
    def disconnect(self):
        """Disconnect from K-Frame without clearing last known state"""
        if self.client:
            snapshot = {}
            try:
                snapshot = self._collect_state_from_client()
            except Exception:
                snapshot = {}
            if snapshot:
                self._cached_state = copy.deepcopy(snapshot)
            try:
                self.client.stop()
            except Exception:
                pass
            self.client = None
        self.status_label.config(text="DISCONNECTED", fg='#ff5555')
        self.connect_btn.config(text="CONNECT", bg='#4CAF50', state="normal")
        self.ip_entry.config(state="normal")
        self.update_display()
    def on_suite_change(self, event=None):
        """Handle suite selection change"""
        # Request fresh data for the new suite
        if self.client and self.client.connected:
            threading.Thread(target=self._request_suite_data, daemon=True).start()
        self.update_display()
        if self.view_mode == "1":
            self._update_single_suite_header()
        else:
            self._update_multi_suite_headers()
    def update_content_frame(self, content_frame, content, bg_color, box_data):
        """Update content frame with mixed-color labels that center properly"""
        # Only update if content changed
        if box_data.get('current_content') == content:
            return
        box_data['current_content'] = content
        # Clear existing content
        for widget in content_frame.winfo_children():
            widget.destroy()
        if not content:
            return
        # For simple states like "DISCONNECTED", show as single centered label
        if content in ["DISCONNECTED", "CONNECTING...", "CONNECTION FAILED"]:
            self._render_centered_message(content_frame, content, bg=bg_color, font=self.source_font)
            return
        # For layer content, create a centered container
        lines = content.split('\n')
        # Create a container frame that will be centered
        line_container = tk.Frame(content_frame, bg=bg_color)
        line_container.pack(expand=True)
        for line in lines:
            if line == "─────────────":
                # Separator line
                sep_label = tk.Label(line_container, text=line,
                                    bg=bg_color, fg='white',
                                    font=self.source_font, justify=tk.CENTER)
                sep_label.pack()
            elif ':' in line:
                # Layer line with mixed colors - create a frame for this line
                line_frame = tk.Frame(line_container, bg=bg_color)
                line_frame.pack()
                parts = line.split(':', 1)
                label_part = parts[0] + ':'
                source_part = parts[1] if len(parts) > 1 else ''
                # Layer name label (black text)
                layer_label = tk.Label(line_frame, text=label_part,
                                      bg=bg_color, fg='black',
                                      font=self.source_font)
                layer_label.pack(side=tk.LEFT)
                # Source name label (white text)
                if source_part:
                    source_label = tk.Label(line_frame, text=source_part,
                                          bg=bg_color, fg='white',
                                          font=self.source_font)
                    source_label.pack(side=tk.LEFT)
            else:
                # Other content
                other_label = tk.Label(line_container, text=line,
                                     bg=bg_color, fg='white',
                                     font=self.source_font, justify=tk.CENTER)
                other_label.pack()
    def _request_suite_data(self):
        """Request fresh data for current suite"""
        if self.client and self.client.connected:
            self.client.request_data()
    def update_display(self):
        """Update display based on current view mode"""
        state = None
        connected = False
        if self.client and self.client.connected:
            state = self._collect_state_from_client()
            if not state or not state.get('source_names'):
                return
            connected = True
            self._cached_state = copy.deepcopy(state)
        else:
            state = copy.deepcopy(self._cached_state) if self._cached_state else None
            if not state:
                self._display_not_connected_state()
                return
        try:
            self._render_display_from_state(state, connected=connected)
        except Exception as exc:
            print(f"Error updating display: {exc}")


def main():
    """Main function for GUI"""
    root = tk.Tk()
    app = VisualOnAirGUI(root)
    root.mainloop()
if __name__ == "__main__":
    main()








