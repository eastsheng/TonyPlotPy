"""Small, dependency-free translations for the desktop interface."""
from __future__ import annotations

import re
import tkinter as tk
from .control_hints import HINTS


ENGLISH = {
    "Atlas STR 云图": "Atlas STR maps",
    "LOG 曲线": "LOG curves",
    "软件设置": "Settings", "语言": "Language", "颜色主题": "Color theme",
    "显示参数": "Display settings", "色图": "Colormap", "标度": "Scale",
    "下限": "Minimum", "上限": "Maximum", "等值带数": "Contour levels",
    "留空的数值使用全局设置或自动范围": "Blank values use global settings or automatic ranges",
    "界面字号": "Interface font size", "默认导出 DPI": "Default export DPI",
    "窗口尺寸": "Window size", "设置会在下次启动时自动恢复": "Settings are restored on the next launch",
    "取消": "Cancel", "应用": "Apply", "预览": "Preview",
    "确定并关闭": "Confirm and close", "预览删除": "Preview deletion",
    "设置无效": "Invalid settings", "参数无效": "Invalid parameters",
    "蓝色": "Blue", "红色": "Red", "青绿": "Teal", "紫色": "Purple",
    "紧凑": "Compact", "标准": "Standard", "宽屏": "Wide",
    "  STR 云图  ": "  STR maps  ", "  LOG 曲线  ": "  LOG curves  ",
    "画图 / 更新预览": "Plot / update preview", "导出图片": "Export image",
    "设置": "Settings", "选择目录": "Choose folder", "加载目录": "Load folder",
    "添加文件": "Add files", "移除": "Remove", "移除选中": "Remove selected",
    "上移": "Move up", "下移": "Move down", "清空": "Clear",
    "仅保留选中项": "Keep selected only", "清除字段选择": "Clear field selection",
    "清除曲线选择": "Clear curve selection", "默认": "Default",
    "数据文件（列表顺序即组合图顺序）": "Data files (list order sets panel order)",
    "LOG 数据文件": "LOG data files", "视图与组合": "View and layout",
    "方向": "Orientation", "纵向（x 横轴）": "Vertical (x horizontal)",
    "横向（深度横轴）": "Horizontal (depth horizontal)",
    "排列": "Layout", "物理量 × 时间": "Quantity × time",
    "时间 × 物理量": "Time × quantity", "自由网格": "Custom grid",
    "自由网格列数": "Custom grid columns", "镜像为完整单胞": "Mirror full cell",
    "镜像轴 x (µm)": "Mirror axis x (µm)",
    "显示结构与结线": "Show structure and junctions",
    "显示坐标网格": "Show grid", "x 最小值": "x minimum", "x 最大值": "x maximum",
    "深度最小值": "Depth minimum", "深度最大值": "Depth maximum",
    "色彩与渲染": "Color and rendering", "电流色图": "Current colormap",
    "温度色图": "Temperature colormap", "电流标度": "Current scale",
    "渲染方式": "Rendering method", "电流下限（空=自动）": "Current minimum (blank = auto)",
    "电流上限（空=自动）": "Current maximum (blank = auto)",
    "温度下限（空=自动）": "Temperature minimum (blank = auto)",
    "温度上限（空=自动）": "Temperature maximum (blank = auto)",
    "自动上限百分位": "Auto maximum percentile",
    "电流等值带数": "Current contour levels", "温度等值带数": "Temperature contour levels",
    "轮廓线数": "Contour lines", "输出": "Output",
    "每列宽度 (英寸)": "Width per column (in)",
    "每行高度 (英寸)": "Height per row (in)",
    "导出 DPI": "Export DPI", "横轴与曲线": "X axis and curves",
    "横轴": "X axis", "纵轴曲线（可按 Ctrl/Shift 多选）": "Y curves (Ctrl/Shift to select)",
    "右轴曲线（从已选纵轴曲线中选择）": "Right-axis curves (from selected Y curves)",
    "绘图方式": "Plot mode", "叠加曲线": "Overlay curves",
    "每信号子图": "One subplot per signal", "每曲线单独图片": "One image per curve",
    "启用双 Y 轴（叠加曲线）": "Enable dual Y axes (overlay)",
    "右轴标度": "Right-axis scale", "右轴最小（空=自动）": "Right minimum (blank = auto)",
    "右轴最大（空=自动）": "Right maximum (blank = auto)",
    "坐标与样式": "Axes and style", "横轴标度": "X-axis scale",
    "纵轴标度": "Y-axis scale", "横轴倍率": "X-axis multiplier",
    "横轴最小（空=自动）": "X minimum (blank = auto)",
    "横轴最大（空=自动）": "X maximum (blank = auto)",
    "纵轴最小（空=自动）": "Y minimum (blank = auto)",
    "纵轴最大（空=自动）": "Y maximum (blank = auto)",
    "线宽": "Line width", "图标题（空=不显示）": "Plot title (blank = hidden)",
    "电子电流密度（幅值）": "Electron current density (magnitude)",
    "空穴电流密度（幅值）": "Hole current density (magnitude)",
    "总电流密度（幅值）": "Total current density (magnitude)",
    "晶格温度": "Lattice temperature",
    "其他已命名字段（多选，双击设置）": "Other named fields (multi-select; double-click to edit)",
    "编辑曲线": "Edit curve", "曲线颜色": "Curve color", "曲线线宽": "Curve width",
    "线型": "Line style", "数据点形状": "Marker shape", "数据点大小": "Marker size",
    "图例名称": "Legend label", "图例字号": "Legend font size",
    "图例字体": "Legend font", "图例标题": "Legend title",
    "图标题": "Plot title", "标题字号": "Title font size",
    "编辑图中文字": "Edit figure text", "内容": "Text",
    "颜色": "Color", "字体": "Font", "标注文字": "Annotation text",
    "字号 (pt)": "Font size (pt)", "箭头线宽": "Arrow width",
    "编辑坐标轴": "Edit axes", "横轴左边界": "X-axis left limit",
    "横轴右边界": "X-axis right limit", "纵轴下边界": "Y-axis lower limit",
    "纵轴上边界": "Y-axis upper limit", "刻度字号": "Tick font size",
    "刻度字体": "Tick font", "刻度颜色": "Tick color",
    "横轴线颜色": "X-axis line color", "纵轴线颜色": "Y-axis line color",
    "编辑图片尺寸": "Edit image size", "宽度 (英寸)": "Width (in)",
    "高度 (英寸)": "Height (in)", "添加箭头": "Add arrow",
    "编辑箭头标注": "Edit arrow annotation", "添加箭头标注": "Add arrow annotation",
    "取消箭头": "Cancel arrow", "选择…": "Choose…",
    "绘图失败": "Plot failed", "导出失败": "Export failed",
    "目录无效": "Invalid folder", "目录存在": "Folder exists",
    "目录不存在，请检查路径": "Folder not found; check its path",
    "请选择至少一个 .str 文件和一个物理量": "Select at least one .str file and one quantity",
    "请选择横轴和至少一条纵轴曲线": "Select an X field and at least one Y curve",
    "请选择 Atlas SSF 数据 LOG": "Select an Atlas SSF data LOG",
    "无法绘图的日志": "Logs without plottable data",
    "这些文件不是 Atlas SSF 数据日志：\n": "These files are not Atlas SSF data logs:\n",
    "点击顶部“画图 / 更新预览”，完成后再导出。": "Click Plot / update preview, then export when drawing is complete.",
    "所选 LOG 没有名称一致的共同曲线": "Selected LOG files have no common named curves",
    "请选择至少一条左轴曲线和一条右轴曲线": "Select at least one curve for each Y axis",
    "请先画图": "Plot a figure first", "图表预览": "Plot preview",
    "选择 .str 文件后生成预览": "Select .str files to create a preview",
    "选择 Atlas 数据 LOG 后生成曲线": "Select an Atlas data LOG to create curves",
    "后台读取与绘制中，界面仍可操作…": "Reading and plotting in the background…",
    "导出全部": "Export all", "字体颜色": "Font color",
    "颜色值无效": "Invalid color value",
    "选择有效的主题和窗口尺寸": "Choose a valid theme and window size",
    "请选择有效的主题和窗口尺寸": "Choose a valid theme and window size",
    "界面字号需在 9–16 之间": "Interface font size must be 9–16",
    "默认导出 DPI 需在 72–1200 之间": "Default export DPI must be 72–1200",
    "每行放几个子图；修改后自动切换为自由网格": "Number of panels per row; changing it selects Custom grid",
    "幅值是合成大小；X/Y 是方向分量，可分别绘制": "Magnitude combines X and Y; each directional component can be plotted separately",
    "Ctrl+单击可取消单项；双击设置显示参数": "Ctrl-click deselects one item; double-click edits display settings",
    "顶部按钮可画图并导出 PNG/PDF/SVG": "Use the top buttons to plot and export PNG/PDF/SVG",
    "只加载含 p/d 数据的 Atlas LOG；运行控制台日志不绘图": "Only Atlas LOG files with p/d data are loaded; console logs are skipped",
    "时间默认乘 1e6，显示为 µs": "Time is multiplied by 1e6 and shown in µs by default",
    "拖动中间分隔线可调整参数区和预览区的宽度。": "Drag the divider to resize the settings and preview panels.",
    "选择 LOG 横轴字段；时间字段默认换算为微秒。": "Choose a LOG X-axis field; time is converted to microseconds by default.",
    "单独绘图模式下切换当前预览的曲线；导出时仍会保存全部图片。": "Choose which curve to preview in separate-image mode; export still saves all images.",
    "STR：二维物理场云图。": "STR: two-dimensional physical-field maps.",
    "LOG：曲线图和双 Y 轴。": "LOG: curves and dual Y axes.",
    "在列表中选择条目；可使用鼠标滚轮浏览更多内容。": "Select items in the list; use the mouse wheel to scroll.",
    "列表中的所有 STR 文件都会参与绘图；选中用于移除、排序或仅保留操作。": "All listed STR files are plotted; select files to remove, reorder, or keep only those selected.",
    "列表中的所有 LOG 文件都会参与绘图；选中用于移除操作。": "All listed LOG files are plotted; select files to remove them from the list.",
    "Ctrl/Shift 多选；双击可设置该字段的色图、标度与范围。": "Ctrl/Shift selects multiple fields; double-click to edit colormap, scale, and range.",
    "Ctrl/Shift 可多选；选中的曲线用于叠加、子图或单独导出。": "Ctrl/Shift selects multiple curves for overlay, subplots, or separate export.",
    "此曲线使用右侧 Y 轴；未选中的曲线使用左侧 Y 轴。": "Selected curves use the right Y axis; the others use the left Y axis.",
    "在后台读取文件并更新预览。修改参数后再次点击生效。": "Read files and update the preview in the background. Click again after changing parameters.",
    "将当前预览导出为 PNG、PDF 或 SVG；图片默认保存到 imgs 文件夹。": "Export the preview as PNG, PDF, or SVG; imgs is the default destination.",
    "切换主题、界面字号、默认导出 DPI 和窗口尺寸。": "Change theme, interface font size, export DPI, window size, and language.",
    "打开文件夹选择器。选定后自动加载目录中的数据文件。": "Choose a folder and load its data files automatically.",
    "读取输入框中的目录，更新文件和可选字段列表。": "Read the entered folder and refresh file and field lists.",
    "从其他位置添加数据文件；原有列表不会清空。": "Add data files from elsewhere without clearing the current list.",
    "从当前列表移除高亮文件；不会删除磁盘文件。": "Remove highlighted files from the list without deleting them from disk.",
    "将选中的 STR 文件上移，改变组合图顺序。": "Move selected STR files up in the panel order.",
    "将选中的 STR 文件下移，改变组合图顺序。": "Move selected STR files down in the panel order.",
    "清空当前文件列表；不会删除磁盘文件。": "Clear the file list without deleting files from disk.",
    "只保留当前高亮的 STR 文件参与绘图。": "Plot only the highlighted STR files.",
    "取消“其他已命名字段”的选择；常用物理量勾选不变。": "Clear selections under Other named fields; common quantities stay selected.",
    "取消 LOG 纵轴曲线选择；横轴设置不变。": "Clear LOG Y-curve selection; keep the X-axis setting.",
    "勾选后绘制该物理量；双击可单独设置色图、标度和范围。": "Select to plot this quantity; double-click to edit its colormap, scale, and range.",
    "只加载含 p/d 数据的 Atlas LOG；运行控制台日志不绘图": "Only Atlas LOG files with p/d data are loaded; console logs are skipped.",
    "列表为空；请先加载目录或添加文件。": "The list is empty; load a folder or add files first.",
}

