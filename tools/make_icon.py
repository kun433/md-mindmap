"""生成应用图标（assets/icon.ico 与 assets/icon.png）。"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw

ACCENT = "#002FA7"
INK = "#111827"
BG = "#FFFFFF"


def draw_icon(size: int = 512) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * 0.2), fill=ACCENT)

    unit = size / 100
    center = (28 * unit, 50 * unit)
    nodes = [
        ((66 * unit, 22 * unit), "#FFFFFF"),
        ((70 * unit, 50 * unit), "#FFFFFF"),
        ((66 * unit, 78 * unit), "#FFFFFF"),
    ]
    branch_colors = ["#FFD166", "#8CE99A", "#FFB4A2"]

    for (x, y), _ in nodes:
        draw.line([center, (x, y)], fill="#FFFFFF88", width=max(2, int(4 * unit)))
    draw.ellipse(
        [
            center[0] - 12 * unit,
            center[1] - 12 * unit,
            center[0] + 12 * unit,
            center[1] + 12 * unit,
        ],
        fill="#FFFFFF",
    )
    draw.ellipse(
        [
            center[0] - 5 * unit,
            center[1] - 5 * unit,
            center[0] + 5 * unit,
            center[1] + 5 * unit,
        ],
        fill=INK,
    )
    for index, ((x, y), _) in enumerate(nodes):
        radius = 9 * unit
        draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=branch_colors[index])

    return image


def main() -> None:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assets = os.path.join(base, "assets")
    os.makedirs(assets, exist_ok=True)
    icon = draw_icon(512)
    icon.save(os.path.join(assets, "icon.png"))
    icon.save(
        os.path.join(assets, "icon.ico"),
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print("已生成", os.path.join(assets, "icon.ico"))


if __name__ == "__main__":
    main()
