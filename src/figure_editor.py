"""Double-click editor for figure text, axes, and physical dimensions."""
from __future__ import annotations

import math
import copy
import tkinter as tk
from tkinter import colorchooser, messagebox, ttk

from matplotlib.colors import is_color_like, to_hex
from matplotlib.text import Annotation

from .plotting.figure_edits import (
    add_arrow, apply_line_style, refresh_legend, set_tick_font_family,
)
from .plotting.font_presets import available_paper_fonts


class FigureEditor:
    def __init__(self, root, figure, canvas, edits: dict, status=None):
        self.root = root
        self.figure = figure
        self.canvas = canvas
        self.edits = edits
        self.status = status
        self.arrow_start = None
        self.arrow_mode = False
        canvas.mpl_connect("button_press_event", self.on_press)

    def on_press(self, event):
        if self.arrow_mode and event.button == 1:
            self._arrow_click(event)
            return
        if not event.dblclick or event.button != 1:
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

    def _dialog(self, title):
        window = tk.Toplevel(self.root)
        window.title(self.root.tr(title) if hasattr(self.root, "tr") else title)
        window.transient(self.root)
        window.resizable(False, False)
        window.configure(bg=self.root.cget("bg"))
        window.grab_set()
        body = ttk.Frame(window, padding=16)
        body.pack(fill="both", expand=True)
        if hasattr(self.root, "tooltips"):
            def finish_dialog():
                if window.winfo_exists():
                    if hasattr(self.root, "_localize_tree"):
                        self.root._localize_tree(window)
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
                commit()
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

    def edit_text(self, key, artist):
        window, body = self._dialog("编辑图中文字")
        original = {"text": artist.get_text(), "size": artist.get_fontsize(),
                    "font_family": artist.get_fontfamily()[0], "color": artist.get_color()}
        value = self._entry(body, "内容", original["text"])
        size = self._entry(body, "字号 (pt)", f"{original['size']:g}")
        font_family = self._font_entry(body, original["font_family"])
        color = self._color_entry(body, original["color"])

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
            self.canvas.draw_idle()
            return True

        def commit():
            self.edits.setdefault("texts", {})[key] = {
                "text": artist.get_text(), "size": artist.get_fontsize(),
                "color": artist.get_color(),
                "font_family": font_family.get(),
            }

        def rollback():
            artist.set_text(original["text"])
            artist.set_fontsize(original["size"])
            artist.set_fontfamily(original["font_family"])
            artist.set_color(original["color"])
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

    def edit_figure(self):
        window, body = self._dialog("编辑图片尺寸")
        width, height = getattr(self.figure, "_tonyplot_export_size", self.figure.get_size_inches())
        preview_size = tuple(self.figure.get_size_inches())
        widget = self.canvas.get_tk_widget()
        widget_size = (widget.cget("width"), widget.cget("height"))
        width_var = self._entry(body, "宽度 (英寸)", f"{width:g}")
        height_var = self._entry(body, "高度 (英寸)", f"{height:g}")

        def preview():
            try:
                size = (float(width_var.get()), float(height_var.get()))
                if not all(math.isfinite(value) and 2 <= value <= 40 for value in size):
                    raise ValueError("宽度和高度需在 2–40 英寸之间")
            except ValueError as exc:
                messagebox.showerror("参数无效", str(exc), parent=window)
                return False
            self.figure.set_size_inches(*size, forward=False)
            if hasattr(self.figure, "_tonyplot_export_size"):
                self.figure._tonyplot_export_size = size
            widget.configure(width=int(size[0] * self.figure.dpi),
                             height=int(size[1] * self.figure.dpi))
            self.canvas.draw_idle()
            return True

        def commit():
            self.edits["figure_size"] = (float(width_var.get()), float(height_var.get()))

        def rollback():
            self.figure.set_size_inches(*preview_size, forward=False)
            if hasattr(self.figure, "_tonyplot_export_size"):
                self.figure._tonyplot_export_size = (width, height)
            widget.configure(width=widget_size[0], height=widget_size[1])
            self.canvas.draw_idle()

        self._buttons(window, body, preview, commit, rollback)
        window.focus_set()