ENGLISH.update({HINTS[key]: text for key, text in {
    "orientation": "Choose the map orientation; horizontal mode puts depth on the X axis.",
    "layout": "Choose the STR panel arrangement; Custom grid uses the column count below.",
    "columns": "Number of panels per row; changing it selects Custom grid.",
    "mirror": "Mirror a half cell across the specified axis to show the full cell.",
    "mirror_x": "Mirror axis position for the half cell, in µm.",
    "overlay": "Overlay junctions, region outlines, and electrode labels.",
    "grid": "Show or hide the STR coordinate grid.",
    "x0": "Lower STR lateral coordinate, in µm.",
    "x1": "Upper STR lateral coordinate; mirror mode may extend it automatically.",
    "y0": "Lower STR depth coordinate, in µm.",
    "y1": "Upper STR depth coordinate, in µm.",
    "current_cmap": "Colormap for current density; double-click a field to override it.",
    "temperature_cmap": "Colormap for lattice temperature.",
    "scale": "Choose linear or logarithmic current color scale.",
    "render": "fine_contour uses narrow bands; smooth fills smoothly; smooth_contours adds contour lines.",
    "current_min": "Current color minimum; blank chooses automatically. Log scale requires positive values.",
    "current_max": "Current color maximum; blank chooses automatically.",
    "temp_min": "Temperature color minimum in K; blank chooses automatically.",
    "temp_max": "Temperature color maximum in K; blank chooses automatically.",
    "percentile": "Data percentile used for the automatic color maximum, reducing isolated outliers.",
    "current_bands": "Number of current contour bands; more bands may draw more slowly.",
    "temp_bands": "Number of temperature contour bands; more bands may draw more slowly.",
    "guide_lines": "Number of contour lines in smooth_contours mode.",
    "panel_width": "Export width per STR column, in inches.",
    "panel_height": "Export height per STR row, in inches.",
    "dpi": "STR export resolution; change the default in Settings.",
    "log_layout": "Overlay shares one image; other modes use subplots or separate images.",
    "log_dual_y": "Available for overlay; choose curves for both left and right Y axes.",
    "log_right_y_scale": "Linear or logarithmic scale for the right Y axis.",
    "log_right_y_min": "Right Y-axis minimum; blank chooses automatically.",
    "log_right_y_max": "Right Y-axis maximum; blank chooses automatically.",
    "log_x_scale": "Linear or logarithmic LOG X axis.",
    "log_y_scale": "Linear or logarithmic LOG left Y axis.",
    "log_x_multiplier": "Multiply raw X values by this factor; time defaults to 1e6 for µs.",
    "log_x_min": "LOG X-axis minimum; blank chooses automatically.",
    "log_x_max": "LOG X-axis maximum; blank chooses automatically.",
    "log_y_min": "LOG left Y-axis minimum; blank chooses automatically.",
    "log_y_max": "LOG left Y-axis maximum; blank chooses automatically.",
    "log_linewidth": "LOG curve width in pt.",
    "log_grid": "Show or hide the LOG coordinate grid.",
    "log_title": "Plot title; blank hides it. Double-click the preview title to edit.",
    "log_dpi": "LOG export resolution; change the default in Settings.",
}.items()})


