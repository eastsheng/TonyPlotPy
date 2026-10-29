"""Tk Matplotlib canvas that coalesces redraws while a pane is resized."""
from __future__ import annotations

import tkinter as tk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


class DeferredFigureCanvasTkAgg(FigureCanvasTkAgg):
    RESIZE_DELAY_MS = 180

    def __init__(self, figure, master=None):
        self._defer_resize_draw = False
        self._resize_after = None
        super().__init__(figure, master=master)

    def resize(self, event):
        self._defer_resize_draw = True
        try:
            super().resize(event)
        finally:
            self._defer_resize_draw = False
        self.cancel_pending_resize()
        self._resize_after = self._tkcanvas.after(
            self.RESIZE_DELAY_MS, self._draw_after_resize
        )

    def draw_idle(self):
        if not self._defer_resize_draw:
            super().draw_idle()

    def _draw_after_resize(self):
        self._resize_after = None
        if self._tkcanvas.winfo_exists():
            self.draw_idle()

    def cancel_pending_resize(self):
        if self._resize_after is not None:
            self._tkcanvas.after_cancel(self._resize_after)
            self._resize_after = None
