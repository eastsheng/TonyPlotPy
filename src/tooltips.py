"""Small, delayed hover hints for Tk widgets."""
from __future__ import annotations

import tkinter as tk


class TooltipManager:
    DELAY_MS = 450

    def __init__(self, root):
        self.root = root
        self.popup = tk.Toplevel(root)
        self.popup.withdraw()
        self.popup.overrideredirect(True)
        self.popup.attributes("-topmost", True)
        self.popup.configure(bg="#cbd5e1", padx=1, pady=1)
        self.label = tk.Label(self.popup, bg="#ffffff", fg="#1e293b",
                              font=("Segoe UI", 9), justify="left",
                              anchor="w", wraplength=380, padx=10, pady=7)
        self.label.pack()
        self.pending = None
        self.active_widget = None
        self.active_text = None
        self.registered = set()

    def register(self, widget, content):
        """Content is a string or a callable receiving the pointer event."""
        if widget in self.registered:
            return
        self.registered.add(widget)
        def schedule(event):
            self._cancel_pending()
            if self.active_widget is widget:
                self.popup.withdraw()
            self.active_widget = widget
            self.pending = self.root.after(
                self.DELAY_MS, lambda: self._show(widget, content, event)
            )

        def hide(_event=None):
            self._cancel_pending()
            if self.active_widget is widget:
                self.active_widget = None
                self.active_text = None
                try:
                    self.popup.withdraw()
                except tk.TclError:
                    pass

        widget.bind("<Enter>", schedule, add="+")
        widget.bind("<Motion>", schedule, add="+")
        widget.bind("<Leave>", hide, add="+")
        widget.bind("<ButtonPress>", hide, add="+")
        def destroyed(event):
            hide(event)
            self.registered.discard(widget)

        widget.bind("<Destroy>", destroyed, add="+")

    def register_tree(self, widget):
        """Give remaining controls a useful generic hint, including dialogs."""
        if isinstance(widget, (tk.Listbox,)):
            self.register(widget, "在列表中选择条目；可使用鼠标滚轮浏览更多内容。")
        elif widget.winfo_class() in ("TEntry", "TCombobox", "TCheckbutton"):
            if widget.winfo_class() == "TCheckbutton":
                label = widget.cget("text")
            else:
                label = next((child.cget("text") for child in widget.master.winfo_children()
                              if child.winfo_class() == "TLabel" and child.cget("text")), "此参数")
            self.register(widget, f"{label}：修改后点击“画图 / 更新预览”查看结果。")
        elif widget.winfo_class() in ("TButton", "Button"):
            label = widget.cget("text")
            if label:
                self.register(widget, f"点击“{label}”执行此操作。")
        for child in widget.winfo_children():
            self.register_tree(child)

    def _cancel_pending(self):
        if self.pending is not None:
            try:
                self.root.after_cancel(self.pending)
            except tk.TclError:
                pass
            self.pending = None

    def set_theme(self, border, font_size):
        self.popup.configure(bg=border)
        self.label.configure(font=("Segoe UI", max(9, font_size - 1)))

    def _show(self, widget, content, event):
        self.pending = None
        if not widget.winfo_exists() or self.active_widget is not widget:
            return
        text = content(event) if callable(content) else content
        if not text:
            self.popup.withdraw()
            return
        self.active_text = self.root.tr(str(text)) if hasattr(self.root, "tr") else str(text)
        self.label.configure(text=self.active_text)
        self.popup.update_idletasks()
        x = event.x_root + 16
        y = event.y_root + 20
        width = self.popup.winfo_reqwidth()
        height = self.popup.winfo_reqheight()
        x = min(x, self.root.winfo_screenwidth() - width - 8)
        y = min(y, self.root.winfo_screenheight() - height - 8)
        self.popup.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.popup.deiconify()
