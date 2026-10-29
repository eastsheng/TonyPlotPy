"""Build cloud-map figures without depending on Tkinter."""
from __future__ import annotations

import math
from pathlib import Path

import matplotlib.tri as mtri
import numpy as np
from matplotlib.colors import LogNorm, Normalize
from matplotlib.figure import Figure

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
    layout = options["layout"]
    panels = [(i, q) for q in quantities for i in range(len(structures))]
    if layout == "时间 × 物理量":
        panels = [(i, q) for i in range(len(structures)) for q in quantities]
        columns = len(quantities)
    elif layout == "物理量 × 时间":
        columns = len(structures)
    else:
        columns = int(options["columns"])
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
    norms = {
        quantity: field_norm(structures, quantity, bounds, field_settings.get(quantity, {}))
        for quantity in quantities
    }
    colorbar_groups = {quantity: {"axes": [], "image": None} for quantity in quantities}
    x0, x1, y0, y1 = bounds
    for index, (file_index, quantity) in enumerate(panels):
        ax = axes.flat[index]
        structure = structures[file_index]
        if rotated:
            tri = mtri.Triangulation(structure.y, structure.x, structure.triangles)
        else:
            tri = mtri.Triangulation(structure.x, structure.y, structure.triangles)
        field_options = field_settings.get(quantity, {})
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
        colorbar_groups[quantity]["axes"].append(ax)
        colorbar_groups[quantity]["image"] = image
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
        ax.set_title(f"{labels[file_index]} · {quantity_label(quantity)}", fontsize=9,
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
        colorbar = engine.add_colorbar(
            figure, group["image"], ax=group["axes"], label=quantity_label(quantity),
            shrink=0.78, pad=0.025,
        )
        colorbar.ax.tick_params(labelsize=8, colors="#52687a")
        colorbar.outline.set_edgecolor("#b8cbd8")
    figure.suptitle(files[0].parent.name, fontsize=12, color="#183b56")
    return figure
