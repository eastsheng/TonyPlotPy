"""Render and play a sequence of STR cloud maps."""
import base64
import copy
import io
import json
import math
import re
import shutil
import subprocess
import tempfile
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import messagebox, ttk

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.backend_bases import MouseEvent
from PIL import Image

from .plotting import renderer
from .plotting.figure_edits import apply_edits
from .plotting.temperature_segments import parse_frame_ranges, parse_segments, segment_norm
from .deferred_canvas import DeferredFigureCanvasTkAgg
from .figure_editor import FigureEditor

COLORBAR_MODES = {
    "manual": "全程统一或手动分段",
    "max": "逐帧最大值",
    "min": "逐帧最小值",
    "both": "逐帧最小值和最大值",
}


def colorbar_mode(rule):
    return rule.get("mode", "both" if rule.get("auto") else "manual")

@dataclass
class AnimationFrame:
    figure: object
    png: bytes
    edits: dict = field(default_factory=dict)
    path: Path | None = None
    dirty: bool = False
    viewport: tuple[int, int] = (960, 680)


def edits_for_snapshot(edits, path):
    result = copy.deepcopy(edits)
    for section in ("texts", "axes"):
        for values in result.get(section, {}).values():
            identity = values.get("axis_key")
            if identity and identity[0] == "str":
                values["axis_key"] = ("str", str(path), *identity[2:])
    return result


