"""Read TonyPlot/Atlas SSF ASCII .log curve data."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import numpy as np


@dataclass(frozen=True)
class LogHeader:
    codes: tuple[int, ...]
    labels: dict[int, str]


@dataclass
class LogData:
    path: Path
    header: LogHeader
    values: dict[int, np.ndarray]


def read_header(path: Path) -> LogHeader:
    """Read the p column declaration and available named signals."""
    outputs: dict[int, str] = {}
    labels: dict[int, str] = {}
    with path.open("r", encoding="latin-1", errors="replace") as source:
        for line in source:
            if line.startswith("o "):
                parts = line.split(maxsplit=2)
                if len(parts) == 3:
                    outputs[int(parts[1])] = parts[2].strip()
            elif line.startswith("Q "):
                match = re.match(r'Q\s+(\d+)\s+\d+\s+"([^"]+)"', line)
                if match:
                    labels[int(match.group(1))] = match.group(2)
            elif line.startswith("p "):
                parts = line.split()
                codes = tuple(map(int, parts[2:]))
                if len(codes) != int(parts[1]):
                    raise ValueError(f"{path.name}: p 字段数不一致")
                if codes and codes[0] == 61:
                    labels[61] = "Time (s)"
                for index, name in outputs.items():
                    labels.setdefault(2999 + index, name)
                labels = {code: label for code, label in labels.items() if code in codes}
                return LogHeader(codes, labels)
    raise ValueError(f"{path.name}: 缺少 Atlas SSF 的 p 记录；可能是运行控制台日志")


def read_log(path: Path) -> LogData:
    """Read d rows aligned with p codes; skip malformed/incomplete rows."""
    header = read_header(path)
    rows = []
    with path.open("r", encoding="latin-1", errors="replace") as source:
        for line in source:
            if not line.startswith("d "):
                continue
            parts = line.split()
            if len(parts) != len(header.codes) + 1:
                continue
            try:
                rows.append(tuple(float(value) for value in parts[1:]))
            except ValueError:
                continue
    if not rows:
        raise ValueError(f"{path.name}: 没有可绘制的 d 数据记录")
    array = np.asarray(rows, dtype=float)
    return LogData(path, header, {code: array[:, index] for index, code in enumerate(header.codes)})
