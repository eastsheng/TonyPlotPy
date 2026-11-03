"""Tk Matplotlib canvas that coalesces redraws while a pane is resized."""
from __future__ import annotations

import tkinter as tk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.backend_bases import ResizeEvent


class DeferredFigureCanvasTkAgg(FigureCanvasTkAgg):
    RESIZE_DELAY_MS = 180

    def __init__(self, figure, master=None):
        self._defer_resize_draw = False
        self._resize_after = None
        self._image_offset = (0, 0)
        super().__init__(figure, master=master)

    def resize(self, event):
        self._defer_resize_draw = True
        try:
            if hasattr(self.figure, "_tonyplot_export_size"):
                self._fit_preview(event.width, event.height)
                ResizeEvent("resize_event", self)._process()
            else:
                super().resize(event)
        finally:
            self._defer_resize_draw = False
        self.cancel_pending_resize()
        self._resize_after = self._tkcanvas.after(
            self.RESIZE_DELAY_MS, self._draw_after_resize
        )

    def _fit_preview(self, width, height):
        size = self.figure._tonyplot_export_size
        scale = min(max(1, width) / (size[0] * self.figure.dpi),
                    max(1, height) / (size[1] * self.figure.dpi))
        self.figure.set_size_inches(size[0] * scale, size[1] * scale, forward=False)

    def set_preview_size(self, size):
        self.figure._tonyplot_export_size = tuple(size)
        self._fit_preview(self._tkcanvas.winfo_width(), self._tkcanvas.winfo_height())
        self.draw_idle()

    def draw(self):
        FigureCanvasAgg.draw(self)
        width, height = self.get_width_height(physical=True)
        viewport_width = max(self._tkcanvas.winfo_width(), width)
        viewport_height = max(self._tkcanvas.winfo_height(), height)
        self._image_offset = ((viewport_width - width) / 2, (viewport_height - height) / 2)
        self._tkcanvas.delete(self._tkcanvas_image_region)
        self._tkphoto = tk.PhotoImage(master=self._tkcanvas, width=width, height=height)
        self._tkcanvas_image_region = self._tkcanvas.create_image(
            viewport_width / 2, viewport_height / 2, image=self._tkphoto)
        self.blit()

    def _event_mpl_coords(self, event):
        x, y = self._image_offset
        return (self._tkcanvas.canvasx(event.x) - x,
                self.figure.bbox.height - (self._tkcanvas.canvasy(event.y) - y))

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


class CenteredNavigationToolbar2Tk(NavigationToolbar2Tk):
    def draw_rubberband(self, event, x0, y0, x1, y1):
        dx, dy = getattr(self.canvas, "_image_offset", (0, 0))
        # Tk's toolbar assumes the rendered image starts at the canvas origin.
        # Compensate for the centered preview before its Y-axis conversion.
        super().draw_rubberband(event, x0 + dx, y0 - dy, x1 + dx, y1 - dy)
