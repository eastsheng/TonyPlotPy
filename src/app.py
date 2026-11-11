"""Interactive Atlas ASCII .str cloud-map viewer."""
from __future__ import annotations

import math
import gc
import copy
import queue
import threading
import re
from pathlib import Path
import tkinter as tk
from tkinter import font as tkfont
from tkinter import filedialog, messagebox, ttk

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.backends.backend_tkagg import NavigationToolbar2Tk

from .plotting import atlas_engine as engine
from .plotting import renderer
from .plotting.axis_breaks import parse_breaks
from .plotting import log_reader, log_renderer
from .plotting.figure_edits import apply_edits
from .plotting.export_diagnostics import quiet_export
from .figure_editor import FigureEditor
from .deferred_canvas import DeferredFigureCanvasTkAgg, CenteredNavigationToolbar2Tk
from .ui_settings import THEMES, WINDOW_SIZES, load_settings, save_settings
from .tooltips import TooltipManager
from .control_hints import hint_for
from .version import APP_VERSION
from .i18n import translate, LocalizedStringVar
from .view_switcher import ViewSwitcher
from .plot_config import save_config, load_config
from .str_animation import render_frames, build_animation_panel, save_animation


QUANTITIES = ("electron", "hole", "total", "temperature")
DEFAULT_FIELD_CODES = {engine.FIELD_CODES[q] for q in QUANTITIES}
FIELD_NAME_BY_CODE = engine.FIELD_UI_LABELS_BY_CODE
BG = "#f4f7fb"
SURFACE = "#ffffff"
INK = "#1e293b"
MUTED = "#64748b"
BORDER = "#dbe4ef"
ACCENT = "#2563eb"


def optional_float(value: str) -> float | None:
    return None if value.strip().lower() in ("", "auto", "none") else float(value)


class TonyPlotApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.preferences = load_settings()
        self.language = self.preferences["language"]
        self._set_palette(self.preferences["theme"])
        self.title(f"TonyPlotPy {APP_VERSION} · Atlas STR 云图")
        self.geometry(WINDOW_SIZES[self.preferences["window_size"]])
        self.minsize(820, 520)
        self.configure(bg=BG)
        self.header_icon = None
        self.header_icon_labels = []
        self.header_title_labels = []
        self._apply_app_icon()
        self._setup_style()
        self.files: list[Path] = []
        self.cache: dict[tuple[Path, int], engine.Structure] = {}
        self.figure = None
        self.canvas_widget = None
        self.log_figure = None
        self.log_canvas_widget = None
        self.log_files: list[Path] = []
        self.log_cache = {}
        self.log_field_codes: list[int] = []
        self.log_field_labels: dict[int, str] = {}
        self.log_right_codes: list[int] = []
        self.log_rendered = []
        self.log_single_edits: dict[int, dict] = {}
        self.figure_edits: dict[str, dict] = {"str": {}, "log": {}}
        self.editors = {}
        self.undo_history = {"str": [], "log": []}
        self.undo_buttons = {}
        self.busy = False
        self.gc_was_enabled = False
        self.render_results = queue.Queue()
        self.file_load_ids = {"str": 0, "log": 0}
        self.file_loading = set()
        self.str_headers = {}
        self.log_headers = {}
        self._pending_set_curve = None
        self.vars: dict[str, tk.Variable] = {}
        self.localized_combos = []
        self.quantity_vars = {
            q: tk.BooleanVar(value=q in ("total", "temperature"))
            for q in QUANTITIES
        }
        self.extra_field_codes: list[int | str] = []
        self.field_settings: dict[str, dict[str, str]] = {}
        self.panel_labels = {}
        self.control_hints = []
        self._build_ui()
        self._refresh_language()
        self._refresh_widget_appearance()
        self.tooltips = TooltipManager(self)
        self.tooltips.set_theme(BORDER, self.preferences["font_size"])
        self._register_tooltips()
        self.bind("<Control-z>", self._undo_shortcut)

    def checkpoint_edit(self, kind):
        snapshot = {"visual": copy.deepcopy(self.figure_edits[kind])}
        if kind == "str":
            snapshot.update(panel_labels=copy.deepcopy(self.panel_labels),
                            field_settings=copy.deepcopy(self.field_settings))
        else:
            snapshot["single"] = copy.deepcopy(self.log_single_edits)
        history = self.undo_history[kind]
        history.append(snapshot)
        del history[:-50]
        button = self.undo_buttons.get(kind)
        if button is not None and button.winfo_exists():
            button.configure(state="normal")

    def undo_edit(self, kind):
        if self.busy or not self.undo_history[kind]:
            return
        snapshot = self.undo_history[kind].pop()
        self.figure_edits[kind] = snapshot["visual"]
        if kind == "str":
            self.panel_labels = snapshot["panel_labels"]
            self.field_settings = snapshot["field_settings"]
        else:
            self.log_single_edits = snapshot["single"]
        button = self.undo_buttons.get(kind)
        if button is not None and button.winfo_exists():
            button.configure(state="normal" if self.undo_history[kind] else "disabled")
        self._start_render(kind)

    def _undo_shortcut(self, _event):
        focus = self.focus_get()
        if self.grab_current() is not None or (focus is not None and focus.winfo_class() in
                ("Entry", "TEntry", "Text", "TCombobox", "Spinbox", "TSpinbox")):
            return
        self.undo_edit(self._active_kind())
        return "break"

    def tr(self, value):
        return translate(str(value), self.language)

    def _localize_tree(self, widget):
        """Update captions in place without replacing controls or current selections."""
        keys = widget.keys()
        if "text" in keys and ("textvariable" not in keys or not widget.cget("textvariable")):
            current = widget.cget("text")
            previous = getattr(widget, "_i18n_last", None)
            if not hasattr(widget, "_i18n_source") or (previous is not None and current != previous):
                widget._i18n_source = current
            translated = self.tr(widget._i18n_source)
            if translated != current:
                widget.configure(text=translated)
            widget._i18n_last = translated
        for child in widget.winfo_children():
            self._localize_tree(child)

    def _refresh_language(self):
        self.title(f"TonyPlotPy {APP_VERSION} · " + self.tr("Atlas STR 云图"))
        self.notebook.tab(self.str_page, text=self.tr("  STR 云图  "))
        self.notebook.tab(self.log_page, text=self.tr("  LOG 曲线  "))
        self.notebook.tab(self.animation_page, text=self.tr("动态云图"))
        self.view_switcher.set_labels((self.tr("STR 云图"), self.tr("动态云图"), self.tr("LOG 曲线")))
        self.edit_menu.entryconfigure(0, label=self.tr("设置…"))
        for index, label in enumerate(("选择目录", "加载目录", "添加文件")):
            self.file_menu.entryconfigure(index, label=self.tr(label))
        self.file_menu.entryconfigure(4, label=self.tr("保存为图片…"))
        for combo, display, internal, options in self.localized_combos:
            combo.configure(values=[self.tr(item) for item in options])
            display.set(self.tr(internal.get()))
        self._localize_tree(self)
        for variable_name in ("status", "log_status"):
            variable = getattr(self, variable_name, None)
            if isinstance(variable, LocalizedStringVar):
                variable.refresh()
        if hasattr(self, "field_list") and self.extra_field_codes:
            self.refresh_fields()

    def _set_palette(self, theme_name):
        global BG, BORDER, ACCENT
        self.palette = THEMES[theme_name]
        BG = self.palette["bg"]
        BORDER = self.palette["border"]
        ACCENT = self.palette["accent"]

    def _apply_app_icon(self):
        images = Path(__file__).resolve().parent.parent / "imgs"
        icon_name = self.palette["icon"]
        icon_path = images / f"tonyplotpy_{icon_name}.ico"
        small_path = images / f"tonyplotpy_{icon_name}_small.png"
        if icon_path.is_file():
            self.iconbitmap(default=str(icon_path))
        if small_path.is_file():
            self.header_icon = tk.PhotoImage(file=str(small_path))
            for label in self.header_icon_labels:
                label.configure(image=self.header_icon)

    def _setup_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.layout("View.TNotebook.Tab", [])
        style.configure("View.TNotebook", borderwidth=0, background=BG)
        font_size = self.preferences["font_size"]
        style.configure("TFrame", background=SURFACE)
        style.configure("Surface.TFrame", background=BG)
        style.layout("TopMenu.TMenubutton", [
            ("Menubutton.border", {"sticky": "nsew", "children": [
                ("Menubutton.padding", {"sticky": "nsew", "children": [
                    ("Menubutton.label", {"sticky": "nsew"}),
                ]}),
            ]}),
        ])
        style.configure("TopMenu.TMenubutton", background=BG, foreground=INK,
                        borderwidth=0, relief="flat", padding=(7, 4),
                        font=("Segoe UI", max(9, font_size - 1)))
        style.map("TopMenu.TMenubutton",
                  background=[("pressed", self.palette["tab_hover"]), ("active", self.palette["soft"])],
                  foreground=[("pressed", ACCENT), ("active", ACCENT)])
        style.configure("TLabel", background=SURFACE, foreground=INK, font=("Segoe UI", font_size))
        style.configure("Menu.TLabel", font=("Segoe UI", max(9, font_size - 1)))
        style.configure("Hint.TLabel", foreground=MUTED, font=("Segoe UI", max(8, font_size - 2)))
        style.configure("Footer.TLabel", background=BG, foreground=MUTED,
                        font=("Segoe UI", max(8, font_size - 2)))
        style.configure("TCheckbutton", background=SURFACE, foreground=INK, font=("Segoe UI", max(9, font_size - 1)))
        style.map("TCheckbutton", background=[("active", SURFACE)])
        style.configure("TEntry", fieldbackground=SURFACE, foreground=INK,
                        bordercolor=BORDER, lightcolor=BORDER, padding=5)
        style.configure("TCombobox", fieldbackground=SURFACE, foreground=INK,
                        background=SURFACE, bordercolor=BORDER, padding=5)
        style.configure("TButton", background=SURFACE, foreground=INK, bordercolor=BORDER,
                        padding=(9, 6), font=("Segoe UI", max(8, font_size - 1)))
        style.configure("Menu.TButton", padding=(6, 4), font=("Segoe UI", max(8, font_size - 2)))
        style.map("TButton", background=[("active", self.palette["soft"]), ("disabled", BG)])
        style.configure("Accent.TButton", background=ACCENT, foreground=SURFACE,
                        bordercolor=ACCENT, padding=(14, 8), font=("Segoe UI", font_size, "bold"))
        style.map("Accent.TButton", background=[("active", self.palette["hover"]), ("disabled", "#94a3b8")],
                  foreground=[("disabled", SURFACE)])
        style.configure("TScrollbar", background=self.palette["scroll"], troughcolor=BG, bordercolor=BG)
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=self.palette["tab"], foreground=MUTED,
                        padding=(20, 9), borderwidth=0, font=("Segoe UI", font_size))
        style.map("TNotebook.Tab", background=[("selected", SURFACE), ("active", self.palette["tab_hover"])],
                  foreground=[("selected", ACCENT)])

    def _refresh_widget_appearance(self):
        font_size = self.preferences["font_size"]

        def update(widget):
            if isinstance(widget, tk.Frame):
                widget.configure(bg=SURFACE)
                if "highlightbackground" in widget.keys():
                    widget.configure(highlightbackground=BORDER)
            elif isinstance(widget, tk.Label):
                widget.configure(bg=SURFACE, fg=INK,
                                 font=("Segoe UI", font_size + 1, "bold"))
            elif isinstance(widget, tk.Listbox):
                widget.configure(bg=SURFACE, fg=INK, selectbackground=ACCENT,
                                 selectforeground=SURFACE, font=("Segoe UI", max(9, font_size - 1)))
                if "highlightbackground" in widget.keys():
                    widget.configure(highlightbackground=BORDER)
            elif isinstance(widget, tk.Button):
                widget.configure(bg=SURFACE, activebackground=self.palette["soft"])
            elif isinstance(widget, (ttk.Entry, ttk.Combobox)):
                widget.configure(font=("Segoe UI", max(9, font_size - 1)))
            for child in widget.winfo_children():
                update(child)

        update(self)
        def menu_typography(widget):
            if isinstance(widget, ttk.Button):
                widget.configure(style="Menu.TButton")
            elif isinstance(widget, ttk.Label):
                muted = str(widget.cget("foreground")) == MUTED
                widget.configure(style="Hint.TLabel" if muted else "Menu.TLabel")
            if isinstance(widget, (ttk.Label, tk.Label)) and not getattr(widget, "_parameter_caption", False):
                if not getattr(widget, "_responsive_wrap", False):
                    def wrap(_event=None, label=widget):
                        available = label.master.winfo_width()
                        if available > 40:
                            label.configure(wraplength=max(40, available - 8))
                    widget.master.bind("<Configure>", wrap, add="+")
                    widget._responsive_wrap = True
                    widget.after_idle(wrap)
            elif isinstance(widget, ttk.Checkbutton) and not getattr(widget, "_responsive_wrap", False):
                def wrap_check(_event=None, checkbox=widget):
                    available = checkbox.master.winfo_width() - 30
                    if available < 50:
                        return
                    source = getattr(checkbox, "_i18n_source", checkbox.cget("text"))
                    checkbox._i18n_source = source
                    font = tkfont.Font(self, family="Segoe UI", size=max(9, self.preferences["font_size"] - 1))
                    lines, line = [], ""
                    for character in self.tr(source):
                        if character == "\n" or (line and font.measure(line + character) > available):
                            lines.append(line)
                            line = ""
                        if character != "\n":
                            line += character
                    lines.append(line)
                    text = "\n".join(lines)
                    if checkbox.cget("text") != text:
                        checkbox.configure(text=text)
                    checkbox._i18n_last = text
                widget.master.bind("<Configure>", wrap_check, add="+")
                widget.bind("<Configure>", wrap_check, add="+")
                widget._responsive_wrap = True
                widget.after_idle(wrap_check)
            for child in widget.winfo_children():
                menu_typography(child)
        menu_typography(self.left_outer)
        menu_typography(self.log_left_outer)
        self.configure(bg=BG)
        self.view_switcher.configure_theme(self.palette, font_size, BG)
        self.left_scroll.configure(bg=BG)
        self.log_left_scroll.configure(bg=BG)
        for label in self.header_title_labels:
            label.configure(font=("Segoe UI", font_size + 6, "bold"))

    def open_settings(self):
        dialog = tk.Toplevel(self)
        dialog.title(self.tr("软件设置"))
        dialog.transient(self)
        dialog.resizable(False, False)
        dialog.configure(bg=BG)
        dialog.grab_set()
        body = ttk.Frame(dialog, padding=18)
        body.pack(fill="both", expand=True)

        theme = tk.StringVar(value=self.tr(self.preferences["theme"]))
        font_size = tk.StringVar(value=str(self.preferences["font_size"]))
        dpi = tk.StringVar(value=str(self.preferences["dpi"]))
        window_size = tk.StringVar(value=self.tr(self.preferences["window_size"]))
        language = tk.StringVar(value=self.language)
        rows = (
            ("语言", language, ("中文", "English")),
            ("颜色主题", theme, tuple(self.tr(item) for item in THEMES)),
            ("界面字号", font_size, tuple(str(value) for value in range(9, 17))),
            ("默认导出 DPI", dpi, None),
            ("窗口尺寸", window_size, tuple(self.tr(item) for item in WINDOW_SIZES)),
        )
        for label, variable, choices in rows:
            row = ttk.Frame(body)
            row.pack(fill="x", pady=6)
            ttk.Label(row, text=self.tr(label), width=15).pack(side="left")
            if choices:
                control = ttk.Combobox(row, textvariable=variable, values=choices,
                                       state="readonly", width=18)
            else:
                control = ttk.Entry(row, textvariable=variable, width=20)
            control.pack(side="left", fill="x", expand=True)
        ttk.Label(body, text=self.tr("设置会在下次启动时自动恢复"), foreground=MUTED).pack(anchor="w", pady=(8, 2))
        ttk.Separator(body, orient="horizontal").pack(fill="x", pady=(12, 6))
        ttk.Label(body, text=self.tr(f"TonyPlotPy 版本 {APP_VERSION}"), foreground=MUTED).pack(anchor="w")

        def apply():
            try:
                size = int(font_size.get())
                export_dpi = int(dpi.get())
                theme_key = next((key for key in THEMES if self.tr(key) == theme.get()), None)
                window_key = next((key for key in WINDOW_SIZES if self.tr(key) == window_size.get()), None)
                if theme_key is None or window_key is None:
                    raise ValueError("请选择有效的主题和窗口尺寸")
                if not 9 <= size <= 16:
                    raise ValueError("界面字号需在 9–16 之间")
                if not 72 <= export_dpi <= 1200:
                    raise ValueError("默认导出 DPI 需在 72–1200 之间")
                values = {"theme": theme_key, "font_size": size,
                          "dpi": export_dpi, "window_size": window_key,
                          "language": language.get()}
                save_settings(values)
            except (ValueError, OSError) as exc:
                messagebox.showerror(self.tr("设置无效"), self.tr(str(exc)), parent=dialog)
                return
            old_window_size = self.preferences["window_size"]
            self.preferences = values
            self.language = values["language"]
            self._set_palette(values["theme"])
            self._setup_style()
            self._refresh_widget_appearance()
            self.tooltips.set_theme(BORDER, values["font_size"])
            self._apply_app_icon()
            self._refresh_language()
            self.vars["dpi"].set(export_dpi)
            self.vars["log_dpi"].set(export_dpi)
            if values["window_size"] != old_window_size:
                self.geometry(WINDOW_SIZES[values["window_size"]])
            dialog.destroy()
            self._notify_saved("软件设置已保存")

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(14, 0))
        ttk.Button(buttons, text=self.tr("取消"), command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text=self.tr("应用"), command=apply, style="Accent.TButton").pack(side="right", padx=8)
        dialog.bind("<Return>", lambda _event: apply())
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        if hasattr(self, "tooltips"):
            self.tooltips.register_tree(dialog)
        dialog.focus_set()

    def var(self, key, value):
        v = tk.BooleanVar(value=value) if isinstance(value, bool) else tk.StringVar(value=str(value))
        self.vars[key] = v
        return v

    def _entry(self, parent, label, key, default, width=11):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        caption = ttk.Label(row, text=label, style="Menu.TLabel")
        entry = ttk.Entry(row, textvariable=self.var(key, default), width=width)
        self._layout_parameter_row(row, caption, entry)
        self.control_hints.extend(((caption, hint_for(key, label)), (entry, hint_for(key, label))))

    def _combo(self, parent, label, key, default, options):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        caption = ttk.Label(row, text=label, style="Menu.TLabel")
        internal = self.var(key, default)
        display = tk.StringVar(value=self.tr(default))
        combo = ttk.Combobox(row, textvariable=display,
                             values=[self.tr(item) for item in options], state="readonly", width=16)
        def chosen(_event=None):
            value = display.get()
            internal.set(next((item for item in options if self.tr(item) == value), value))
        def synced(*_args):
            display.set(self.tr(internal.get()))
        combo.bind("<<ComboboxSelected>>", chosen, add="+")
        internal.trace_add("write", synced)
        self.localized_combos.append((combo, display, internal, tuple(options)))
        self._layout_parameter_row(row, caption, combo)
        self.control_hints.extend(((caption, hint_for(key, label)), (combo, hint_for(key, label))))

    @staticmethod
    def _layout_parameter_row(row, caption, control):
        """Use full-width inputs in narrow menus and two columns when widened."""
        caption._parameter_caption = True
        def arrange(event=None):
            width = event.width if event is not None else row.winfo_width()
            if getattr(row, "_layout_width", None) == width:
                return
            row._layout_width = width
            caption.grid_forget()
            control.grid_forget()
            if width >= 380:
                row.columnconfigure(0, weight=1, uniform="parameter")
                row.columnconfigure(1, weight=1, uniform="parameter")
                caption.configure(wraplength=max(60, width // 2 - 12))
                caption.grid(row=0, column=0, sticky="w", padx=(0, 10))
                control.grid(row=0, column=1, sticky="ew")
            else:
                row.columnconfigure(0, weight=1, uniform="")
                row.columnconfigure(1, weight=0, uniform="")
                caption.configure(wraplength=max(80, width - 8))
                caption.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 2))
                control.grid(row=1, column=0, columnspan=2, sticky="ew")
        row.bind("<Configure>", arrange)
        arrange()

    def _check(self, parent, label, key, default):
        checkbox = ttk.Checkbutton(parent, text=label, variable=self.var(key, default))
        checkbox.pack(anchor="w", pady=2)
        self.control_hints.append((checkbox, hint_for(key, label)))

    @staticmethod
    def _horizontal_list_scroll(parent, listing):
        scrollbar = ttk.Scrollbar(parent, orient="horizontal", command=listing.xview)
        scrollbar.pack(fill="x", pady=(0, 2))
        listing.configure(xscrollcommand=scrollbar.set)

    @staticmethod
    def _wrap_buttons(row, buttons):
        """Wrap action buttons instead of letting packed siblings be clipped."""
        def arrange(_event=None):
            width = row.winfo_width()
            minimum = max(button.winfo_reqwidth() for button in buttons) + 4
            columns = max(1, min(len(buttons), width // minimum))
            if getattr(row, "_button_columns", None) == columns:
                return
            row._button_columns = columns
            for index in range(len(buttons)):
                row.columnconfigure(index, weight=1 if index < columns else 0,
                                    uniform="actions" if index < columns else "")
            for index, button in enumerate(buttons):
                button.grid(row=index // columns, column=index % columns,
                            sticky="ew", padx=2, pady=2)
        row.bind("<Configure>", arrange, add="+")
        for button in buttons:
            button.bind("<Configure>", arrange, add="+")
        row.after_idle(arrange)

    def _section(self, parent, title, hint=None):
        card = tk.Frame(parent, bg=SURFACE, highlightbackground=BORDER,
                        highlightthickness=1, bd=0)
        card.pack(fill="x", padx=10, pady=7)
        heading = tk.Label(card, text=title, bg=SURFACE, fg=INK,
                           font=("Segoe UI", self.preferences["font_size"], "bold"), anchor="w")
        heading.pack(fill="x", padx=12, pady=(12, 6))
        if hint:
            self.control_hints.append((heading, hint))
        frame = ttk.Frame(card, padding=(12, 0, 12, 12))
        frame.pack(fill="x")
        return frame

    def _build_ui(self):
        menu_bar = ttk.Frame(self, padding=(4, 2), style="Surface.TFrame")
        menu_bar.pack(fill="x")
        navigation = ttk.Frame(self, height=44, style="Surface.TFrame")
        self.navigation = navigation
        navigation.pack(fill="x")
        navigation.pack_propagate(False)
        file_button = ttk.Menubutton(menu_bar, text="文件", style="TopMenu.TMenubutton")
        file_button.pack(side="left")
        edit_button = ttk.Menubutton(menu_bar, text="编辑", style="TopMenu.TMenubutton")
        edit_button.pack(side="left")
        self.edit_menu = tk.Menu(edit_button, tearoff=False)
        self.edit_menu.add_command(label="设置…", command=self.open_settings)
        edit_button.configure(menu=self.edit_menu)
        self.file_menu = tk.Menu(file_button, tearoff=False)
        for label, action in (("选择目录", "choose"), ("加载目录", "load"), ("添加文件", "add")):
            self.file_menu.add_command(label=label, command=lambda action=action: self._file_menu_action(action))
        self.file_menu.add_separator()
        self.file_menu.add_command(label="保存为图片…", command=self.export)
        file_button.configure(menu=self.file_menu)
        self.view_switcher = ViewSwitcher(navigation, lambda index: self.notebook.select(index))
        self.view_switcher.place(x=10, y=6)
        self.notebook = ttk.Notebook(self, style="View.TNotebook")
        self.notebook.bind("<<NotebookTabChanged>>",
                           lambda _event: self.view_switcher.select(self.notebook.index(self.notebook.select())))
        self.notebook.bind("<<NotebookTabChanged>>", lambda _event: self.after_idle(self._align_view_switcher), add="+")
        footer = ttk.Frame(self, style="Surface.TFrame", padding=(8, 2, 12, 3))
        footer.pack(side="bottom", fill="x")
        self.version_label = ttk.Label(footer, text=f"v{APP_VERSION}", style="Footer.TLabel")
        self.version_label.pack(side="right")
        self.notebook.pack(fill="both", expand=True)
        str_page = ttk.Frame(self.notebook)
        self.animation_page = ttk.Frame(self.notebook)
        log_page = ttk.Frame(self.notebook)
        self.str_page, self.log_page = str_page, log_page
        self.notebook.add(str_page, text="  STR 云图  ")
        self.notebook.add(self.animation_page, text="动态云图")
        self.notebook.add(log_page, text="  LOG 曲线  ")
        paned = ttk.PanedWindow(self.notebook, orient="horizontal")
        self.str_paned = paned
        paned.place(in_=str_page, relwidth=1, relheight=1)
        left_outer = ttk.Frame(paned, width=285, style="Surface.TFrame")
        right = ttk.Frame(paned)
        paned.add(left_outer, weight=0)
        paned.add(right, weight=1)
        actions = ttk.Frame(right, padding=(12, 10))
        actions.pack(fill="x")
        self.str_actions = actions
        if self.header_icon:
            icon_label = ttk.Label(actions, image=self.header_icon)
            icon_label.pack(side="left", padx=(0, 9))
            self.header_icon_labels.append(icon_label)
        title_label = ttk.Label(actions, text="TonyPlotPy", font=("Segoe UI", self.preferences["font_size"] + 6, "bold"), foreground=INK)
        title_label.pack(side="left", padx=(0, 18))
        self.header_title_labels.append(title_label)
        self.draw_button = ttk.Button(actions, text="画图 / 更新预览", command=self.preview, style="Accent.TButton")
        self.draw_button.pack(side="left", padx=(0, 8))
        scroll = tk.Canvas(left_outer, highlightthickness=0, width=285, bg=BG)
        bar = ttk.Scrollbar(left_outer, orient="vertical", command=scroll.yview)
        scroll.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        scroll.pack(side="left", fill="both", expand=True)
        controls = ttk.Frame(scroll, style="Surface.TFrame")
        window = scroll.create_window((0, 0), window=controls, anchor="nw")
        controls.bind("<Configure>", lambda e: scroll.configure(scrollregion=scroll.bbox("all")))
        scroll.bind("<Configure>", lambda e: scroll.itemconfigure(window, width=e.width))
        self.left_scroll = scroll
        self.left_outer = left_outer

        files = self._section(controls, "数据文件", "列表顺序即组合图顺序。")
        self.directory_var = tk.StringVar()
        self.directory_entry = ttk.Entry(files, textvariable=self.directory_var)
        self.directory_entry.pack(fill="x")
        self.file_list = tk.Listbox(files, selectmode="extended", height=7, exportselection=False,
                                    bg=SURFACE, fg=INK, selectbackground=ACCENT,
                                    selectforeground=SURFACE, relief="flat", borderwidth=1,
                                    highlightthickness=1, highlightbackground=BORDER)
        self.file_list.pack(fill="x")
        row = ttk.Frame(files); row.pack(fill="x", pady=4)
        buttons = []
        for label, action in (("移除", self.remove_files), ("上移", lambda: self.move_file(-1)), ("下移", lambda: self.move_file(1)), ("清空", self.clear_files)):
            buttons.append(ttk.Button(row, text=label, command=action, style="Menu.TButton"))
        self._wrap_buttons(row, buttons)
        ttk.Button(files, text="仅保留选中项", command=self.keep_selected).pack(fill="x")
        self._config_buttons(files)

        view = self._section(controls, "视图与组合")
        self._check(view, "仅显示材料（不绘制云图）", "materials_only", False)
        self._combo(view, "方向", "orientation", "纵向（x 横轴）", ("纵向（x 横轴）", "横向（深度横轴）"))
        self._combo(view, "排列", "layout", "物理量 × 时间", ("物理量 × 时间", "时间 × 物理量", "自由网格"))
        self._entry(view, "自由网格列数", "columns", 3)
        ttk.Label(view, text="每行放几个子图；修改后自动切换为自由网格", foreground=MUTED,
                  wraplength=245).pack(anchor="w", pady=(0, 4))
        self.vars["columns"].trace_add("write", self._on_columns_changed)
        for q, label in (("electron", "电子电流密度（幅值）"),
                         ("hole", "空穴电流密度（幅值）"),
                         ("total", "总电流密度（幅值）"),
                         ("temperature", "晶格温度")):
            checkbox = ttk.Checkbutton(view, text=label, variable=self.quantity_vars[q])
            checkbox.pack(anchor="w")
            self.control_hints.append((checkbox, "勾选后绘制该物理量；双击可单独设置色图、标度和范围。"))
            checkbox.bind("<Double-Button-1>", lambda event, field=q, title=label: self._configure_common(event, field, title))
        ttk.Label(view, text="其他已命名字段（多选，双击设置）", foreground=INK).pack(anchor="w", pady=(8, 2))
        ttk.Label(view, text="幅值是合成大小；X/Y 是方向分量，可分别绘制",
                  foreground=MUTED, wraplength=245).pack(anchor="w", pady=(0, 3))
        field_frame = ttk.Frame(view)
        field_frame.pack(fill="x")
        self.field_list = tk.Listbox(field_frame, selectmode="extended", height=8,
                                     exportselection=False, bg=SURFACE, fg=INK,
                                     selectbackground=ACCENT, selectforeground=SURFACE)
        self.field_list.pack(side="left", fill="x", expand=True)
        self.field_list.bind("<Double-Button-1>", self._configure_extra)
        field_scroll = ttk.Scrollbar(field_frame, orient="vertical", command=self.field_list.yview)
        field_scroll.pack(side="right", fill="y")
        self.field_list.configure(yscrollcommand=field_scroll.set)
        self._horizontal_list_scroll(view, self.field_list)
        field_actions = ttk.Frame(view)
        field_actions.pack(fill="x", pady=(4, 0))
        ttk.Button(field_actions, text="清除字段选择", command=self.clear_extra_fields).pack(side="left")
        ttk.Label(view, text="Ctrl+单击可取消单项；双击设置显示参数", foreground=MUTED).pack(anchor="w")
        self._check(view, "镜像为完整单胞", "mirror", True)
        self._entry(view, "镜像轴 x (µm)", "mirror_x", 9.5)
        self._check(view, "显示结构与结线", "overlay", True)
        self._check(view, "显示结构标注（材料图）", "structure_labels", True)
        self._check(view, "显示坐标网格", "grid", False)
        self._check(view, "显示三角网格", "mesh", False)
        self._check(view, "显示物理量标题", "show_quantity_title", False)
        ttk.Button(view, text="子图轴标签…", command=self.open_panel_labels).pack(anchor="w", pady=4)
        self._entry(view, "x 最小值", "x0", 0)
        self._entry(view, "x 最大值", "x1", 9.5)
        self._entry(view, "深度最小值", "y0", 0)
        self._entry(view, "深度最大值", "y1", 25)

        breaks = self._section(controls, "坐标轴截断")
        for axis in ("x", "y"):
            self._entry(breaks, f"{axis.upper()} 截断起点 (µm)", f"{axis}_break_start", "")
            self._entry(breaks, f"{axis.upper()} 截断终点 (µm)", f"{axis}_break_end", "")
            self._entry(breaks, f"{axis.upper()} 断口宽度 (%)", f"{axis}_break_gap", 5)
            self._combo(breaks, f"{axis.upper()} 断口样式", f"{axis}_break_style",
                        "闪电线", ("闪电线", "波浪线", "斜杠"))

        colors = self._section(controls, "色彩与渲染")
        presets = tuple(engine.COLOR_PRESETS)
        self._combo(colors, "电流色图", "current_cmap", "tonyplot_user_smooth", presets)
        self._combo(colors, "温度色图", "temperature_cmap", "tonyplot_user_smooth", presets)
        self._combo(colors, "电流标度", "scale", "linear", ("linear", "log"))
        self._combo(colors, "渲染方式", "render", "fine_contour", ("fine_contour", "smooth", "smooth_contours"))
        self._entry(colors, "电流下限（空=自动）", "current_min", 0)
        self._entry(colors, "电流上限（空=自动）", "current_max", "")
        self._entry(colors, "温度下限（空=自动）", "temp_min", 300)
        self._entry(colors, "温度上限（空=自动）", "temp_max", "")
        self._entry(colors, "自动上限百分位", "percentile", 99.5)
        self._entry(colors, "电流等值带数", "current_bands", 120)
        self._entry(colors, "温度等值带数", "temp_bands", 90)
        self._entry(colors, "轮廓线数", "guide_lines", 16)

        output = self._section(controls, "输出")
        self._entry(output, "每列宽度 (英寸)", "panel_width", 3.2)
        self._entry(output, "每行高度 (英寸)", "panel_height", 2.2)
        self._entry(output, "导出 DPI", "dpi", self.preferences["dpi"])
        self.status = LocalizedStringVar(self, value="选择 .str 文件后生成预览")
        status_row = ttk.Frame(right)
        status_row.pack(fill="x", padx=8, pady=4)
        self.status_label = ttk.Label(status_row, textvariable=self.status, anchor="w")
        self.status_label.pack(side="left", fill="x", expand=True)
        self.plot_area = ttk.Frame(right)
        self.plot_area.pack(fill="both", expand=True)
        self.animation_area = ttk.Frame(right)
        self.animation_exporting = False
        self.show_animation_frames, self.current_animation_figure, self.animation_snapshot = build_animation_panel(
            self, self.animation_area, lambda request: self._start_render("str", animation=request))
        self.notebook.bind("<<NotebookTabChanged>>", self._switch_str_workspace, add="+")
        self.bind_class("LeftSettingsScroll", "<MouseWheel>", self._scroll_left)
        self._install_scroll_tag(left_outer)
        self._build_log_ui(log_page)
        for menu in (self.left_outer, self.log_left_outer):
            menu.bind("<Configure>", lambda _event: self.after_idle(self._align_view_switcher), add="+")
        self.after_idle(self._align_view_switcher)

    def _switch_str_workspace(self, _event=None):
        page = self.notebook.select()
        if page == str(self.log_page):
            self.str_paned.place_forget()
            return
        animated = page == str(self.animation_page)
        self.str_paned.place(in_=self.animation_page if animated else self.str_page,
                             relwidth=1, relheight=1)
        self.str_paned.lift()
        if animated:
            self.str_actions.pack_forget()
            self.plot_area.pack_forget()
            self.animation_area.pack(fill="both", expand=True)
        else:
            self.animation_area.pack_forget()
            self.str_actions.pack(fill="x", before=self.status_label.master)
            self.plot_area.pack(fill="both", expand=True)

    def _align_view_switcher(self):
        if not hasattr(self, "log_plot_area"):
            return
        menu = self.log_left_outer if self._active_kind() == "log" else self.left_outer
        self.view_switcher.place_configure(x=menu.winfo_rootx() - self.navigation.winfo_rootx() + 10)
        self.navigation.configure(height=int(self.view_switcher.cget("height")) + 12)

    def _register_tooltips(self):
        for widget, hint in self.control_hints:
            self.tooltips.register(widget, hint)
        self.tooltips.register(self.view_switcher, lambda event: (
            "STR：二维物理场云图。", "选择至少两个 STR 文件后播放。未高亮文件时使用整个列表。",
            "LOG：曲线图和双 Y 轴。")[self.view_switcher.segment_at(event.x)])
        for paned in (self.str_paned, self.log_paned):
            self.tooltips.register(paned, "拖动中间分隔线可调整参数区和预览区的宽度。")
        self.tooltips.register(self.status_label, lambda _event: self.status.get())
        self.tooltips.register(self.log_status_label, lambda _event: self.log_status.get())
        self.tooltips.register(self.version_label, f"TonyPlotPy 版本 {APP_VERSION}")
        self.tooltips.register(self.log_x_combo,
                               "选择 LOG 横轴字段；时间字段默认换算为微秒。")
        self.tooltips.register(self.log_preview_combo,
                               "单独绘图模式下切换当前预览的曲线；导出时仍会保存全部图片。")
        self.tooltips.register(
            self.directory_entry,
            lambda _event: self._directory_hint(self.directory_var.get(), "STR"),
        )
        self.tooltips.register(
            self.log_directory_entry,
            lambda _event: self._directory_hint(self.log_directory_var.get(), "LOG"),
        )
        self.tooltips.register(
            self.file_list,
            lambda event: self._list_hint(self.file_list, event, self.files,
                                          "列表中的所有 STR 文件都会参与绘图；选中用于移除、排序或仅保留操作。"),
        )
        self.tooltips.register(
            self.log_file_list,
            lambda event: self._list_hint(self.log_file_list, event, self.log_files,
                                          "列表中的所有 LOG 文件都会参与绘图；选中用于移除操作。"),
        )
        self.tooltips.register(
            self.field_list,
            lambda event: self._list_hint(self.field_list, event,
                                          self.field_list.get(0, "end"),
                                          "Ctrl/Shift 多选；双击可设置该字段的色图、标度与范围。"),
        )
        self.tooltips.register(
            self.log_y_list,
            lambda event: self._list_hint(self.log_y_list, event,
                                          self.log_y_list.get(0, "end"),
                                          "Ctrl/Shift 可多选；选中的曲线用于叠加、子图或单独导出。"),
        )
        self.tooltips.register(
            self.log_right_list,
            lambda event: self._list_hint(self.log_right_list, event,
                                          self.log_right_list.get(0, "end"),
                                          "此曲线使用右侧 Y 轴；未选中的曲线使用左侧 Y 轴。"),
        )

        def visit(widget):
            if isinstance(widget, ttk.Button):
                hint = self._button_hint(widget)
                if hint:
                    self.tooltips.register(widget, hint)
            for child in widget.winfo_children():
                visit(child)

        visit(self.notebook)
        self.tooltips.register_tree(self.notebook)

    def _notebook_hint(self, event):
        try:
            index = self.notebook.index(f"@{event.x},{event.y}")
        except tk.TclError:
            return None
        return "STR：二维物理场云图。" if index == 0 else "LOG：曲线图和双 Y 轴。"

    @staticmethod
    def _directory_hint(value, kind):
        if not value.strip():
            return f"输入或选择包含 .{kind.lower()} 文件的目录，然后点击“加载目录”。"
        path = Path(value.strip())
        state = "目录存在" if path.is_dir() else "目录不存在，请检查路径"
        return f"{path}\n{state}。修改路径后点击“加载目录”读取 .{kind.lower()} 文件。"

    @staticmethod
    def _list_hint(listing, event, items, explanation):
        if not items:
            return "列表为空；请先加载目录或添加文件。"
        index = listing.nearest(event.y)
        bounds = listing.bbox(index)
        if bounds is None or not bounds[1] <= event.y < bounds[1] + bounds[3]:
            return None
        return f"{items[index]}\n{explanation}"

    def _button_hint(self, widget):
        label = getattr(widget, "_i18n_source", widget.cget("text"))
        hints = {
            "画图 / 更新预览": "在后台读取文件并更新预览。修改参数后再次点击生效。",
            "导出图片": "将当前预览导出为 PNG、PDF 或 SVG；默认打开当前页签选择的数据目录。",
            "设置": "切换主题、界面字号、默认导出 DPI 和窗口尺寸。",
            "选择目录": "打开文件夹选择器。选定后自动加载目录中的数据文件。",
            "加载目录": "读取输入框中的目录，更新文件和可选字段列表。",
            "添加文件": "从其他位置添加数据文件；原有列表不会清空。",
            "移除": "从当前列表移除高亮文件；不会删除磁盘文件。",
            "移除选中": "从当前列表移除高亮文件；不会删除磁盘文件。",
            "上移": "将选中的 STR 文件上移，改变组合图顺序。",
            "下移": "将选中的 STR 文件下移，改变组合图顺序。",
            "清空": "清空当前文件列表；不会删除磁盘文件。",
            "仅保留选中项": "只保留当前高亮的 STR 文件参与绘图。",
            "清除字段选择": "取消“其他已命名字段”的选择；常用物理量勾选不变。",
            "清除曲线选择": "取消 LOG 纵轴曲线选择；横轴设置不变。",
        }
        return hints.get(label)

    def _install_scroll_tag(self, widget, tag="LeftSettingsScroll"):
        widget.bindtags((tag,) + widget.bindtags())
        for child in widget.winfo_children():
            self._install_scroll_tag(child, tag)

    def _on_columns_changed(self, *_):
        self.vars["layout"].set("自由网格")

    def _build_log_ui(self, page):
        paned = ttk.PanedWindow(page, orient="horizontal")
        self.log_paned = paned
        paned.pack(fill="both", expand=True)
        left = ttk.Frame(paned, width=285, style="Surface.TFrame")
        right = ttk.Frame(paned)
        paned.add(left, weight=0)
        paned.add(right, weight=1)
        actions = ttk.Frame(right, padding=(12, 10))
        actions.pack(fill="x")
        if self.header_icon:
            icon_label = ttk.Label(actions, image=self.header_icon)
            icon_label.pack(side="left", padx=(0, 9))
            self.header_icon_labels.append(icon_label)
        title_label = ttk.Label(actions, text="LOG 曲线", font=("Segoe UI", self.preferences["font_size"] + 6, "bold"), foreground=INK)
        title_label.pack(side="left", padx=(0, 18))
        self.header_title_labels.append(title_label)
        self.log_draw_button = ttk.Button(actions, text="画图 / 更新预览", command=self.preview_log,
                                          style="Accent.TButton")
        self.log_draw_button.pack(side="left", padx=(0, 8))
        self.log_preview_var = tk.StringVar()
        self.log_preview_combo = ttk.Combobox(actions, textvariable=self.log_preview_var,
                                               state="readonly", width=23)
        self.log_preview_combo.bind("<<ComboboxSelected>>", self._select_log_preview)
        scroll = tk.Canvas(left, highlightthickness=0, width=285, bg=BG)
        bar = ttk.Scrollbar(left, orient="vertical", command=scroll.yview)
        scroll.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        scroll.pack(side="left", fill="both", expand=True)
        controls = ttk.Frame(scroll, style="Surface.TFrame")
        window = scroll.create_window((0, 0), window=controls, anchor="nw")
        controls.bind("<Configure>", lambda e: scroll.configure(scrollregion=scroll.bbox("all")))
        scroll.bind("<Configure>", lambda e: scroll.itemconfigure(window, width=e.width))
        self.log_left_outer, self.log_left_scroll = left, scroll

        files = self._section(controls, "LOG 数据文件")
        self._config_buttons(files)
        self.log_directory_var = tk.StringVar()
        self.log_directory_entry = ttk.Entry(files, textvariable=self.log_directory_var)
        self.log_directory_entry.pack(fill="x")
        self.log_file_list = tk.Listbox(files, selectmode="extended", height=6,
                                        exportselection=False, bg=SURFACE, fg=INK,
                                        selectbackground=ACCENT, selectforeground=SURFACE)
        self.log_file_list.pack(fill="x")
        row = ttk.Frame(files); row.pack(fill="x", pady=4)
        ttk.Button(row, text="移除选中", command=self.remove_log_files).pack(side="left")
        ttk.Button(row, text="清空", command=self.clear_log_files).pack(side="left", padx=4)
        ttk.Label(files, text="只加载含 p/d 数据的 Atlas LOG；运行控制台日志不绘图",
                  wraplength=245, foreground=MUTED).pack(anchor="w")

        signals = self._section(controls, "横轴与曲线")
        row = ttk.Frame(signals); row.pack(fill="x", pady=2)
        ttk.Label(row, text="横轴", width=8).pack(side="left")
        self.log_x_var = tk.StringVar()
        self.log_x_combo = ttk.Combobox(row, textvariable=self.log_x_var, state="readonly", width=24)
        self.log_x_combo.pack(side="left", fill="x", expand=True)
        self.log_x_combo.bind("<<ComboboxSelected>>", self._on_log_x_changed)
        ttk.Label(signals, text="纵轴曲线（可按 Ctrl/Shift 多选）").pack(anchor="w", pady=(8, 2))
        y_frame = ttk.Frame(signals); y_frame.pack(fill="x")
        self.log_y_list = tk.Listbox(y_frame, selectmode="extended", height=9,
                                     exportselection=False, bg=SURFACE, fg=INK,
                                     selectbackground=ACCENT, selectforeground=SURFACE)
        self.log_y_list.pack(side="left", fill="x", expand=True)
        y_scroll = ttk.Scrollbar(y_frame, orient="vertical", command=self.log_y_list.yview)
        y_scroll.pack(side="right", fill="y")
        self.log_y_list.configure(yscrollcommand=y_scroll.set)
        self._horizontal_list_scroll(signals, self.log_y_list)
        self.log_y_list.bind("<<ListboxSelect>>", self._refresh_right_axis_choices)
        ttk.Button(signals, text="清除曲线选择", command=self._clear_log_y_selection).pack(anchor="w", pady=4)
        self._combo(signals, "绘图方式", "log_layout", "每信号子图",
                    ("每信号子图", "叠加曲线", "每曲线单独图片"))
        self._check(signals, "启用双 Y 轴（叠加曲线）", "log_dual_y", False)
        self.log_dual_frame = ttk.Frame(signals)
        ttk.Label(self.log_dual_frame, text="右轴曲线（从已选纵轴曲线中选择）",
                  foreground=MUTED).pack(anchor="w", pady=(4, 2))
        self.log_right_list = tk.Listbox(self.log_dual_frame, selectmode="extended", height=5,
                                         exportselection=False, bg=SURFACE, fg=INK,
                                         selectbackground=ACCENT, selectforeground=SURFACE)
        self.log_right_list.pack(fill="x")
        self._horizontal_list_scroll(self.log_dual_frame, self.log_right_list)
        self._combo(self.log_dual_frame, "右轴标度", "log_right_y_scale", "linear", ("linear", "log"))
        self._entry(self.log_dual_frame, "右轴最小（空=自动）", "log_right_y_min", "")
        self._entry(self.log_dual_frame, "右轴最大（空=自动）", "log_right_y_max", "")
        self.vars["log_layout"].trace_add("write", self._update_dual_y_visibility)
        self.vars["log_dual_y"].trace_add("write", self._update_dual_y_visibility)

        axes = self._section(controls, "坐标与样式")
        self._combo(axes, "横轴标度", "log_x_scale", "linear", ("linear", "log"))
        self._combo(axes, "纵轴标度", "log_y_scale", "linear", ("linear", "log"))
        self._entry(axes, "横轴倍率", "log_x_multiplier", "1e6")
        ttk.Label(axes, text="时间默认乘 1e6，显示为 µs", foreground=MUTED).pack(anchor="w")
        self._entry(axes, "横轴最小（空=自动）", "log_x_min", "")
        self._entry(axes, "横轴最大（空=自动）", "log_x_max", "")
        self._entry(axes, "纵轴最小（空=自动）", "log_y_min", "")
        self._entry(axes, "纵轴最大（空=自动）", "log_y_max", "")
        self._entry(axes, "线宽", "log_linewidth", 1.2)
        self._check(axes, "显示坐标网格", "log_grid", False)
        self._entry(axes, "图标题（空=不显示）", "log_title", "")
        output = self._section(controls, "输出")
        self._entry(output, "导出 DPI", "log_dpi", self.preferences["dpi"])
        self.log_status = LocalizedStringVar(self, value="选择 Atlas 数据 LOG 后生成曲线")
        status_row = ttk.Frame(right)
        status_row.pack(fill="x", padx=8, pady=4)
        self.log_status_label = ttk.Label(status_row, textvariable=self.log_status, anchor="w")
        self.log_status_label.pack(side="left", fill="x", expand=True)
        self.log_plot_area = ttk.Frame(right)
        self.log_plot_area.pack(fill="both", expand=True)
        self.bind_class("LogSettingsScroll", "<MouseWheel>", self._scroll_log)
        self._install_scroll_tag(left, "LogSettingsScroll")

    def _config_buttons(self, parent):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=4)
        self._wrap_buttons(row, [ttk.Button(row, text=label, command=command, style="Menu.TButton")
                                for label, command in (("导入配置", self.import_plot_set),
                                                       ("保存配置", self.save_plot_set))])

    def _plot_state(self):
        current_curve = None
        if self.log_rendered and self.log_preview_combo.current() >= 0:
            current_curve = self.log_rendered[self.log_preview_combo.current()][0]
        state = {"active": self._active_kind(),
                "files": {"str": [str(path) for path in self.files],
                          "log": [str(path) for path in self.log_files]},
                "vars": {key: value.get() for key, value in self.vars.items()},
                "quantities": {key: value.get() for key, value in self.quantity_vars.items()},
                "extra_fields": [self.extra_field_codes[i] for i in self.field_list.curselection()],
                "log_x": self._selected_log_x_code(),
                "log_y": [self.log_field_codes[i] for i in self.log_y_list.curselection()],
                "log_right": [self.log_right_codes[i] for i in self.log_right_list.curselection()],
                "log_curve": current_curve, "field_settings": copy.deepcopy(self.field_settings),
                "panel_labels": copy.deepcopy(self.panel_labels),
                "figure_edits": copy.deepcopy(self.figure_edits),
                "log_single_edits": copy.deepcopy(self.log_single_edits)}
        for kind, figure in (("str", self.figure), ("log", self.log_figure)):
            if figure is None:
                continue
            if kind == "log" and current_curve is not None:
                visual = state["log_single_edits"].setdefault(current_curve, {})
            else:
                visual = state["figure_edits"][kind]
            for index, axis in enumerate(figure.axes):
                if hasattr(axis, "_colorbar"):
                    continue
                ticks = axis.get_xticklabels() or axis.get_yticklabels()
                values = visual.setdefault("axes", {}).setdefault(str(index), {})
                values.update(xlim=tuple(axis.get_xlim()), ylim=tuple(axis.get_ylim()),
                              xscale=axis.get_xscale(), yscale=axis.get_yscale(),
                              tick_size=ticks[0].get_fontsize() if ticks else 8)
                if hasattr(axis, "_tonyplot_axis_key"):
                    values["axis_key"] = axis._tonyplot_axis_key
                if hasattr(figure, "_tonyplot_str_view"):
                    values["str_view"] = figure._tonyplot_str_view
        return state

    def save_plot_set(self):
        if self.busy or self.file_loading:
            return
        kind = self._active_kind()
        files = self.log_files if kind == "log" else self.files
        directory = self.log_directory_var.get() if kind == "log" else self.directory_var.get()
        path = filedialog.asksaveasfilename(
            title=self.tr("保存绘图配置"), initialdir=directory or (str(files[0].parent) if files else str(Path.home())),
            initialfile="plot.set", defaultextension=".set",
            filetypes=[("TonyPlotPy set", "*.set"), ("JSON", "*.json")])
        if not path:
            return
        try:
            save_config(path, self._plot_state())
            (self.log_status if kind == "log" else self.status).set(self.tr("配置已保存：") + path)
            self._notify_saved(self.tr("配置已保存：") + path)
        except (OSError, ValueError, TypeError) as exc:
            messagebox.showerror(self.tr("配置保存失败"), str(exc), parent=self)

    def import_plot_set(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(title=self.tr("导入绘图配置"),
                                          filetypes=[("TonyPlotPy set", "*.set *.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            state = load_config(path)
            # Validate the state shape before starting any asynchronous mutation.
            for key in ("vars", "quantities", "figure_edits", "log_single_edits", "panel_labels", "field_settings"):
                if not isinstance(state[key], dict):
                    raise ValueError("Invalid configuration section: " + key)
            files = {kind: [Path(name) for name in state["files"][kind]] for kind in ("str", "log")}
        except (OSError, ValueError, KeyError, TypeError) as exc:
            messagebox.showerror(self.tr("配置导入失败"), str(exc), parent=self)
            return

        def restore():
            try:
                for kind in ("str", "log"):
                    self.checkpoint_edit(kind)
                for key, value in state["vars"].items():
                    if key in self.vars and key != "layout":
                        self.vars[key].set(value)
                if "layout" in state["vars"]:
                    self.vars["layout"].set(state["vars"]["layout"])
                for key, value in state["quantities"].items():
                    if key in self.quantity_vars:
                        self.quantity_vars[key].set(value)
                self.field_list.selection_clear(0, "end")
                for index, code in enumerate(self.extra_field_codes):
                    if code in state.get("extra_fields", []):
                        self.field_list.selection_set(index)
                if state.get("log_x") in self.log_field_codes:
                    self.log_x_combo.current(self.log_field_codes.index(state["log_x"]))
                self.log_y_list.selection_clear(0, "end")
                for index, code in enumerate(self.log_field_codes):
                    if code in state.get("log_y", []):
                        self.log_y_list.selection_set(index)
                self._refresh_right_axis_choices()
                self.log_right_list.selection_clear(0, "end")
                for index, code in enumerate(self.log_right_codes):
                    if code in state.get("log_right", []):
                        self.log_right_list.selection_set(index)
                self.field_settings = state["field_settings"]
                self.panel_labels = state["panel_labels"]
                self.figure_edits = state["figure_edits"]
                old_axes = [item for item in self.figure_edits["str"].get("axes", {}).values()
                            if "str_view" not in item]
                if old_axes:
                    current = {key: variable.get() for key, variable in self.vars.items()}
                    saved_view = renderer.str_view_ranges(self._str_bounds(current), current["orientation"])
                    for item in old_axes:
                        item["str_view"] = saved_view
                self.log_single_edits = state["log_single_edits"]
                self._pending_set_curve = state.get("log_curve")
                if self.files:
                    self.directory_var.set(str(self.files[0].parent))
                if self.log_files:
                    self.log_directory_var.set(str(self.log_files[0].parent))
                self.notebook.select(self.str_page if state["active"] == "str" else self.log_page)
                if files[state["active"]]:
                    self._start_render(state["active"])
            except (ValueError, KeyError, TypeError, tk.TclError) as exc:
                messagebox.showerror(self.tr("配置导入失败"), str(exc), parent=self)

        self._queue_file_read(("str", "log"), additions=files, on_complete=restore, strict=True)

    def choose_directory(self):
        folder = filedialog.askdirectory(initialdir=self.directory_var.get() or str(Path.home()))
        if folder:
            self.directory_var.set(folder)
            self.load_directory()

    def _scroll_left(self, event):
        for listing in (self.file_list, self.field_list):
            if self._scroll_list_under_pointer(event, listing):
                return "break"
        return self._scroll_pane(event, self.left_outer, self.left_scroll)

    def _scroll_log(self, event):
        for listing in (self.log_file_list, self.log_y_list, self.log_right_list):
            if self._scroll_list_under_pointer(event, listing):
                return "break"
        return self._scroll_pane(event, self.log_left_outer, self.log_left_scroll)

    @staticmethod
    def _scroll_list_under_pointer(event, listing):
        inside = (listing.winfo_rootx() <= event.x_root < listing.winfo_rootx() + listing.winfo_width()
                  and listing.winfo_rooty() <= event.y_root < listing.winfo_rooty() + listing.winfo_height())
        if inside:
            steps = -1 if event.delta > 0 else 1
            listing.yview_scroll(steps * max(1, abs(event.delta) // 120), "units")
            return True
        return False

    @staticmethod
    def _scroll_pane(event, left, scroll):
        inside = (left.winfo_rootx() <= event.x_root < left.winfo_rootx() + left.winfo_width()
                  and left.winfo_rooty() <= event.y_root < left.winfo_rooty() + left.winfo_height())
        if inside:
            delta = -1 if event.delta > 0 else 1
            scroll.yview_scroll(delta * max(1, abs(event.delta) // 120), "units")
            return "break"

    def choose_log_directory(self):
        folder = filedialog.askdirectory(initialdir=self.log_directory_var.get() or str(Path.home()))
        if folder:
            self.log_directory_var.set(folder)
            self.load_log_directory()

    def _queue_file_read(self, kinds, folder=None, additions=None, on_complete=None, strict=False):
        """Read paths and headers off the UI thread; apply only the latest result."""
        tokens = {}
        for kind in kinds:
            self.file_load_ids[kind] += 1
            tokens[kind] = self.file_load_ids[kind]
            self.file_loading.add(kind)
            (self.status if kind == "str" else self.log_status).set("正在后台扫描文件和读取字段…")
        results = queue.Queue()

        def worker():
            try:
                directory = Path(folder).expanduser() if folder else None
                if additions is None and (directory is None or not directory.is_dir()):
                    raise ValueError(self.tr("目录无效") + ": " + str(folder or ""))
                batches = {}
                for kind in kinds:
                    paths = sorted(directory.glob(f"*.{kind}")) if additions is None else additions[kind]
                    paths = list(dict.fromkeys(paths))
                    headers, invalid = {}, []
                    for path in paths:
                        if tokens[kind] != self.file_load_ids[kind]:
                            break
                        try:
                            headers[path] = (engine.list_field_codes(path) if kind == "str"
                                             else log_reader.read_header(path))
                        except (OSError, ValueError):
                            invalid.append(path.name)
                    batches[kind] = (list(headers), headers, invalid)
                    if strict and invalid:
                        raise ValueError("配置引用的数据文件无法读取：\n" + "\n".join(invalid))
                results.put((batches, None))
            except Exception as exc:
                results.put(({}, str(exc)))

        def poll():
            if not any(tokens[kind] == self.file_load_ids[kind] for kind in kinds):
                return
            try:
                batches, error = results.get_nowait()
            except queue.Empty:
                self.after(50, poll)
                return
            for kind in kinds:
                if tokens[kind] != self.file_load_ids[kind]:
                    continue
                self.file_loading.discard(kind)
                if error:
                    (self.status if kind == "str" else self.log_status).set(error)
                    continue
                paths, headers, invalid = batches[kind]
                if kind == "str":
                    self.files = paths
                    self.str_headers = headers
                    self.refresh_files()
                else:
                    self.log_files = paths
                    self.log_headers = headers
                    self.refresh_log_files()
                if additions is not None and invalid:
                    messagebox.showwarning(self.tr("无法读取的文件"), "\n".join(invalid), parent=self)
            if error:
                messagebox.showerror(self.tr("目录无效"), error, parent=self)
            elif on_complete is not None and all(tokens[kind] == self.file_load_ids[kind] for kind in kinds):
                on_complete()

        threading.Thread(target=worker, daemon=True).start()
        self.after(50, poll)

    def load_log_directory(self, sync=True):
        folder = self.log_directory_var.get().strip()
        if sync:
            self.directory_var.set(folder)
        self._queue_file_read(("str", "log") if sync else ("log",), folder=folder)

    def add_log_files(self):
        paths = filedialog.askopenfilenames(filetypes=[("Atlas LOG", "*.log"), ("All files", "*.*")])
        if paths:
            self._queue_file_read(("log",), additions={"log": [*self.log_files, *map(Path, paths)]})

    def remove_log_files(self):
        for index in reversed(self.log_file_list.curselection()):
            self.log_files.pop(index)
        self.refresh_log_files()

    def clear_log_files(self):
        self.file_load_ids["log"] += 1
        self.file_loading.discard("log")
        self.log_files.clear()
        self.refresh_log_files()

    def refresh_log_files(self):
        self.log_file_list.delete(0, "end")
        for path in self.log_files:
            self.log_file_list.insert("end", f"{path.parent.name} / {path.name}")
        self.refresh_log_fields()
        self.log_status.set(f"已选择 {len(self.log_files)} 个数据 LOG")

    def refresh_log_fields(self):
        old_y = {self.log_field_codes[index] for index in self.log_y_list.curselection()}
        self.log_y_list.delete(0, "end")
        self.log_field_codes = []
        self.log_field_labels = {}
        if not self.log_files:
            self.log_x_combo.configure(values=())
            self.log_x_var.set("")
            self.log_right_list.delete(0, "end")
            self.log_right_codes = []
            return
        headers = [self.log_headers[path] for path in self.log_files]
        available = set(headers[0].labels)
        for header in headers[1:]:
            available = {code for code in available if header.labels.get(code) == headers[0].labels[code]}
        self.log_field_codes = [code for code in headers[0].codes if code in available]
        self.log_field_labels = {code: headers[0].labels[code] for code in self.log_field_codes}
        if not self.log_field_codes:
            self.log_x_combo.configure(values=())
            self.log_x_var.set("")
            self.log_right_list.delete(0, "end")
            self.log_right_codes = []
            self.log_status.set("所选 LOG 没有名称一致的共同曲线")
            return
        displays = self._unique_display_names([self.log_field_labels[code] for code in self.log_field_codes])
        self.log_x_combo.configure(values=displays)
        x_code = self._selected_log_x_code()
        preferred_x = x_code if x_code in self.log_field_codes else (61 if 61 in self.log_field_codes else self.log_field_codes[0])
        self.log_x_var.set(displays[self.log_field_codes.index(preferred_x)])
        for index, display in enumerate(displays):
            self.log_y_list.insert("end", display)
            if self.log_field_codes[index] in old_y:
                self.log_y_list.selection_set(index)
        if not old_y:
            default_y = 10002 if 10002 in self.log_field_codes else next(
                (code for code in self.log_field_codes if code != preferred_x), None
            )
            if default_y is not None:
                self.log_y_list.selection_set(self.log_field_codes.index(default_y))
        self._refresh_right_axis_choices()

    def _clear_log_y_selection(self):
        self.log_y_list.selection_clear(0, "end")
        self._refresh_right_axis_choices()

    def _refresh_right_axis_choices(self, _event=None):
        selected_right = {self.log_right_codes[index] for index in self.log_right_list.curselection()
                          if index < len(self.log_right_codes)}
        self.log_right_list.delete(0, "end")
        self.log_right_codes = [self.log_field_codes[index] for index in self.log_y_list.curselection()
                                if index < len(self.log_field_codes)]
        for index, code in enumerate(self.log_right_codes):
            self.log_right_list.insert("end", self.log_field_labels[code])
            if code in selected_right:
                self.log_right_list.selection_set(index)
        if (self.vars["log_dual_y"].get() and len(self.log_right_codes) >= 2
                and not self.log_right_list.curselection()):
            self.log_right_list.selection_set(len(self.log_right_codes) - 1)

    def _update_dual_y_visibility(self, *_args):
        enabled = (self.vars["log_layout"].get() == "叠加曲线"
                   and self.vars["log_dual_y"].get())
        if enabled:
            self.log_dual_frame.pack(fill="x", pady=(3, 0))
            self._refresh_right_axis_choices()
        else:
            self.log_dual_frame.pack_forget()

    def _selected_log_x_code(self):
        selected = self.log_x_var.get()
        for index, display in enumerate(self.log_x_combo.cget("values")):
            if display == selected and index < len(self.log_field_codes):
                return self.log_field_codes[index]
        return None

    @staticmethod
    def _unique_display_names(names):
        seen = {}
        result = []
        for name in names:
            seen[name] = seen.get(name, 0) + 1
            result.append(name if seen[name] == 1 else f"{name} ({seen[name]})")
        return result

    def _on_log_x_changed(self, _event=None):
        self.vars["log_x_multiplier"].set("1e6" if self._selected_log_x_code() == 61 else "1")

    def settings_log(self):
        if not self.log_files:
            raise ValueError("请先选择 Atlas SSF 数据 LOG")
        x_code = self._selected_log_x_code()
        y_codes = [self.log_field_codes[index] for index in self.log_y_list.curselection()]
        if x_code is None or not y_codes:
            raise ValueError("请选择横轴和至少一条纵轴曲线")
        dual_y = (self.vars["log_layout"].get() == "叠加曲线"
                  and self.vars["log_dual_y"].get())
        right_y_codes = [self.log_right_codes[index] for index in self.log_right_list.curselection()]
        if dual_y and (not right_y_codes or len(right_y_codes) == len(y_codes)):
            raise ValueError("双 Y 轴需要至少一条左轴曲线和一条右轴曲线")
        get = lambda key: self.vars[key].get()
        return {
            "kind": "log", "files": list(self.log_files), "x_code": x_code,
            "y_codes": y_codes, "layout": get("log_layout"),
            "x_scale": get("log_x_scale"), "y_scale": get("log_y_scale"),
            "x_multiplier": get("log_x_multiplier"), "linewidth": get("log_linewidth"),
            "x_min": get("log_x_min"), "x_max": get("log_x_max"),
            "y_min": get("log_y_min"), "y_max": get("log_y_max"),
            "grid": get("log_grid"), "title": get("log_title"),
            "dual_y": dual_y, "right_y_codes": right_y_codes if dual_y else [],
            "right_y_scale": get("log_right_y_scale"),
            "right_y_min": get("log_right_y_min"), "right_y_max": get("log_right_y_max"),
        }

    def load_directory(self, sync=True):
        folder = self.directory_var.get().strip()
        if sync:
            self.log_directory_var.set(folder)
        self._queue_file_read(("str", "log") if sync else ("str",), folder=folder)

    def add_files(self):
        paths = filedialog.askopenfilenames(filetypes=[("Atlas STR", "*.str"), ("All files", "*.*")])
        if paths:
            self._queue_file_read(("str",), additions={"str": [*self.files, *map(Path, paths)]})

    def refresh_files(self):
        self.file_list.delete(0, "end")
        for path in self.files: self.file_list.insert("end", path.name)
        self.refresh_fields()
        self.status.set(f"已选择 {len(self.files)} 个 .str 文件")

    def refresh_fields(self):
        selected = {self.extra_field_codes[index] for index in self.field_list.curselection()}
        self.field_list.delete(0, "end")
        self.extra_field_codes = []
        if not self.files:
            return
        try:
            available = set(self.str_headers[self.files[0]])
            for path in self.files[1:]:
                available.intersection_update(self.str_headers[path])
            named = (available & set(FIELD_NAME_BY_CODE)) - DEFAULT_FIELD_CODES
            self.extra_field_codes = [code for code in engine.FIELD_DISPLAY_ORDER if code in named]
            if 115 in named:
                self.extra_field_codes.insert(self.extra_field_codes.index(115) + 1, "absolute_net_doping")
            for index, code in enumerate(self.extra_field_codes):
                self.field_list.insert("end", self._extra_field_label(code))
                if code in selected:
                    self.field_list.selection_set(index)
        except (OSError, ValueError) as exc:
            self.status.set(f"字段读取失败：{exc}")

    def _configure_common(self, event, field, title):
        self.quantity_vars[field].set(True)
        self.open_field_settings(field, title)
        return "break"

    def _configure_extra(self, event):
        index = self.field_list.nearest(event.y)
        if not 0 <= index < len(self.extra_field_codes):
            return "break"
        self.field_list.selection_set(index)
        code = self.extra_field_codes[index]
        self.open_field_settings(self._extra_field_id(code), self._extra_field_label(code))

    @staticmethod
    def _extra_field_id(code):
        return f"code:{code}" if isinstance(code, int) else code

    def _extra_field_label(self, code):
        if code == "absolute_net_doping":
            return self.tr("绝对净掺杂浓度")
        return engine.FIELD_LABELS_BY_CODE[code] if self.language == "English" else FIELD_NAME_BY_CODE[code]
        return "break"

    def open_field_settings(self, field: str, title: str):
        """Edit per-field plot settings without changing other quantities."""
        dialog = tk.Toplevel(self)
        dialog.title(self.tr("显示参数") + " · " + self.tr(title))
        dialog.transient(self)
        dialog.resizable(False, False)
        dialog.configure(bg=BG)
        dialog.grab_set()
        values = self.field_settings.get(field, {})
        edits = {}
        body = ttk.Frame(dialog, padding=16)
        body.pack(fill="both", expand=True)
        is_doping = field in renderer.DOPING_FIELDS
        scales = ("默认", "linear", "log")
        if field == "absolute_net_doping":
            scales = (*scales, "symlog")
        elif is_doping:
            scales = ("默认", "linear", "symlog")
        controls = [
            ("色图", "cmap", ("默认", *engine.COLOR_PRESETS)),
            ("标度", "scale", scales),
            ("下限", "vmin", None),
            ("上限", "vmax", None),
            ("等值带数", "bands", None),
        ]
        if is_doping:
            controls.append(("对数阈值", "doping_floor", None))
        for label, key, choices in controls:
            row = ttk.Frame(body); row.pack(fill="x", pady=4)
            ttk.Label(row, text=self.tr(label), width=10).pack(side="left")
            default = "默认" if choices else ""
            variable = tk.StringVar(value=self.tr(values.get(key, default)))
            edits[key] = variable
            if choices:
                ttk.Combobox(row, textvariable=variable, values=[self.tr(item) for item in choices],
                             state="readonly", width=22).pack(side="left")
            else:
                ttk.Entry(row, textvariable=variable, width=24).pack(side="left")
        ttk.Label(body, text=self.tr("留空的数值使用全局设置或自动范围"), foreground=MUTED).pack(anchor="w", pady=(8, 4))
        buttons = ttk.Frame(body); buttons.pack(fill="x", pady=(8, 0))

        def save():
            data = {key: ("默认" if var.get() == self.tr("默认") else var.get().strip())
                    for key, var in edits.items()}
            try:
                if is_doping and data["doping_floor"] and float(data["doping_floor"]) <= 0:
                    raise ValueError("净掺杂对数阈值必须大于 0")
                lower = optional_float(data["vmin"])
                upper = optional_float(data["vmax"])
                if lower is not None and upper is not None and upper <= lower:
                    raise ValueError("上限必须大于下限")
                if data["bands"] and int(data["bands"]) < 2:
                    raise ValueError("等值带数必须至少为 2")
            except ValueError as exc:
                messagebox.showerror(self.tr("参数无效"), self.tr(str(exc)), parent=dialog)
                return
            self.checkpoint_edit("str")
            self.field_settings[field] = data
            dialog.destroy()

        ttk.Button(buttons, text=self.tr("取消"), command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text=self.tr("应用"), command=save, style="Accent.TButton").pack(side="right", padx=8)
        dialog.bind("<Return>", lambda event: save())
        dialog.bind("<Escape>", lambda event: dialog.destroy())
        self.tooltips.register_tree(dialog)
        dialog.wait_visibility()
        dialog.focus_set()

    def remove_files(self):
        for index in reversed(self.file_list.curselection()): self.files.pop(index)
        self.refresh_files()

    def clear_files(self):
        self.file_load_ids["str"] += 1
        self.file_loading.discard("str")
        self.files.clear(); self.refresh_files()

    def clear_extra_fields(self):
        self.field_list.selection_clear(0, "end")

    def keep_selected(self):
        selected = self.file_list.curselection()
        if not selected: return
        self.files = [self.files[index] for index in selected]
        self.refresh_files()

    def move_file(self, direction):
        selected = self.file_list.curselection()
        if len(selected) != 1: return
        index = selected[0]; dest = index + direction
        if not 0 <= dest < len(self.files): return
        self.files[index], self.files[dest] = self.files[dest], self.files[index]
        self.refresh_files(); self.file_list.selection_set(dest)

    def open_panel_labels(self):
        try:
            options = self.settings()
            panels, columns = renderer.panel_layout(options)
            if columns < 1:
                raise ValueError("列数必须至少为 1")
        except ValueError as exc:
            messagebox.showerror(self.tr("参数无效"), self.tr(str(exc)), parent=self)
            return
        dialog = tk.Toplevel(self)
        dialog.title(self.tr("子图轴标签"))
        dialog.transient(self)
        dialog.geometry("680x460")
        dialog.grab_set()
        body = ttk.Frame(dialog, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=self.tr("勾选表示显示轴名称；不影响刻度数字。隐藏后自动收紧行列间距。"),
                  wraplength=640).pack(anchor="w", pady=(0, 8))
        presets = ttk.Frame(body)
        presets.pack(fill="x", pady=(0, 8))
        area = ttk.Frame(body)
        area.pack(fill="both", expand=True)
        canvas = tk.Canvas(area, highlightthickness=0, bg=SURFACE)
        scroll = ttk.Scrollbar(area, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        rows = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=rows, anchor="nw")
        rows.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        dialog.bind("<MouseWheel>", lambda event: canvas.yview_scroll(-int(event.delta / 120), "units"))
        choices = []
        for index, (file_index, quantity) in enumerate(panels):
            path = options["files"][file_index]
            key = (str(path), quantity)
            saved = self.panel_labels.get(key, {})
            x = tk.BooleanVar(value=saved.get("x", True))
            y = tk.BooleanVar(value=saved.get("y", True))
            row = ttk.Frame(rows, padding=(4, 5))
            row.pack(fill="x")
            label = f"[{index // columns + 1}, {index % columns + 1}] {path.name}\n{renderer.quantity_label(quantity)}"
            ttk.Label(row, text=label, wraplength=450).pack(side="left", fill="x", expand=True)
            ttk.Checkbutton(row, text="X label", variable=x).pack(side="left", padx=8)
            ttk.Checkbutton(row, text="Y label", variable=y).pack(side="left", padx=8)
            choices.append((key, x, y))

        def preset(mode):
            for index, (_key, x, y) in enumerate(choices):
                x.set(mode == "all" or (mode == "outer" and index + columns >= len(panels)))
                y.set(mode == "all" or (mode == "outer" and index % columns == 0))

        for text, mode in (("全部显示", "all"), ("仅显示外侧", "outer"), ("全部隐藏", "none")):
            ttk.Button(presets, text=self.tr(text), command=lambda mode=mode: preset(mode)).pack(side="left", padx=(0, 6))

        def apply():
            self.checkpoint_edit("str")
            for key, x, y in choices:
                self.panel_labels[key] = {"x": x.get(), "y": y.get()}
            dialog.destroy()
            if not self.busy:
                self.preview()

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text=self.tr("取消"), command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text=self.tr("应用"), command=apply,
                   style="Accent.TButton").pack(side="right", padx=8)
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        self.tooltips.register_tree(dialog)

    def settings(self):
        options = {key: variable.get() for key, variable in self.vars.items()}
        options["quantities"] = [q for q in QUANTITIES if self.quantity_vars[q].get()]
        options["quantities"].extend(
            self._extra_field_id(self.extra_field_codes[index]) for index in self.field_list.curselection()
        )
        options["field_settings"] = {key: value.copy() for key, value in self.field_settings.items()}
        options["panel_labels"] = copy.deepcopy(self.panel_labels)
        options["files"] = list(self.files)
        if options.get("materials_only", False):
            options["quantities"] = ["materials"]
        get = options.__getitem__
        quantities = options["quantities"]
        if not options["files"] or not quantities: raise ValueError("请选择至少一个 .str 文件和一个物理量")
        if not 0 < float(get("percentile")) <= 100: raise ValueError("百分位必须在 0–100 之间")
        # A zero lower bound is useful for linear plots. In log mode the
        # renderer interprets it as automatic positive lower bound.
        options["bounds"] = self._str_bounds(options)
        options["axis_breaks"] = parse_breaks(options, options["bounds"])
        return options

    @staticmethod
    def _str_bounds(options):
        x0, x1, y0, y1 = (float(options[key]) for key in ("x0", "x1", "y0", "y1"))
        if x1 <= x0 or y1 <= y0:
            raise ValueError("显示范围的最大值必须大于最小值")
        if options["mirror"] and math.isclose(x1, float(options["mirror_x"])):
            x1 = 2 * x1 - x0
        return x0, x1, y0, y1

    def preview(self):
        self._start_render("str")

    def preview_log(self):
        self._start_render("log")

    def _start_render(self, kind, animation=None):
        if kind in self.file_loading:
            (self.status if kind == "str" else self.log_status).set("正在后台扫描文件和读取字段…")
            return
        if self.busy or self.animation_exporting: return
        try:
            options = self.settings() if kind == "str" else self.settings_log()
            if animation:
                selected = self.file_list.curselection()
                if selected:
                    options["files"] = [self.files[index] for index in selected]
                if len(options["files"]) < 2:
                    raise ValueError("动态云图至少需要两个 STR 文件")
                if options.get("materials_only"):
                    raise ValueError("请关闭仅显示材料并选择云图物理量")
                options["animation"] = animation
            options["kind"] = kind
            options["visual_edits"] = copy.deepcopy(self.figure_edits[kind])
            if kind == "log":
                options["signal_labels"] = self.log_field_labels.copy()
                options["visual_edits_by_code"] = copy.deepcopy(self.log_single_edits)
            self.busy = True
            self.draw_button.configure(state="disabled")
            self.log_draw_button.configure(state="disabled")
            status = self.status if kind == "str" else self.log_status
            status.set("后台读取与绘制中，界面仍可操作…")
            # Tk image objects must be finalized on the UI thread, never by
            # the rendering worker's cyclic garbage collector.
            self.gc_was_enabled = gc.isenabled()
            gc.disable()
            threading.Thread(target=self._render_worker, args=(options,), daemon=True).start()
            self.after(100, self._poll_render)
        except Exception as exc:
            if self.gc_was_enabled: gc.enable()
            messagebox.showerror(self.tr("绘图失败"), self.tr(str(exc)))

    def _render_worker(self, options):
        try:
            if options.get("animation"):
                frames = render_frames(options, self.cache)
                self.render_results.put((frames, None, options, None))
                return
            if options["kind"] == "str":
                figure = renderer.make_figure(options, self.cache)
            elif options["layout"] == "每曲线单独图片":
                rendered = []
                for code in options["y_codes"]:
                    single = options.copy()
                    single["y_codes"] = [code]
                    single["layout"] = "叠加曲线"
                    single["title"] = options["title"]
                    figure = log_renderer.make_figure(single, self.log_cache)
                    apply_edits(figure, options["visual_edits_by_code"].get(code, {}))
                    agg = FigureCanvasAgg(figure)
                    agg.draw()
                    rendered.append((code, options["signal_labels"].get(code, "Signal"), figure, agg.renderer))
                self.render_results.put((rendered, None, options, None))
                return
            else:
                figure = log_renderer.make_figure(options, self.log_cache)
            apply_edits(figure, options["visual_edits"])
            agg = FigureCanvasAgg(figure)
            agg.draw()
            self.render_results.put((figure, agg.renderer, options, None))
        except Exception as exc:
            self.render_results.put((None, None, options, str(exc)))

    def _poll_render(self):
        try:
            figure, renderer, options, error = self.render_results.get_nowait()
        except queue.Empty:
            if self.busy: self.after(100, self._poll_render)
            return
        try:
            if error: self._render_failed(error, options["kind"] if options else self._active_kind())
            elif options.get("animation"):
                self.busy = False
                for button in (self.draw_button, self.log_draw_button):
                    button.configure(state="normal")
                preview = options["animation"].get("preview")
                if preview is not None:
                    preview(figure[0])
                    self.status.set("预览完成")
                else:
                    self.status.set("动态云图已生成")
                    self.animation_render_options = options
                    self.show_animation_frames(figure)
            elif isinstance(figure, list): self._show_log_batch(figure, options)
            else:
                if options["kind"] == "log":
                    self.log_rendered = []
                    self.log_preview_combo.pack_forget()
                self._show_figure(figure, renderer, options)
        finally:
            if self.gc_was_enabled: gc.enable()
            gc.collect()

    def _show_figure(self, figure, renderer, options):
        kind = options["kind"]
        is_log = kind == "log"
        plot_area = self.log_plot_area if is_log else self.plot_area
        old_figure = self.log_figure if is_log else self.figure
        old_canvas_widget = self.log_canvas_widget if is_log else self.canvas_widget
        preserve_old = (is_log and options.get("layout") == "每曲线单独图片"
                        and any(old_figure is item[2] for item in self.log_rendered))
        try:
            # Matplotlib's Figure.clear() updates its toolbar. The old toolbar
            # must still exist when this call runs.
            if old_figure and not preserve_old:
                if hasattr(old_figure.canvas, "cancel_pending_resize"):
                    old_figure.canvas.cancel_pending_resize()
                old_figure.clear()
            elif old_figure and old_figure.canvas:
                if hasattr(old_figure.canvas, "cancel_pending_resize"):
                    old_figure.canvas.cancel_pending_resize()
                old_figure.canvas.toolbar = None
            if old_canvas_widget:
                old_canvas_widget.destroy()
            for child in plot_area.winfo_children(): child.destroy()
            # Tk image/variable finalizers must run on the UI thread.
            if is_log:
                self.log_figure = None
                self.log_canvas_widget = None
            else:
                self.figure = None
                self.canvas_widget = None
            old_figure = None
            gc.collect()
            canvas = DeferredFigureCanvasTkAgg(figure, master=plot_area)
            canvas.renderer = renderer
            canvas.blit()
            toolbar = CenteredNavigationToolbar2Tk(canvas, plot_area, pack_toolbar=False)
            toolbar.configure(bg=SURFACE, bd=0)
            for tool in toolbar.winfo_children():
                if isinstance(tool, tk.Button):
                    tool.configure(bg=SURFACE, activebackground="#edf4ff",
                                   relief="flat", bd=0, highlightthickness=0)
            toolbar.update(); toolbar.pack(side="top", fill="x")
            canvas.get_tk_widget().pack(fill="both", expand=True)
            edits = (self.log_single_edits.setdefault(options["curve_code"], {})
                     if is_log and "curve_code" in options else self.figure_edits[kind])
            editor = FigureEditor(self, figure, canvas, edits,
                                  self.log_status if is_log else self.status)
            editor.edit_kind = kind
            editor.arrow_button = ttk.Button(toolbar, text="添加箭头", command=editor.start_arrow)
            editor.arrow_button.pack(side="left", padx=8)
            undo = ttk.Button(toolbar, text=self.tr("撤销"), command=lambda: self.undo_edit(kind),
                              state="normal" if self.undo_history[kind] else "disabled")
            undo.pack(side="left", padx=4)
            self.undo_buttons[kind] = undo
            self.tooltips.register(undo, "撤销上一次已确认的图形编辑（Ctrl+Z），最多保留 50 步。")
            self.tooltips.register(editor.arrow_button,
                                   "依次点击图中的起点和终点，再设置标注文字、颜色与线宽。")
            self.tooltips.register_tree(toolbar)
            self.editors[kind] = editor
            if is_log:
                self.log_figure = figure
                self.log_canvas_widget = canvas.get_tk_widget()
                self.log_status.set(f"预览完成：{len(options['files'])} 个文件 × {len(options['y_codes'])} 条曲线")
            else:
                self.figure = figure
                self.canvas_widget = canvas.get_tk_widget()
                self.status.set(f"预览完成：{len(options['files'])} 个文件 × {len(options['quantities'])} 个物理量")
        except Exception as exc:
            self._render_failed(str(exc), kind)
        finally:
            self.busy = False
            self.draw_button.configure(state="normal")
            self.log_draw_button.configure(state="normal")

    def _active_kind(self):
        return "log" if self.notebook.select() == str(self.log_page) else "str"

    def _file_menu_action(self, action):
        qualifier = "log_" if self._active_kind() == "log" else ""
        target = "files" if action == "add" else "directory"
        getattr(self, f"{action}_{qualifier}{target}")()

    def _show_log_batch(self, rendered, options):
        self.log_rendered = rendered
        labels = self._unique_display_names([label for _code, label, _, _ in rendered])
        self.log_preview_combo.configure(values=labels)
        self.log_preview_var.set(labels[0])
        if not self.log_preview_combo.winfo_manager():
            self.log_preview_combo.pack(side="left", padx=10)
        index = next((i for i, (code, *_rest) in enumerate(rendered) if code == self._pending_set_curve), 0)
        self._pending_set_curve = None
        self.log_preview_combo.current(index)
        self._show_log_selection(index, options)

    def _select_log_preview(self, _event=None):
        index = self.log_preview_combo.current()
        if index >= 0 and self.log_rendered:
            self._show_log_selection(index, {"kind": "log", "layout": "每曲线单独图片",
                                             "files": self.log_files})

    def _show_log_selection(self, index, options):
        code, _label, figure, renderer = self.log_rendered[index]
        display_options = {**options, "kind": "log", "layout": "每曲线单独图片",
                           "curve_code": code, "y_codes": [code]}
        self._show_figure(figure, renderer, display_options)
        self.log_status.set(f"单独图片预览：第 {index + 1}/{len(self.log_rendered)} 张")

    def _render_failed(self, error, kind):
        self.busy = False
        self.draw_button.configure(state="normal")
        self.log_draw_button.configure(state="normal")
        (self.log_status if kind == "log" else self.status).set("绘图失败")
        messagebox.showerror(self.tr("绘图失败"), self.tr(error))

    def export(self):
        kind = "animation" if self.notebook.select() == str(self.animation_page) else self._active_kind()
        self._export_kind(kind)

    def _export_kind(self, kind):
        if self.busy or self.animation_exporting:
            return
        if kind == "animation":
            figure = self.current_animation_figure()
        else:
            figure = self.log_figure if kind == "log" else self.figure
        if figure is None:
            messagebox.showinfo(self.tr("请先画图"), self.tr("生成预览后即可保存图片。"))
            return
        directory = self.log_directory_var if kind == "log" else self.directory_var
        files = self.log_files if kind == "log" else self.files
        selected_directory = directory.get().strip()
        image_dir = Path(selected_directory).expanduser() if selected_directory else None
        if image_dir is None or not image_dir.is_dir():
            image_dir = files[0].parent if files else Path.home()
        if kind == "log":
            default_name = f"{self.log_files[0].parent.name}_log_curves.png" if self.log_files else "log_curves.png"
        elif kind == "animation":
            default_name = "animation.gif"
        else:
            default_name = f"{self.files[0].parent.name}_cloud_map.png" if self.files else "cloud_map.png"
        filetypes = [("PNG image", "*.png"), ("PDF document", "*.pdf"), ("SVG vector", "*.svg")]
        if kind == "animation":
            filetypes[:0] = [("GIF animation", "*.gif"), ("MP4 video", "*.mp4")]
        path = filedialog.asksaveasfilename(
            initialdir=str(image_dir), initialfile=default_name,
            defaultextension=".gif" if kind == "animation" else ".png",
            filetypes=filetypes,
        )
        if not path: return
        try:
            dpi_key = "log_dpi" if kind == "log" else "dpi"
            dpi = int(self.vars[dpi_key].get())
            if kind == "animation" and Path(path).suffix.lower() in (".gif", ".mp4"):
                snapshot = self.animation_snapshot()
                if snapshot is None:
                    messagebox.showinfo(self.tr("请先画图"), self.tr("请先点击“画动态图”生成完整序列。"), parent=self)
                    return
                self._export_animation(path, *snapshot, dpi)
                return
            if kind == "log" and self.log_rendered:
                base = Path(path)
                outputs = []
                for index, (code, label, item, _renderer) in enumerate(self.log_rendered, 1):
                    safe_label = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", label).strip(" ._")[:60] or "signal"
                    output = base.with_name(f"{base.stem}_{index}_{safe_label}{base.suffix}")
                    self._save_figure(item, output, dpi)
                    outputs.append(output)
                self.log_status.set(f"已导出 {len(outputs)} 张图片到：{base.parent}")
                self._notify_saved(f"已导出 {len(outputs)} 张图片到：{base.parent}")
            else:
                self._save_figure(figure, path, dpi)
                (self.log_status if kind == "log" else self.status).set(f"已导出：{path}")
                self._notify_saved(f"已导出：{path}")
        except Exception as exc: messagebox.showerror(self.tr("导出失败"), self.tr(str(exc)))

    def _export_animation(self, path, edits_by_path, fps, dpi):
        options = self.animation_render_options
        cache = self.cache.copy()
        self.animation_exporting = True
        self.status.set("正在后台导出动画…")
        result = queue.Queue()
        gc_enabled = gc.isenabled()
        gc.disable()

        def worker():
            try:
                with quiet_export():
                    frames = render_frames(options, cache, export_dpi=dpi, edits_by_path=edits_by_path)
                    save_animation(path, frames, fps)
            except Exception as exc:
                result.put(str(exc))
            else:
                result.put(None)

        def poll():
            try:
                error = result.get_nowait()
            except queue.Empty:
                self.after(100, poll)
                return
            self.animation_exporting = False
            if gc_enabled:
                gc.enable()
            if error is None:
                self.status.set(f"已导出：{path}")
                self._notify_saved(f"已导出：{path}")
            else:
                self.status.set("导出失败")
                messagebox.showerror(self.tr("导出失败"), self.tr(error), parent=self)

        threading.Thread(target=worker, daemon=True).start()
        self.after(100, poll)

    def _notify_saved(self, message):
        messagebox.showinfo(self.tr("保存完成"), self.tr(message), parent=self)

    @staticmethod
    def _save_figure(figure, path, dpi):
        export_size = getattr(figure, "_tonyplot_export_size", None)
        preview_size = tuple(figure.get_size_inches())
        with quiet_export():
            try:
                if export_size is not None:
                    figure.set_size_inches(*export_size, forward=False)
                figure.savefig(path, dpi=dpi, bbox_inches="tight")
            finally:
                if export_size is not None:
                    figure.set_size_inches(*preview_size, forward=False)



