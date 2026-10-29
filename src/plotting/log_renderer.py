"""Render Atlas LOG curves independently of STR cloud maps."""
from __future__ import annotations

import math

import matplotlib as mpl
import numpy as np
from matplotlib.figure import Figure

from .log_reader import LogData, read_log


# Match the compact Matplotlib publication style in the supplied example.
COLORS = ("#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b")
MARKERS = ("o", "s", "^", "D", "v", "P")
mpl.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
    "svg.fonttype": "none",
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "font.size": 8,
    "axes.labelsize": 9,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 7.5,
    "axes.linewidth": 0.8,
    "xtick.direction": "in",
    "ytick.direction": "in",
    "xtick.major.size": 4,
    "ytick.major.size": 4,
    "xtick.minor.size": 2,
    "ytick.minor.size": 2,
    "xtick.major.width": 0.8,
    "ytick.major.width": 0.8,
    "xtick.minor.width": 0.6,
    "ytick.minor.width": 0.6,
    "lines.linewidth": 1.2,
})


def optional_float(value) -> float | None:
    return None if str(value).strip() == "" else float(value)


def make_figure(options: dict, cache: dict) -> Figure:
    files = options["files"]
    data: list[LogData] = []
    for path in files:
        key = (path, path.stat().st_mtime_ns)
        if key not in cache:
            for old_key in [entry for entry in cache if entry[0] == path]:
                del cache[old_key]
            cache[key] = read_log(path)
        data.append(cache[key])

    x_code = options["x_code"]
    y_codes = options["y_codes"]
    layout = options["layout"]
    panels = 1 if layout == "叠加曲线" else len(y_codes)
    columns = 1 if panels == 1 else min(2, panels)
    rows = math.ceil(panels / columns)
    figure = Figure(figsize=(3.5 * columns, 2.75 * rows))
    figure.patch.set_facecolor("white")
    axes = figure.subplots(rows, columns, squeeze=False)
    x_multiplier = float(options["x_multiplier"])
    linewidth = float(options["linewidth"])
    if linewidth <= 0:
        raise ValueError("线宽必须大于 0")
    x_min, x_max = optional_float(options["x_min"]), optional_float(options["x_max"])
    y_min, y_max = optional_float(options["y_min"]), optional_float(options["y_max"])
    if x_min is not None and x_max is not None and x_max <= x_min:
        raise ValueError("横轴上限必须大于下限")
    if y_min is not None and y_max is not None and y_max <= y_min:
        raise ValueError("纵轴上限必须大于下限")
    dual_y = layout == "叠加曲线" and bool(options.get("dual_y", False))
    right_codes = set(options.get("right_y_codes", ())) if dual_y else set()
    if dual_y and (not right_codes or not right_codes < set(y_codes)):
        raise ValueError("双 Y 轴需要至少一条左轴曲线和一条右轴曲线")
    right_min = optional_float(options.get("right_y_min", "")) if dual_y else None
    right_max = optional_float(options.get("right_y_max", "")) if dual_y else None
    if right_min is not None and right_max is not None and right_max <= right_min:
        raise ValueError("右轴上限必须大于下限")
    right_scale = options.get("right_y_scale", "linear")
    if dual_y and right_scale == "log" and right_min is not None and right_min <= 0:
        raise ValueError("log 右轴下限必须为正")
    labels = data[0].header.labels
    for panel_index in range(panels):
        ax = axes.flat[panel_index]
        panel_codes = y_codes if panels == 1 else [y_codes[panel_index]]
        right_ax = ax.twinx() if dual_y else None
        plotted = 0
        plotted_right = 0
        legend_handles = []
        for file_index, item in enumerate(data):
            if x_code not in item.values:
                raise ValueError(f"{item.path.name}: 缺少横轴字段 {x_code}")
            x_all = item.values[x_code] * x_multiplier
            for quantity_index, y_code in enumerate(panel_codes):
                if y_code not in item.values:
                    raise ValueError(f"{item.path.name}: 缺少纵轴字段 {y_code}")
                y_all = item.values[y_code]
                target = right_ax if y_code in right_codes else ax
                valid = (np.isfinite(x_all) & np.isfinite(y_all)
                         & (np.abs(x_all) < 1e100) & (np.abs(y_all) < 1e100))
                if options["x_scale"] == "log":
                    valid &= x_all > 0
                if (right_scale if target is right_ax else options["y_scale"]) == "log":
                    valid &= y_all > 0
                if not np.any(valid):
                    continue
                name = labels.get(y_code, "Signal")
                if len(data) > 1 and len(panel_codes) > 1:
                    legend = f"{item.path.parent.name} · {name}"
                elif len(data) > 1:
                    legend = item.path.parent.name
                else:
                    legend = name
                series_index = file_index * len(y_codes) + quantity_index
                x, y = x_all[valid], y_all[valid]
                line, = target.plot(x, y, color=COLORS[series_index % len(COLORS)],
                                    lw=linewidth, marker=MARKERS[quantity_index % len(MARKERS)],
                                    markersize=2.8, markerfacecolor="white", markeredgewidth=0.75,
                                    markevery=max(1, len(x) // 16), label=legend)
                line._tonyplot_line_key = f"{file_index}:{y_code}:{panel_index}"
                line._tonyplot_base_markevery = max(1, len(x) // 16)
                line._tonyplot_legend_axis = ax
                line._tonyplot_legend_size = 7.5
                line._tonyplot_legend_font_family = "Arial"
                legend_handles.append(line)
                plotted += 1
                if target is right_ax:
                    plotted_right += 1
        if plotted == 0:
            raise ValueError("所选曲线在当前标度下没有有效数据")
        if dual_y and (plotted_right == 0 or plotted_right == plotted):
            raise ValueError("双 Y 轴两侧都需要有效曲线数据")
        ax.set_xscale(options["x_scale"])
        ax.set_yscale(options["y_scale"])
        if right_ax is not None:
            right_ax.set_yscale(right_scale)
        if x_min is not None or x_max is not None:
            ax.set_xlim(left=x_min, right=x_max)
        if y_min is not None or y_max is not None:
            ax.set_ylim(bottom=y_min, top=y_max)
        if right_ax is not None and (right_min is not None or right_max is not None):
            right_ax.set_ylim(bottom=right_min, top=right_max)
        if options["grid"]:
            ax.grid(True, axis="both", color="#d9d9d9", linewidth=0.45)
        else:
            ax.grid(False)
        ax.set_axisbelow(True)
        ax.set_facecolor("white")
        x_label = labels.get(x_code, "X")
        if x_code == 61 and x_multiplier == 1e6:
            x_label = "Time (µs)"
        ax.set_xlabel(x_label, labelpad=3)
        left_codes = [code for code in panel_codes if code not in right_codes]
        left_label = (labels.get(left_codes[0], "Signal") if len(left_codes) == 1
                      else "Left axis" if dual_y else "Value" if panels == 1
                      else labels.get(panel_codes[0], "Signal"))
        ax.set_ylabel(left_label, labelpad=3)
        if right_ax is not None:
            right_label = (labels.get(next(iter(right_codes)), "Signal")
                           if len(right_codes) == 1 else "Right axis")
            right_ax.set_ylabel(right_label, labelpad=3)
            right_ax.grid(False)
            right_ax.minorticks_on()
            right_ax.tick_params(axis="y", which="major", direction="in", length=4, width=0.8, pad=3)
            right_ax.tick_params(axis="y", which="minor", direction="in", length=2, width=0.6)
            ax.spines["right"].set_visible(False)
            right_ax.spines["left"].set_visible(False)
            for spine in right_ax.spines.values():
                spine.set_linewidth(0.8)
        if panels > 1:
            ax.set_title(labels.get(panel_codes[0], "Signal"),
                         fontsize=9, pad=4)
        ax.minorticks_on()
        ax.tick_params(axis="both", which="major", direction="in", length=4, width=0.8, pad=3)
        ax.tick_params(axis="both", which="minor", direction="in", length=2, width=0.6)
        legend_options = ({"loc": "lower center", "bbox_to_anchor": (0.5, 1.01),
                           "ncol": min(3, plotted)} if dual_y else
                          {"loc": "upper left", "ncol": 2 if plotted > 5 else 1})
        ax._tonyplot_legend_lines = legend_handles
        ax._tonyplot_legend_title = ""
        ax._tonyplot_legend_kwargs = dict(frameon=False, columnspacing=0.65,
                                          handlelength=1.6, handletextpad=0.35,
                                          borderaxespad=0.2, labelspacing=0.3,
                                          **legend_options)
        ax.legend(handles=legend_handles, **ax._tonyplot_legend_kwargs)
        for spine in ax.spines.values():
            spine.set_linewidth(0.8)
    for ax in list(axes.flat)[panels:]:
        ax.set_visible(False)
    if options.get("title"):
        figure.suptitle(options["title"], fontsize=9)
    figure.tight_layout(pad=0.5)
    figure._tonyplot_export_size = tuple(figure.get_size_inches())
    return figure
