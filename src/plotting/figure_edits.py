"""Apply saved visual edits to freshly rendered Matplotlib figures."""
from __future__ import annotations

from matplotlib.transforms import Bbox
from matplotlib.layout_engine import ConstrainedLayoutEngine
from .tick_intervals import interval_locator


class CloudLayoutEngine(ConstrainedLayoutEngine):
    """Measure the default colorbar positions before applying user offsets."""

    measuring_colorbars = False

    def execute(self, figure):
        self.measuring_colorbars = True
        try:
            return super().execute(figure)
        finally:
            self.measuring_colorbars = False


class ColorbarLocator:
    """Keep custom physical dimensions while following automatic panel layout."""

    def __init__(self, base, values):
        self.base = base
        self.values = values

    def __call__(self, axis, renderer):
        box = self.base(axis, renderer) if self.base else axis.get_position(original=True)
        width, height = axis.figure.get_size_inches()
        values = self.values
        w, h = values["width"] / width, values["height"] / height
        measuring = getattr(axis.figure.get_layout_engine(), "measuring_colorbars", False)
        dx, dy = (0, 0) if measuring else (values["dx"], values["dy"])
        return Bbox.from_bounds(box.x0 + box.width / 2 - w / 2 + dx / width,
                                box.y0 + box.height / 2 - h / 2 + dy / height, w, h)


def apply_colorbar_style(axis, values):
    locator = axis.get_axes_locator()
    base = locator.base if isinstance(locator, ColorbarLocator) else locator
    if hasattr(axis, "_colorbar_info"):
        axis._colorbar_info["aspect"] = values["height"] / values["width"]
    axis.set_box_aspect(None)
    axis.set_aspect("auto")
    axis.set_axes_locator(ColorbarLocator(base, values.copy()))
    axis.set_ylabel(values["label"], fontsize=values["label_size"],
                    color=values["color"], fontfamily=values["font_family"])
    bar = axis._colorbar
    bar.locator = interval_locator(axis.yaxis, values.get("tick_interval"), bar.locator)
    bar.update_ticks()
    axis.tick_params(labelsize=values["tick_size"], colors=values["color"])
    set_tick_font_family(axis, values["font_family"])
    axis._colorbar.outline.set_edgecolor(values["color"])
    axis._colorbar.outline.set_linewidth(values["linewidth"])
    axis._tonyplot_colorbar_style = values.copy()


def add_arrow(figure, values: dict, index: int):
    """Draw one editable annotation from saved data coordinates."""
    axis = figure.axes[values["axis"]]
    arrow = axis.annotate(
        values["text"], xy=values["xy"], xytext=values["xytext"],
        color=values["color"], fontsize=values["size"],
        fontfamily=values.get("font_family", "sans-serif"),
        arrowprops={"arrowstyle": "->", "color": values["color"],
                    "linewidth": values.get("linewidth", 1.2)},
        annotation_clip=False,
    )
    arrow._tonyplot_arrow_index = index
    return arrow


def set_tick_font_family(axis, family: str) -> None:
    for label in (*axis.get_xticklabels(), *axis.get_yticklabels()):
        label.set_fontfamily(family)


def apply_line_style(line, values: dict) -> None:
    line.set_color(values["color"])
    line.set_linewidth(values["linewidth"])
    line.set_linestyle(values["linestyle"])
    line.set_marker(values["marker"])
    line.set_markersize(values["markersize"])
    line.set_markeredgecolor(values["color"])
    line.set_markevery(1 if values["linestyle"] == "None"
                       else getattr(line, "_tonyplot_base_markevery", None))
    line.set_label(values["label"])
    line._tonyplot_legend_size = values["legend_size"]
    line._tonyplot_legend_font_family = values.get("legend_font_family", "Arial")


def refresh_legend(axis) -> None:
    lines = getattr(axis, "_tonyplot_legend_lines", None)
    if lines is None:
        return
    title = getattr(axis, "_tonyplot_legend_title", "")
    legend = axis.legend(handles=lines, **axis._tonyplot_legend_kwargs)
    legend.set_title(title)
    for text, line in zip(legend.get_texts(), lines):
        text.set_fontsize(getattr(line, "_tonyplot_legend_size", 7.5))
        text.set_fontfamily(getattr(line, "_tonyplot_legend_font_family", "Arial"))


def edited_axis(figure, index, values):
    identity = values.get("axis_key")
    if identity is not None:
        return next((axis for axis in figure.axes
                     if getattr(axis, "_tonyplot_axis_key", None) == tuple(identity)), None)
    axis = figure.axes[int(index)]
    # Legacy numeric panel edits must never overwrite a colorbar's field label.
    return None if hasattr(axis, "_tonyplot_colorbar_key") else axis


