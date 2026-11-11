"""Compact, theme-aware segmented navigation for STR and LOG views."""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont


class ViewSwitcher(tk.Canvas):
    def __init__(self, parent, command):
        super().__init__(parent, width=224, height=32, highlightthickness=0,
                         bd=0, takefocus=True, cursor="hand2")
        self.command = command
        self.selected = 0
        self.hovered = None
        self.labels = ("STR 云图", "LOG 曲线")
        self.palette = {}
        self.font_size = 10
        self.bind("<Button-1>", self._click)
        self.bind("<Motion>", self._hover)
        self.bind("<Leave>", lambda _event: self._set_hover(None))
        self.bind("<Left>", lambda _event: self._choose((self.selected - 1) % len(self.labels)))
        self.bind("<Right>", lambda _event: self._choose((self.selected + 1) % len(self.labels)))
        self.bind("<space>", lambda _event: self._choose((self.selected + 1) % len(self.labels)))
        self.bind("<Configure>", lambda _event: self.redraw())

    def configure_theme(self, palette, font_size, background):
        self.palette = palette
        self.font_size = max(9, font_size - 1)
        self.configure(bg=background, height=self.font_size * 2 + 14)
        self._resize_width()
        self.redraw()

    def set_labels(self, labels):
        self.labels = labels
        self._resize_width()
        self.redraw()

    def _resize_width(self):
        font = tkfont.Font(self, family="Segoe UI", size=self.font_size, weight="bold")
        self.configure(width=len(self.labels) * (max(font.measure(label) for label in self.labels) + 49) + 6)

    def segment_at(self, x):
        return min(len(self.labels) - 1, max(0, int(x * len(self.labels) / self.winfo_width())))

    def select(self, index):
        self.selected = index
        self.redraw()

    def _choose(self, index):
        self.command(index)
        return "break"

    def _click(self, event):
        self.focus_set()
        return self._choose(self.segment_at(event.x))

    def _hover(self, event):
        self._set_hover(self.segment_at(event.x))

    def _set_hover(self, index):
        if self.hovered != index:
            self.hovered = index
            self.redraw()

    def _rounded(self, x0, y0, x1, y1, radius, **kwargs):
        self.create_polygon(x0 + radius, y0, x1 - radius, y0, x1, y0,
                            x1, y0 + radius, x1, y1 - radius, x1, y1,
                            x1 - radius, y1, x0 + radius, y1, x0, y1,
                            x0, y1 - radius, x0, y0 + radius, x0, y0,
                            smooth=True, splinesteps=24, **kwargs)

    def redraw(self):
        if not self.palette:
            return
        self.delete("all")
        width = self.winfo_width() if self.winfo_width() > 1 else int(self.cget("width"))
        height = max(self.winfo_height(), int(self.cget("height")))
        segment = (width - 6) / len(self.labels)
        self._rounded(0, 0, width, height, 8, fill=self.palette["tab"], outline="")
        for index, label in enumerate(self.labels):
            left = 3 + index * segment
            selected = index == self.selected
            if selected or self.hovered == index:
                self._rounded(left, 3, left + segment, height - 3, 6,
                              fill="#ffffff" if selected else self.palette["tab_hover"],
                              outline=self.palette["border"] if selected else "", width=1)
            color = self.palette["accent"] if selected else "#64748b"
            center = height / 2
            x = left + 10
            if index == 0:
                for offset in (-5, 0, 5):
                    self.create_line(x, center + offset + 2, x + 5, center + offset - 2,
                                     x + 11, center + offset + 1, x + 16, center + offset - 3,
                                     smooth=True, fill=color, width=1.5)
            elif index == 1:
                self.create_polygon(x + 2, center - 8, x + 2, center + 8, x + 16, center,
                                    fill=color)
            else:
                self.create_line(x, center - 8, x, center + 8, x + 17, center + 8,
                                 fill=color, width=1.3)
                self.create_line(x + 3, center + 4, x + 7, center - 1,
                                 x + 11, center + 1, x + 16, center - 7,
                                 fill=color, width=1.8)
            self.create_text(left + 34, center, text=label, anchor="w", fill=color,
                             font=("Segoe UI", self.font_size, "bold" if selected else "normal"))
