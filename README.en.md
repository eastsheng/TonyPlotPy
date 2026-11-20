# TonyPlotPy

**Language: [中文（默认）](README.md) | English** · Version v0.4.2 · [MIT License](LICENSE)

A desktop tool for Silvaco Atlas ASCII STR maps, animations, and LOG curves. Supports combined plots, figure editing, saved configurations, and image and animation export.

## Usage

Select a folder or drop STR and LOG files into the window, adjust parameters, and plot. Static maps and animations have independent file lists.

STR files must use ASCII SSF format. MP4 export requires FFmpeg on PATH.

## Run from source

```powershell
py -m pip install -r requirements.txt
py tonyplotpy.py
```

## Build an installer

Install 64-bit Python and Inno Setup 6. For the first build, run from the project directory:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File src/packaging/build-installer.ps1 -InstallDependencies
```

For later builds, double-click `src/packaging/build-installer.bat`. Installers are written to `installer-output`.