def text_artist(figure, key: str, values=None):
    if key == "figure_title":
        return figure._suptitle or figure.suptitle("")
    _, index, role = key.split(":", 2)
    axis = edited_axis(figure, index, values or {})
    if axis is None:
        return None
    return {"xlabel": axis.xaxis.label, "ylabel": axis.yaxis.label,
            "title": axis.title, "left_title": axis._left_title,
            "right_title": axis._right_title}[role]


def apply_edits(figure, edits: dict) -> None:
    if "figure_size" in edits:
        figure.set_size_inches(*edits["figure_size"], forward=False)
        figure._tonyplot_export_size = tuple(edits["figure_size"])
    for key, values in edits.get("texts", {}).items():
        try:
            artist = text_artist(figure, key, values)
        except (IndexError, KeyError, ValueError):
            continue
        if artist is not None:
            if not values.get("preserve_text"):
                artist.set_text(values["text"])
            artist.set_fontsize(values["size"])
            if "color" in values:
                artist.set_color(values["color"])
            if "font_family" in values:
                artist.set_fontfamily(values["font_family"])
            if "weight" in values:
                artist.set_fontweight(values["weight"])
    for index_text, values in edits.get("axes", {}).items():
        try:
            axis = edited_axis(figure, index_text, values)
        except (IndexError, ValueError):
            continue
        if axis is None:
            continue
        axis.set_xscale(values["xscale"])
        axis.set_yscale(values["yscale"])
        broken_x, broken_y = getattr(axis, "_tonyplot_break_limits", (False, False))
        current_view = getattr(figure, "_tonyplot_str_view", None)
        saved_view = values.get("str_view", current_view)
        if not broken_x and (current_view is None or current_view[0] == saved_view[0]):
            axis.set_xlim(*values["xlim"])
        if not broken_y and (current_view is None or current_view[1] == saved_view[1]):
            axis.set_ylim(*values["ylim"])
        axis.xaxis.set_major_locator(interval_locator(axis.xaxis, values.get("x_tick_interval")))
        axis.yaxis.set_major_locator(interval_locator(axis.yaxis, values.get("y_tick_interval")))
        axis.tick_params(axis="both", labelsize=values["tick_size"])
        if "tick_color" in values:
            axis.tick_params(axis="both", colors=values["tick_color"])
        if "tick_font_family" in values:
            set_tick_font_family(axis, values["tick_font_family"])
        if "x_spine_color" in values:
            axis.spines["bottom"].set_color(values["x_spine_color"])
        if "y_spine_color" in values:
            side = "right" if axis.yaxis.get_ticks_position() == "right" else "left"
            axis.spines[side].set_color(values["y_spine_color"])
    line_lookup = {line._tonyplot_line_key: line for axis in figure.axes for line in axis.lines
                   if hasattr(line, "_tonyplot_line_key")}
    touched_legends = set()
    for key, values in edits.get("lines", {}).items():
        line = line_lookup.get(key)
        if line is None:
            continue
        apply_line_style(line, values)
        touched_legends.add(line._tonyplot_legend_axis)
    for index_text, title in edits.get("legend_titles", {}).items():
        try:
            axis = figure.axes[int(index_text)]
        except (IndexError, ValueError):
            continue
        axis._tonyplot_legend_title = title
        touched_legends.add(axis)
    for axis in touched_legends:
        refresh_legend(axis)
    # A constrained layout must keep its engine once colorbars have been added.
    if hasattr(figure, "_tonyplot_export_size") and not isinstance(
        figure.get_layout_engine(), ConstrainedLayoutEngine
    ) and (
        edits.get("texts") or touched_legends or edits.get("axes")
    ):
        figure.tight_layout(pad=0.5)
    if "arrows" in edits:
        for axis in figure.axes:
            for artist in list(axis.texts):
                if hasattr(artist, "_tonyplot_arrow_index"):
                    artist.remove()
    for index, values in enumerate(edits.get("arrows", [])):
        try:
            add_arrow(figure, values, index)
        except (IndexError, KeyError, ValueError):
            continue
    for axis in figure.axes:
        identity = getattr(axis, "_tonyplot_axis_key", None)
        if hasattr(axis, "_tonyplot_materials") and identity in edits.get("material_legends", {}):
            from .material_renderer import apply_material_legend
            apply_material_legend(axis, edits["material_legends"][identity])
        key = getattr(axis, "_tonyplot_colorbar_key", None)
        if key in edits.get("colorbars", {}):
            apply_colorbar_style(axis, edits["colorbars"][key])
