"""Build cloud-map figures without depending on Tkinter."""
from __future__ import annotations

import math
from pathlib import Path

import matplotlib.tri as mtri
import numpy as np
from matplotlib.colors import LogNorm, Normalize
from matplotlib.figure import Figure
from matplotlib.transforms import Bbox

from . import atlas_engine as engine

FIELD_NAME_BY_CODE = engine.FIELD_LABELS_BY_CODE


def quantity_label(quantity: str) -> str:
    if quantity in engine.LABELS:
        return engine.LABELS[quantity]
    if quantity.startswith("code:"):
        code = int(quantity.split(":", 1)[1])
        return FIELD_NAME_BY_CODE.get(code, "STR field")
    return quantity


def optional_float(value: str) -> float | None:
    return None if str(value).strip().lower() in ("", "auto", "none") else float(value)


def panel_layout(options):
    """Return panel order and column count for both the renderer and settings UI."""
    count = len(options["files"])
    quantities = options["quantities"]
    if options["layout"] == "时间 × 物理量":
        return [(i, q) for i in range(count) for q in quantities], len(quantities)
    panels = [(i, q) for q in quantities for i in range(count)]
    columns = count if options["layout"] == "物理量 × 时间" else int(options["columns"])
    return panels, columns


def read_structure(path: Path, options: dict, cache: dict) -> engine.Structure:
    """Reuse parsed source data; apply the requested mirror only for this render."""
    key = (path, path.stat().st_mtime_ns)
    if key not in cache:
        for old_key in [item for item in cache if item[0] == path]:
            del cache[old_key]
        cache[key] = engine.read_structure(path)
    structure = cache[key]
    if options["mirror"]:
        return engine.mirror_structure(structure, float(options["mirror_x"]))
    return structure


def field_norm(structures: list[engine.Structure], quantity: str, bounds: tuple,
               overrides: dict):
    """Use the field's shared auto range, then apply its optional overrides."""
    base = engine.color_norm(structures, quantity, bounds)
    if not overrides:
        return base
    scale = overrides.get("scale", "默认")
    if scale == "默认":
        scale = "log" if isinstance(base, LogNorm) else "linear"
    lower = optional_float(overrides.get("vmin", ""))
    upper = optional_float(overrides.get("vmax", ""))
    if upper is None:
        upper = base.vmax
    if lower is None:
        lower = base.vmin
    if scale == "log" and (lower is None or lower <= 0 or upper <= 0):
        x0, x1, y0, y1 = bounds
        positive = []
        for structure in structures:
            nodes = np.unique(structure.triangles)
            in_view = ((structure.x[nodes] >= x0) & (structure.x[nodes] <= x1)
                       & (structure.y[nodes] >= y0) & (structure.y[nodes] <= y1))
            data = structure.values[quantity][nodes[in_view]]
            positive.append(data[np.isfinite(data) & (data > 0)])
        positive = np.concatenate(positive)
        if positive.size == 0:
            raise ValueError(f"{quantity}: 当前视野没有正值，无法使用 log 标度")
        if upper <= 0:
            upper = float(np.percentile(positive, engine.PERCENTILE_MAX))
        lower = max(float(np.min(positive)), upper * 1e-5)
    if upper <= lower:
        raise ValueError(f"{quantity}: 色标上限必须大于下限")
    return LogNorm(vmin=lower, vmax=upper, clip=True) if scale == "log" else Normalize(vmin=lower, vmax=upper, clip=True)


