"""Apply saved visual edits to freshly rendered Matplotlib figures."""
from __future__ import annotations


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


def text_artist(figure, key: str):
    if key == "figure_title":
        return figure._suptitle or figure.suptitle("")
    _, index, role = key.split(":", 2)
    axis = figure.axes[int(index)]
    return {"xlabel": axis.xaxis.label, "ylabel": axis.yaxis.label,
            "title": axis.title, "left_title": axis._left_title,
            "right_title": axis._right_title}[role]


def apply_edits(figure, edits: dict) -> None:
    if "figure_size" in edits:
        figure.set_size_inches(*edits["figure_size"], forward=False)
        if hasattr(figure, "_tonyplot_export_size"):
            figure._tonyplot_export_size = tuple(edits["figure_size"])
    for key, values in edits.get("texts", {}).items():
        try:
            artist = text_artist(figure, key)
        except (IndexError, KeyError, ValueError):
            continue
        if artist is not None:
            artist.set_text(values["text"])
            artist.set_fontsize(values["size"])
            if "color" in values:
                artist.set_color(values["color"])
            if "font_family" in values:
                artist.set_fontfamily(values["font_family"])
    for index_text, values in edits.get("axes", {}).items():
        try:
            axis = figure.axes[int(index_text)]
        except (IndexError, ValueError):
            continue
        axis.set_xscale(values["xscale"])
        axis.set_yscale(values["yscale"])
        axis.set_xlim(*values["xlim"])
        axis.set_ylim(*values["ylim"])
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
    if hasattr(figure, "_tonyplot_export_size") and (
        edits.get("texts") or touched_legends or edits.get("axes")
    ):
        figure.tight_layout(pad=0.5)
    for index, values in enumerate(edits.get("arrows", [])):
        try:
            add_arrow(figure, values, index)
        except (IndexError, KeyError, ValueError):
            continue
