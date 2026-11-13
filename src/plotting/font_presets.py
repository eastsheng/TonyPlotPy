"""Installed fonts commonly used in scientific figures."""
from __future__ import annotations

from matplotlib import font_manager


AXIS_TICK_SIZE = 18
AXIS_LABEL_SIZE = 20
TITLE_SIZE = 18
COLORBAR_TICK_SIZE = 15
COLORBAR_LABEL_SIZE = 16


PAPER_FONTS = (
    "Arial", "Helvetica", "Times New Roman", "Cambria", "Calibri",
    "DejaVu Sans", "DejaVu Serif", "Liberation Sans", "Liberation Serif",
    "STIXGeneral", "Microsoft YaHei",
)


def available_paper_fonts(current: str | None = None) -> tuple[str, ...]:
    installed = {font.name.casefold() for font in font_manager.fontManager.ttflist}
    # Matplotlib resolves this generic family through its font configuration.
    choices = ["sans-serif"]
    choices.extend(font for font in PAPER_FONTS if font.casefold() in installed)
    if current and current not in choices:
        choices.insert(0, current)
    return tuple(choices)
