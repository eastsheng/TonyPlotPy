"""Independent temperature color scales for groups of animation frames."""
import math

import numpy as np
from matplotlib.colors import Normalize

from .atlas_engine import visible_field_values


def parse_frame_ranges(rows, *, signed=False):
    ranges = []
    for row in rows:
        if not any(str(value).strip() for value in row):
            continue
        try:
            start, end, lower, upper = row
            start, end = int(start), int(end)
            lower, upper = (float(value) if value is not None and str(value).strip() else None
                            for value in (lower, upper))
            if (not 0 <= start <= end
                    or any(value is not None and (not math.isfinite(value) or (not signed and value <= 0))
                           for value in (lower, upper))
                    or (lower is not None and upper is not None and lower >= upper)):
                raise ValueError
        except (ValueError, TypeError) as exc:
            raise ValueError("请填写有效的帧区间和色棒范围。") from exc
        ranges.append((start, end, lower, upper))
    ranges.sort()
    if any(left[1] >= right[0] for left, right in zip(ranges, ranges[1:])):
        raise ValueError("帧区间不能重叠。")
    return ranges


def parse_segments(interval, entries):
    try:
        interval = int(interval)
        if interval < 1:
            raise ValueError
    except (ValueError, TypeError) as exc:
        raise ValueError("每段帧数必须是正整数。") from exc
    limits = {}
    for line in entries.splitlines():
        if not line.strip():
            continue
        try:
            segment, lower, upper = line.replace("，", ",").split(",")
            segment = int(segment)
            lower, upper = (float(value) if value.strip() else None for value in (lower, upper))
            if (segment < 1 or segment in limits
                    or any(value is not None and (not math.isfinite(value) or value <= 0)
                           for value in (lower, upper))
                    or (lower is not None and upper is not None and lower >= upper)):
                raise ValueError
        except ValueError as exc:
            raise ValueError("请按“段号,下限,上限”填写，每段一行；段号不可重复，温度须为正且下限小于上限。") from exc
        limits[segment] = (lower, upper)
    return interval, limits


def segment_norm(structures, bounds, percentile, limits):
    lower, upper = limits
    if lower is None or upper is None:
        values = visible_field_values(structures, "temperature", bounds)
        if lower is None:
            lower = float(np.min(values)) if upper is None else min(float(np.min(values)), upper - 1)
        if upper is None:
            upper = float(np.percentile(values, percentile))
            if upper <= lower:
                upper = lower + 1
    return Normalize(vmin=lower, vmax=upper, clip=True)
