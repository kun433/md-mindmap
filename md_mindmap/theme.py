"""配色主题：节点填充、文字、边框与连线颜色。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

from .layout import ACCENTS

__all__ = ["Theme", "LIGHT", "DARK", "THEMES", "hex_to_rgb", "rgb_to_hex", "mix"]


def hex_to_rgb(value: str) -> Tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def rgb_to_hex(rgb: Tuple[float, float, float]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*(max(0, min(255, round(c))) for c in rgb))


def mix(color_a: str, color_b: str, ratio: float) -> str:
    """把 color_a 按 ratio 比例混向 color_b。"""
    ratio = max(0.0, min(1.0, ratio))
    a = hex_to_rgb(color_a)
    b = hex_to_rgb(color_b)
    return rgb_to_hex(tuple(a[i] + (b[i] - a[i]) * ratio for i in range(3)))  # type: ignore[arg-type]


@dataclass
class Theme:
    name: str
    label: str
    dark: bool
    bg: str
    ink: str
    muted: str
    root_fill: str
    root_text: str
    accents: List[str] = field(default_factory=lambda: list(ACCENTS))

    # ------------------------------------------------------------------ #
    def node_style(self, depth: int, accent: str) -> Tuple[str, str, str, float]:
        """返回 (填充, 文字, 边框, 边框粗细)。"""
        if depth == 0:
            return self.root_fill, self.root_text, self.root_fill, 0.0
        if depth == 1:
            return accent, "#FFFFFF", accent, 0.0
        if self.dark:
            if depth == 2:
                return mix(accent, self.bg, 0.74), self.ink, mix(accent, self.bg, 0.34), 1.4
            return "#1E2128", mix(self.ink, self.bg, 0.22), mix(accent, self.bg, 0.62), 1.2
        if depth == 2:
            return mix(accent, self.bg, 0.87), "#1B2233", accent, 1.4
        return "#FFFFFF", mix(self.ink, self.bg, 0.24), mix(accent, self.bg, 0.58), 1.2

    def edge_color(self, accent: str, depth: int) -> str:
        ratio = 0.42 if depth <= 1 else 0.5
        return mix(accent, self.bg, ratio)

    def root_shadow(self) -> str:
        """Tk 画布只支持不带透明通道的颜色值。"""
        return "#DCDCD6" if not self.dark else "#0A0B0E"


LIGHT = Theme(
    name="light",
    label="浅色",
    dark=False,
    bg="#F6F6F3",
    ink="#111827",
    muted="#6B7280",
    root_fill="#111827",
    root_text="#FFFFFF",
)

DARK = Theme(
    name="dark",
    label="深色",
    dark=True,
    bg="#14161B",
    ink="#E8EAF0",
    muted="#98A2B3",
    root_fill="#EDEFF5",
    root_text="#0B0D12",
)

THEMES = {LIGHT.name: LIGHT, DARK.name: DARK}