def save_animation(path, frames, fps):
    path = Path(path).resolve()
    suffix = path.suffix.lower()
    encoder = shutil.which("ffmpeg") if suffix == ".mp4" else None
    if suffix == ".mp4" and encoder is None:
        raise RuntimeError("导出 MP4 需要将 FFmpeg 加入 PATH")
    images = [Image.open(io.BytesIO(data)) for data in frames]
    width = max(image.width for image in images)
    height = max(image.height for image in images)
    if suffix == ".mp4":
        width += width % 2
        height += height % 2

    def padded(image):
        result = Image.new("RGB", (width, height), "white")
        rgba = image.convert("RGBA")
        result.paste(rgba, ((width - image.width) // 2, (height - image.height) // 2), rgba)
        return result

    with tempfile.TemporaryDirectory(prefix=".tonyplotpy-", dir=path.parent) as staging:
        folder = Path(staging)
        output = folder / ("animation" + suffix)
        if suffix == ".gif":
            duration = [10 * (round((i + 1) * 100 / fps) - round(i * 100 / fps))
                        for i in range(len(images))]
            padded(images[0]).save(output, save_all=True,
                                   append_images=(padded(image) for image in images[1:]),
                                   duration=duration, loop=0, disposal=2)
        else:
            for index, image in enumerate(images):
                padded(image).save(folder / f"{index:06d}.png")
            result = subprocess.run(
                [encoder, "-hide_banner", "-loglevel", "error", "-framerate", str(fps),
                 "-i", str(folder / "%06d.png"), "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
                 "-movflags", "+faststart", str(output)],
                capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if result.returncode:
                raise RuntimeError(result.stderr.decode(errors="replace").strip())
        output.replace(path)


def refresh_frame_image(frame):
    if frame.dirty:
        previous = frame.figure.canvas
        previous_dpi = frame.figure.dpi
        width, height = frame.figure.get_size_inches()
        max_width, max_height = frame.viewport
        stream = io.BytesIO()
        try:
            frame.figure.set_dpi(min(100, max_width / width, max_height / height))
            FigureCanvasAgg(frame.figure).print_png(stream)
            frame.png = stream.getvalue()
            frame.dirty = False
        finally:
            frame.figure.set_dpi(previous_dpi)
            frame.figure.set_canvas(previous)


def editable_frame(root, parent, frame, arrow_button, sync):
    canvas = DeferredFigureCanvasTkAgg(frame.figure, master=parent)
    editor = FigureEditor(root, frame.figure, canvas, frame.edits, root.status,
                          on_commit=lambda: sync(frame))
    editor.arrow_button = arrow_button
    arrow_button.configure(text=root.tr("添加箭头"), command=editor.start_arrow, state="normal")
    widget = canvas.get_tk_widget()
    widget.pack(fill="both", expand=True)
    widget.bind("<Destroy>", lambda _event: canvas.cancel_pending_resize(), add="+")
    canvas.draw_idle()
    return editor


def ordered_snapshots(paths):
    def sort_key(path):
        try:
            seconds = float(path.stem.lower().rsplit("_tr_", 1)[1])
            if math.isfinite(seconds):
                return 1, seconds
        except (IndexError, ValueError):
            pass
        if re.search(r"(?:^|[_-])(?:init|initial)(?:$|[_-])", path.stem, re.IGNORECASE):
            return 0, 0
        return 2, 0

    keys = {path: sort_key(path) for path in paths}
    if not any(group == 1 for group, _ in keys.values()):
        return list(paths)
    return sorted(paths, key=keys.__getitem__)


def colorbar_fields(quantities):
    currents = tuple(q for q in quantities if q in {"electron", "hole", "total"})
    groups = {q: (q,) for q in quantities if len(currents) < 2 or q not in currents}
    if len(currents) >= 2:
        groups["shared_current"] = currents
    return groups


def render_frames(options, cache, *, export_dpi=None, edits_by_path=None, report_progress=None):
    paths = ordered_snapshots(options["files"])
    prepared = {}
    for index, path in enumerate(paths, 1):
        prepared[path] = renderer.read_structure(path, options, cache)
        if report_progress is not None:
            report_progress("reading", index, len(paths))
    options = renderer.resolve_depth(options, prepared.values())
    norms, frames = {}, []
    axes_positions = None
    segment_limits_cache = {}
    request = options["animation"]
    rules = request.get("colorbar_rules", {})
    groups = colorbar_fields(options["quantities"])
    segment_settings = request.get("temperature_segments")
    per_frame = request.get("temperature_per_frame", False)
    frame_ranges = iter(request.get("temperature_frame_ranges", ()))
    active_range = next(frame_ranges, None)
    segment_size, manual_limits = segment_settings or (len(paths), {})
    temperature_norm = None
    layout = options.get("layout", renderer.STACKED)
    if layout not in renderer.PANEL_LAYOUTS:
        layout = renderer.STACKED
    frame_paths = paths[:1] if request.get("preview") is not None else paths
    if report_progress is not None:
        report_progress("drawing", 0, len(frame_paths))
    for index, path in enumerate(frame_paths, 1):
        frame_number = index - 1
        color_limits = []
        for key, rule in rules.items():
            mode = colorbar_mode(rule)
            if mode != "manual":
                fixed = rule.get("fixed")
                limits = (fixed if mode == "max" else None, fixed if mode == "min" else None)
                color_limits.append((groups[key], [prepared[path]], limits, 100, mode, None))
                continue
            for start, end, lower, upper in rule["ranges"]:
                if start <= frame_number <= end:
                    group = [prepared[item] for item in paths[start:end + 1]]
                    color_limits.append((groups[key], group, (lower, upper), float(options["percentile"]),
                                         "manual", (key, start)))
                    break
        if per_frame:
            temperature_norm = segment_norm([prepared[path]], options["bounds"], 100, (None, None))
        if active_range and frame_number > active_range[1]:
            active_range = next(frame_ranges, None)
            temperature_norm = None
        if active_range and frame_number == active_range[0]:
            start, end, lower, upper = active_range
            group = [prepared[item] for item in paths[start:end + 1]]
            temperature_norm = segment_norm(group, options["bounds"], float(options["percentile"]), (lower, upper))
        if segment_settings and (index - 1) % segment_size == 0:
            segment = (index - 1) // segment_size + 1
            group = [prepared[item] for item in paths[index - 1:index - 1 + segment_size]]
            temperature_norm = segment_norm(group, options["bounds"], float(options["percentile"]),
                                            manual_limits.get(segment, (None, None)))
        frame = renderer.make_figure({**options, "files": [path], "layout": layout},
                                     cache, prepared=prepared, sequence_norms=norms,
                                     temperature_norm=temperature_norm, frame_color_limits=color_limits,
                                     segment_limits_cache=segment_limits_cache)
        frame.set_size_inches(*request["size"], forward=False)
        edits = (edits_for_snapshot(request.get("shared_edits", {}), path)
                 if edits_by_path is None else edits_by_path.get(path, {}))
        apply_edits(frame, edits)
        width, height = frame.get_size_inches()
        max_width, max_height = request.get("viewport", (960, 680))
        frame.set_dpi(export_dpi if export_dpi is not None else min(100, max_width / width, max_height / height))
        canvas = FigureCanvasAgg(frame)
        if axes_positions is None:
            frame.get_layout_engine().execute(frame)
            axes_positions = [axis.get_position(original=True).frozen() for axis in frame.axes]
        # Fix the axes rectangles across the sequence. Changing tick widths
        # must not change the scale or position of the device in the next frame.
        frame.set_layout_engine("none")
        for axis, position in zip(frame.axes, axes_positions):
            axis.set_position(position)
        stream = io.BytesIO()
        canvas.print_png(stream, pil_kwargs={"compress_level": 1})
        if export_dpi is not None:
            frames.append(stream.getvalue())
            frame.clear()
            frame.set_canvas(None)
        else:
            frame._tonyplot_export_size = (width, height)
            frames.append(AnimationFrame(frame, stream.getvalue(), edits, path,
                                         viewport=(max_width, max_height)))
        if report_progress is not None:
            report_progress("drawing", index, len(frame_paths))
    return frames


def build_animation_panel(root, parent, launch):
    form = ttk.Frame(parent, padding=12)
    form.pack(fill="both", expand=True)
    dimensions = ttk.Frame(form)
    dimensions.pack(fill="x")
    values = []
    for column, (label, default) in enumerate((("宽度 (mm)", "100"), ("高度 (mm)", "160"))):
        ttk.Label(dimensions, text=label).grid(row=0, column=column, sticky="w", padx=4)
        value = tk.StringVar(master=parent, value=default)
        entry = ttk.Entry(dimensions, textvariable=value, width=12)
        entry.grid(row=1, column=column, sticky="ew", padx=4)
        dimensions.columnconfigure(column, weight=1)
        values.append(value)
        root.control_hints.append((entry, "设置动态云图每帧的宽度和高度。"))

    output = ttk.Frame(form)
    output.pack(side="bottom", fill="both", expand=True, pady=8)
    output.pack_propagate(False)
    current_figure = None
    sequence_snapshot = None
    pause_playback = None
    shared_edits = {}
    displayed_frames = []
    frames_per_segment = root.var("animation_temperature_interval", "")
    segment_entries = root.var("animation_temperature_limits", "")
    frame_ranges = root.var("animation_temperature_frame_ranges", "[]")
    temperature_per_frame = root.var("animation_temperature_per_frame", False)
    colorbar_rules = root.var("animation_colorbar_rules", "{}")

    def edit_temperature_segments():
        groups = colorbar_fields(root.selected_str_quantities())
        if not groups:
            messagebox.showinfo(root.tr("色棒范围…"), root.tr("请先选择云图物理量。"), parent=root)
            return
        rules = json.loads(colorbar_rules.get())
        dialog = tk.Toplevel(root)
        dialog.title(root.tr("色棒范围…"))
        dialog.transient(root)
        dialog.grab_set()
        body = ttk.Frame(dialog, padding=12)
        body.pack(fill="both", expand=True)
        labels = [root.tr("共用电流密度色棒") if key == "shared_current" else renderer.quantity_label(key)
                  for key in groups]
        selector = ttk.Combobox(body, values=labels, state="readonly", width=46)
        selector.pack(fill="x", pady=(0, 8))
        selector.current(0)
        current = next(iter(groups))
        modes = ttk.Combobox(body, values=[root.tr(label) for label in COLORBAR_MODES.values()], state="readonly")
        modes.pack(fill="x", pady=(0, 4))
        fixed_row = ttk.Frame(body)
        fixed_label = ttk.Label(fixed_row)
        fixed_label.pack(side="left", padx=(0, 8))
        fixed_value = tk.StringVar(master=dialog)
        ttk.Entry(fixed_row, textvariable=fixed_value, width=16).pack(side="left")

        def mode_changed(_event=None):
            mode = list(COLORBAR_MODES)[modes.current()]
            fixed_row.pack_forget()
            if mode in ("min", "max"):
                caption = "固定下限（留空使用全程下限）" if mode == "max" else "固定上限（留空使用全程上限）"
                fixed_label.configure(text=root.tr(caption))
                fixed_row.pack(fill="x", after=modes, pady=(0, 4))

        modes.bind("<<ComboboxSelected>>", mode_changed)
        ttk.Label(body, text=root.tr("启用逐帧自动时，暂停使用下方的手动分段。"),
                  wraplength=500).pack(anchor="w", pady=(0, 8))
        ttk.Label(body, text=root.tr("帧从 0 开始，包含起止帧。上下限留空自动计算，未列出的帧使用全程范围。"),
                  wraplength=500).pack(anchor="w", pady=(0, 8))
        table = ttk.Frame(body)
        table.pack(fill="both", expand=True)
        for column, title in enumerate(("起始帧", "结束帧", "下限", "上限")):
            ttk.Label(table, text=root.tr(title)).grid(row=0, column=column, sticky="w", padx=4)
            table.columnconfigure(column, weight=1)
        rows = {}
        next_row = 1

        def add_row(values=("", "", "", "")):
            nonlocal next_row
            row = next_row
            next_row += 1
            cells = []
            for column, value in enumerate(values):
                entry = ttk.Entry(table, width=12)
                entry.insert(0, value if value is not None else "")
                entry.grid(row=row, column=column, sticky="ew", padx=4, pady=3)
                cells.append(entry)
            rows[row] = cells

            def remove():
                for widget in (*rows.pop(row), button):
                    widget.destroy()

            button = ttk.Button(table, text=root.tr("移除"), command=remove)
            button.grid(row=row, column=4, padx=4)
            cells[0].focus_set()

        saved = json.loads(frame_ranges.get())
        if not saved and frames_per_segment.get():
            size, limits = parse_segments(frames_per_segment.get(), segment_entries.get())
            selected = root.file_list.curselection()
            count = len(selected) or len(root.files)
            saved = [(start, min(start + size, count) - 1, *limits.get(index, (None, None)))
                     for index, start in enumerate(range(0, count, size), 1)]
        if "temperature" not in rules and (saved or temperature_per_frame.get()):
            rules["temperature"] = {"auto": temperature_per_frame.get(), "ranges": saved}

        def load_rows():
            for widget in table.grid_slaves():
                if int(widget.grid_info()["row"]) > 0:
                    widget.destroy()
            rows.clear()
            rule = rules.get(current, {})
            modes.current(list(COLORBAR_MODES).index(colorbar_mode(rule)))
            fixed_value.set(rule["fixed"] if rule.get("fixed") is not None else "")
            mode_changed()
            for row in rule.get("ranges") or [("", "", "", "")]:
                add_row(row)

        def store_rows():
            mode = list(COLORBAR_MODES)[modes.current()]
            try:
                parsed = parse_frame_ranges([[cell.get() for cell in cells] for cells in rows.values()], signed=True)
            except ValueError as exc:
                messagebox.showerror(root.tr("参数无效"), root.tr(str(exc)), parent=dialog)
                return False
            fixed = None
            if mode in ("min", "max") and fixed_value.get().strip():
                try:
                    fixed = float(fixed_value.get())
                    if not math.isfinite(fixed):
                        raise ValueError
                except ValueError:
                    messagebox.showerror(root.tr("参数无效"), root.tr("固定上下限必须是有限数值。"), parent=dialog)
                    return False
            rules[current] = {"mode": mode, "fixed": fixed, "ranges": parsed}
            return True

        def select_field(_event):
            nonlocal current
            keys = list(groups)
            if not store_rows():
                selector.current(keys.index(current))
                return
            current = keys[selector.current()]
            load_rows()

        def save():
            if not store_rows():
                return
            colorbar_rules.set(json.dumps(rules))
            frame_ranges.set("[]")
            temperature_per_frame.set(False)
            frames_per_segment.set("")
            segment_entries.set("")
            dialog.destroy()

        selector.bind("<<ComboboxSelected>>", select_field)
        load_rows()
        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text=root.tr("添加一行"), command=add_row).pack(side="left")
        ttk.Button(actions, text=root.tr("取消"), command=dialog.destroy).pack(side="right", padx=4)
        ttk.Button(actions, text=root.tr("应用"), command=save).pack(side="right")
        dialog.bind("<Escape>", lambda _event: dialog.destroy())

    def sync(source):
        nonlocal shared_edits
        shared_edits = copy.deepcopy(source.edits)
        if "figure_size" in shared_edits:
            for value, inches in zip(values, shared_edits["figure_size"]):
                value.set(f"{inches * 25.4:.12g}")
        for frame in displayed_frames:
            frame.dirty = True
            if frame is source:
                continue
            frame.edits.clear()
            frame.edits.update(edits_for_snapshot(shared_edits, frame.path))
            apply_edits(frame.figure, frame.edits)

    def select_frame(frame):
        nonlocal current_figure
        current_figure = frame.figure

    def clear():
        for child in output.winfo_children():
            child.destroy()

    def display(frame):
        nonlocal sequence_snapshot, pause_playback
        clear()
        sequence_snapshot = None
        pause_playback = None
        displayed_frames[:] = [frame]
        select_frame(frame)
        editable_frame(root, output, frame, arrow_button, sync)

    def start(preview_only):
        try:
            size = tuple(float(value.get()) / 25.4 for value in values)
            if not all(math.isfinite(value) and value > 0 for value in size):
                raise ValueError
        except ValueError:
            messagebox.showerror(root.tr("参数无效"), root.tr("宽度和高度必须是大于 0 的有限数值"), parent=root)
            return
        viewport = (max(1, output.winfo_width() - 8), max(1, output.winfo_height() - 48))
        edits = copy.deepcopy(shared_edits)
        edits.pop("figure_size", None)
        launch({"size": size, "viewport": viewport, "preview": display if preview_only else None,
                "shared_edits": edits})

    buttons = ttk.Frame(form)
    buttons.pack(fill="x")
    preview_button = ttk.Button(buttons, text="预览首帧", command=lambda: start(True))
    preview_button.pack(side="left", padx=4)
    render_button = ttk.Button(buttons, text="画动态图", command=lambda: start(False))
    render_button.pack(side="left", padx=4)
    arrow_button = ttk.Button(buttons, text="添加箭头", state="disabled")
    arrow_button.pack(side="left", padx=4)
    segment_button = ttk.Button(buttons, text="色棒范围…", command=edit_temperature_segments)
    segment_button.pack(side="left", padx=4)
    root.control_hints.append((segment_button, "为所选物理量设置逐帧自动或手动分段的色棒范围。"))

    progress_row = ttk.Frame(form)
    progress_label = ttk.Label(progress_row)
    progress_label.pack(side="left", padx=4)
    progress_bar = ttk.Progressbar(progress_row, mode="determinate")
    progress_bar.pack(side="left", fill="x", expand=True, padx=4)

    def update_progress(stage=None, done=0, total=1):
        if stage is None:
            progress_row.pack_forget()
            for button in (preview_button, render_button, segment_button):
                button.state(["!disabled"])
            return
        label = "正在读取 STR 文件" if stage == "reading" else "正在绘制动画帧"
        progress_label.configure(text=f"{root.tr(label)}  {done}/{total}  ({done / total:.0%})")
        progress_bar.configure(maximum=total, value=done)
        if not progress_row.winfo_manager():
            if pause_playback is not None:
                pause_playback()
            for button in (preview_button, render_button, segment_button):
                button.state(["disabled"])
            progress_row.pack(fill="x", pady=(6, 0))

    def display_sequence(frames):
        nonlocal sequence_snapshot, pause_playback
        clear()
        displayed_frames[:] = frames
        sequence_snapshot, pause_playback = show_player(root, output, frames, arrow_button, select_frame, sync)

    return (display_sequence, lambda: current_figure,
            lambda: sequence_snapshot() if sequence_snapshot else None, update_progress)


def show_player(root, parent, frames, arrow_button, select_frame, sync):
    window = ttk.Frame(parent)
    window.pack(fill="both", expand=True)
    view = ttk.Label(window, anchor="center")
    editor_area = ttk.Frame(window)
    controls = ttk.Frame(window, padding=8)
    controls.pack(side="bottom", fill="x")
    view.pack(fill="both", expand=True)
    counter = ttk.Label(controls)
    counter.pack(side="right")
    position = tk.IntVar(master=window)
    applied_fps = 5.0
    fps = tk.StringVar(master=window, value=f"{applied_fps:g}")
    interval = round(1000 / applied_fps)
    timer = None
    editor = None
    edited_index = None

    def close_editor():
        nonlocal editor, edited_index
        if editor is None:
            return
        frame = frames[edited_index]
        refresh_frame_image(frame)
        FigureCanvasAgg(frame.figure)
        for child in editor_area.winfo_children():
            child.destroy()
        editor_area.pack_forget()
        arrow_button.configure(text=root.tr("添加箭头"), command="", state="disabled")
        editor = edited_index = None

    def edit_current():
        nonlocal editor, edited_index
        if editor is None:
            view.pack_forget()
            editor_area.pack(fill="both", expand=True)
            edited_index = position.get()
            editor = editable_frame(root, editor_area, frames[edited_index], arrow_button, sync)

    def display(value):
        index = int(float(value))
        if editor is not None and index != edited_index:
            close_editor()
        position.set(index)
        select_frame(frames[index])
        if timer is None:
            edit_current()
        else:
            refresh_frame_image(frames[index])
            view.image = tk.PhotoImage(master=window, data=base64.b64encode(frames[index].png))
            view.configure(image=view.image)
        counter.configure(text=f"{index + 1} / {len(frames)}")

    def advance():
        nonlocal timer
        display((position.get() + 1) % len(frames))
        timer = window.after(interval, advance)

    def change_speed():
        nonlocal interval, timer, applied_fps
        try:
            rate = float(fps.get())
            if not 0.1 <= rate <= 60:
                raise ValueError
        except ValueError:
            messagebox.showerror(root.tr("参数无效"), root.tr("FPS 必须在 0.1 到 60 之间"), parent=window)
            return False
        interval = round(1000 / rate)
        applied_fps = rate
        if timer is not None:
            window.after_cancel(timer)
            timer = window.after(interval, advance)
        return True

    def toggle():
        nonlocal timer
        if timer is None:
            if root.busy:
                return
            if not change_speed():
                return
            close_editor()
            view.pack(fill="both", expand=True)
            timer = window.after(interval, advance)
            display(position.get())
            play.configure(text=root.tr("暂停"))
        else:
            pause()
            edit_current()

    def pause():
        nonlocal timer
        if timer is not None:
            window.after_cancel(timer)
            timer = None
            play.configure(text=root.tr("播放"))

    def edit_from_playback(event):
        image = view.image
        x = event.x - (view.winfo_width() - image.width()) / 2
        y = (view.winfo_height() + image.height()) / 2 - event.y
        toggle()
        editor.canvas.draw()
        figure = editor.figure
        editor.on_press(MouseEvent("button_press_event", editor.canvas,
                                   x * figure.bbox.width / image.width(),
                                   y * figure.bbox.height / image.height(),
                                   button=1, dblclick=True, guiEvent=event))

    def stop(event):
        nonlocal timer
        if event.widget is not window:
            return
        if timer is not None:
            window.after_cancel(timer)
            timer = None
            if event.type == tk.EventType.Unmap:
                play.configure(text=root.tr("播放"))
                edit_current()

    play = ttk.Button(controls, text=root.tr("播放"), command=toggle)
    play.pack(side="left", padx=(0, 8))
    ttk.Label(controls, text="FPS").pack(side="left")
    speed = ttk.Entry(controls, textvariable=fps, width=5)
    speed.pack(side="left", padx=4)
    speed.bind("<Return>", lambda _event: change_speed())
    ttk.Button(controls, text=root.tr("应用帧率"), command=change_speed).pack(side="left", padx=(0, 8))
    tk.Scale(controls, from_=0, to=len(frames) - 1, orient="horizontal",
             variable=position, showvalue=False, command=display).pack(side="left", fill="x", expand=True)
    display(0)
    view.bind("<Double-Button-1>", edit_from_playback)
    window.bind("<Destroy>", stop, add="+")
    window.bind("<Unmap>", stop, add="+")

    def snapshot():
        return {frame.path: copy.deepcopy(frame.edits) for frame in frames}, applied_fps

    return snapshot, pause
