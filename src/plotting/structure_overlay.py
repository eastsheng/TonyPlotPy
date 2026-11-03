"""Junction lines and optional structure annotations from saved STR data."""
from __future__ import annotations

import numpy as np
from matplotlib.tri import Triangulation
from .doping_regions import igbt_targets


def draw_structure_info(axis, structure, rotated=False, junctions=True, labels=True):
    x, y = (structure.y, structure.x) if rotated else (structure.x, structure.y)
    doping = structure.values.get("net_doping", structure.values.get("code:115"))
    junction_segments = []
    targets = igbt_targets(structure, doping) if doping is not None and labels else None

    def annotate(text, point, offset=(18, 12)):
        relative = axis.transAxes.inverted().transform(axis.transData.transform(point))
        offset = (-(abs(offset[0]) + 4) if relative[0] > 0.75 else abs(offset[0]),
                  -abs(offset[1]) if relative[1] > 0.8 else offset[1])
        artist = axis.annotate(text, point, xytext=offset, textcoords="offset points",
                               fontsize=7.5, color="#111827", zorder=8, clip_on=True,
                               ha="right" if offset[0] < 0 else "left",
                               va="top" if offset[1] < 0 else "bottom",
                               arrowprops={"arrowstyle": "-|>", "color": "#111827",
                                           "linewidth": 0.85, "mutation_scale": 8,
                                           "shrinkA": 2, "shrinkB": 1,
                                           "connectionstyle": "arc3,rad=0"})
        artist.set_in_layout(False)
        return artist

    def visible_centers(triangles):
        centers = np.column_stack((x[triangles].mean(axis=1), y[triangles].mean(axis=1)))
        xmin, xmax = sorted(axis.get_xlim())
        ymin, ymax = sorted(axis.get_ylim())
        return centers[(centers[:, 0] >= xmin) & (centers[:, 0] <= xmax)
                       & (centers[:, 1] >= ymin) & (centers[:, 1] <= ymax)]

    def center(points):
        return points[np.argmin(np.sum((points - points.mean(axis=0)) ** 2, axis=1))]

    if doping is not None:
        for triangles in structure.region_triangles.values():
            values = doping[triangles]
            valid = np.all(np.isfinite(values), axis=1)
            finite_values = values[valid]
            if not finite_values.size:
                continue
            if junctions and np.min(finite_values) < 0 < np.max(finite_values):
                tri = Triangulation(x, y, triangles)
                tri.set_mask(~valid)
                contours = axis.tricontour(tri, np.nan_to_num(doping), levels=[0],
                                           colors="#334155", linewidths=0.85,
                                           linestyles="--", zorder=5)
                junction_segments.extend(segment for segment in contours.allsegs[0] if len(segment) > 1)
            if labels and targets is None:
                for name, selected in (("N", np.all(values > 0, axis=1)),
                                       ("P", np.all(values < 0, axis=1))):
                    points = visible_centers(triangles[valid & selected])
                    if len(points):
                        annotate(name, center(points))
    if labels and junction_segments:
        segment = max(junction_segments, key=len)
        points = segment
        xmin, xmax = sorted(axis.get_xlim())
        ymin, ymax = sorted(axis.get_ylim())
        points = points[(points[:, 0] >= xmin) & (points[:, 0] <= xmax)
                        & (points[:, 1] >= ymin) & (points[:, 1] <= ymax)]
        if len(points):
            annotate("PN junction", points[len(points) // 2], offset=(5, -10))
    if labels:
        if targets is not None:
            xmin, xmax = sorted(axis.get_xlim())
            ymin, ymax = sorted(axis.get_ylim())
            for name, points in targets.items():
                if rotated:
                    points = points[:, [1, 0]]
                points = points[(points[:, 0] >= xmin) & (points[:, 0] <= xmax)
                                & (points[:, 1] >= ymin) & (points[:, 1] <= ymax)]
                if len(points):
                    annotate(name, center(points), offset=(24, -16) if name.startswith("Emitter") else (18, 12))
        for name, region in structure.electrodes.items():
            if targets is not None and name == "emitter" and "Emitter (P++ contact)" in targets:
                continue
            triangles = structure.region_triangles.get(region)
            if triangles is None:
                continue
            points = visible_centers(triangles)
            if len(points):
                annotate(name.capitalize(), center(points))
