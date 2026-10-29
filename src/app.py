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
from tkinter import filedialog, messagebox, ttk

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.backends.backend_tkagg import NavigationToolbar2Tk

from .plotting import atlas_engine as engine
from .plotting import renderer
from .plotting import log_reader, log_renderer
from .plotting.figure_edits import apply_edits
from .figure_editor import FigureEditor
from .deferred_canvas import DeferredFigureCanvasTkAgg
from .ui_settings import THEMES, WINDOW_SIZES, load_settings, save_settings
from .tooltips import TooltipManager
from .control_hints import hint_for
from .version import APP_VERSION
from .i18n import translate, LocalizedStringVar


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
        self.busy = False
        self.gc_was_enabled = False
        self.render_results = queue.Queue()
        self.vars: dict[str, tk.Variable] = {}
        self.localized_combos = []
        self.quantity_vars = {
            q: tk.BooleanVar(value=q in ("total", "temperature"))
            for q in QUANTITIES
        }
        self.extra_field_codes: list[int] = []
        self.field_settings: dict[str, dict[str, str]] = {}
        self.control_hints = []
        self._build_ui()
        self._refresh_language()
        self._refresh_widget_appearance()
        self.tooltips = TooltipManager(self)
        self.tooltips.set_theme(BORDER, self.preferences["font_size"])
        self._register_tooltips()

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
        font_size = self.preferences["font_size"]
        style.configure("TFrame", background=SURFACE)
        style.configure("Surface.TFrame", background=BG)
        style.configure("TLabel", background=SURFACE, foreground=INK, font=("Segoe UI", font_size))
        style.configure("TCheckbutton", background=SURFACE, foreground=INK, font=("Segoe UI", font_size))
        style.map("TCheckbutton", background=[("active", SURFACE)])
        style.configure("TEntry", fieldbackground=SURFACE, foreground=INK,
                        bordercolor=BORDER, lightcolor=BORDER, padding=5)
        style.configure("TCombobox", fieldbackground=SURFACE, foreground=INK,
                        background=SURFACE, bordercolor=BORDER, padding=5)
        style.configure("TButton", background=SURFACE, foreground=INK, bordercolor=BORDER,
                        padding=(9, 6), font=("Segoe UI", max(8, font_size - 1)))
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
                                 font=("Segoe UI", font_size, "bold"))
            elif isinstance(widget, tk.Listbox):
                widget.configure(bg=SURFACE, fg=INK, selectbackground=ACCENT,
                                 selectforeground=SURFACE, font=("Segoe UI", font_size))
                if "highlightbackground" in widget.keys():
                    widget.configure(highlightbackground=BORDER)
            elif isinstance(widget, tk.Button):
                widget.configure(bg=SURFACE, activebackground=self.palette["soft"])
            elif isinstance(widget, (ttk.Entry, ttk.Combobox)):
                widget.configure(font=("Segoe UI", font_size))
            for child in widget.winfo_children():
                update(child)

        update(self)
        self.configure(bg=BG)
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
        caption = ttk.Label(row, text=label, width=18)
        caption.pack(side="left")
        entry = ttk.Entry(row, textvariable=self.var(key, default), width=width)
        entry.pack(side="left", fill="x", expand=True)
        self.control_hints.extend(((caption, hint_for(key, label)), (entry, hint_for(key, label))))

    def _combo(self, parent, label, key, default, options):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        caption = ttk.Label(row, text=label, width=18)
        caption.pack(side="left")
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
        combo.pack(side="left", fill="x", expand=True)
        self.control_hints.extend(((caption, hint_for(key, label)), (combo, hint_for(key, label))))

    def _check(self, parent, label, key, default):
        checkbox = ttk.Checkbutton(parent, text=label, variable=self.var(key, default))
        checkbox.pack(anchor="w", pady=2)
        self.control_hints.append((checkbox, hint_for(key, label)))

    def _section(self, parent, title):
        card = tk.Frame(parent, bg=SURFACE, highlightbackground=BORDER,
                        highlightthickness=1, bd=0)
        card.pack(fill="x", padx=10, pady=7)
        tk.Label(card, text=title, bg=SURFACE, fg=INK,
                 font=("Segoe UI", self.preferences["font_size"], "bold"), anchor="w").pack(fill="x", padx=12, pady=(12, 6))
        frame = ttk.Frame(card, padding=(12, 0, 12, 12))
        frame.pack(fill="x")
        return frame

    def _build_ui(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)
        str_page = ttk.Frame(self.notebook)
        log_page = ttk.Frame(self.notebook)
        self.str_page, self.log_page = str_page, log_page
        self.notebook.add(str_page, text="  STR 云图  ")
        self.notebook.add(log_page, text="  LOG 曲线  ")
        paned = ttk.PanedWindow(str_page, orient="horizontal")
        self.str_paned = paned
        paned.pack(fill="both", expand=True)
        left_outer = ttk.Frame(paned, width=285, style="Surface.TFrame")
        right = ttk.Frame(paned)
        paned.add(left_outer, weight=0)
        paned.add(right, weight=1)
        actions = ttk.Frame(right, padding=(12, 10))
        actions.pack(fill="x")
        if self.header_icon:
            icon_label = ttk.Label(actions, image=self.header_icon)
            icon_label.pack(side="left", padx=(0, 9))
            self.header_icon_labels.append(icon_label)
        title_label = ttk.Label(actions, text="TonyPlotPy", font=("Segoe UI", self.preferences["font_size"] + 6, "bold"), foreground=INK)
        title_label.pack(side="left", padx=(0, 18))
        self.header_title_labels.append(title_label)
        self.draw_button = ttk.Button(actions, text="画图 / 更新预览", command=self.preview, style="Accent.TButton")
        self.draw_button.pack(side="left", padx=(0, 8))
        self.export_button = ttk.Button(actions, text="导出图片", command=self.export)
        self.export_button.pack(side="left")
        ttk.Button(actions, text="设置", command=self.open_settings).pack(side="right", padx=8)
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

        files = self._section(controls, "数据文件（列表顺序即组合图顺序）")
        self.directory_var = tk.StringVar()
        self.directory_entry = ttk.Entry(files, textvariable=self.directory_var)
        self.directory_entry.pack(fill="x")
        row = ttk.Frame(files); row.pack(fill="x", pady=4)
        ttk.Button(row, text="选择目录", command=self.choose_directory).pack(side="left")
        ttk.Button(row, text="加载目录", command=self.load_directory).pack(side="left")
        ttk.Button(row, text="添加文件", command=self.add_files).pack(side="left")
        self.file_list = tk.Listbox(files, selectmode="extended", height=7, exportselection=False,
                                    bg=SURFACE, fg=INK, selectbackground=ACCENT,
                                    selectforeground=SURFACE, relief="flat", borderwidth=1,
                                    highlightthickness=1, highlightbackground=BORDER)
        self.file_list.pack(fill="x")
        row = ttk.Frame(files); row.pack(fill="x", pady=4)
        for label, action in (("移除", self.remove_files), ("上移", lambda: self.move_file(-1)), ("下移", lambda: self.move_file(1)), ("清空", self.clear_files)):
            ttk.Button(row, text=label, command=action).pack(side="left")
        ttk.Button(files, text="仅保留选中项", command=self.keep_selected).pack(fill="x")

        view = self._section(controls, "视图与组合")
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
        field_actions = ttk.Frame(view)
        field_actions.pack(fill="x", pady=(4, 0))
        ttk.Button(field_actions, text="清除字段选择", command=self.clear_extra_fields).pack(side="left")
        ttk.Label(view, text="Ctrl+单击可取消单项；双击设置显示参数", foreground=MUTED).pack(anchor="w")
        self._check(view, "镜像为完整单胞", "mirror", True)
        self._entry(view, "镜像轴 x (µm)", "mirror_x", 9.5)
        self._check(view, "显示结构与结线", "overlay", True)
        self._check(view, "显示坐标网格", "grid", False)
        self._entry(view, "x 最小值", "x0", 0)
        self._entry(view, "x 最大值", "x1", 9.5)
        self._entry(view, "深度最小值", "y0", 0)
        self._entry(view, "深度最大值", "y1", 25)

        colors = self._section(controls, "色彩与渲染")
        presets = tuple(engine.COLOR_PRESETS)
        self._combo(colors, "电流色图", "current_cmap", "tonyplot_user_smooth", presets)
        self._combo(colors, "温度色图", "temperature_cmap", "tonyplot_user_smooth", presets)
        self._combo(colors, "电流标度", "scale", "linear", ("linear", "log"))
        self._combo(colors, "渲染方式", "render", "fine_contour", ("fine_contour", "smooth", "smooth_contours"))
        self._entry(colors, "电流下限（空=自动）", "current_min", 0)
        self._entry(colors, "电流上限（空=自动）", "current_max", 100)
        self._entry(colors, "温度下限（空=自动）", "temp_min", 300)
        self._entry(colors, "温度上限（空=自动）", "temp_max", 334.5)
        self._entry(colors, "自动上限百分位", "percentile", 99.5)
        self._entry(colors, "电流等值带数", "current_bands", 120)
        self._entry(colors, "温度等值带数", "temp_bands", 90)
        self._entry(colors, "轮廓线数", "guide_lines", 16)

        output = self._section(controls, "输出")
        self._entry(output, "每列宽度 (英寸)", "panel_width", 3.2)
        self._entry(output, "每行高度 (英寸)", "panel_height", 2.2)
        self._entry(output, "导出 DPI", "dpi", self.preferences["dpi"])
        ttk.Label(output, text="顶部按钮可画图并导出 PNG/PDF/SVG").pack(anchor="w", pady=3)
        self.status = LocalizedStringVar(self, value="选择 .str 文件后生成预览")
        status_row = ttk.Frame(right)
        status_row.pack(fill="x", padx=8, pady=4)
        self.status_label = ttk.Label(status_row, textvariable=self.status, anchor="w")
        self.status_label.pack(side="left", fill="x", expand=True)
        self.version_labels = [ttk.Label(status_row, text=f"v{APP_VERSION}", foreground=MUTED)]
        self.version_labels[0].pack(side="right")
        self.plot_area = ttk.Frame(right)
        self.plot_area.pack(fill="both", expand=True)
        self.bind_class("LeftSettingsScroll", "<MouseWheel>", self._scroll_left)
        self._install_scroll_tag(left_outer)
        self._build_log_ui(log_page)

    def _register_tooltips(self):
        for widget, hint in self.control_hints:
            self.tooltips.register(widget, hint)
        self.tooltips.register(self.notebook, self._notebook_hint)
        for paned in (self.str_paned, self.log_paned):
            self.tooltips.register(paned, "拖动中间分隔线可调整参数区和预览区的宽度。")
        self.tooltips.register(self.status_label, lambda _event: self.status.get())
        self.tooltips.register(self.log_status_label, lambda _event: self.log_status.get())
        for label in self.version_labels:
            self.tooltips.register(label, f"TonyPlotPy 版本 {APP_VERSION}")
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
            "导出图片": "将当前预览导出为 PNG、PDF 或 SVG；图片默认保存到 imgs 文件夹。",
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
        self.log_export_button = ttk.Button(actions, text="导出图片", command=self.export_log)
        self.log_export_button.pack(side="left")
        self.log_preview_var = tk.StringVar()
        self.log_preview_combo = ttk.Combobox(actions, textvariable=self.log_preview_var,
                                               state="readonly", width=23)
        self.log_preview_combo.bind("<<ComboboxSelected>>", self._select_log_preview)
        ttk.Button(actions, text="设置", command=self.open_settings).pack(side="right", padx=8)
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
        self.log_directory_var = tk.StringVar()
        self.log_directory_entry = ttk.Entry(files, textvariable=self.log_directory_var)
        self.log_directory_entry.pack(fill="x")
        row = ttk.Frame(files); row.pack(fill="x", pady=4)
        ttk.Button(row, text="选择目录", command=self.choose_log_directory).pack(side="left")
        ttk.Button(row, text="加载目录", command=self.load_log_directory).pack(side="left")
        ttk.Button(row, text="添加文件", command=self.add_log_files).pack(side="left")
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
        version_label = ttk.Label(status_row, text=f"v{APP_VERSION}", foreground=MUTED)
        version_label.pack(side="right")
        self.version_labels.append(version_label)
        self.log_plot_area = ttk.Frame(right)
        self.log_plot_area.pack(fill="both", expand=True)
        self.bind_class("LogSettingsScroll", "<MouseWheel>", self._scroll_log)
        self._install_scroll_tag(left, "LogSettingsScroll")

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

    def load_log_directory(self):
        folder = Path(self.log_directory_var.get())
        if not folder.is_dir():
            messagebox.showerror(self.tr("目录无效"), str(folder)); return
        self.log_files = []
        for path in sorted(folder.glob("*.log")):
            try:
                log_reader.read_header(path)
                self.log_files.append(path)
            except (OSError, ValueError):
                continue
        self.refresh_log_files()

    def add_log_files(self):
        paths = filedialog.askopenfilenames(filetypes=[("Atlas LOG", "*.log"), ("All files", "*.*")])
        invalid = []
        for path in map(Path, paths):
            try:
                log_reader.read_header(path)
                if path not in self.log_files:
                    self.log_files.append(path)
            except (OSError, ValueError):
                invalid.append(path.name)
        self.refresh_log_files()
        if invalid:
            messagebox.showwarning(self.tr("无法绘图的日志"),
                                   self.tr("这些文件不是 Atlas SSF 数据日志：\n") + "\n".join(invalid))

    def remove_log_files(self):
        for index in reversed(self.log_file_list.curselection()):
            self.log_files.pop(index)
        self.refresh_log_files()

    def clear_log_files(self):
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
        headers = [log_reader.read_header(path) for path in self.log_files]
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

    def load_directory(self):
        folder = Path(self.directory_var.get())
        if not folder.is_dir():
            messagebox.showerror(self.tr("目录无效"), str(folder)); return
        self.files = sorted(folder.glob("*.str"))
        self.refresh_files()

    def add_files(self):
        paths = filedialog.askopenfilenames(filetypes=[("Atlas STR", "*.str"), ("All files", "*.*")])
        for path in map(Path, paths):
            if path not in self.files: self.files.append(path)
        self.refresh_files()

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
            available = set(engine.list_field_codes(self.files[0]))
            for path in self.files[1:]:
                available.intersection_update(engine.list_field_codes(path))
            named = (available & set(FIELD_NAME_BY_CODE)) - DEFAULT_FIELD_CODES
            self.extra_field_codes = [code for code in engine.FIELD_DISPLAY_ORDER if code in named]
            for index, code in enumerate(self.extra_field_codes):
                name = (engine.FIELD_LABELS_BY_CODE[code] if self.language == "English"
                        else FIELD_NAME_BY_CODE[code])
                self.field_list.insert("end", self.tr(name))
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
        title = (engine.FIELD_LABELS_BY_CODE[code] if self.language == "English"
                 else FIELD_NAME_BY_CODE[code])
        self.open_field_settings(f"code:{code}", title)
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
        for label, key, choices in (
            ("色图", "cmap", ("默认", *engine.COLOR_PRESETS)),
            ("标度", "scale", ("默认", "linear", "log")),
            ("下限", "vmin", None),
            ("上限", "vmax", None),
            ("等值带数", "bands", None),
        ):
            row = ttk.Frame(body); row.pack(fill="x", pady=4)
            ttk.Label(row, text=self.tr(label), width=10).pack(side="left")
            variable = tk.StringVar(value=self.tr(values.get(key, "默认" if choices else "")))
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
                lower = optional_float(data["vmin"])
                upper = optional_float(data["vmax"])
                if lower is not None and upper is not None and upper <= lower:
                    raise ValueError("上限必须大于下限")
                if data["bands"] and int(data["bands"]) < 2:
                    raise ValueError("等值带数必须至少为 2")
            except ValueError as exc:
                messagebox.showerror(self.tr("参数无效"), self.tr(str(exc)), parent=dialog)
                return
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

    def settings(self):
        options = {key: variable.get() for key, variable in self.vars.items()}
        options["quantities"] = [q for q in QUANTITIES if self.quantity_vars[q].get()]
        options["quantities"].extend(
            f"code:{self.extra_field_codes[index]}" for index in self.field_list.curselection()
        )
        options["field_settings"] = {key: value.copy() for key, value in self.field_settings.items()}
        options["files"] = list(self.files)
        get = options.__getitem__
        quantities = options["quantities"]
        if not options["files"] or not quantities: raise ValueError("请选择至少一个 .str 文件和一个物理量")
        x0, x1, y0, y1 = (float(get(k)) for k in ("x0", "x1", "y0", "y1"))
        if x1 <= x0 or y1 <= y0: raise ValueError("显示范围的最大值必须大于最小值")
        if get("mirror") and math.isclose(x1, float(get("mirror_x"))): x1 = 2 * x1 - x0
        if not 0 < float(get("percentile")) <= 100: raise ValueError("百分位必须在 0–100 之间")
        # A zero lower bound is useful for linear plots. In log mode the
        # renderer interprets it as automatic positive lower bound.
        options["bounds"] = (x0, x1, y0, y1)
        return options

    def preview(self):
        self._start_render("str")

    def preview_log(self):
        self._start_render("log")

    def _start_render(self, kind):
        if self.busy: return
        try:
            options = self.settings() if kind == "str" else self.settings_log()
            options["kind"] = kind
            options["visual_edits"] = copy.deepcopy(self.figure_edits[kind])
            if kind == "log":
                options["signal_labels"] = self.log_field_labels.copy()
                options["visual_edits_by_code"] = copy.deepcopy(self.log_single_edits)
            self.busy = True
            self.draw_button.configure(state="disabled")
            self.export_button.configure(state="disabled")
            self.log_draw_button.configure(state="disabled")
            self.log_export_button.configure(state="disabled")
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
            elif isinstance(figure, list): self._show_log_batch(figure, options)
            else:
                if options["kind"] == "log":
                    self.log_rendered = []
                    self.log_preview_combo.pack_forget()
                    self.log_export_button.configure(text="导出图片")
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
            toolbar = NavigationToolbar2Tk(canvas, plot_area, pack_toolbar=False)
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
            editor.arrow_button = ttk.Button(toolbar, text="添加箭头", command=editor.start_arrow)
            editor.arrow_button.pack(side="left", padx=8)
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
            self.export_button.configure(state="normal")
            self.log_draw_button.configure(state="normal")
            self.log_export_button.configure(state="normal")

    def _active_kind(self):
        return "log" if self.notebook.index(self.notebook.select()) == 1 else "str"

    def _show_log_batch(self, rendered, options):
        self.log_rendered = rendered
        self.log_export_button.configure(text=f"导出全部 {len(rendered)} 张")
        labels = self._unique_display_names([label for _code, label, _, _ in rendered])
        self.log_preview_combo.configure(values=labels)
        self.log_preview_var.set(labels[0])
        if not self.log_preview_combo.winfo_manager():
            self.log_preview_combo.pack(side="left", padx=10)
        self._show_log_selection(0, options)

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
        self.export_button.configure(state="normal")
        self.log_draw_button.configure(state="normal")
        self.log_export_button.configure(state="normal")
        (self.log_status if kind == "log" else self.status).set("绘图失败")
        messagebox.showerror(self.tr("绘图失败"), self.tr(error))

    def export(self):
        self._export_kind("str")

    def export_log(self):
        self._export_kind("log")

    def _export_kind(self, kind):
        if self.busy: return
        figure = self.log_figure if kind == "log" else self.figure
        if figure is None:
            messagebox.showinfo(self.tr("请先画图"),
                                self.tr("点击顶部“画图 / 更新预览”，完成后再导出。"))
            return
        image_dir = Path(__file__).resolve().parent.parent / "imgs"
        image_dir.mkdir(exist_ok=True)
        if kind == "log":
            default_name = f"{self.log_files[0].parent.name}_log_curves.png" if self.log_files else "log_curves.png"
        else:
            default_name = f"{self.files[0].parent.name}_cloud_map.png" if self.files else "cloud_map.png"
        path = filedialog.asksaveasfilename(
            initialdir=str(image_dir), initialfile=default_name,
            defaultextension=".png",
            filetypes=[("PNG image", "*.png"), ("PDF document", "*.pdf"), ("SVG vector", "*.svg")],
        )
        if not path: return
        try:
            dpi_key = "log_dpi" if kind == "log" else "dpi"
            dpi = int(self.vars[dpi_key].get())
            if kind == "log" and self.log_rendered:
                base = Path(path)
                outputs = []
                for index, (code, label, item, _renderer) in enumerate(self.log_rendered, 1):
                    safe_label = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", label).strip(" ._")[:60] or "signal"
                    output = base.with_name(f"{base.stem}_{index}_{safe_label}{base.suffix}")
                    self._save_figure(item, output, dpi)
                    outputs.append(output)
                self.log_status.set(f"已导出 {len(outputs)} 张图片到：{base.parent}")
            else:
                self._save_figure(figure, path, dpi)
                (self.log_status if kind == "log" else self.status).set(f"已导出：{path}")
        except Exception as exc: messagebox.showerror(self.tr("导出失败"), self.tr(str(exc)))

    @staticmethod
    def _save_figure(figure, path, dpi):
        export_size = getattr(figure, "_tonyplot_export_size", None)
        if export_size is None:
            figure.savefig(path, dpi=dpi, bbox_inches="tight")
            return
        preview_size = tuple(figure.get_size_inches())
        try:
            figure.set_size_inches(*export_size, forward=False)
            figure.savefig(path, dpi=dpi, bbox_inches="tight")
        finally:
            figure.set_size_inches(*preview_size, forward=False)