def make_figure(options: dict, cache: dict) -> Figure:
    """Create one combined figure from selected snapshots and quantities."""
    engine.RENDER_STYLE = options["render"]
    engine.CURRENT_CONTOUR_BANDS = int(options["current_bands"])
    engine.TEMPERATURE_CONTOUR_BANDS = int(options["temp_bands"])
    engine.GUIDE_CONTOUR_LINES = int(options["guide_lines"])
    engine.CURRENT_SCALE = options["scale"]
    engine.CURRENT_VMIN = optional_float(options["current_min"])
    engine.CURRENT_VMAX = optional_float(options["current_max"])
    if engine.CURRENT_SCALE == "log" and engine.CURRENT_VMIN is not None and engine.CURRENT_VMIN <= 0:
        engine.CURRENT_VMIN = None
    engine.TEMPERATURE_VMIN = optional_float(options["temp_min"])
    engine.TEMPERATURE_VMAX = optional_float(options["temp_max"])
    engine.PERCENTILE_MAX = float(options["percentile"])

    quantities, bounds, files = options["quantities"], options["bounds"], options["files"]
    structures = [read_structure(path, options, cache) for path in files]
    labels = [engine.snapshot_info(str(path))[1] for path in files]
    panels, columns = panel_layout(options)
    if columns < 1:
        raise ValueError("列数必须至少为 1")
    rows = math.ceil(len(panels) / columns)
    width, height = float(options["panel_width"]), float(options["panel_height"])
    if width <= 0 or height <= 0:
        raise ValueError("图尺寸必须大于 0")

    figure = Figure(figsize=(width * columns, height * rows), constrained_layout=True)
    figure.patch.set_facecolor("white")
    axes = figure.subplots(rows, columns, squeeze=False)
    rotated = options["orientation"].startswith("横向")
    overlay = options["overlay"]
    field_settings = options.get("field_settings", {})
    shared_currents = set(quantities) & {"electron", "hole", "total"}
    if len(shared_currents) < 2:
        shared_currents = set()
    norms = {
        quantity: field_norm(structures, quantity, bounds,
                             {} if quantity in shared_currents else field_settings.get(quantity, {}))
        for quantity in quantities
    }
    if shared_currents:
        current_norms = [norms[q] for q in shared_currents]
        norm_type = LogNorm if options["scale"] == "log" else Normalize
        common_norm = norm_type(vmin=min(norm.vmin for norm in current_norms),
                                vmax=max(norm.vmax for norm in current_norms), clip=True)
        for quantity in shared_currents:
            norms[quantity] = common_norm
    colorbar_groups = {}
    x0, x1, y0, y1 = bounds
    for index, (file_index, quantity) in enumerate(panels):
        ax = axes.flat[index]
        structure = structures[file_index]
        if rotated:
            tri = mtri.Triangulation(structure.y, structure.x, structure.triangles)
        else:
            tri = mtri.Triangulation(structure.x, structure.y, structure.triangles)
        field_options = {} if quantity in shared_currents else field_settings.get(quantity, {})
        cmap_key = "temperature_cmap" if quantity == "temperature" else "current_cmap"
        cmap_name = field_options.get("cmap", "默认")
        if cmap_name == "默认":
            cmap_name = options[cmap_key]
        cmap = engine.COLOR_PRESETS[cmap_name]
        bands = field_options.get("bands", "")
        if bands:
            if quantity == "temperature":
                engine.TEMPERATURE_CONTOUR_BANDS = int(bands)
            else:
                engine.CURRENT_CONTOUR_BANDS = int(bands)
        else:
            if quantity == "temperature":
                engine.TEMPERATURE_CONTOUR_BANDS = int(options["temp_bands"])
            else:
                engine.CURRENT_CONTOUR_BANDS = int(options["current_bands"])
        image = engine.draw_field(ax, tri, structure.values[quantity], quantity, cmap, norms[quantity])
        group_key = "shared_current" if quantity in shared_currents else quantity
        group = colorbar_groups.setdefault(group_key, {"axes": [], "image": None})
        group["axes"].append(ax)
        group["image"] = image
        ax.set_facecolor("#f8fbfd")
        if rotated:
            ax.set_xlim(y0 - (1.25 if overlay else 0), y1)
            ax.set_ylim(x0, x1)
            ax.set_xlabel("Depth y (µm)")
            ax.set_ylabel("Lateral x (µm)")
        else:
            ax.set_xlim(x0, x1)
            ax.set_ylim(y1, y0 - (2.6 if overlay else 0))
            ax.set_xlabel("x (µm)")
            ax.set_ylabel("Depth y (µm)")
        if overlay:
            try:
                if "net_doping" in structure.values:
                    ax.tricontour(tri, structure.values["net_doping"], levels=[0],
                                  colors="white", linewidths=0.7, linestyles="--", zorder=3)
            except ValueError:
                pass
            engine.plot_region(ax, structure, 2, "#a9cce3", rotated=rotated)
            for electrode, color in (("gate", "#d990ba"), ("emitter", "#f0af65")):
                if electrode in structure.electrodes:
                    engine.plot_region(ax, structure, structure.electrodes[electrode], color,
                                       rotated=rotated)
        visibility = options.get("panel_labels", {}).get((str(files[file_index]), quantity), {})
        ax.xaxis.label.set_visible(visibility.get("x", True))
        ax.yaxis.label.set_visible(visibility.get("y", True))
        panel_title = labels[file_index]
        if options.get("show_quantity_title", False):
            panel_title += f" · {quantity_label(quantity)}"
        ax.set_title(panel_title, fontsize=9,
                     color="#183b56", pad=7)
        ax.tick_params(direction="in", labelsize=8, colors="#52687a", width=0.7)
        if options.get("grid", False):
            ax.grid(True, axis="both", color="#64748b", linewidth=0.5, alpha=0.45)
        else:
            ax.grid(False)
        for spine in ax.spines.values():
            spine.set_color("#b8cbd8")
            spine.set_linewidth(0.7)
    for ax in list(axes.flat)[len(panels):]:
        ax.set_visible(False)
    for quantity, group in colorbar_groups.items():
        panel_rows = {index // columns
                      for index, (_file_index, q) in enumerate(panels)
                      if (q in shared_currents if quantity == "shared_current" else q == quantity)}
        row_span = max(panel_rows) - min(panel_rows) + 1
        shrink = 0.78 / row_span if quantity == "shared_current" else 0.78
        colorbar = engine.add_colorbar(
            figure, group["image"], ax=group["axes"],
            label=(r"Current density $|J|$ (A/cm$^2$)" if quantity == "shared_current"
                   else quantity_label(quantity)),
            shrink=shrink, pad=0.025,
        )
        if quantity == "shared_current":
            base_locator = colorbar.ax.get_axes_locator()

            def compact_locator(axis, canvas_renderer, base=base_locator, parents=tuple(group["axes"])):
                box = base(axis, canvas_renderer)
                height = min(parent.get_position().height for parent in parents) * 0.78
                figure_width, figure_height = axis.figure.get_size_inches()
                width = height * figure_height / figure_width / 20
                return Bbox.from_bounds(box.x0 + (box.width - width) / 2,
                                        box.y0 + (box.height - height) / 2, width, height)

            colorbar.ax.set_axes_locator(compact_locator)
        colorbar.ax.tick_params(labelsize=8, colors="#52687a")
        colorbar.ax._tonyplot_colorbar_key = quantity
        colorbar.outline.set_edgecolor("#b8cbd8")
    figure.suptitle(files[0].parent.name, fontsize=12, color="#183b56")
    return figure
