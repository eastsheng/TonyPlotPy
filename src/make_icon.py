"""Generate original chart icons for each interface color theme."""
from pathlib import Path
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent.parent
IMAGES = HERE / "imgs"
IMAGES.mkdir(exist_ok=True)
SIZE = 512
ICON_COLORS = {
    "blue": ("#2563eb", "#bfdbfe", "#e84050"),
    "red": ("#d92345", "#ffd9df", "#ffffff"),
    "green": ("#0f766e", "#bfe9da", "#f7c948"),
    "purple": ("#7c3aed", "#e1d2ff", "#f5a649"),
}


def bezier(p0, p1, p2, p3, steps=48):
    points = []
    for index in range(steps + 1):
        t = index / steps
        u = 1 - t
        points.append((
            u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0],
            u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1],
        ))
    return points


def make_icon(name, background, axes, point):
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((18, 18, 494, 494), radius=112, fill=background)
    draw.line((120, 120, 120, 386, 392, 386), fill=axes, width=18, joint="curve")
    curve = bezier((145, 323), (218, 332), (220, 204), (285, 234))
    curve += bezier((285, 234), (326, 255), (329, 170), (385, 142))
    draw.line(curve, fill="#ffffff", width=27)
    for x, y in curve:
        draw.ellipse((x - 13.5, y - 13.5, x + 13.5, y + 13.5), fill="#ffffff")
    draw.ellipse((364, 121, 406, 163), fill=point)
    image.save(IMAGES / f"tonyplotpy_{name}.png")
    image.resize((36, 36), Image.Resampling.LANCZOS).save(IMAGES / f"tonyplotpy_{name}_small.png")
    image.save(IMAGES / f"tonyplotpy_{name}.ico", format="ICO",
               sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    if name == "blue":
        image.save(IMAGES / "tonyplotpy.png")
        image.resize((36, 36), Image.Resampling.LANCZOS).save(IMAGES / "tonyplotpy_small.png")
        image.save(IMAGES / "tonyplotpy.ico", format="ICO",
                   sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


for theme, colors in ICON_COLORS.items():
    make_icon(theme, *colors)
print("Created TonyPlotPy theme icons in imgs/")
