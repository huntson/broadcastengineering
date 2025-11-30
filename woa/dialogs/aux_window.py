"""Auxiliary outputs window controller."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import tkinter as tk

from window_helpers import FloatingWindowMixin


@dataclass
class AuxEntry:
    suite_index: int
    suite_label: str
    output_number: str
    name: str
    source_label: str


class AuxWindow:
    """Encapsulates creation and updates for the Aux Outputs window."""

    def __init__(self, owner: FloatingWindowMixin) -> None:
        self.owner = owner
        self.window: tk.Toplevel | None = None
        self.canvas: tk.Canvas | None = None
        self.content: tk.Frame | None = None
        self.scrollbar: tk.Scrollbar | None = None
        self.canvas_window_id: int | None = None
        self.entries_state: tuple[AuxEntry, ...] | None = None
        self.entries_cache: list[AuxEntry] | None = None
        self._resize_pending: bool = False
        self._last_width: int = 0

    def open(self, bring_to_front: bool = True) -> None:
        window_exists = self.window and self.window.winfo_exists()
        should_lift = bring_to_front or not window_exists
        if window_exists:
            if should_lift:
                self.window.deiconify()
                self.window.lift()
            return

        window = tk.Toplevel(self.owner.root)
        window.title("Aux Outputs")
        window.configure(bg="#1e1e1e")
        window.minsize(320, 240)
        window.geometry("462x520")

        outer = tk.Frame(window, bg="#1e1e1e")
        outer.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        outer.grid_rowconfigure(0, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        canvas = tk.Canvas(outer, bg="#1e1e1e", highlightthickness=0)
        canvas.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scrollbar.set, takefocus=1)

        content = tk.Frame(canvas, bg="#1e1e1e")
        self.canvas_window_id = canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
        self.owner._enable_canvas_mousewheel(canvas, content)

        window.protocol("WM_DELETE_WINDOW", self._on_close)
        window.bind("<Configure>", self._on_configure)

        self.window = window
        self.canvas = canvas
        self.scrollbar = scrollbar
        self.content = content
        if should_lift:
            window.lift()
        self.entries_state = None
        self.entries_cache = []
        self._resize_pending = False
        window.update_idletasks()
        self._last_width = window.winfo_width()
        self.owner._position_floating_window(window)
        self.render([])

    def close(self) -> None:
        if self.window and self.window.winfo_exists():
            self.window.destroy()
        self.window = None
        self.canvas = None
        self.content = None
        self.canvas_window_id = None
        self.entries_state = None
        self.entries_cache = None
        self._resize_pending = False
        self._last_width = 0

    def _on_close(self) -> None:
        if self.owner.show_aux_var.get():
            self.owner.show_aux_var.set(False)
        self.close()

    def _on_configure(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        if not self.window or event.widget is not self.window:
            return
        new_width = event.width
        if new_width <= 0:
            return
        if abs(new_width - self._last_width) < 2:
            return
        self._last_width = new_width
        if self._resize_pending:
            return
        self._resize_pending = True
        self.owner.root.after_idle(self._refresh_after_resize)

    def _refresh_after_resize(self) -> None:
        if not self.window or not self.window.winfo_exists():
            self._resize_pending = False
            return
        cached = list(self.entries_cache or [])
        self.entries_state = None
        self.render(cached)
        self._resize_pending = False

    def render(self, entries: Sequence[AuxEntry]) -> None:
        if not self.window or not self.content or not self.window.winfo_exists():
            return

        normalized = tuple(entries)
        if normalized == self.entries_state:
            return
        self.entries_state = normalized
        self.entries_cache = list(entries)

        content = self.content
        canvas = self.canvas
        canvas_id = self.canvas_window_id

        for widget in content.winfo_children():
            widget.destroy()

        for col in range(12):
            content.grid_columnconfigure(col, weight=0)

        if not entries:
            message = "NOT CONNECTED" if not self.owner.client or not self.owner.client.connected else "No aux data received yet."
            self.owner._render_centered_message(content, message, bg="#1e1e1e", margin=24)
            self.owner._adjust_canvas_placeholder_bounds(canvas, canvas_id, self.window, True)
            self.owner._refresh_canvas_window_height(canvas, canvas_id, content)
            return

        available_width = self._fit_canvas_width()
        window_width = 0
        if self.window and self.window.winfo_exists():
            try:
                self.window.update_idletasks()
            except Exception:
                pass
            window_width = self.window.winfo_width()
        if window_width and window_width > 1:
            target_width = max(window_width - 48, 120)
            if target_width > available_width and canvas_id is not None:
                self.canvas.itemconfig(canvas_id, width=target_width)
                available_width = target_width

        columns = self.owner._compute_flow_columns(available_width, len(entries), 160, 12)
        if columns <= 0:
            columns = 1
        for col in range(columns):
            content.grid_columnconfigure(col, weight=1)

        for idx, entry in enumerate(entries):
            row = idx // columns
            col = idx % columns
            entry_frame = tk.Frame(content, bg="#1e1e1e", bd=1, relief=tk.FLAT)
            entry_frame.grid(row=row, column=col, sticky="nsew", padx=6, pady=4)

            header = f"{entry.suite_label} - {entry.name}"
            header_label = tk.Label(entry_frame, text=header, bg="#1e1e1e", fg="#99ccff",
                                     font=self.owner.label_font, anchor="w")
            header_label.pack(fill=tk.X, padx=4, pady=(4, 0))

            source_text = entry.source_label or "No Source"
            source_label_widget = tk.Label(entry_frame, text=source_text, bg="#1e1e1e", fg="white",
                                            font=self.owner.source_font, anchor="w", justify=tk.LEFT)
            source_label_widget.pack(fill=tk.X, padx=4, pady=(0, 4))

        self.owner._adjust_canvas_placeholder_bounds(canvas, canvas_id, self.window, False)
        self.owner._refresh_canvas_window_height(canvas, canvas_id, content)
        if self.window and self.window.winfo_exists():
            self._last_width = self.window.winfo_width()

    def _fit_canvas_width(self) -> int:
        width = self.owner._measure_canvas_width(
            self.canvas,
            self.window,
            self.content,
            self._last_width,
            200,
        )

        # Update scroll availability based on content height.
        if self.canvas and self.content:
            try:
                self.canvas.update_idletasks()
                self.content.update_idletasks()
            except Exception:
                pass
            content_height = self.content.winfo_reqheight()
            canvas_height = self.canvas.winfo_height() or content_height
            binder = getattr(self.canvas, '_woa_mousewheel_binder', None)
            if content_height <= canvas_height + 2:
                if self.scrollbar:
                    self.scrollbar.configure(command=lambda *args: None)
                    self.scrollbar.set(0, 1)
                self.canvas.configure(yscrollcommand=lambda *args: None)
                if binder:
                    binder.set_enabled(False)
            else:
                if self.scrollbar:
                    self.scrollbar.configure(command=self.canvas.yview)
                    self.canvas.configure(yscrollcommand=self.scrollbar.set)
                else:
                    self.canvas.configure(yscrollcommand=lambda *args: None)
                if binder:
                    binder.set_enabled(True)

        return width

    @staticmethod
    def from_raw(entries: Iterable[tuple[int, str, str, str, str]]) -> list[AuxEntry]:
        return [AuxEntry(*entry) for entry in entries]