def translate(value: str, language: str) -> str:
    """Translate a UI string while leaving file/data labels untouched."""
    if language != "English" or not value:
        return value
    if value in ENGLISH:
        return ENGLISH[value]
    if "\n" in value:
        return "\n".join(translate(part, language) for part in value.split("\n"))
    if value.startswith("TonyPlotPy 版本 "):
        return value.replace("TonyPlotPy 版本 ", "TonyPlotPy version ", 1)
    button_hint = re.fullmatch(r"点击“(.+)”执行此操作。", value)
    if button_hint:
        return f"Click {translate(button_hint.group(1), language)} to run this action."
    if "：修改后点击“画图 / 更新预览”" in value:
        label = value.split("：", 1)[0]
        return f"Change {translate(label, language)}, then click Plot / update preview."
    folder_hint = re.fullmatch(r"输入或选择包含 \.(str|log) 文件的目录，然后点击“加载目录”。", value)
    if folder_hint:
        return f"Enter or choose a folder with .{folder_hint.group(1)} files, then click Load folder."
    folder_state = re.fullmatch(r"(目录存在|目录不存在，请检查路径)。修改路径后点击“加载目录”读取 \.(str|log) 文件。", value)
    if folder_state:
        return f"{translate(folder_state.group(1), language)}. Click Load folder to read .{folder_state.group(2)} files."
    patterns = (
        (r"^已选择 (\d+) 个数据 LOG$", r"Selected \1 data LOG files"),
        (r"^已选择 (\d+) 个 \.str 文件$", r"Selected \1 .str files"),
        (r"^预览完成：(\d+) 个文件 × (\d+) 条曲线$", r"Preview ready: \1 files × \2 curves"),
        (r"^预览完成：(\d+) 个文件 × (\d+) 个物理量$", r"Preview ready: \1 files × \2 quantities"),
        (r"^单独图片预览：第 (\d+)/(\d+) 张$", r"Image preview: \1 of \2"),
        (r"^已导出 (\d+) 张图片到：(.*)$", r"Exported \1 images to: \2"),
        (r"^已导出：(.*)$", r"Exported: \1"),
        (r"^导出全部 (\d+) 张$", r"Export all \1 images"),
        (r"^字段读取失败：(.*)$", r"Could not read fields: \1"),
    )
    for pattern, replacement in patterns:
        if re.match(pattern, value):
            return re.sub(pattern, replacement, value)
    return value


class LocalizedStringVar(tk.StringVar):
    """Keep original status text so language changes can refresh it."""

    def __init__(self, app, value: str = ""):
        self.app = app
        self.source = value
        super().__init__(master=app, value=app.tr(value))

    def set(self, value):
        self.source = str(value)
        super().set(self.app.tr(self.source))

    def refresh(self):
        super().set(self.app.tr(self.source))
