# TonyPlotPy

**Language: [中文（默认）](README.md) | English** · Version 0.4.0 · [MIT License](LICENSE)

TonyPlotPy is a desktop application for Atlas ASCII `.str` cloud maps and Atlas SSF `.log` curves. The STR workflow builds on `plot_switching_str_cloud_maps_on.py` and supports mesh parsing, field mapping validation, cell mirroring, structure overlays, TonyPlot colormaps, and three rendering methods.

## Run

```powershell
py -m pip install -r requirements.txt
py tonyplotpy.py
```

STR and LOG have separate tabs, file lists, parameters, previews, and export controls. Files are read and figures are generated in a background worker, so the window stays responsive. Use the Matplotlib toolbar to zoom or pan the preview, then export PNG, PDF, or SVG.

## STR maps

Select a folder containing `.str` files or add files individually. Choose physical fields, view limits, cell mirroring, color scales, rendering method, and panel layout, then click **Plot / update preview**. A blank color limit selects an automatic range. For a logarithmic current scale, a zero or blank lower limit selects a positive value automatically.

Only explicitly named nodal fields found in every selected file are listed. Current and temperature have common checkboxes; other named fields can be selected with Ctrl/Shift and included in a combined figure. Double-click a field or common checkbox to override its colormap, linear/log scale, range, and contour bands. Blank values use global or automatic settings. Unnamed Atlas field numbers remain available to the parser but are hidden in the interface.

Current density magnitude combines the X and Y components as `|J| = √(Jx² + Jy²)`. Fields ending in X or Y are directional components. The parser uses Atlas 5.30 field numbers and validates current magnitudes against components. Binary `.str` files are not supported.

**Custom grid columns** is the number of panels in each row. Changing it selects **Custom grid** automatically; click **Plot / update preview** to apply it. Combined maps share colorbars by quantity to reduce clutter.

## LOG curves

Select a folder containing Atlas SSF data `.log` files or add them individually. Choose an X field and one or more Y curves. **Overlay curves** puts them in one plot; **One subplot per signal** creates a multi-panel image; **One image per curve** lets you preview each curve and export all images with curve names in their filenames. Adjust linear/log axes, limits, line width, title, and grid as needed. Time is shown in microseconds by default. Console logs that lack SSF curve data are skipped.

In overlay mode, **Enable dual Y axes** lets you assign selected curves to the right axis. The right axis has its own linear/log scale and limits; both sides share the X axis and legend.

LOG curves use a white background, thin axis lines, inward ticks, and editable text in SVG/PDF output. Double-click a curve to change its color, width, line style, marker shape and size, legend label, legend font size and family, legend title, and plot title.

## Edit figures

Both tabs support direct editing in the preview. Double-click an axis label or title to edit its text, size, color, and font. Double-click an axis, tick, or spine to edit limits, scales, tick typography and colors, or axis-line colors. Double-click empty figure space to change figure dimensions in inches. Font choices include commonly used paper fonts installed on your computer.

Use **Add arrow** on the preview toolbar and click its start and end points in the same subplot. Set annotation text, font, size, color, and arrow width. Double-click an arrow annotation to edit or delete it. Editing dialogs offer **Preview**; **Cancel** restores the original figure, while **Confirm and close** saves the change for subsequent previews and exports.

## Settings and interface

Chinese is the default language. Use **Settings** on either tab to switch between Chinese and English immediately. You can also select blue, red, teal, or purple themes; change interface font size, default export DPI (300 by default), and window size. Preferences are saved in `settings.json` and restored on the next launch. The app version appears at the bottom of each tab and in Settings.

The file chooser opens `imgs/` by default for exports. Hover over controls for help. The mouse wheel scrolls the list under the pointer or the settings panel. You can resize the settings and preview panels by dragging their divider.

## Project files

- `tonyplotpy.py`: launcher; `start.bat` calls it
- `src/app.py`: interface, settings collection, and background tasks
- `src/plotting/atlas_engine.py`: Atlas STR parsing and base plotting functions
- `src/plotting/renderer.py`: STR combined-figure renderer
- `src/plotting/log_reader.py`, `src/plotting/log_renderer.py`: LOG data reader and curve renderer
- `src/figure_editor.py`, `src/plotting/figure_edits.py`: interactive preview editing and persistence
- `src/plotting/font_presets.py`: available paper-font presets
- `src/ui_settings.py`, `src/i18n.py`: preferences and translations
- `src/tooltips.py`, `src/control_hints.py`: hover help
- `src/make_icon.py`: icon generator (requires Pillow)
- `imgs/`: app icons and default figure export folder

## License

Licensed under the [MIT License](LICENSE).
