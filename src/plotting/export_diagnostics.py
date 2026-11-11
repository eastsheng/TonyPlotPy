"""Limit repetitive Matplotlib font diagnostics during image export."""
from contextlib import contextmanager
import logging
import threading
import warnings


@contextmanager
def quiet_export():
    logger = logging.getLogger("matplotlib.font_manager")
    thread_id = threading.get_ident()
    seen = set()

    def allow(record):
        message = record.getMessage()
        if record.thread != thread_id or not message.startswith("findfont:"):
            return True
        if message in seen:
            return False
        seen.add(message)
        return True

    logger.addFilter(allow)
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("once", message=r"Glyph .* missing from font", category=UserWarning)
            yield
    finally:
        logger.removeFilter(allow)
