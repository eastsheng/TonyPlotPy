"""Persistent appearance preferences for the desktop interface."""
from __future__ import annotations

import json
from pathlib import Path


SETTINGS_FILE = Path(__file__).resolve().parent.parent / "settings.json"
THEMES = {
    "蓝色": {"bg": "#f4f7fb", "border": "#dbe4ef", "accent": "#2563eb",
             "hover": "#1d4ed8", "soft": "#edf4ff", "tab": "#e8eff8",
             "tab_hover": "#dbeafe", "scroll": "#cbd5e1", "icon": "blue"},
    "红色": {"bg": "#fff5f6", "border": "#f4d7db", "accent": "#d92345",
             "hover": "#b91c3b", "soft": "#fff0f2", "tab": "#fbe6ea",
             "tab_hover": "#ffdce3", "scroll": "#e8bec7", "icon": "red"},
    "青绿": {"bg": "#f1f8f6", "border": "#d0e7df", "accent": "#0f766e",
             "hover": "#0b5f58", "soft": "#eaf7f3", "tab": "#e0f0eb",
             "tab_hover": "#cce9df", "scroll": "#bfdcd2", "icon": "green"},
    "紫色": {"bg": "#f8f5fc", "border": "#e5d9f3", "accent": "#7c3aed",
             "hover": "#6d28d9", "soft": "#f4edff", "tab": "#eee5fa",
             "tab_hover": "#e4d5fa", "scroll": "#d6c5eb", "icon": "purple"},
}
WINDOW_SIZES = {"紧凑": "960x620", "标准": "1080x700", "宽屏": "1280x800"}
DEFAULTS = {"theme": "蓝色", "font_size": 10, "dpi": 300,
            "window_size": "标准", "language": "中文"}


def load_settings() -> dict:
    values = DEFAULTS.copy()
    try:
        saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        if isinstance(saved, dict):
            values.update(saved)
    except (OSError, ValueError):
        pass
    if values["theme"] not in THEMES:
        values["theme"] = DEFAULTS["theme"]
    if values["window_size"] not in WINDOW_SIZES:
        values["window_size"] = DEFAULTS["window_size"]
    if values["language"] not in ("中文", "English"):
        values["language"] = DEFAULTS["language"]
    try:
        values["font_size"] = int(values["font_size"])
        values["dpi"] = int(values["dpi"])
    except (TypeError, ValueError):
        values["font_size"] = DEFAULTS["font_size"]
        values["dpi"] = DEFAULTS["dpi"]
    if not 9 <= values["font_size"] <= 16:
        values["font_size"] = DEFAULTS["font_size"]
    if not 72 <= values["dpi"] <= 1200:
        values["dpi"] = DEFAULTS["dpi"]
    return values


def save_settings(values: dict) -> None:
    SETTINGS_FILE.write_text(json.dumps(values, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
