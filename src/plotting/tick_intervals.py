"""Configurable major tick intervals for linear and logarithmic axes."""
import math

from matplotlib.ticker import Locator


def parse_interval(text):
    if not text.strip():
        return None
    try:
        value = float(text)
    except ValueError:
        value = math.nan
    if not math.isfinite(value) or value <= 0:
        raise ValueError("刻度间隔必须是大于 0 的有限数值")
    return value


class IntervalLocator(Locator):
    def __init__(self, automatic, step, scale, threshold=0):
        self.automatic = automatic
        self.step = step
        self.scale = scale
        self.threshold = threshold

    def __call__(self):
        low, high = sorted(self.axis.get_view_interval())
        try:
            if self.scale == "log":
                return self._log_ticks(low, high)
            if self.scale == "symlog":
                negative = self._log_ticks(max(self.threshold, -high), -low)
                positive = self._log_ticks(max(self.threshold, low), high)
                return [-value for value in reversed(negative)] + ([0] if low <= 0 <= high else []) + positive
            return [index * self.step for index in self._indices(low, high)]
        except (ValueError, OverflowError):
            # A later zoom-out can make a previously reasonable interval too dense.
            return self.automatic()

    def _indices(self, low, high):
        first = math.ceil(low / self.step - 1e-10)
        last = math.floor(high / self.step + 1e-10)
        if last - first >= self.MAXTICKS:
            raise ValueError
        return range(first, last + 1)

    def _log_ticks(self, low, high):
        if high < low:
            return []
        return [10.0 ** (index * self.step)
                for index in self._indices(math.log10(low), math.log10(high))]


def interval_locator(axis, step, current=None):
    locator = axis.get_major_locator() if current is None else current
    if isinstance(locator, IntervalLocator):
        locator = locator.automatic
    if step is None:
        return locator
    scale = axis.get_scale()
    threshold = axis.get_transform().linthresh if scale == "symlog" else 0
    return IntervalLocator(locator, step, scale, threshold)
