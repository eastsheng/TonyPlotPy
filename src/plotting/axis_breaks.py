"""Lay out clipped views of a cloud map while retaining physical coordinates."""
import math


def parse_breaks(options, bounds):
    cuts = {}
    for axis, (minimum, maximum) in zip(("x", "y"), (bounds[:2], bounds[2:])):
        start = options.get(f"{axis}_break_start", "").strip()
        end = options.get(f"{axis}_break_end", "").strip()
        if not start and not end:
            continue
        try:
            lower, upper = float(start), float(end)
            gap = float(options.get(f"{axis}_break_gap", "5")) / 100
            if not (all(math.isfinite(value) for value in (lower, upper, gap))
                    and minimum < lower < upper < maximum and 0 < gap < 1):
                raise ValueError
        except ValueError:
            raise ValueError(f"{axis.upper()} 轴截断需要两个位于显示范围内的递增坐标，断口百分比须大于 0 且小于 100。") from None
        cuts[axis] = lower, upper, gap
    return cuts


def _segments(limits, cut):
    if cut is None:
        return [limits], [1]
    first, last = limits
    lower, upper, gap = cut
    segments = ([(first, lower), (upper, last)] if first < last
                else [(first, upper), (lower, last)])
    lengths = [abs(end - start) for start, end in segments]
    return segments, [lengths[0], sum(lengths) * gap / (1 - gap), lengths[1]]


def panel_cells(figure, rows, columns, count, xlim, ylim, xcut, ycut):
    xs, widths = _segments(xlim, xcut)
    ys, heights = _segments(ylim, ycut)
    ys.reverse()
    heights.reverse()
    grid = figure.add_gridspec(rows * len(heights), columns * len(widths),
                              height_ratios=heights * rows, width_ratios=widths * columns,
                              hspace=0, wspace=0)
    for index in range(count):
        panel_row, panel_column = divmod(index, columns)
        for row, ylimits in enumerate(ys):
            for column, xlimits in enumerate(xs):
                axis = figure.add_subplot(grid[panel_row * len(heights) + row * 2,
                                               panel_column * len(widths) + column * 2])
                yield index, axis, xlimits, ylimits, row, column, len(ys), len(xs)


def _draw_break(axis, edge, vertical, pattern):
    style = dict(transform=axis.transAxes, color="#334155", clip_on=False, zorder=10)
    if pattern == "斜杠":
        x, y = ([edge, edge], [0, 1]) if vertical else ([0, 1], [edge, edge])
        axis.plot(x, y, marker=[(-1, -.6), (1, .6)], markersize=6, linestyle="none", **style)
        return
    if pattern == "波浪线":
        along = [index / 60 for index in range(61)]
        offsets = [.009 * math.sin(6 * math.pi * value) for value in along]
    else:
        # A small lightning-shaped kink in the center of a straight seam.
        along = [0, .44, .49, .47, .56, 1]
        offsets = [0, 0, .016, -.016, 0, 0]
    across = [edge + offset for offset in offsets]
    x, y = (across, along) if vertical else (along, across)
    axis.plot(x, y, linewidth=.85, solid_joinstyle="round", **style)


def mark_breaks(axis, row, column, rows, columns, xstyle, ystyle):
    if columns > 1:
        edge = 1 if column == 0 else 0
        axis.spines["right" if edge else "left"].set_visible(False)
        _draw_break(axis, edge, True, xstyle)
        if column:
            axis.tick_params(axis="y", left=False, labelleft=False)
    if rows > 1:
        edge = 0 if row == 0 else 1
        axis.spines["top" if edge else "bottom"].set_visible(False)
        _draw_break(axis, edge, False, ystyle)
        if row < rows - 1:
            axis.tick_params(axis="x", bottom=False, labelbottom=False)
