# TonyPlotPy

**语言：中文（默认） | [English](README.en.md)** · 版本 v0.4.2 · [MIT 许可](LICENSE)

用于 Silvaco Atlas ASCII STR 云图、动态云图和 LOG 曲线的桌面软件。支持组合图、图形编辑、配置保存、图片及动画导出。

## 使用

选择目录或拖入 STR、LOG 文件，调整参数后点击绘图。STR 云图和动态云图的文件列表分别管理。

STR 需要为 ASCII SSF 格式。导出 MP4 需要将 FFmpeg 加入 PATH。

## 源码运行

```powershell
py -m pip install -r requirements.txt
py tonyplotpy.py
```

## 打包

安装 64 位 Python 和 Inno Setup 6。首次在项目目录运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File installer/build-installer.ps1 -InstallDependencies
```

之后双击 `installer/build-installer.bat`，安装包输出到同一目录。
