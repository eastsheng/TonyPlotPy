"""Interactive straight cutlines on STR figures."""
import math
import csv
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import matplotlib.tri as mtri
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

from .plotting import renderer

PLOT_MODES = ("同图共用 Y 轴", "同图双 Y 轴", "多子图", "每变量单独图片")


def cutline_figures(data, labels, mode, right_indices=()):
    right = set(right_indices)
    if mode == PLOT_MODES[1] and (not right or not right < set(range(len(labels)))):
        raise ValueError("双 Y 轴需要至少一条左轴曲线和一条右轴曲线")
    if mode == PLOT_MODES[3]:
        figures = []
        for index, label in enumerate(labels):
            plot = Figure(figsize=(6, 4), layout="constrained")
            ax = plot.subplots()
            ax.plot(data[:, 0], data[:, index + 3], color=f"C{index % 10}")
            ax.set(xlabel="Distance (µm)", ylabel=label)
            figures.append(plot)
        return figures
    plot = Figure(figsize=(6, 3 * len(labels) if mode == PLOT_MODES[2] else 4), layout="constrained")
    if mode == PLOT_MODES[2]:
        axes = plot.subplots(len(labels), 1, squeeze=False, sharex=True)
        for index, ax in enumerate(axes.flat):
            ax.plot(data[:, 0], data[:, index + 3], color=f"C{index % 10}")
            ax.set_ylabel(labels[index])
        axes[-1, 0].set_xlabel("Distance (µm)")
    else:
        left_ax = plot.subplots()
        right_ax = left_ax.twinx() if mode == PLOT_MODES[1] else None
        handles = []
        for index, label in enumerate(labels):
            ax = right_ax if right_ax is not None and index in right else left_ax
            line, = ax.plot(data[:, 0], data[:, index + 3], label=label, color=f"C{index % 10}")
            handles.append(line)
        left_ax.set_xlabel("Distance (µm)")
        left_ax.set_ylabel("\n".join(label for i, label in enumerate(labels) if right_ax is None or i not in right))
        if right_ax is not None:
            right_ax.set_ylabel("\n".join(label for i, label in enumerate(labels) if i in right))
        left_ax.legend(handles=handles, fontsize=8)
    return [plot]


def sample_line(structure, quantity, endpoints, count):
    x0, y0, x1, y1 = endpoints
    x, y = np.linspace(x0, x1, count), np.linspace(y0, y1, count)
    source = "code:115" if quantity == "absolute_net_doping" else quantity
    values = structure.values[source]
    if quantity == "absolute_net_doping":
        values = np.abs(values)
    invalid = ~np.isfinite(values)[structure.triangles].all(axis=1)
    mesh = mtri.Triangulation(structure.x, structure.y, structure.triangles, mask=invalid)
    sampled = mtri.LinearTriInterpolator(mesh, np.where(np.isfinite(values), values, 0))(x, y)
    distance = np.linspace(0, math.hypot(x1 - x0, y1 - y0), count)
    return np.column_stack((distance, x, y, sampled.filled(np.nan)))


