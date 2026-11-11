# TonyPlotPy

**Language: [中文（默认）](README.md) | English** · Version v0.4.2 · [MIT License](LICENSE)

TonyPlotPy is a desktop application for Atlas ASCII `.str` cloud maps and Atlas SSF `.log` curves. The STR workflow builds on `plot_switching_str_cloud_maps_on.py` and supports mesh parsing, field mapping validation, cell mirroring, structure overlays, TonyPlot colormaps, and three rendering methods.

## Run

**Save set** on either tab saves file order, selected fields/curves, plot parameters, current axis view limits, text/curve/colorbar/arrow edits, and material-legend positions in a TonyPlotPy `.set` file. **Load set** reads the source data in the background and restores the active plot. Data paths are relative where possible; preserve the relative folder layout when moving files. This JSON format does not embed simulation data and is distinct from TonyPlot's native `.set/.setx`. Reproduction requires the original data, fonts, and a compatible software version. Existing double-click editors are also accessible through **Edit this element…** in the right-click menu; active zoom/pan tools retain priority.

```powershell
py -m pip install -r requirements.txt
py tonyplotpy.py
```

STR and LOG have separate tabs, file lists, parameters, previews, and export controls. Files are read and figures are generated in a background worker, so the window stays responsive. Use the Matplotlib toolbar to zoom or pan the preview, then export PNG, PDF, or SVG.

## STR maps

Enable **Materials only (no field map)** to fill regions using the material identifiers in STR `r` records. Matching materials share colors and a legend replaces field colorbars. **Show triangular mesh** independently overlays the original mesh on material or field plots; **Show grid** controls coordinate reference lines.

Material plots also support structure outlines and PN junctions derived from the saved net-doping zero contour. Electrodes are identified from STR electrode names and regions, including the top electrode extent. **Structure labels (material view)** independently toggles electrode names, N/P types, and junction text. Junctions require saved net doping; electrodes outside the visible range are not annotated.

For planar IGBT structures with gate/emitter/collector contacts, semiconductor geometry, depth and doping are used to infer N drift, P-well, N++, N buffer and P+ collector labels. The emitter arrow targets the shallow, heavily doped P-type contact. These are topology-based display inferences rather than stored region names; other device layouts require verification. Buffer and collector labels appear only when their depths are in view.

Structure annotations use arrows without background fills. The material legend defaults to the lower right; double-click it to edit material names/fills, text color, font/size/weight, title, columns, position, and background/border, with preview, cancel, save and undo. Figure-size edits center and fit the preview while retaining the requested physical output size.

Named fields include total/donor/acceptor and ionized doping, potential, electric field magnitude/components, carrier concentrations, quasi-Fermi levels, velocities, mobilities/components, Joule/recombination/total heat power densities, thermal conductivity, specific heat, recombination rates, and ionization coefficients. Only known fields saved in all selected files appear; colorbars include units. Unknown extensions and region-index metadata remain hidden. The metadata in `src/plotting/field_catalog.py` was checked against TonyPlot 5.0.22.R's quantity catalog.

STR maps and animations offer Net doping concentration and Absolute net doping concentration as separate fields. Net doping retains the N/P sign and defaults to a symmetric logarithmic scale. Absolute net doping defaults to a logarithmic scale with a lower limit of 1e12 cm⁻³ and an upper limit rounded up to the next decade from the visible maximum magnitude. Double-click either field to adjust its limits, scale, and log threshold independently. The `tonyplot_user_smooth` palette is approximate. Exact color matching requires the same reference palette, display mode, and limits.

Cloud maps use triangles and stored nodal values from every material region, including electrode, gate, and emitter regions. Structure overlays draw boundaries without covering the physical field with fixed material colors. Automatic color limits include all regions.

Panel titles show only time or file labels by default. Quantity names remain on the colorbars. Enable **Show quantity in panel titles** to include quantity names in panel titles as well.

Selecting two or more of electron, hole, and total current density uses one shared current-density colorbar. These maps use the global current colormap, scale, limits, and contour bands; automatic limits cover all selected current quantities. Individual overrides are replaced by the global settings in this case. Temperature and other quantities retain separate colorbars.

