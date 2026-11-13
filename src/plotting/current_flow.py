"""Draw signed Atlas current vectors over the native STR mesh."""
from __future__ import annotations

import matplotlib.patheffects as effects
import matplotlib.tri as mtri
import numpy as np
from matplotlib.lines import Line2D


FLOW_STYLES = {
    "total": ("总电流密度", r"$J_{\mathrm{tot}}$", "#202936"),
    "electron": ("电子电流密度", r"$J_e$", "#1557d3"),
    "hole": ("空穴电流密度", r"$J_h$", "#ba1759"),
}
DENSITIES = {"稀疏": (0.45, 7), "标准": (0.65, 10), "密集": (1.0, 14)}
DEFAULT_ARROW_LENGTH = 9
OUTLINE = [effects.withStroke(linewidth=1.65, foreground="white")]


def parse_arrow_length(value):
    message = "箭头长度须为 3–24 pt。"
    try:
        length = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(message) from exc
    if not 3 <= length <= 24:
        raise ValueError(message)
    return length


def prepare_flow(structure, path, enabled, rotated):
    """Build interpolators confined to triangles with valid components."""
    x, y = (structure.y, structure.x) if rotated else (structure.x, structure.y)
    interpolators = {}
    for current in enabled:
        keys = (f"{current}_x", f"{current}_y")
        if not all(key in structure.values for key in keys):
            label = FLOW_STYLES[current][0]
            raise ValueError(f"{path.name}：缺少{label}的 X 或 Y 分量，无法绘制流线或方向。")
        u, v = (structure.values[key] for key in keys)
        if rotated:
            u, v = v, u
        invalid = ~np.isfinite(u) | ~np.isfinite(v)
        mask = invalid[structure.triangles].any(axis=1)
        if mask.all():
            continue
        mesh = mtri.Triangulation(x, y, structure.triangles, mask=mask)
        interpolators[current] = (mtri.LinearTriInterpolator(mesh, u), mtri.LinearTriInterpolator(mesh, v))
    return interpolators, (x.min(), x.max(), y.min(), y.max())


def draw_flow(ax, prepared, xlim, ylim, density, arrow_length, *, legend=False):
    interpolators, (xmin, xmax, ymin, ymax) = prepared
    x0, x1 = max(min(xlim), xmin), min(max(xlim), xmax)
    y0, y1 = max(min(ylim), ymin), min(max(ylim), ymax)
    if x0 >= x1 or y0 >= y1:
        return
    stream_density, arrow_count = DENSITIES[density]
    handles = []
    for current, (interpolate_u, interpolate_v) in interpolators.items():
        _, label, color = FLOW_STYLES[current]
        if current == "total":
            x, y = np.linspace(x0, x1, 101), np.linspace(y0, y1, 101)
            xx, yy = np.meshgrid(x, y)
            u, v = interpolate_u(xx, yy), interpolate_v(xx, yy)
            if np.ma.any(np.ma.hypot(u, v) > 0):
                first_arrow = len(ax.patches)
                streams = ax.streamplot(x, y, u, v, color=color, linewidth=0.85,
                                        density=stream_density, arrowsize=arrow_length / 9, zorder=6)
                streams.lines.set_path_effects(OUTLINE)
                for arrow in list(ax.patches)[first_arrow:]:
                    arrow.set_path_effects(OUTLINE)
                if streams.lines.get_segments():
                    handles.append(Line2D([], [], color=color, linewidth=1.2, label=label))
            continue

        # Offset the two arrow grids so parallel currents are both visible.
        offset = 0.30 if current == "electron" else 0.70
        sample = (np.arange(arrow_count) + offset) / arrow_count
        xx, yy = np.meshgrid(x0 + (x1 - x0) * sample, y0 + (y1 - y0) * sample)
        u, v = interpolate_u(xx, yy), interpolate_v(xx, yy)
        length = np.ma.hypot(u, v)
        valid = np.ma.filled(length > 0, False)
        if valid.any():
            # Direction only: normalize each arrow before drawing in display units.
            ax.quiver(xx[valid], yy[valid], u[valid] / length[valid], v[valid] / length[valid],
                      angles="xy", scale_units="inches", scale=72 / arrow_length,
                      units="inches", width=0.012,
                      pivot="mid", color=color, edgecolor="white", linewidth=0.35, zorder=7)
            handles.append(Line2D([], [], color=color, marker=r"$\rightarrow$",
                                  linestyle="none", markersize=9, label=label))
    if legend and handles:
        key = ax.legend(handles=handles, loc="upper right", fontsize=8, framealpha=0.9)
        key.set_zorder(8)
