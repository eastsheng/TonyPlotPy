"""直接读取 Atlas ASCII .str，绘制可定制的二维电流密度云图。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from matplotlib.collections import LineCollection, PolyCollection
from matplotlib.colors import LinearSegmentedColormap, LogNorm, Normalize
from matplotlib.cm import ScalarMappable


# Renderer defaults. The desktop interface supplies data paths and plot settings.
# The color sequence is interpolated continuously from low to high values.
TONYPLOT_COLORS = (
    "#ff00ff", "#e500ff", "#c700ff", "#ac00ff", "#9500ff", "#7500ff",
    "#6200ff", "#0000ff", "#0064ff", "#0076ff", "#0097ff", "#00afff",
    "#00c7ff", "#00e4ff", "#00ffff", "#00ffe4", "#00ffc7", "#00ffb1",
    "#00ff92", "#00ff76", "#2bff00", "#75ff00", "#b0ff00", "#c8ff00",
    "#e4ff00", "#ffff00", "#ffe500", "#ffca00", "#ffac00", "#ff9500",
    "#ff7500", "#ff6100", "#ff2300", "#ff0000",
)
TONYPLOT_CMAP = LinearSegmentedColormap.from_list(
    "tonyplot_user_smooth", TONYPLOT_COLORS, N=1024,
)
COLOR_PRESETS = {
    "tonyplot_user_smooth": TONYPLOT_CMAP,
    "viridis": "viridis",
    "cividis": "cividis",
    "inferno": "inferno",
    "magma": "magma",
    "plasma": "plasma",
    "turbo": "turbo",
    "jet": "jet",
}
CURRENT_SCALE = "linear"  # "log" 或 "linear"
RENDER_STYLE = "fine_contour"  # "smooth" 原效果；"fine_contour" 细等值带；"smooth_contours" 平滑云图叠细轮廓线
CURRENT_CONTOUR_BANDS = 120  # 仅 fine_contour 模式使用，避免 10 级色带过粗
TEMPERATURE_CONTOUR_BANDS = 90
GUIDE_CONTOUR_LINES = 16  # 仅 smooth_contours 模式使用
CURRENT_VMIN = 0  # 例如 1e-2；None 表示自动
CURRENT_VMAX = 100  # 例如 1e4；None 表示自动
TEMPERATURE_VMIN = 300
TEMPERATURE_VMAX = 334.5
PERCENTILE_MAX = 99.5  # 自动色标上限，抑制孤立极值
# 以下数字为 Atlas 5.30 ASCII .str 中 s 记录的字段编号。读取时会检验
# |J_e|、|J_h| 与其 x/y 分量的关系，避免静默使用不兼容的 .str 文件。
FIELD_CODES = {
    "net_doping": 115,  # 带符号净掺杂；零等值线为 P/N 冶金结
    "electron": 211,
    "electron_x": 220,
    "electron_y": 224,
    "hole": 210,
    "hole_x": 221,
    "hole_y": 225,
    "conduction_total": 108,
    "conduction_x": 524,
    "conduction_y": 525,
    "total": 215,  # Atlas 保存的 J.TOTAL，包含瞬态位移电流
    "total_x": 222,
    "total_y": 226,
    "temperature": 124,
}

FIELD_LABELS_BY_CODE = {
    115: "Net doping concentration",
    211: "Electron current density |J|",
    220: "Electron current density X component",
    224: "Electron current density Y component",
    210: "Hole current density |J|",
    221: "Hole current density X component",
    225: "Hole current density Y component",
    108: "Conduction current density |J|",
    524: "Conduction current density X component",
    525: "Conduction current density Y component",
    215: "Total current density |J|",
    222: "Total current density X component",
    226: "Total current density Y component",
    124: "Lattice temperature",
}

FIELD_UI_LABELS_BY_CODE = {
    115: "净掺杂浓度",
    211: "电子电流密度 · 幅值 |J|",
    220: "电子电流密度 · X 分量",
    224: "电子电流密度 · Y 分量",
    210: "空穴电流密度 · 幅值 |J|",
    221: "空穴电流密度 · X 分量",
    225: "空穴电流密度 · Y 分量",
    108: "传导电流密度 · 幅值 |J|",
    524: "传导电流密度 · X 分量",
    525: "传导电流密度 · Y 分量",
    215: "总电流密度 · 幅值 |J|",
    222: "总电流密度 · X 分量",
    226: "总电流密度 · Y 分量",
    124: "晶格温度",
}

FIELD_DISPLAY_ORDER = (115, 108, 524, 525, 211, 220, 224,
                       210, 221, 225, 215, 222, 226, 124)

LABELS = {
    "electron": r"Electron current density $|J_e|$ (A/cm$^2$)",
    "hole": r"Hole current density $|J_h|$ (A/cm$^2$)",
    "total": r"Total current density $|J_{total}|$ (A/cm$^2$)",
    "temperature": "Lattice temperature (K)",
}


@dataclass
class Structure:
    x: np.ndarray
    y: np.ndarray
    triangles: np.ndarray
    region_triangles: dict[int, np.ndarray]
    electrodes: dict[str, int]
    values: dict[str, np.ndarray]
    field_codes: tuple[int, ...]


def list_field_codes(path: Path) -> tuple[int, ...]:
    """Read only the ASCII STR field header, without loading the mesh."""
    with path.open("r", encoding="latin-1") as source:
        for line in source:
            if line.startswith("s "):
                parts = line.split()
                codes = tuple(map(int, parts[2:]))
                if len(codes) != int(parts[1]):
                    raise ValueError(f"{path}: s 记录字段数不一致")
                return codes
    raise ValueError(f"{path}: 未找到 s 字段记录，可能不是 ASCII .str")


def snapshot_info(file_name: str) -> tuple[Path, str, str]:
    """返回路径、图题和输出标签；非瞬态文件也能直接绘制。"""
    path = Path(file_name).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.is_file():
        raise FileNotFoundError(f"结构文件不存在：{path}")
    tag = path.stem
    try:
        seconds = float(tag.rsplit("_tr_", 1)[1])
        label = f"t = {seconds * 1e6:g} µs"
        tag = f"t{seconds * 1e6:g}".replace(".", "p") + "us"
    except (ValueError, IndexError):
        label = tag
    return path, label, tag


def read_structure(path: Path) -> Structure:
    """读取 c/t/s/n 记录；采用原始三角网格，不再做插值或镜像。"""
    coordinates: dict[int, tuple[float, float]] = {}
    triangles_by_node: list[tuple[int, int, int]] = []
    triangle_regions: list[int] = []
    node_fields: dict[int, list[float]] = {}
    codes: list[int] | None = None
    electrodes: dict[str, int] = {}
    current_region: int | None = None

    with path.open("r", encoding="latin-1") as source:
        for line in source:
            if line.startswith("c "):
                parts = line.split()
                coordinates[int(parts[1])] = (float(parts[2]), float(parts[3]))
            elif line.startswith("t "):
                parts = line.split()
                triangle_regions.append(int(parts[2]))
                triangles_by_node.append(tuple(map(int, parts[3:6])))
            elif line.startswith("s "):
                parts = line.split()
                codes = list(map(int, parts[2:]))
                if len(codes) != int(parts[1]):
                    raise ValueError(f"{path}: s 记录字段数不一致")
            elif line.startswith("n "):
                parts = line.split()
                # n 节点编号 材料编号 <s 记录对应的全部数值>
                node_fields[int(parts[1])] = [float(x) for x in parts[3:]]
            elif line.startswith("r "):
                current_region = int(line.split()[1])
            elif line.startswith("w ") and current_region is not None and '"' in line:
                # w 记录将当前 region 与 Atlas 电极名称关联。
                electrodes[line.split('"')[1].lower()] = current_region

    if not coordinates or not triangles_by_node or codes is None or not node_fields:
        raise ValueError(f"{path}: 缺少 c/t/s/n 网格记录，可能不是 ASCII .str")

    node_ids = sorted(coordinates)
    id_to_index = {node_id: index for index, node_id in enumerate(node_ids)}
    xy = np.array([coordinates[node_id] for node_id in node_ids], dtype=float)
    code_index = {code: index for index, code in enumerate(codes)}
    values: dict[str, np.ndarray] = {}
    for name, code in FIELD_CODES.items():
        if code not in code_index:
            continue
        column = code_index[code]
        # SSF 的 c/t 节点编号从 1 开始，n 记录从 0 开始。
        values[name] = np.array(
            [node_fields[node_id - 1][column] for node_id in node_ids], dtype=float
        )
    for code, column in code_index.items():
        values[f"code:{code}"] = np.array(
            [node_fields[node_id - 1][column] for node_id in node_ids], dtype=float
        )

    triangles = np.array(
        [[id_to_index[node_id] for node_id in triangle] for triangle in triangles_by_node],
        dtype=int,
    )
    # 仅显示 region 1 的 4H-SiC；氧化层和金属中这些电流量没有相同物理意义。
    region_ids = np.array(triangle_regions, dtype=int)
    region_triangles = {
        region_id: triangles[region_ids == region_id]
        for region_id in np.unique(region_ids)
    }
    silicon_carbide = region_triangles.get(1, np.empty((0, 3), dtype=int))
    if silicon_carbide.size == 0:
        silicon_carbide = triangles

    # 核验字段编号：幅值必须与对应方向分量的模一致。
    sic_nodes = np.unique(silicon_carbide)
    for magnitude, x_name, y_name in (
        ("electron", "electron_x", "electron_y"),
        ("hole", "hole_x", "hole_y"),
        ("conduction_total", "conduction_x", "conduction_y"),
        ("total", "total_x", "total_y"),
    ):
        if not all(name in values for name in (magnitude, x_name, y_name)):
            continue
        expected = np.hypot(values[x_name][sic_nodes], values[y_name][sic_nodes])
        actual = values[magnitude][sic_nodes]
        if not np.allclose(actual, expected, rtol=2e-3, atol=1e-5):
            raise ValueError(
                f"{path}: {magnitude} 与 x/y 分量不符；请核对 .str 字段映射"
            )

    return Structure(
        x=xy[:, 0], y=xy[:, 1], triangles=silicon_carbide,
        region_triangles=region_triangles, electrodes=electrodes, values=values,
        field_codes=tuple(codes),
    )


def mirror_structure(structure: Structure, axis_x: float) -> Structure:
    """把半胞的原始 x 坐标和所有节点场量映射到对称的另一半。"""
    if structure.x.min() < -1e-8 or structure.x.max() > axis_x + 1e-8:
        raise ValueError(
            f"输入结构的 x 范围为 {structure.x.min():g}–{structure.x.max():g} µm，"
            f"不能按半胞 x={axis_x:g} µm 镜像；请关闭镜像选项"
        )
    old_count = structure.x.size
    seam = np.isclose(structure.x, axis_x, rtol=0, atol=1e-8)
    reflected_sources = np.flatnonzero(~seam)
    mirrored_index = np.arange(old_count, dtype=int)
    mirrored_index[reflected_sources] = old_count + np.arange(reflected_sources.size)

    def join_triangles(triangles: np.ndarray) -> np.ndarray:
        reflected = mirrored_index[triangles[:, [0, 2, 1]]]
        return np.vstack((triangles, reflected))

    return Structure(
        x=np.concatenate((structure.x, 2 * axis_x - structure.x[reflected_sources])),
        y=np.concatenate((structure.y, structure.y[reflected_sources])),
        triangles=join_triangles(structure.triangles),
        region_triangles={
            region: join_triangles(triangles)
            for region, triangles in structure.region_triangles.items()
        },
        electrodes=structure.electrodes.copy(),
        values={
            name: np.concatenate((
                value,
                -value[reflected_sources]
                if name in {"electron_x", "hole_x", "conduction_x", "total_x",
                             "code:220", "code:221", "code:524", "code:222"}
                else value[reflected_sources],
            ))
            for name, value in structure.values.items()
        },
        field_codes=structure.field_codes,
    )


def plot_region(ax, structure: Structure, region_id: int, color: str,
                rotated: bool = True) -> None:
    """按 .str 原始三角形填充材料，并画出该区域的外轮廓。"""
    triangles = structure.region_triangles.get(region_id)
    if triangles is None or triangles.size == 0:
        return
    xy = np.column_stack((structure.y, structure.x)) if rotated else np.column_stack((structure.x, structure.y))
    ax.add_collection(PolyCollection(
        xy[triangles], facecolor=color, edgecolor="none",
        linewidth=0, antialiased=False, zorder=2,
    ))
    edges = np.sort(
        np.concatenate((triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]])),
        axis=1,
    )
    unique_edges, counts = np.unique(edges, axis=0, return_counts=True)
    outline = unique_edges[counts == 1]
    ax.add_collection(LineCollection(xy[outline], colors="#303030", linewidths=0.65, zorder=3))


def color_norm(structures: list[Structure], quantity: str, bounds: tuple[float, ...]):
    """同一物理量的全部时间点共用色标，且只按当前显示区域统计。"""
    x0, x1, y0, y1 = bounds
    selected = []
    for structure in structures:
        active_nodes = np.zeros(structure.x.size, dtype=bool)
        active_nodes[np.unique(structure.triangles)] = True
        in_view = (
            (structure.x >= x0) & (structure.x <= x1)
            & (structure.y >= y0) & (structure.y <= y1)
            & active_nodes
        )
        data = structure.values[quantity][in_view]
        selected.append(data[np.isfinite(data)])
    all_values = np.concatenate(selected)
    if all_values.size == 0:
        raise ValueError(f"{quantity}: 当前视野没有有效节点")

    if quantity.startswith("code:") or quantity not in ("electron", "hole", "total", "temperature"):
        lower = float(np.min(all_values))
        upper = float(np.percentile(all_values, PERCENTILE_MAX))
        if upper <= lower:
            upper = lower + max(abs(lower) * 0.01, 1e-30)
        return Normalize(vmin=lower, vmax=upper, clip=True)

    if quantity == "temperature":
        lower = TEMPERATURE_VMIN if TEMPERATURE_VMIN is not None else float(np.min(all_values))
        upper = TEMPERATURE_VMAX if TEMPERATURE_VMAX is not None else float(np.percentile(all_values, PERCENTILE_MAX))
        if upper <= lower:
            upper = lower + 1
        return Normalize(vmin=lower, vmax=upper, clip=True)

    if CURRENT_SCALE == "log":
        positive = all_values[all_values > 0]
        if positive.size == 0:
            raise ValueError(f"{quantity}: 当前视野没有正电流密度")
        upper = CURRENT_VMAX if CURRENT_VMAX is not None else float(np.percentile(positive, PERCENTILE_MAX))
        lower = CURRENT_VMIN if CURRENT_VMIN is not None else max(1e-4, upper * 1e-5)
        if upper <= lower:
            upper = lower * 10
        return LogNorm(vmin=lower, vmax=upper, clip=True)

    lower = CURRENT_VMIN if CURRENT_VMIN is not None else 0.0
    upper = CURRENT_VMAX if CURRENT_VMAX is not None else float(np.percentile(all_values, PERCENTILE_MAX))
    if upper <= lower:
        upper = lower + 1
    return Normalize(vmin=lower, vmax=upper, clip=True)


def draw_field(ax, triangulation, values, quantity, cmap, norm):
    """按选定模式绘制场量；等值带使用真实网格插值，而非像素分箱。"""
    # Atlas current magnitudes can contain zeros (and tiny negative roundoff).
    # Matplotlib's logarithmic contouring requires every node to be positive.
    plot_values = np.maximum(values, norm.vmin) if isinstance(norm, LogNorm) else values
    if RENDER_STYLE in {"smooth", "smooth_contours"}:
        image = ax.tripcolor(
            triangulation, plot_values, shading="gouraud",
            cmap=cmap, norm=norm, rasterized=True,
        )
        if RENDER_STYLE == "smooth_contours":
            levels = (
                np.geomspace(norm.vmin, norm.vmax, GUIDE_CONTOUR_LINES + 2)[1:-1]
                if isinstance(norm, LogNorm)
                else np.linspace(norm.vmin, norm.vmax, GUIDE_CONTOUR_LINES + 2)[1:-1]
            )
            levels = levels[(levels > np.min(plot_values)) & (levels < np.max(plot_values))]
            if levels.size:
                ax.tricontour(triangulation, plot_values, levels=levels,
                              colors="black", linewidths=0.18, alpha=0.25)
        return image
    if RENDER_STYLE != "fine_contour":
        raise ValueError(f"未知 RENDER_STYLE: {RENDER_STYLE}")
    bands = TEMPERATURE_CONTOUR_BANDS if quantity == "temperature" else CURRENT_CONTOUR_BANDS
    if bands < 2:
        raise ValueError("等值带数量必须不少于 2")
    levels = (
        np.geomspace(norm.vmin, norm.vmax, bands + 1)
        if isinstance(norm, LogNorm)
        else np.linspace(norm.vmin, norm.vmax, bands + 1)
    )
    # 使用 extend 着色超出色标的区域；直接截成 vmax 会让最高值平台留下白块。
    return ax.tricontourf(
        triangulation, plot_values, levels=levels,
        cmap=cmap, norm=norm, extend="both", antialiased=False,
    )


def add_colorbar(figure, image, **kwargs):
    """等值带图仍使用连续色条，避免色条出现分段线。"""
    if RENDER_STYLE == "fine_contour":
        image = ScalarMappable(norm=image.norm, cmap=image.cmap)
    return figure.colorbar(image, **kwargs)
