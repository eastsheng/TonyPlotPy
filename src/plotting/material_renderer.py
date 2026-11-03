"""Material-only STR figures using SSF region material identifiers."""
from __future__ import annotations

import math
from matplotlib import colormaps
from matplotlib.figure import Figure
from matplotlib.patches import Patch
from . import atlas_engine as engine
from .structure_overlay import draw_structure_info


MATERIALS = {
    0: ("Gas", "#e2e8f0"), 1: ("SiO2", "#00b2ff"),
    2: ("Nitride", "#c4b5fd"), 3: ("Silicon", "#a7d7b8"),
    4: ("Polysilicon", "#ffff00"), 5: ("Oxynitride", "#b6c9ef"),
    6: ("Aluminum", "#e5b7b7"), 8: ("GaAs", "#d6c5a4"),
    9: ("Sapphire", "#b9d5ed"), 10: ("Gold", "#e5c45f"),
    11: ("Silver", "#b9c0cc"), 13: ("Tungsten", "#94a3b8"),
    14: ("Titanium", "#9ca3af"), 91: ("Electrode", "#f0af65"),
    99: ("3C-SiC", "#81c8a5"), 100: ("Diamond", "#a5d8e2"),
    101: ("SiGe", "#a5bea3"), 102: ("6H-SiC", "#6fbdb2"),
    103: ("4H-SiC", "#a0a0a0"), 124: ("GaN", "#9abde6"),
    125: ("AlN", "#a6cbe0"), 126: ("InN", "#b7add5"),
}


def material_style(code):
    return MATERIALS.get(code, (f"Material {code}", colormaps["tab20"](code % 20)))


def apply_material_legend(axis, values):
    old_legend = axis.get_legend()
    if old_legend is not None:
        old_legend.set_draggable(False)
    handles = []
    for name, item in axis._tonyplot_materials.items():
        entry = values.get("entries", {}).get(name, {})
        color = entry.get("color", item["color"])
        for artist in item["artists"]:
            artist.set_facecolor(color)
        handles.append(Patch(facecolor=color, edgecolor="#64748b", label=entry.get("label", name)))
    legend = axis.legend(handles=handles, loc=values.get("location", "lower right"),
                         ncols=values.get("columns", 1), frameon=values.get("frame", False),
                         prop={"size": values.get("size", 7), "family": values.get("font_family", "Arial"),
                               "weight": "bold" if values.get("bold", False) else "normal"},
                         labelcolor=values.get("color", "#1e293b"))
    legend.set_title(values.get("title", ""), prop={"size": values.get("title_size", 8),
                                                    "family": values.get("font_family", "Arial")})
    legend.get_title().set_color(values.get("color", "#1e293b"))
    legend.set_draggable(True, use_blit=False, update="loc")
    axis._tonyplot_material_legend_style = values.copy()


def make_material_figure(options, structures, labels):
    from .renderer import panel_layout
    options = {**options, "quantities": ["materials"]}
    panels, columns = panel_layout(options)
    if columns < 1:
        raise ValueError("列数必须至少为 1")
    width, height = float(options["panel_width"]), float(options["panel_height"])
    if width <= 0 or height <= 0:
        raise ValueError("图尺寸必须大于 0")
    rows = math.ceil(len(panels) / columns)
    figure = Figure(figsize=(width * columns, height * rows), constrained_layout=True)
    axes = figure.subplots(rows, columns, squeeze=False)
    rotated = options["orientation"].startswith("横向")
    x0, x1, y0, y1 = options["bounds"]
    for index, (file_index, _) in enumerate(panels):
        axis = axes.flat[index]
        structure = structures[file_index]
        axis._tonyplot_axis_key = ("str", str(options["files"][file_index]), "materials")
        used = {}
        axis._tonyplot_materials = {}
        for region in structure.region_triangles:
            code = structure.region_materials.get(region)
            name, color = material_style(code) if code is not None else (f"Region {region}", "#cbd5e1")
            before = len(axis.collections)
            engine.plot_region(axis, structure, region, color, rotated=rotated,
                               outline=options["overlay"])
            record = axis._tonyplot_materials.setdefault(name, {"color": color, "artists": []})
            if len(axis.collections) > before:
                record["artists"].append(axis.collections[before])
            used[name] = color
        if options.get("mesh", False):
            engine.plot_mesh(axis, structure, rotated=rotated)
        structure_y0 = min(y0, float(structure.y.min())) if options["overlay"] else y0
        axis.set_xlim((structure_y0, y1) if rotated else (x0, x1))
        axis.set_ylim((x0, x1) if rotated else (y1, structure_y0))
        draw_structure_info(axis, structure, rotated=rotated, junctions=options["overlay"],
                            labels=options.get("structure_labels", True))
        axis.set_xlabel("Depth y (µm)" if rotated else "x (µm)")
        axis.set_ylabel("Lateral x (µm)" if rotated else "Depth y (µm)")
        visibility = options.get("panel_labels", {}).get((str(options["files"][file_index]), "materials"), {})
        axis.xaxis.label.set_visible(visibility.get("x", True))
        axis.yaxis.label.set_visible(visibility.get("y", True))
        axis.set_title(labels[file_index], fontsize=9, color="#183b56", pad=7)
        axis.tick_params(direction="in", labelsize=8, colors="#52687a")
        axis.grid(options.get("grid", False))
        apply_material_legend(axis, {})
    for axis in list(axes.flat)[len(panels):]:
        axis.set_visible(False)
    figure.suptitle(options["files"][0].parent.name, fontsize=12, color="#183b56")
    return figure
