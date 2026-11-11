"""Render and play a sequence of STR cloud maps."""
import base64
import copy
import io
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
from .deferred_canvas import DeferredFigureCanvasTkAgg
from .figure_editor import FigureEditor


@dataclass
class AnimationFrame:
    figure: object
    png: bytes
    edits: dict = field(default_factory=dict)
    path: Path | None = None
    dirty: bool = False


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
        stream = io.BytesIO()
        try:
            FigureCanvasAgg(frame.figure).print_png(stream)
            frame.png = stream.getvalue()
            frame.dirty = False
        finally:
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


def render_frames(options, cache, *, export_dpi=None, edits_by_path=None):
    paths = ordered_snapshots(options["files"])
    prepared = {path: renderer.read_structure(path, options, cache) for path in paths}
    norms, frames = {}, []
    request = options["animation"]
    for path in paths[:1] if request.get("preview") is not None else paths:
        frame = renderer.make_figure({**options, "files": [path], "layout": "物理量 × 时间"},
                                     cache, prepared=prepared, sequence_norms=norms)
        frame.set_size_inches(*request["size"], forward=False)
        edits = (edits_for_snapshot(request.get("shared_edits", {}), path)
                 if edits_by_path is None else edits_by_path.get(path, {}))
        apply_edits(frame, edits)
        width, height = frame.get_size_inches()
        max_width, max_height = request.get("viewport", (960, 680))
        frame.set_dpi(export_dpi if export_dpi is not None else min(100, max_width / width, max_height / height))
        canvas = FigureCanvasAgg(frame)
        stream = io.BytesIO()
        canvas.print_png(stream)
        if export_dpi is not None:
            frames.append(stream.getvalue())
            frame.clear()
            frame.set_canvas(None)
        else:
            frame._tonyplot_export_size = (width, height)
            frames.append(AnimationFrame(frame, stream.getvalue(), edits, path))
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
    shared_edits = {}
    displayed_frames = []

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
        nonlocal sequence_snapshot
        clear()
        sequence_snapshot = None
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
    ttk.Button(buttons, text="预览首帧", command=lambda: start(True)).pack(side="left", padx=4)
    ttk.Button(buttons, text="画动态图", command=lambda: start(False)).pack(side="left", padx=4)
    arrow_button = ttk.Button(buttons, text="添加箭头", state="disabled")
    arrow_button.pack(side="left", padx=4)

    def display_sequence(frames):
        nonlocal sequence_snapshot
        clear()
        displayed_frames[:] = frames
        sequence_snapshot = show_player(root, output, frames, arrow_button, select_frame, sync)

    return display_sequence, lambda: current_figure, lambda: sequence_snapshot() if sequence_snapshot else None


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
            if not change_speed():
                return
            close_editor()
            view.pack(fill="both", expand=True)
            timer = window.after(interval, advance)
            display(position.get())
            play.configure(text=root.tr("暂停"))
        else:
            window.after_cancel(timer)
            timer = None
            play.configure(text=root.tr("播放"))
            edit_current()

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

    return snapshot
