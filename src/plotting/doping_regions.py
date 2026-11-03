"""Infer planar IGBT annotation targets from mesh, doping, and contacts.

These are topology-based display labels, not region names stored by Atlas.
They are enabled only for structures with gate/emitter/collector contacts.
"""
from __future__ import annotations
import numpy as np


def igbt_targets(structure, doping):
    if not {"gate", "emitter", "collector"} <= set(structure.electrodes):
        return None
    # Exclude oxide, metal, and polysilicon from device doping classifications.
    regions = [tri for region, tri in structure.region_triangles.items()
               if structure.region_materials.get(region) in (3, 8, 99, 101, 102, 103, 124, 125, 126)]
    if not regions:
        return None
    triangles = np.concatenate(regions)
    nodes = np.unique(triangles)
    x, y = structure.x, structure.y
    top, bottom = float(y[nodes].min()), float(y[nodes].max())
    middle = (top + bottom) / 2
    values = np.median(doping[triangles], axis=1)
    centers = np.column_stack((x[triangles].mean(axis=1), y[triangles].mean(axis=1)))
    valid = np.all(np.isfinite(doping[triangles]), axis=1)
    positive = valid & (values > 0)
    negative = valid & (values < 0)
    if not positive.any() or not negative.any():
        return None
    dx1 = x[triangles[:, 1]] - x[triangles[:, 0]]
    dy1 = y[triangles[:, 1]] - y[triangles[:, 0]]
    dx2 = x[triangles[:, 2]] - x[triangles[:, 0]]
    dy2 = y[triangles[:, 2]] - y[triangles[:, 0]]
    area = np.abs(dx1 * dy2 - dy1 * dx2) / 2
    logs = np.log10(values[positive])
    bins = np.arange(np.floor(logs.min() * 4) / 4, np.ceil(logs.max() * 4) / 4 + .5, .25)
    counts, bins = np.histogram(logs, bins=bins, weights=area[positive])
    peak = int(np.argmax(counts))
    background = 10 ** ((bins[peak] + bins[peak + 1]) / 2)
    targets = {
        "N drift": centers[positive & (values < background * 5)],
        "N++": centers[positive & (values >= background * 100) & (centers[:, 1] < middle)],
        "N buffer": centers[positive & (values >= background * 5) & (centers[:, 1] >= middle)],
        "P+ collector": centers[negative & (centers[:, 1] >= middle)],
    }
    well = negative & (centers[:, 1] < middle)
    if well.any():
        depth = centers[well, 1]
        well_min, well_max = depth.min(), depth.max()
        targets["P-well"] = centers[well & (centers[:, 1] >= well_min + .25 * (well_max - well_min))
                                    & (centers[:, 1] <= well_min + .8 * (well_max - well_min))]

    # The emitter contact target is a shallow, highly doped P-type node,
    # rather than the centroid of the overlying metal interconnect.
    pnodes = nodes[np.isfinite(doping[nodes]) & (doping[nodes] < 0) & (y[nodes] < middle)]
    if len(pnodes):
        first_depth = y[pnodes].min()
        shallow = pnodes[y[pnodes] <= first_depth + max((bottom - top) * 1e-5, 1e-6)]
        strong = shallow[np.abs(doping[shallow]) >= .5 * np.max(np.abs(doping[shallow]))]
        electrode_tri = structure.region_triangles.get(structure.electrodes["emitter"])
        if electrode_tri is not None:
            ex = x[np.unique(electrode_tri)]
            strong = strong[(x[strong] >= ex.min()) & (x[strong] <= ex.max())]
        if len(strong):
            strong = strong[np.argsort(x[strong])]
            node = strong[len(strong) // 4]
            targets["Emitter (P++ contact)"] = np.array([[x[node], y[node]]])
    return targets
