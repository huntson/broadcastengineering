"""Helper mixins for Visual On-Air floating windows and canvas scrolling."""

from __future__ import annotations

import tkinter as tk
from typing import Optional


class CanvasMousewheelBinder:
    """Attach cross-platform mousewheel bindings to a Tk canvas."""

    def __init__(self, owner: "FloatingWindowMixin", canvas: tk.Canvas, extra_widgets: Optional[list[tk.Widget]] = None) -> None:
        self._owner = owner
        self._canvas = canvas
        self._extra_widgets = list(extra_widgets) if extra_widgets else []
        self._enabled = True

    def bind_all(self) -> None:
        """Register mousewheel handlers for vertical and horizontal scrolling."""
        canvas = self._canvas
        handlers = {
            '<MouseWheel>': self._on_mousewheel,
            '<Shift-MouseWheel>': self._on_shift_mousewheel,
            '<Button-4>': self._on_button4,
            '<Button-5>': self._on_button5,
            '<Shift-Button-4>': self._on_shift_button4,
            '<Shift-Button-5>': self._on_shift_button5,
        }
        targets = [canvas] + self._extra_widgets
        for sequence, handler in handlers.items():
            for widget in targets:
                widget.bind(sequence, handler, add='+')
        for widget in targets:
            widget.bind('<Enter>', self._focus_canvas, add='+')
        canvas.bind_all('<MouseWheel>', self._dispatch_mousewheel, add='+')
        canvas.bind_all('<Shift-MouseWheel>', self._dispatch_shift_mousewheel, add='+')
        # Keep a reference so the binder is not garbage-collected.
        setattr(canvas, '_woa_mousewheel_binder', self)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)


    # -- internal helpers -------------------------------------------------

    def _mark_scroll(self) -> None:
        self._owner._mark_canvas_scrolling(self._canvas)

    def _owns_widget(self, widget: Optional[tk.Widget]) -> bool:
        while widget is not None:
            if widget == self._canvas:
                return True
            widget = getattr(widget, 'master', None)
        return False

    def _delta_to_steps(self, delta: int) -> int:
        if delta == 0:
            return 0
        steps = int(-delta / 120)
        if steps == 0:
            steps = -1 if delta > 0 else 1
        return steps

    def _focus_canvas(self, _event: Optional[tk.Event] = None) -> None:  # type: ignore[type-arg]
        if self._canvas.winfo_exists():
            try:
                self._canvas.focus_set()
            except Exception:
                pass

    def _dispatch_mousewheel(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        if not self._owns_widget(getattr(event, 'widget', None)):
            return
        self._on_mousewheel(event)

    def _dispatch_shift_mousewheel(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        if not self._owns_widget(getattr(event, 'widget', None)):
            return
        self._on_shift_mousewheel(event)

    def _scroll_y(self, steps: int) -> None:
        if steps and self._canvas.winfo_exists():
            self._canvas.yview_scroll(steps, 'units')

    def _scroll_x(self, steps: int) -> None:
        if steps and self._canvas.winfo_exists():
            self._canvas.xview_scroll(steps, 'units')

    # -- event callbacks --------------------------------------------------

    def _on_mousewheel(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        if not self._enabled:
            return "break"
        steps = self._delta_to_steps(getattr(event, 'delta', 0))
        if not steps:
            return
        self._mark_scroll()
        self._scroll_y(steps)

    def _on_shift_mousewheel(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        if not self._enabled:
            return "break"
        steps = self._delta_to_steps(getattr(event, 'delta', 0))
        if not steps:
            return
        self._mark_scroll()
        self._scroll_x(steps)

    def _on_button4(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        if not self._enabled:
            return "break"
        self._mark_scroll()
        self._scroll_y(-1)

    def _on_button5(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        if not self._enabled:
            return "break"
        self._mark_scroll()
        self._scroll_y(1)

    def _on_shift_button4(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        if not self._enabled:
            return "break"
        self._mark_scroll()
        self._scroll_x(-1)

    def _on_shift_button5(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        if not self._enabled:
            return "break"
        self._mark_scroll()
        self._scroll_x(1)


class FloatingWindowMixin:
    """Reusable helpers shared across Visual On-Air floating windows."""

    _canvas_scroll_state: Optional[dict] = None

    def _cancel_logical_render_job(self) -> None:
        if self._logical_render_job is not None:
            try:
                self.root.after_cancel(self._logical_render_job)
            except Exception:
                pass
            self._logical_render_job = None

    def _cancel_engineering_render_job(self) -> None:
        if self._engineering_render_job is not None:
            try:
                self.root.after_cancel(self._engineering_render_job)
            except Exception:
                pass
            self._engineering_render_job = None

    def _render_logical_entries_chunk(self, entries, columns, start_index, content, chunk_size):
        if not self.logical_window or not content or not content.winfo_exists():
            self._logical_render_job = None
            return
        end_index = min(len(entries), start_index + chunk_size)
        for idx in range(start_index, end_index):
            entry = entries[idx]
            row = idx // columns
            col = idx % columns
            card = tk.Frame(content, bg='#1e1e1e', bd=1, relief=tk.FLAT)
            columnspan = 1
            if columns > 1 and len(entries) % columns == 1 and idx == len(entries) - 1:
                columnspan = columns
            card.grid(row=row, column=col, columnspan=columnspan, sticky='nsew', padx=6, pady=4)
            header_text = f"ID {entry['id']}"
            if entry.get('type'):
                header_text = f"{header_text} ({entry['type']})"
            tk.Label(
                card,
                text=header_text,
                bg='#1e1e1e',
                fg='#ffcc66',
                font=self.label_font,
                anchor='w',
            ).pack(fill=tk.X, padx=6, pady=(6, 0))
            tk.Label(
                card,
                text=entry.get('name') or 'No Name',
                bg='#1e1e1e',
                fg='white',
                font=self.source_font,
                anchor='w',
                justify=tk.LEFT,
                wraplength=300,
            ).pack(fill=tk.X, padx=6, pady=(0, 4))
            for line in entry.get('lines', []):
                tk.Label(
                    card,
                    text=line,
                    bg='#1e1e1e',
                    fg='#a0d8ff',
                    font=self.label_font,
                    anchor='w',
                    justify=tk.LEFT,
                    wraplength=300,
                ).pack(fill=tk.X, padx=6, pady=(0, 2))
        if end_index < len(entries):
            self._logical_render_job = self.root.after(
                1,
                lambda: self._render_logical_entries_chunk(
                    entries,
                    columns,
                    end_index,
                    content,
                    chunk_size,
                ),
            )
        else:
            self._logical_render_job = None
            self._refresh_canvas_window_height(self.logical_canvas, self._logical_canvas_window_id, content)

    def _render_engineering_entries_chunk(self, entries, columns, start_index, content, chunk_size):
        if not self.engineering_window or not content or not content.winfo_exists():
            self._engineering_render_job = None
            return
        end_index = min(len(entries), start_index + chunk_size)
        for idx in range(start_index, end_index):
            entry = entries[idx]
            row = idx // columns
            col = idx % columns
            card = tk.Frame(content, bg='#1e1e1e', bd=1, relief=tk.FLAT)
            columnspan = 1
            if columns > 1 and len(entries) % columns == 1 and idx == len(entries) - 1:
                columnspan = columns
            card.grid(row=row, column=col, columnspan=columnspan, sticky='nsew', padx=6, pady=4)
            tk.Label(
                card,
                text=f"ENG {entry['id']}",
                bg='#1e1e1e',
                fg='#99ccff',
                font=self.label_font,
                anchor='w',
            ).pack(fill=tk.X, padx=6, pady=(6, 0))
            tk.Label(
                card,
                text=entry.get('name') or 'No Name',
                bg='#1e1e1e',
                fg='white',
                font=self.source_font,
                anchor='w',
                justify=tk.LEFT,
                wraplength=300,
            ).pack(fill=tk.X, padx=6, pady=(0, 4))
            if entry.get('type'):
                tk.Label(
                    card,
                    text=f"Type: {entry['type']}",
                    bg='#1e1e1e',
                    fg='#cccccc',
                    font=self.label_font,
                    anchor='w',
                ).pack(fill=tk.X, padx=6, pady=(0, 2))
            if entry.get('bnc'):
                tk.Label(
                    card,
                    text=f"BNC: {entry['bnc']}",
                    bg='#1e1e1e',
                    fg='#cccccc',
                    font=self.label_font,
                    anchor='w',
                ).pack(fill=tk.X, padx=6, pady=(0, 2))
        if end_index < len(entries):
            self._engineering_render_job = self.root.after(
                1,
                lambda: self._render_engineering_entries_chunk(
                    entries,
                    columns,
                    end_index,
                    content,
                    chunk_size,
                ),
            )
        else:
            self._engineering_render_job = None
            self._refresh_canvas_window_height(
                self.engineering_canvas,
                self._engineering_canvas_window_id,
                content,
            )

    def _refresh_canvas_window_height(self, canvas, window_id, content) -> None:
        if not canvas or window_id is None or not content:
            return
        if not canvas.winfo_exists() or not content.winfo_exists():
            return
        try:
            content.update_idletasks()
            canvas.update_idletasks()
            viewport_width = canvas.winfo_width()
            req_width = max(1, content.winfo_reqwidth())
            req_height = max(1, content.winfo_reqheight())
            if viewport_width <= 1:
                viewport_width = req_width
            canvas.itemconfigure(window_id, width=viewport_width)
            bbox = canvas.bbox(window_id)
            if bbox:
                x0, y0, x1, y1 = bbox
                x1 = max(x1, viewport_width)
                y1 = max(y1, req_height)
                canvas.configure(scrollregion=(x0, y0, x1, y1))
            else:
                canvas.configure(scrollregion=(0, 0, viewport_width, req_height))
        except Exception:
            pass

    def _enable_canvas_mousewheel(self, canvas, *widgets) -> None:
        if not canvas:
            return
        extra_widgets = [widget for widget in widgets if widget]
        binder = CanvasMousewheelBinder(self, canvas, extra_widgets)
        binder.bind_all()

    def _mark_canvas_scrolling(self, canvas) -> None:
        if not canvas or not canvas.winfo_exists():
            return
        if not hasattr(self, '_canvas_scroll_state') or self._canvas_scroll_state is None:
            self._canvas_scroll_state = {}
        state = self._canvas_scroll_state.setdefault(canvas, {'active': False, 'after_id': None})
        state['active'] = True
        after_id = state.get('after_id')
        if after_id:
            try:
                canvas.after_cancel(after_id)
            except Exception:
                pass

        def _clear():
            state['after_id'] = None
            self._clear_canvas_scrolling(canvas)

        try:
            state['after_id'] = canvas.after(180, _clear)
        except Exception:
            state['after_id'] = None

    def _clear_canvas_scrolling(self, canvas) -> None:
        if not hasattr(self, '_canvas_scroll_state') or self._canvas_scroll_state is None:
            return
        if canvas in self._canvas_scroll_state:
            state = self._canvas_scroll_state[canvas]
            after_id = state.get('after_id')
            if after_id:
                try:
                    canvas.after_cancel(after_id)
                except Exception:
                    pass
            state['active'] = False
            state['after_id'] = None

    def _is_canvas_scrolling(self, canvas) -> bool:
        if not hasattr(self, '_canvas_scroll_state') or self._canvas_scroll_state is None:
            return False
        state = self._canvas_scroll_state.get(canvas)
        if not state:
            return False
        return bool(state.get('active'))

    def _update_canvas_scroll_region(self, canvas) -> None:
        if not canvas:
            return
        try:
            canvas.update_idletasks()
        except Exception:
            pass
        bbox = canvas.bbox('all')
        if bbox:
            canvas.configure(scrollregion=bbox)


__all__ = [
    'CanvasMousewheelBinder',
    'FloatingWindowMixin',
]