Double-click a colorbar, its label, or ticks to edit its length, width, horizontal/vertical offset (inches), label text, label/tick font sizes, font, color, and outline width. **Apply size and style to all colorbars** gives them matching dimensions while retaining their own labels. Preview, cancel/restore, and confirm/save are supported; edits persist through plotting and export.

Use **Panel axis labels…** to choose X/Y axis names for each panel, identified by row/column, file, and quantity. Presets show all, keep outer labels only, or hide all. Tick numbers remain visible. Panel spacing is recalculated automatically; **Apply** refreshes the preview and exports use the same layout.

Select a folder containing `.str` files or add files individually. Choose physical fields, view limits, cell mirroring, color scales, rendering method, and panel layout, then click **Plot / update preview**. A blank color limit selects an automatic range. For a logarithmic current scale, a zero or blank lower limit selects a positive value automatically.

Only explicitly named nodal fields found in every selected file are listed. Current and temperature have common checkboxes; other named fields can be selected with Ctrl/Shift and included in a combined figure. Double-click a field or common checkbox to override its colormap, linear/log scale, range, and contour bands. Blank values use global or automatic settings. Unnamed Atlas field numbers remain available to the parser but are hidden in the interface.

Current density magnitude combines the X and Y components as `|J| = √(Jx² + Jy²)`. Fields ending in X or Y are directional components. The parser uses Atlas 5.30 field numbers and validates current magnitudes against components. Binary `.str` files are not supported.

**Custom grid columns** is the number of panels in each row. Changing it selects **Custom grid** automatically; click **Plot / update preview** to apply it. Combined maps share colorbars by quantity to reduce clutter.

## LOG curves

Select a folder containing Atlas SSF data `.log` files or add them individually. Choose an X field and one or more Y curves. **Overlay curves** puts them in one plot; **One subplot per signal** creates a multi-panel image; **One image per curve** lets you preview each curve and export all images with curve names in their filenames. Adjust linear/log axes, limits, line width, title, and grid as needed. Time is shown in microseconds by default. Console logs that lack SSF curve data are skipped.

In overlay mode, **Enable dual Y axes** lets you assign selected curves to the right axis. The right axis has its own linear/log scale and limits; both sides share the X axis and legend.

LOG curves use a white background, thin axis lines, inward ticks, and editable text in SVG/PDF output. Double-click a curve to change its color, width, line style, marker shape and size, legend label, legend font size and family, legend title, and plot title.

## Edit figures

Both tabs support direct editing in the preview. Double-click an axis label or title to edit its text, size, color, and font. Double-click an axis, tick, or spine to edit limits, scales, tick typography and colors, or axis-line colors. Double-click empty figure space to set an aspect ratio, millimeters, or pixels. Aspect ratio is the default: 10:20 yields 80×160 mm with a configurable 160 mm long edge. Device coordinates remain in µm. Font choices include commonly used paper fonts installed on your computer.

Use **Add arrow** on the preview toolbar and click its start and end points in the same subplot. Set annotation text, font, size, color, and arrow width. Double-click an arrow annotation to edit or delete it. Editing dialogs offer **Preview**; **Cancel** restores the original figure, while **Confirm and close** saves the change for subsequent previews and exports.

## Settings and interface

Chinese is the default language. Use **Settings** on either tab to switch between Chinese and English immediately. You can also select blue, red, teal, or purple themes; change interface font size, default export DPI (300 by default), and window size. Preferences are saved in `settings.json` and restored on the next launch. The app version appears at the bottom of each tab and in Settings.

The export dialog opens the data folder selected on the current tab. If no folder is selected, it uses the first data file's folder. Hover over controls for help. The mouse wheel scrolls the list under the pointer or the settings panel. You can resize the settings and preview panels by dragging their divider.

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
- `imgs/`: app icons

The preview toolbar's **Undo** (Ctrl+Z) restores confirmed text, curve, axis, colorbar, figure-size, and arrow edits, as well as STR panel-label and field settings. STR and LOG have separate histories of up to 50 steps, cleared when the app closes.

## License

Licensed under the [MIT License](LICENSE).