def open_cutline(root, figure, canvas):
    structures = getattr(figure, "_tonyplot_structures", {})
    if not structures:
        return
    tr = root.tr
    window = tk.Toplevel(root)
    window.title(tr("自定义截线"))
    window.transient(root)
    body = ttk.Frame(window, padding=12)
    body.pack(fill="both", expand=True)
    paths = list(structures)
    file_choice = ttk.Combobox(body, state="readonly", values=paths, width=65)
    file_choice.pack(fill="x")
    file_choice.current(0)
    ttk.Label(body, text=tr("物理量（Ctrl / Shift 多选）")).pack(anchor="w", pady=(6, 0))
    field_area = ttk.Frame(body)
    field_area.pack(fill="x", pady=(0, 6))
    listing = tk.Listbox(field_area, selectmode="extended", exportselection=False, height=5)
    scrollbar = ttk.Scrollbar(field_area, orient="vertical", command=listing.yview)
    listing.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    listing.pack(side="left", fill="x", expand=True)
    layout = ttk.Combobox(body, state="readonly", values=[tr(mode) for mode in PLOT_MODES])
    layout.current(0)
    layout.pack(fill="x", pady=(0, 6))
    right_area = ttk.Frame(body)
    ttk.Label(right_area, text=tr("右 Y 轴变量（多选）")).pack(anchor="w")
    right_listing = tk.Listbox(right_area, selectmode="extended", exportselection=False, height=3)
    right_scroll = ttk.Scrollbar(right_area, command=right_listing.yview)
    right_listing.configure(yscrollcommand=right_scroll.set)
    right_scroll.pack(side="right", fill="y")
    right_listing.pack(fill="x", expand=True)
    right_fields = []
    quantities = []
    coordinates = []
    row = ttk.Frame(body)
    row.pack(fill="x")
    for label, value in zip(("x₀ (µm)", "y₀ (µm)", "x₁ (µm)", "y₁ (µm)", tr("采样点数")), (0, 0, 0, 1, 300)):
        cell = ttk.Frame(row)
        cell.pack(side="left", padx=3)
        ttk.Label(cell, text=label).pack(anchor="w")
        variable = tk.StringVar(value=str(value))
        ttk.Entry(cell, textvariable=variable, width=12).pack()
        coordinates.append(variable)
    status = ttk.Label(body, text=tr("点击选点后，在同一子图点选两个端点。"))
    status.pack(anchor="w", pady=6)
    result_area = ttk.Frame(body)
    result_area.pack(fill="both", expand=True)
    result = None
    result_label = ""
    line = None
    connection = None
    key_connection = None
    pick_snapshot = None
    first_point_marker = None
    points = []
    selected_axis = None

    def right_choices(_event=None):
        previous = {right_fields[i] for i in right_listing.curselection()}
        right_fields[:] = [quantities[i] for i in listing.curselection()]
        right_listing.delete(0, "end")
        for index, field in enumerate(right_fields):
            right_listing.insert("end", renderer.quantity_label(field))
            if field in previous:
                right_listing.selection_set(index)
        if not right_listing.curselection() and len(right_fields) > 1:
            right_listing.selection_set(len(right_fields) - 1)
        if layout.current() == 1:
            right_area.pack(fill="x", before=row, pady=(0, 6))
        else:
            right_area.pack_forget()

    def fields(_event=None):
        selected = {quantities[i] for i in listing.curselection()}
        quantities[:] = [key for key in structures[paths[file_choice.current()]].values
                         if key in renderer.engine.LABELS or key in renderer.DOPING_FIELDS
                         or (key.startswith("code:") and int(key[5:]) in renderer.FIELD_NAME_BY_CODE)]
        listing.delete(0, "end")
        for index, quantity in enumerate(quantities):
            listing.insert("end", renderer.quantity_label(quantity))
            if quantity in selected:
                listing.selection_set(index)
        if not listing.curselection() and quantities:
            listing.selection_set(0)
        right_choices()

    def stop_pick():
        nonlocal connection, key_connection
        if connection is not None:
            canvas.mpl_disconnect(connection)
            connection = None
        if key_connection is not None:
            canvas.mpl_disconnect(key_connection)
            key_connection = None

    def clear_point_marker():
        nonlocal first_point_marker
        if first_point_marker is not None:
            first_point_marker.remove()
            first_point_marker = None
            canvas.draw_idle()

    def cancel_pick(_event=None):
        nonlocal selected_axis, pick_snapshot
        stop_pick()
        clear_point_marker()
        points.clear()
        selected_axis = None
        if pick_snapshot is not None:
            file_index, selected, values = pick_snapshot
            file_choice.current(file_index)
            fields()
            listing.selection_clear(0, "end")
            for index, quantity in enumerate(quantities):
                if quantity in selected:
                    listing.selection_set(index)
            for variable, value in zip(coordinates, values):
                variable.set(value)
            right_choices()
            pick_snapshot = None
        status.configure(text=tr("已取消选点"))

    def draw():
        nonlocal result, result_label, line
        try:
            endpoints = tuple(float(v.get()) for v in coordinates[:4])
            count = int(coordinates[4].get())
            if not all(math.isfinite(v) for v in endpoints) or not 2 <= count <= 100000:
                raise ValueError(tr("坐标须为有限数值，采样点数为 2–100000。"))
            if endpoints[:2] == endpoints[2:]:
                raise ValueError(tr("截线两个端点不能重合。"))
            path = paths[file_choice.current()]
            selected = [quantities[i] for i in listing.curselection()]
            if not selected:
                raise ValueError(tr("请选择至少一个物理量。"))
            samples = [sample_line(structures[path], quantity, endpoints, count) for quantity in selected]
            combined = np.column_stack([samples[0][:, :3], *[sample[:, 3] for sample in samples]])
            if not np.isfinite(combined[:, 3:]).any():
                raise ValueError(tr("截线没有穿过有效网格。"))
            labels = [renderer.quantity_label(quantity) for quantity in selected]
            right_choices()
            plots = cutline_figures(combined, labels, PLOT_MODES[layout.current()], right_listing.curselection())
            result = combined
            result_label = labels
            axis = next(ax for ax in figure.axes if getattr(ax, "_tonyplot_axis_key", ())[:2] == ("str", path))
            if line is not None:
                line.remove()
            x0, y0, x1, y1 = endpoints
            xx, yy = ([y0, y1], [x0, x1]) if figure._tonyplot_rotated else ([x0, x1], [y0, y1])
            line, = axis.plot(xx, yy, color="#111827", linestyle="--", marker="o", linewidth=1.5, zorder=12)
            canvas.draw_idle()
            for child in result_area.winfo_children():
                child.destroy()
            tabs = ttk.Notebook(result_area)
            tabs.pack(fill="both", expand=True)
            for index, plot in enumerate(plots):
                panel = ttk.Frame(tabs)
                tabs.add(panel, text=labels[index] if len(plots) > 1 else tr("截线曲线"))
                chart = FigureCanvasTkAgg(plot, master=panel)
                NavigationToolbar2Tk(chart, panel)
                chart.get_tk_widget().pack(fill="both", expand=True)
                chart.draw_idle()
        except (ValueError, StopIteration) as exc:
            messagebox.showerror(tr("参数无效"), str(exc), parent=window)

    def picked(event):
        nonlocal selected_axis, pick_snapshot, first_point_marker
        identity = getattr(event.inaxes, "_tonyplot_axis_key", ())
        if event.button != 1 or len(identity) < 3 or identity[0] != "str":
            return
        if points and event.inaxes is not selected_axis:
            return
        selected_axis = event.inaxes
        file_choice.current(paths.index(identity[1]))
        fields()
        point = (event.ydata, event.xdata) if figure._tonyplot_rotated else (event.xdata, event.ydata)
        points.append(point)
        if len(points) == 1:
            first_point_marker, = event.inaxes.plot(
                [event.xdata], [event.ydata], marker="o", markersize=8,
                markerfacecolor="#ef4444", markeredgecolor="white", markeredgewidth=1.4,
                linestyle="none", zorder=15, scalex=False, scaley=False)
            canvas.draw_idle()
        for variable, value in zip(coordinates[(len(points) - 1) * 2:], point):
            variable.set(f"{value:.10g}")
        if len(points) == 2:
            stop_pick()
            clear_point_marker()
            pick_snapshot = None
            status.configure(text=tr("选点完成"))
            draw()

    def pick():
        nonlocal connection, key_connection, pick_snapshot
        if connection is not None:
            cancel_pick()
        points.clear()
        pick_snapshot = (file_choice.current(), [quantities[i] for i in listing.curselection()],
                         [value.get() for value in coordinates])
        toolbar = getattr(canvas, "toolbar", None)
        if toolbar and toolbar.mode:
            toolbar.pan() if toolbar.mode == "pan/zoom" else toolbar.zoom()
        connection = canvas.mpl_connect("button_press_event", picked)
        key_connection = canvas.mpl_connect("key_press_event", lambda event: cancel_pick() if event.key == "escape" else None)
        status.configure(text=tr("请在云图中依次点选两个端点。"))

    def export():
        if result is None:
            return
        path = filedialog.asksaveasfilename(parent=window, defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if path:
            with open(path, "w", newline="", encoding="utf-8-sig") as output:
                writer = csv.writer(output)
                writer.writerow(["distance_um", "x_um", "y_um", *result_label])
                writer.writerows(result)
            messagebox.showinfo(tr("保存完成"), path, parent=window)

    actions = ttk.Frame(body)
    actions.pack(fill="x", before=result_area)
    for label, command in (("在云图选点", pick), ("取消选点", cancel_pick), ("绘制截线曲线", draw), ("导出 CSV", export)):
        ttk.Button(actions, text=tr(label), command=command).pack(side="left", padx=3)
    file_choice.bind("<<ComboboxSelected>>", fields)
    listing.bind("<<ListboxSelect>>", right_choices)
    layout.bind("<<ComboboxSelected>>", right_choices)
    fields()
    window.bind("<Escape>", cancel_pick)
    def close(event):
        if event.widget is window:
            stop_pick()
            clear_point_marker()

    window.bind("<Destroy>", close, add="+")
