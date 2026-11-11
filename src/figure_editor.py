"""Double-click editor for figure text, axes, and physical dimensions."""
from __future__ import annotations

import math
import copy
import tkinter as tk
from tkinter import colorchooser, messagebox, ttk

from matplotlib.colors import is_color_like, to_hex
from matplotlib.text import Annotation

from .plotting.figure_edits import (
    add_arrow, apply_line_style, refresh_legend, set_tick_font_family, apply_colorbar_style,
)
from .plotting.font_presets import available_paper_fonts


class FigureEditor:
    def __init__(self, root, figure, canvas, edits: dict, status=None, on_commit=None):
        self.root = root
        self.figure = figure
        self.canvas = canvas
        self.edits = edits
        self.status = status
        self.on_commit = on_commit
        self.arrow_start = None
        self.arrow_mode = False
        self._material_drag = None
        canvas.mpl_connect("button_press_event", self.on_press)
        canvas.mpl_connect("button_release_event", self.on_release)

    def on_press(self, event):
        if event.button == 3:
            if not getattr(self.canvas.toolbar, "mode", ""):
                self.open_context_menu(event)
            return
        if event.button == 1 and not event.dblclick and not getattr(self.canvas.toolbar, "mode", ""):
            for axis in self.figure.axes:
                legend = axis.get_legend()
                if hasattr(axis, "_tonyplot_materials") and legend is not None and legend.contains(event)[0]:
                    self._material_drag = (axis, legend, copy.deepcopy(legend._loc))
                    break
        if self.arrow_mode and event.button == 1:
            self._arrow_click(event)
            return
        if not event.dblclick or event.button != 1:
            return
        for axis in self.figure.axes:
            legend = axis.get_legend()
            if hasattr(axis, "_tonyplot_materials") and legend is not None and legend.contains(event)[0]:
                self.edit_material_legend(axis)
                return
        for axis in self.figure.axes:
            if hasattr(axis, "_tonyplot_colorbar_key"):
                box = axis.get_tightbbox(self.canvas.get_renderer())
                if event.inaxes is axis or (box is not None and box.contains(event.x, event.y)):
                    self.edit_colorbar(axis)
                    return
        for axis in self.figure.axes:
            for artist in axis.texts:
                if isinstance(artist, Annotation) and hasattr(artist, "_tonyplot_arrow_index"):
                    hit, _ = artist.contains(event)
                    arrow_hit = (artist.arrow_patch is not None
                                 and artist.arrow_patch.contains(event)[0])
                    if hit or arrow_hit:
                        self.edit_arrow(artist._tonyplot_arrow_index, artist)
                        return
        for axis in self.figure.axes:
            for line in axis.lines:
                if hasattr(line, "_tonyplot_line_key") and line.contains(event)[0]:
                    self.edit_line(line)
                    return
        candidates = [("figure_title", self.figure._suptitle)]
        for index, axis in enumerate(self.figure.axes):
            candidates.extend((
                (f"axis:{index}:title", axis.title),
                (f"axis:{index}:left_title", axis._left_title),
                (f"axis:{index}:right_title", axis._right_title),
                (f"axis:{index}:xlabel", axis.xaxis.label),
                (f"axis:{index}:ylabel", axis.yaxis.label),
            ))
        for key, artist in candidates:
            if artist is not None and artist.get_visible() and artist.get_text():
                hit, _ = artist.contains(event)
                if hit:
                    self.edit_text(key, artist)
                    return
        for index, axis in enumerate(self.figure.axes):
            for label in (*axis.get_xticklabels(), *axis.get_yticklabels()):
                hit, _ = label.contains(event)
                if hit:
                    self.edit_axes(index, axis)
                    return
            if self._spine_hit(axis, event):
                self.edit_axes(index, axis)
                return
        if event.inaxes is not None:
            self.edit_axes(self.figure.axes.index(event.inaxes), event.inaxes)
        else:
            self.edit_figure()

    def on_release(self, event):
        if self._material_drag is None:
            return
        axis, legend, old_position = self._material_drag
        self._material_drag = None
        if legend._loc == old_position:
            return
        if hasattr(self.root, "checkpoint_edit") and hasattr(self, "edit_kind"):
            self.root.checkpoint_edit(self.edit_kind)
        values = copy.deepcopy(axis._tonyplot_material_legend_style)
        values["location"] = tuple(legend._loc)
        axis._tonyplot_material_legend_style = values
        self.edits.setdefault("material_legends", {})[axis._tonyplot_axis_key] = copy.deepcopy(values)
        if self.on_commit is not None:
            self.on_commit()

    def open_context_menu(self, event):
        menu = tk.Menu(self.root, tearoff=False)
        self.context_menu = menu
        tr = self.root.tr if hasattr(self.root, "tr") else str

        def edit_target():
            target = copy.copy(event)
            target.button = 1
            target.dblclick = True
            self.arrow_mode = False
            self.on_press(target)

        menu.add_command(label=tr("编辑此元素…"), command=edit_target)
        menu.add_command(label=tr("编辑图片尺寸"), command=self.edit_figure)
        menu.add_command(label=tr("添加箭头"), command=self.start_arrow)
        if hasattr(self.root, "undo_edit") and hasattr(self, "edit_kind"):
            menu.add_separator()
            menu.add_command(label=tr("撤销"), command=lambda: self.root.undo_edit(self.edit_kind))
        if hasattr(self.root, "save_plot_set"):
            menu.add_separator()
            menu.add_command(label=tr("保存配置"), command=self.root.save_plot_set)
            menu.add_command(label=tr("导入配置"), command=self.root.import_plot_set)
        gui = getattr(event, "guiEvent", None)
        if gui is not None and hasattr(gui, "x_root"):
            x, y = gui.x_root, gui.y_root
        else:
            widget = self.canvas.get_tk_widget()
            dx, dy = getattr(self.canvas, "_image_offset", (0, 0))
            x = widget.winfo_rootx() + event.x + dx
            y = widget.winfo_rooty() + self.figure.bbox.height - event.y + dy
        try:
            menu.tk_popup(int(x), int(y))
        finally:
            menu.grab_release()

    def _dialog(self, title, scroll=True):
        window = tk.Toplevel(self.root)
        window.title(self.root.tr(title) if hasattr(self.root, "tr") else title)
        window.transient(self.root)
        window.resizable(False, False)
        window.configure(bg=self.root.cget("bg"))
        window.grab_set()
        body = ttk.Frame(window, padding=16)
        body.pack(fill="both", expand=True)
        if scroll:
            window.geometry(f"480x{min(720, self.root.winfo_screenheight() - 120)}")
            viewport = tk.Canvas(body, highlightthickness=0)
            scrollbar = ttk.Scrollbar(body, orient="vertical", command=viewport.yview)
            viewport.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side="right", fill="y")
            viewport.pack(side="left", fill="both", expand=True)
            content = ttk.Frame(viewport)
            item = viewport.create_window((0, 0), window=content, anchor="nw")
            content.bind("<Configure>", lambda _event: viewport.configure(scrollregion=viewport.bbox("all")))
            viewport.bind("<Configure>", lambda event: viewport.itemconfigure(item, width=event.width))
            window.bind("<MouseWheel>", lambda event: viewport.yview_scroll(-int(event.delta / 120), "units"))
            body = content
        if hasattr(self.root, "tooltips"):
            def finish_dialog():
                if window.winfo_exists():
                    if hasattr(self.root, "_localize_tree"):
                        self.root._localize_tree(window)
                    style = ttk.Style(self.root)
                    style.configure("Editor.TLabel", font=("Segoe UI", 10))
                    style.configure("Editor.TCheckbutton", font=("Segoe UI", 10))
                    style.configure("Editor.TButton", font=("Segoe UI", 9), padding=(8, 5))
                    def compact(widget):
                        if isinstance(widget, ttk.Label):
                            widget.configure(style="Editor.TLabel", width=0, wraplength=145)
                        elif isinstance(widget, (ttk.Entry, ttk.Combobox)):
                            widget.configure(font=("Segoe UI", 10))
                        elif isinstance(widget, ttk.Checkbutton):
                            widget.configure(style="Editor.TCheckbutton")
                        elif isinstance(widget, ttk.Button):
                            widget.configure(style="Editor.TButton")
                        children = widget.winfo_children()
                        captions = [child for child in children if isinstance(child, ttk.Label)]
                        controls = [child for child in children if isinstance(child, (ttk.Entry, ttk.Combobox))]
                        if len(captions) == 1 and controls:
                            for child in children:
                                child.pack_forget()
                            widget.columnconfigure(0, minsize=155)
                            widget.columnconfigure(1, weight=1)
                            captions[0].grid(row=0, column=0, sticky="w", padx=(0, 8))
                            for index, control in enumerate(child for child in children if child is not captions[0]):
                                control.grid(row=0, column=index + 1, sticky="ew", padx=(0, 4))
                        for child in children:
                            compact(child)
                    compact(body)
                    window.update_idletasks()
                    if scroll:
                        window.geometry(f"500x{min(body.winfo_reqheight() + 36, self.root.winfo_screenheight() - 120)}")
                    self.root.tooltips.register_tree(window)
            window.after_idle(finish_dialog)
        return window, body

    @staticmethod
    def _entry(parent, label, value):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text=label, width=12).pack(side="left")
        variable = tk.StringVar(value=str(value))
        ttk.Entry(row, textvariable=variable, width=30).pack(side="left")
        return variable

    def _buttons(self, window, body, preview, commit, rollback, preview_command=None):
        row = ttk.Frame(body)
        row.pack(fill="x", pady=(12, 0))

        def cancel():
            rollback()
            window.destroy()

        def apply():
            if preview():
                if hasattr(self.root, "checkpoint_edit") and hasattr(self, "edit_kind"):
                    self.root.checkpoint_edit(self.edit_kind)
                commit()
                if self.on_commit is not None:
                    self.on_commit()
                window.destroy()

        ttk.Button(row, text="取消", command=cancel).pack(side="right")
        ttk.Button(row, text="确定并关闭", command=apply,
                   style="Accent.TButton").pack(side="right", padx=8)
        ttk.Button(row, text="预览", command=preview_command or preview).pack(side="right")
        window.protocol("WM_DELETE_WINDOW", cancel)
        window.bind("<Return>", lambda _event: apply())
        window.bind("<Escape>", lambda _event: cancel())

    @staticmethod
    def _color_entry(parent, initial, label="颜色"):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text=label, width=12).pack(side="left")
        value = tk.StringVar(value=str(initial))
        ttk.Entry(row, textvariable=value, width=20).pack(side="left")

        def choose():
            chosen = colorchooser.askcolor(color=value.get(), parent=parent.winfo_toplevel())[1]
            if chosen:
                value.set(chosen)

        ttk.Button(row, text="选择…", command=choose).pack(side="left", padx=5)
        return value

    @staticmethod
    def _valid_color(value):
        if not is_color_like(value):
            raise ValueError("请输入有效颜色，例如 #2563eb")
        return value

    @staticmethod
    def _font_entry(parent, current, label="字体"):
        family = current[0] if isinstance(current, (list, tuple)) else str(current)
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text=label, width=12).pack(side="left")
        value = tk.StringVar(value=family)
        ttk.Combobox(row, textvariable=value, values=available_paper_fonts(family),
                     state="readonly", width=27).pack(side="left")
        return value

    @staticmethod
    def _y_spine(axis):
        return axis.spines["right" if axis.yaxis.get_ticks_position() == "right" else "left"]

    @staticmethod
    def _spine_hit(axis, event, tolerance=6):
        bounds = axis.bbox
        on_horizontal = bounds.x0 - tolerance <= event.x <= bounds.x1 + tolerance
        on_vertical = bounds.y0 - tolerance <= event.y <= bounds.y1 + tolerance
        return bool(
            (axis.spines["bottom"].get_visible() and on_horizontal
             and abs(event.y - bounds.y0) <= tolerance)
            or (axis.spines["top"].get_visible() and on_horizontal
                and abs(event.y - bounds.y1) <= tolerance)
            or (axis.spines["left"].get_visible() and on_vertical
                and abs(event.x - bounds.x0) <= tolerance)
            or (axis.spines["right"].get_visible() and on_vertical
                and abs(event.x - bounds.x1) <= tolerance)
        )

    def start_arrow(self):
        if self.arrow_mode:
            self.arrow_mode = False
            self.arrow_start = None
            if hasattr(self, "arrow_button"):
                self.arrow_button.configure(text="添加箭头")
            if self.status is not None:
                self.status.set("已取消添加箭头")
            return
        toolbar = getattr(self.canvas, "toolbar", None)
        if toolbar is not None and toolbar.mode:
            messagebox.showinfo("添加箭头", "请先关闭工具栏的平移或缩放模式")
            return
        self.arrow_mode = True
        self.arrow_start = None
        if hasattr(self, "arrow_button"):
            self.arrow_button.configure(text="取消箭头")
        if self.status is not None:
            self.status.set("请在图中点击箭头起点，再点击箭头终点")

    def _arrow_click(self, event):
        if event.inaxes is None or event.xdata is None or event.ydata is None:
            return
        axis_index = self.figure.axes.index(event.inaxes)
        point = (float(event.xdata), float(event.ydata))
        if self.arrow_start is None or self.arrow_start[0] != axis_index:
            self.arrow_start = (axis_index, point)
            if self.status is not None:
                self.status.set("已确定起点；请在同一子图点击箭头终点")
            return
        start_index, start_point = self.arrow_start
        self.arrow_mode = False
        self.arrow_start = None
        if hasattr(self, "arrow_button"):
            self.arrow_button.configure(text="添加箭头")
        self._arrow_dialog(start_index, start_point, point)

    def _arrow_dialog(self, axis_index, start, end, index=None, artist=None):
        window, body = self._dialog("编辑箭头标注" if index is not None else "添加箭头标注")
        old = copy.deepcopy(self.edits["arrows"][index]) if index is not None else {}
        value = self._entry(body, "标注文字", old.get("text", ""))
        size = self._entry(body, "字号 (pt)", old.get("size", 9))
        font_family = self._font_entry(body, old.get("font_family", "Arial"))
        color = self._color_entry(body, old.get("color", "#e84050"))
        width = self._entry(body, "箭头线宽", old.get("linewidth", 1.2))
        current_artist = [artist]
        latest = [None]
        delete_requested = [False]

        def values_from_form():
            font_size = float(size.get())
            line_width = float(width.get())
            if not math.isfinite(font_size) or not 5 <= font_size <= 72:
                raise ValueError("字号需在 5–72 pt 之间")
            if not math.isfinite(line_width) or not 0.2 <= line_width <= 10:
                raise ValueError("箭头线宽需在 0.2–10 之间")
            return {"axis": axis_index, "xytext": start, "xy": end,
                    "text": value.get(), "size": font_size,
                    "color": self._valid_color(color.get()), "linewidth": line_width,
                    "font_family": font_family.get()}

        def preview():
            if delete_requested[0]:
                if current_artist[0] is not None:
                    current_artist[0].remove()
                    current_artist[0] = None
                self.canvas.draw_idle()
                return True
            try:
                values = values_from_form()
            except ValueError as exc:
                messagebox.showerror("参数无效", str(exc), parent=window)
                return False
            if current_artist[0] is not None:
                current_artist[0].remove()
            current_artist[0] = add_arrow(
                self.figure, values,
                len(self.edits.get("arrows", [])) if index is None else index,
            )
            latest[0] = values
            self.canvas.draw_idle()
            return True

        def commit():
            arrows = self.edits.setdefault("arrows", [])
            if delete_requested[0]:
                arrows.pop(index)
                for axis in self.figure.axes:
                    for other in axis.texts:
                        other_index = getattr(other, "_tonyplot_arrow_index", -1)
                        if other_index > index:
                            other._tonyplot_arrow_index = other_index - 1
            elif index is None:
                arrows.append(latest[0])
            else:
                arrows[index] = latest[0]
            if self.status is not None:
                self.status.set("箭头标注已删除" if delete_requested[0]
                                else "箭头标注已添加" if index is None
                                else "箭头标注已更新")

        def rollback():
            if current_artist[0] is not None and current_artist[0] is not artist:
                current_artist[0].remove()
            if index is not None and artist not in self.figure.axes[axis_index].texts:
                add_arrow(self.figure, old, index)
            self.canvas.draw_idle()

        def preview_changes():
            delete_requested[0] = False
            return preview()

        self._buttons(window, body, preview, commit, rollback,
                      preview_command=preview_changes)
        if index is not None:
            def preview_delete():
                delete_requested[0] = True
                preview()

            ttk.Button(body, text="预览删除", command=preview_delete).pack(anchor="w", pady=(4, 0))
        window.focus_set()

    def edit_arrow(self, index, artist):
        values = self.edits["arrows"][index]
        self._arrow_dialog(values["axis"], values["xytext"], values["xy"], index, artist)

    def edit_line(self, line):
        window, body = self._dialog("编辑曲线")
        legend_axis = line._tonyplot_legend_axis
        legend = legend_axis.get_legend()
        figure_title = self.figure._suptitle
        original_title = figure_title.get_text() if figure_title is not None else ""
        original_title_size = figure_title.get_fontsize() if figure_title is not None else 9
        original_legend_title = getattr(legend_axis, "_tonyplot_legend_title", "")
        original = {
            "color": line.get_color(), "linewidth": line.get_linewidth(),
            "linestyle": line.get_linestyle(), "marker": line.get_marker(),
            "markersize": line.get_markersize(), "label": line.get_label(),
            "legend_size": getattr(line, "_tonyplot_legend_size", 7.5),
            "legend_font_family": getattr(line, "_tonyplot_legend_font_family", "Arial"),
        }
        color = self._color_entry(body, original["color"], "曲线颜色")
        width = self._entry(body, "曲线线宽", f"{original['linewidth']:g}")

        def choice(label, current, options):
            row = ttk.Frame(body)
            row.pack(fill="x", pady=4)
            ttk.Label(row, text=label, width=12).pack(side="left")
            variable = tk.StringVar(value=current)
            ttk.Combobox(row, textvariable=variable, values=options,
                         state="readonly", width=27).pack(side="left")
            return variable

        linestyle = choice("线型", original["linestyle"], ("-", "--", "-.", ":", "None"))
        marker = choice("数据点形状", original["marker"],
                        ("None", "o", "s", "^", "D", "v", "x", "+", "*", "."))
        marker_size = self._entry(body, "数据点大小", f"{original['markersize']:g}")
        legend_label = self._entry(body, "图例名称", original["label"])
        legend_size = self._entry(body, "图例字号", f"{original['legend_size']:g}")
        legend_font = self._font_entry(body, original["legend_font_family"], "图例字体")
        legend_title = self._entry(body, "图例标题", original_legend_title)
        title = self._entry(body, "图标题", original_title)
        title_size = self._entry(body, "标题字号", f"{original_title_size:g}")

        def values_from_form():
            line_width = float(width.get())
            point_size = float(marker_size.get())
            label_size = float(legend_size.get())
            heading_size = float(title_size.get())
            if not all(math.isfinite(v) for v in (line_width, point_size, label_size, heading_size)):
                raise ValueError("线宽和字号必须是有限数值")
            if not 0.2 <= line_width <= 20:
                raise ValueError("曲线线宽需在 0.2–20 pt 之间")
            if not 0 <= point_size <= 30:
                raise ValueError("数据点大小需在 0–30 pt 之间")
            if not 5 <= label_size <= 40 or not 5 <= heading_size <= 72:
                raise ValueError("图例或标题字号超出范围")
            if linestyle.get() == "None" and marker.get() == "None":
                raise ValueError("线型和数据点形状不能同时为 None")
            return {
                "color": self._valid_color(color.get()), "linewidth": line_width,
                "linestyle": linestyle.get(), "marker": marker.get(),
                "markersize": point_size, "label": legend_label.get(),
                "legend_size": label_size,
                "legend_font_family": legend_font.get(),
            }, heading_size

        def preview():
            try:
                values, heading_size = values_from_form()
            except ValueError as exc:
                messagebox.showerror("参数无效", str(exc), parent=window)
                return False
            apply_line_style(line, values)
            legend_axis._tonyplot_legend_title = legend_title.get()
            refresh_legend(legend_axis)
            if title.get() or self.figure._suptitle is not None:
                self.figure.suptitle(title.get(), fontsize=heading_size)
            self.figure.tight_layout(pad=0.5)
            self.canvas.draw_idle()
            return True

        def commit():
            values, heading_size = values_from_form()
            self.edits.setdefault("lines", {})[line._tonyplot_line_key] = values
            axis_index = self.figure.axes.index(legend_axis)
            self.edits.setdefault("legend_titles", {})[str(axis_index)] = legend_title.get()
            if title.get() != original_title or figure_title is not None:
                artist = self.figure._suptitle
                self.edits.setdefault("texts", {})["figure_title"] = {
                    "text": title.get(), "size": heading_size,
                    "color": artist.get_color(),
                    "font_family": artist.get_fontfamily()[0],
                }

        def rollback():
            apply_line_style(line, original)
            legend_axis._tonyplot_legend_title = original_legend_title
            refresh_legend(legend_axis)
            if figure_title is None and self.figure._suptitle is not None:
                self.figure._suptitle.remove()
                self.figure._suptitle = None
            elif figure_title is not None:
                figure_title.set_text(original_title)
                figure_title.set_fontsize(original_title_size)
            self.figure.tight_layout(pad=0.5)
            self.canvas.draw_idle()

        self._buttons(window, body, preview, commit, rollback)
        window.focus_set()

    def edit_colorbar(self, axis):
        self.canvas.draw()
        window, body = self._dialog("编辑色棒")
        bars = [item for item in self.figure.axes if hasattr(item, "_tonyplot_colorbar_key")]
        originals = {}
        for item in bars:
            box = item.get_position()
            width, height = self.figure.get_size_inches()
            ticks = item.get_yticklabels()
            values = getattr(item, "_tonyplot_colorbar_style", {
                "width": box.width * width, "height": box.height * height,
                "dx": 0., "dy": 0., "label": item.get_ylabel(),
                "label_size": item.yaxis.label.get_fontsize(),
                "tick_size": ticks[0].get_fontsize() if ticks else 8,
                "font_family": item.yaxis.label.get_fontfamily()[0],
                "color": to_hex(item.yaxis.label.get_color()),
                "linewidth": item._colorbar.outline.get_linewidth(),
            }).copy()
            originals[item] = (values, item.get_axes_locator(), item.get_box_aspect(),
                               item.get_aspect(), hasattr(item, "_tonyplot_colorbar_style"),
                               ticks[0].get_color() if ticks else values["color"],
                               item._colorbar.outline.get_edgecolor(),
                               getattr(item, "_colorbar_info", {}).get("aspect"))
        original = originals[axis][0]
        fields = {}
        for label, key in (("色棒长度 (英寸)", "height"), ("色棒宽度 (英寸)", "width"),
                           ("水平偏移 (英寸)", "dx"), ("垂直偏移 (英寸)", "dy"),
                           ("标签字号", "label_size"), ("刻度字号", "tick_size"),
                           ("边框线宽", "linewidth")):
            fields[key] = self._entry(body, label, f"{original[key]:.4g}")
        label = self._entry(body, "色棒标签", original["label"])
        family = self._font_entry(body, original["font_family"])
        color = self._color_entry(body, original["color"])
        all_bars = tk.BooleanVar(value=False)
        ttk.Checkbutton(body, text="将尺寸和样式应用到全部色棒", variable=all_bars).pack(anchor="w", pady=5)
        pending = {}

        def rollback():
            for item, (values, locator, box_aspect, aspect, had_style, tick_color, border_color, bar_aspect) in originals.items():
                apply_colorbar_style(item, values)
                item.set_axes_locator(locator)
                item.set_box_aspect(box_aspect)
                item.set_aspect(aspect)
                if bar_aspect is not None:
                    item._colorbar_info["aspect"] = bar_aspect
                item.tick_params(colors=tick_color)
                item._colorbar.outline.set_edgecolor(border_color)
                if not had_style:
                    del item._tonyplot_colorbar_style
            self.canvas.draw_idle()

        def preview():
            try:
                values = {key: float(value.get()) for key, value in fields.items()}
                if not all(math.isfinite(value) for value in values.values()):
                    raise ValueError("请输入有限数值")
                if values["width"] <= 0 or values["height"] <= 0:
                    raise ValueError("色棒长度和宽度必须大于 0")
                if not 5 <= values["label_size"] <= 72 or not 5 <= values["tick_size"] <= 72 or not 0 <= values["linewidth"] <= 10:
                    raise ValueError("色棒字号或线宽超出范围")
                values.update(label=label.get(), font_family=family.get(), color=self._valid_color(color.get()))
            except ValueError as exc:
                messagebox.showerror("参数无效", str(exc), parent=window)
                return False
            rollback()
            pending.clear()
            for item in bars if all_bars.get() else [axis]:
                style = values.copy()
                if item is not axis:
                    style["label"] = originals[item][0]["label"]
                apply_colorbar_style(item, style)
                pending[item._tonyplot_colorbar_key] = style
            self.canvas.draw_idle()
            return True

        def commit():
            self.edits.setdefault("colorbars", {}).update(copy.deepcopy(pending))

        self._buttons(window, body, preview, commit, rollback)
        window.focus_set()

    def edit_text(self, key, artist):
        window, body = self._dialog("编辑图中文字")
        original = {"text": artist.get_text(), "size": artist.get_fontsize(),
                    "font_family": artist.get_fontfamily()[0], "color": artist.get_color(),
                    "weight": artist.get_fontweight()}
        value = self._entry(body, "内容", original["text"])
        size = self._entry(body, "字号 (pt)", f"{original['size']:g}")
        font_family = self._font_entry(body, original["font_family"])
        color = self._color_entry(body, original["color"])
        weight = original["weight"]
        bold = tk.BooleanVar(value=weight in ("bold", "heavy", "black", "semibold", "demibold")
                             or isinstance(weight, (int, float)) and weight >= 600)
        ttk.Checkbutton(body, text="加粗", variable=bold).pack(anchor="w", pady=4)

        def preview():
            try:
                font_size = float(size.get())
                if not 5 <= font_size <= 72 or not math.isfinite(font_size):
                    raise ValueError("字号需在 5–72 pt 之间")
                text_color = self._valid_color(color.get())
            except ValueError as exc:
                messagebox.showerror("参数无效", str(exc), parent=window)
                return False
            artist.set_text(value.get())
            artist.set_fontsize(font_size)
            artist.set_fontfamily(font_family.get())
            artist.set_color(text_color)
            artist.set_fontweight("bold" if bold.get() else "normal")
            self.canvas.draw_idle()
            return True

        def commit():
            previous = self.edits.get("texts", {}).get(key, {})
            self.edits.setdefault("texts", {})[key] = {
                "text": artist.get_text(), "size": artist.get_fontsize(),
                "color": artist.get_color(),
                "font_family": font_family.get(),
                "weight": artist.get_fontweight(),
            }
            if (self.on_commit is not None and key.endswith(":title")
                    and artist.get_text() == original["text"] and previous.get("preserve_text", not previous)):
                self.edits["texts"][key]["preserve_text"] = True
            if key != "figure_title":
                axis = self.figure.axes[int(key.split(":")[1])]
                if hasattr(axis, "_tonyplot_axis_key"):
                    self.edits["texts"][key]["axis_key"] = axis._tonyplot_axis_key

        def rollback():
            artist.set_text(original["text"])
            artist.set_fontsize(original["size"])
            artist.set_fontfamily(original["font_family"])
            artist.set_color(original["color"])
            artist.set_fontweight(original["weight"])
            self.canvas.draw_idle()

        self._buttons(window, body, preview, commit, rollback)
        window.focus_set()

    def edit_axes(self, index, axis):
        window, body = self._dialog("编辑坐标轴")
        xlim, ylim = axis.get_xlim(), axis.get_ylim()
        x0 = self._entry(body, "横轴左边界", f"{xlim[0]:g}")
        x1 = self._entry(body, "横轴右边界", f"{xlim[1]:g}")
        y0 = self._entry(body, "纵轴下边界", f"{ylim[0]:g}")
        y1 = self._entry(body, "纵轴上边界", f"{ylim[1]:g}")
        tick_labels = axis.xaxis.get_ticklabels() or axis.yaxis.get_ticklabels()
        current_tick_size = tick_labels[0].get_fontsize() if tick_labels else 8
        original = {
            "xlim": tuple(xlim), "ylim": tuple(ylim),
            "xscale": axis.get_xscale(), "yscale": axis.get_yscale(),
            "tick_size": current_tick_size,
            "tick_color": tick_labels[0].get_color() if tick_labels else "#1e293b",
            "tick_font_family": tick_labels[0].get_fontfamily()[0] if tick_labels else "Arial",
            "x_spine_color": to_hex(axis.spines["bottom"].get_edgecolor()),
            "y_spine_color": to_hex(self._y_spine(axis).get_edgecolor()),
        }
        tick_size = self._entry(body, "刻度字号", f"{current_tick_size:g}")
        tick_family = self._font_entry(body, original["tick_font_family"], "刻度字体")
        tick_color = self._color_entry(body, original["tick_color"], "刻度颜色")
        x_spine_color = self._color_entry(body, original["x_spine_color"], "横轴线颜色")
        y_spine_color = self._color_entry(body, original["y_spine_color"], "纵轴线颜色")
        xscale = tk.StringVar(value=axis.get_xscale())
        yscale = tk.StringVar(value=axis.get_yscale())
        for label, variable in (("横轴标度", xscale), ("纵轴标度", yscale)):
            row = ttk.Frame(body); row.pack(fill="x", pady=4)
            ttk.Label(row, text=label, width=12).pack(side="left")
            ttk.Combobox(row, textvariable=variable, values=("linear", "log"),
                         state="readonly", width=27).pack(side="left")

        def preview():
            try:
                xx = (float(x0.get()), float(x1.get()))
                yy = (float(y0.get()), float(y1.get()))
                tick = float(tick_size.get())
                if not all(map(math.isfinite, (*xx, *yy, tick))):
                    raise ValueError("边界和字号必须是有限数值")
                if xx[0] == xx[1] or yy[0] == yy[1]:
                    raise ValueError("坐标轴两端不能相等")
                if not 5 <= tick <= 40:
                    raise ValueError("刻度字号需在 5–40 pt 之间")
                color = self._valid_color(tick_color.get())
                x_line_color = self._valid_color(x_spine_color.get())
                y_line_color = self._valid_color(y_spine_color.get())
                if xscale.get() == "log" and min(xx) <= 0:
                    raise ValueError("log 横轴边界必须为正")
                if yscale.get() == "log" and min(yy) <= 0:
                    raise ValueError("log 纵轴边界必须为正")
            except ValueError as exc:
                messagebox.showerror("参数无效", str(exc), parent=window)
                return False
            axis.set_xscale(xscale.get())
            axis.set_yscale(yscale.get())
            axis.set_xlim(*xx)
            axis.set_ylim(*yy)
            axis.tick_params(axis="both", labelsize=tick, colors=color)
            set_tick_font_family(axis, tick_family.get())
            axis.spines["bottom"].set_color(x_line_color)
            self._y_spine(axis).set_color(y_line_color)
            self.canvas.draw_idle()
            return True

        def commit():
            self.edits.setdefault("axes", {})[str(index)] = {
                "xlim": tuple(axis.get_xlim()), "ylim": tuple(axis.get_ylim()),
                "xscale": axis.get_xscale(), "yscale": axis.get_yscale(),
                "tick_size": float(tick_size.get()), "tick_color": tick_color.get(),
                "tick_font_family": tick_family.get(),
                "x_spine_color": x_spine_color.get(),
                "y_spine_color": y_spine_color.get(),
            }
            if hasattr(axis, "_tonyplot_axis_key"):
                self.edits["axes"][str(index)]["axis_key"] = axis._tonyplot_axis_key
            if hasattr(self.figure, "_tonyplot_str_view"):
                self.edits["axes"][str(index)]["str_view"] = self.figure._tonyplot_str_view

        def rollback():
            axis.set_xscale(original["xscale"])
            axis.set_yscale(original["yscale"])
            axis.set_xlim(*original["xlim"])
            axis.set_ylim(*original["ylim"])
            axis.tick_params(axis="both", labelsize=original["tick_size"],
                             colors=original["tick_color"])
            set_tick_font_family(axis, original["tick_font_family"])
            axis.spines["bottom"].set_color(original["x_spine_color"])
            self._y_spine(axis).set_color(original["y_spine_color"])
            self.canvas.draw_idle()

        self._buttons(window, body, preview, commit, rollback)
        window.focus_set()

    def edit_material_legend(self, axis):
        from .plotting.material_renderer import apply_material_legend
        window, body = self._dialog("编辑材料图例", scroll=True)
        original = copy.deepcopy(axis._tonyplot_material_legend_style)
        title = self._entry(body, "图例标题", original.get("title", ""))
        size = self._entry(body, "图例字号", original.get("size", 7))
        title_size = self._entry(body, "标题字号", original.get("title_size", 8))
        columns = self._entry(body, "图例列数", original.get("columns", 1))
        family = self._font_entry(body, original.get("font_family", "Arial"))
        color = self._color_entry(body, original.get("color", "#1e293b"), "文字颜色")
        original_location = original.get("location", "lower right")
        location = tk.StringVar(value="custom" if isinstance(original_location, (tuple, list)) else original_location)
        box = axis.get_legend().get_window_extent(self.canvas.get_renderer())
        anchor = axis.transAxes.inverted().transform((box.x0, box.y0))
        position_x = self._entry(body, "图例水平位置", f"{anchor[0]:.4g}")
        position_y = self._entry(body, "图例垂直位置", f"{anchor[1]:.4g}")
        row = ttk.Frame(body); row.pack(fill="x", pady=4)
        ttk.Label(row, text="图例位置", width=12).pack(side="left")
        ttk.Combobox(row, textvariable=location, state="readonly", width=30,
                     values=("custom", "lower right", "lower left", "upper right", "upper left", "center right", "center left", "upper center", "lower center", "center")).pack(side="left")
        if hasattr(self.root, "tooltips"):
            hint = "custom：位置按坐标区比例设置；也可直接拖动图例"
            for control in row.winfo_children():
                self.root.tooltips.register(control, hint)
        bold = tk.BooleanVar(value=original.get("bold", False))
        frame = tk.BooleanVar(value=original.get("frame", False))
        ttk.Checkbutton(body, text="加粗", variable=bold).pack(anchor="w")
        ttk.Checkbutton(body, text="显示图例底色与边框", variable=frame).pack(anchor="w")
        entries = {}
        for name, item in axis._tonyplot_materials.items():
            saved = original.get("entries", {}).get(name, {})
            label = self._entry(body, name, saved.get("label", name))
            fill = self._color_entry(body, saved.get("color", item["color"]), "材料颜色")
            entries[name] = (label, fill)
        pending = {}

        def preview():
            try:
                values = {"title": title.get(), "size": float(size.get()),
                          "title_size": float(title_size.get()), "columns": int(columns.get()),
                          "font_family": family.get(), "color": self._valid_color(color.get()),
                          "location": location.get(), "bold": bold.get(), "frame": frame.get(),
                          "entries": {name: {"label": label.get(), "color": self._valid_color(fill.get())}
                                      for name, (label, fill) in entries.items()}}
                if not (5 <= values["size"] <= 72 and 5 <= values["title_size"] <= 72 and 1 <= values["columns"] <= 10):
                    raise ValueError("图例字号或列数超出范围")
                if location.get() == "custom":
                    position = (float(position_x.get()), float(position_y.get()))
                    if not all(math.isfinite(value) for value in position):
                        raise ValueError("请输入有限数值")
                    values["location"] = position
            except ValueError as exc:
                messagebox.showerror("参数无效", str(exc), parent=window)
                return False
            pending.clear(); pending.update(values)
            apply_material_legend(axis, values)
            self.canvas.draw_idle()
            return True

        def commit():
            self.edits.setdefault("material_legends", {})[axis._tonyplot_axis_key] = copy.deepcopy(pending)

        def rollback():
            apply_material_legend(axis, original)
            self.canvas.draw_idle()

        self._buttons(window, body, preview, commit, rollback)
        window.focus_set()

    def edit_figure(self):
        window, body = self._dialog("编辑图片尺寸")
        width, height = getattr(self.figure, "_tonyplot_export_size", self.figure.get_size_inches())
        preview_size = tuple(self.figure.get_size_inches())
        original_export_size = getattr(self.figure, "_tonyplot_export_size", None)
        tr = self.root.tr if hasattr(self.root, "tr") else str
        modes = ("宽高比例", "毫米 (mm)", "像素 (px)")
        mode = tk.StringVar(value=tr(modes[0]))
        row = ttk.Frame(body); row.pack(fill="x", pady=4)
        ttk.Label(row, text=tr("尺寸方式"), width=12).pack(side="left")
        selector = ttk.Combobox(row, textvariable=mode, values=[tr(item) for item in modes],
                                state="readonly", width=30)
        selector.pack(side="left")
        width_var = self._entry(body, "宽度 / 比例", f"{20 * width / max(width, height):g}")
        height_var = self._entry(body, "高度 / 比例", f"{20 * height / max(width, height):g}")
        long_edge = self._entry(body, "比例模式长边 (mm)", "160")
        if hasattr(self.root, "tooltips"):
            hint = "比例 10:20 默认导出为 80×160 mm；器件坐标仍为 µm"
            for field_row in body.winfo_children():
                for control in field_row.winfo_children():
                    self.root.tooltips.register(control, hint)
        dpi_key = "log_dpi" if getattr(self, "edit_kind", "str") == "log" else "dpi"
        export_dpi = int(self.root.vars[dpi_key].get()) if hasattr(self.root, "vars") else 300
        pending_size = None

        def dimensions(unit):
            w, h = float(width_var.get()), float(height_var.get())
            if not all(math.isfinite(value) and value > 0 for value in (w, h)):
                raise ValueError("宽度和高度必须是大于 0 的有限数值")
            if unit == modes[0]:
                edge = float(long_edge.get())
                if not math.isfinite(edge) or edge <= 0:
                    raise ValueError("宽度和高度必须是大于 0 的有限数值")
                return (edge / 25.4 * w / max(w, h), edge / 25.4 * h / max(w, h))
            return (w / 25.4, h / 25.4) if unit == modes[1] else (w / export_dpi, h / export_dpi)

        current_mode = modes[0]

        def change_mode(_event):
            nonlocal current_mode
            try:
                size = dimensions(current_mode)
            except ValueError:
                size = (160 / 25.4 * width / max(width, height), 160 / 25.4 * height / max(width, height))
            current_mode = next(item for item in modes if tr(item) == mode.get())
            factor = 20 / max(size) if current_mode == modes[0] else (25.4 if current_mode == modes[1] else export_dpi)
            width_var.set(f"{size[0] * factor:g}")
            height_var.set(f"{size[1] * factor:g}")
            if current_mode == modes[0]:
                long_edge.set(f"{max(size) * 25.4:g}")

        selector.bind("<<ComboboxSelected>>", change_mode)

        def preview():
            nonlocal pending_size
            try:
                unit = next(item for item in modes if tr(item) == mode.get())
                size = dimensions(unit)
            except ValueError as exc:
                messagebox.showerror("参数无效", str(exc), parent=window)
                return False
            pending_size = size
            if hasattr(self.canvas, "set_preview_size"):
                self.canvas.set_preview_size(size)
            else:
                self.figure.set_size_inches(*size, forward=False)
                self.canvas.draw_idle()
            return True

        def commit():
            self.edits["figure_size"] = pending_size

        def rollback():
            self.figure.set_size_inches(*preview_size, forward=False)
            if original_export_size is None:
                if hasattr(self.figure, "_tonyplot_export_size"):
                    del self.figure._tonyplot_export_size
            else:
                self.figure._tonyplot_export_size = original_export_size
            self.canvas.draw_idle()

        self._buttons(window, body, preview, commit, rollback)
        window.focus_set()
