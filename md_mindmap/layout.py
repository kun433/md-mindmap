"""把节点树排成经典思维导图布局（右向树、父节点垂直居中于子树）。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from PIL import ImageFont

from .fonts import load_font
from .parser import Node

__all__ = [
    "ACCENTS",
    "Box",
    "Layout",
    "LayoutConfig",
    "Placed",
    "build_layout",
    "node_edges",
    "wrap_text",
]

# 分支配色（克莱因蓝 / 橙 / 绿 / 紫 / 红 / 青）
ACCENTS: List[str] = [
    "#002FA7",
    "#E8590C",
    "#0F8A4C",
    "#6D28D9",
    "#C2255C",
    "#0B7285",
    "#946200",
    "#3B5BDB",
]

_CJK_RE = re.compile(
    r"[\u1100-\u115F\u2E80-\uA4CF\uA960-\uA97F\uAC00-\uD7A3\uF900-\uFAFF"
    r"\uFE30-\uFE4F\uFF00-\uFF60\uFFE0-\uFFE6\u3000-\u303F]"
    r"|[\U0001F000-\U0001FAFF]"
)


@dataclass
class LayoutConfig:
    """布局参数（单位：像素）。"""

    font_size: int = 14
    root_font_size: int = 20
    size_step: float = 0.0  # 每层字号递减量，0 表示不递减
    min_font_size: int = 12
    line_spacing: float = 1.42
    pad_x: int = 15
    pad_y: int = 9
    gap_x: int = 52
    gap_y: int = 13
    max_text_width: int = 300
    root_max_text_width: int = 340
    min_width: int = 88
    radius: int = 9

    def font_size_at(self, depth: int) -> int:
        if depth == 0:
            return self.root_font_size
        size = self.root_font_size - round(self.size_step * depth) - 4
        return max(self.min_font_size, size)


@dataclass
class Box:
    left: float
    top: float
    width: float
    height: float
    lines: List[str]
    font_size: int

    @property
    def right(self) -> float:
        return self.left + self.width

    @property
    def bottom(self) -> float:
        return self.top + self.height

    @property
    def center_y(self) -> float:
        return self.top + self.height / 2

    def contains(self, x: float, y: float) -> bool:
        return self.left <= x <= self.right and self.top <= y <= self.bottom


@dataclass
class Placed:
    node: Node
    depth: int
    box: Box
    accent: str
    parent: Optional["Placed"] = None
    children: List["Placed"] = field(default_factory=list)


@dataclass
class Layout:
    root: Placed
    nodes: List[Placed]
    width: float
    height: float
    config: LayoutConfig

    def hit_test(self, x: float, y: float) -> Optional[Placed]:
        for placed in reversed(self.nodes):
            if placed.box.contains(x, y):
                return placed
        return None


# --------------------------------------------------------------------------- #
# 文本换行
# --------------------------------------------------------------------------- #


def _chunks(text: str) -> List[str]:
    """把文本切成可用于换行的片段：中文/表情单字成块，英文单词成块。"""
    chunks: List[str] = []
    buffer = ""
    for char in text:
        if _CJK_RE.match(char):
            if buffer:
                chunks.append(buffer)
                buffer = ""
            chunks.append(char)
        elif char == " ":
            buffer += char
            chunks.append(buffer)
            buffer = ""
        else:
            buffer += char
    if buffer:
        chunks.append(buffer)
    return chunks


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: float) -> List[str]:
    """按像素宽度换行，同时保留原文中的显式换行。"""
    result: List[str] = []
    for raw_line in text.split("\n"):
        raw_line = raw_line.strip()
        if not raw_line:
            result.append("")
            continue
        current = ""
        for chunk in _chunks(raw_line):
            candidate = current + chunk
            if not current or font.getlength(candidate) <= max_width:
                current = candidate
            else:
                result.append(current.rstrip())
                current = chunk.lstrip()
        result.append(current.rstrip())
    while result and result[-1] == "":
        result.pop()
    return result or [""]


# --------------------------------------------------------------------------- #
# 布局
# --------------------------------------------------------------------------- #


def build_layout(
    root: Node,
    config: Optional[LayoutConfig] = None,
    accents: Optional[List[str]] = None,
) -> Layout:
    """计算整棵树的几何布局。"""
    config = config or LayoutConfig()
    accents = accents or ACCENTS

    sizes: Dict[int, Box] = {}
    column_width: Dict[int, float] = {}

    def measure(node: Node, depth: int) -> None:
        size = config.font_size_at(depth)
        font = load_font(size)
        limit = config.root_max_text_width if depth == 0 else config.max_text_width
        lines = wrap_text(node.text, font, limit)
        text_width = max((font.getlength(line) for line in lines), default=0.0)
        width = max(config.min_width, text_width + 2 * config.pad_x)
        height = len(lines) * config.line_spacing * size + 2 * config.pad_y
        sizes[id(node)] = Box(0.0, 0.0, width, height, lines, size)
        column_width[depth] = max(column_width.get(depth, 0.0), width)
        if not node.collapsed:
            for child in node.children:
                measure(child, depth + 1)

    measure(root, 0)

    column_left: Dict[int, float] = {}
    cursor = 0.0
    for depth in sorted(column_width):
        column_left[depth] = cursor
        cursor += column_width[depth] + config.gap_x

    subtree_height: Dict[int, float] = {}

    def measure_height(node: Node, depth: int) -> float:
        own = sizes[id(node)].height
        if node.collapsed or not node.children:
            subtree_height[id(node)] = own
            return own
        total = sum(measure_height(child, depth + 1) for child in node.children)
        total += config.gap_y * (len(node.children) - 1)
        value = max(own, total)
        subtree_height[id(node)] = value
        return value

    measure_height(root, 0)

    placed_nodes: List[Placed] = []

    def place(node: Node, depth: int, top: float, accent: str) -> Placed:
        box = sizes[id(node)]
        height = subtree_height[id(node)]
        box.left = column_left[depth] + (column_width[depth] - box.width) / 2
        box.top = top + height / 2 - box.height / 2
        placed = Placed(node=node, depth=depth, box=box, accent=accent)
        placed_nodes.append(placed)

        if not node.collapsed and node.children:
            children_total = sum(subtree_height[id(c)] for c in node.children)
            children_total += config.gap_y * (len(node.children) - 1)
            y = top + (height - children_total) / 2
            for index, child in enumerate(node.children):
                child_accent = accents[index % len(accents)] if depth == 0 else accent
                child_placed = place(child, depth + 1, y, child_accent)
                child_placed.parent = placed
                placed.children.append(child_placed)
                y += subtree_height[id(child)] + config.gap_y

        return placed

    root_placed = place(root, 0, 0.0, accents[0])

    width = max((p.box.right for p in placed_nodes), default=0.0)
    height = max((p.box.bottom for p in placed_nodes), default=0.0)
    min_top = min((p.box.top for p in placed_nodes), default=0.0)
    if min_top < 0:
        for placed in placed_nodes:
            placed.box.top -= min_top
        height -= min_top

    return Layout(root=root_placed, nodes=placed_nodes, width=width, height=height, config=config)


def node_edges(placed: Placed) -> List[tuple[float, float, float, float, str, int]]:
    """产出 (x1, y1, x2, y2, 颜色, 线宽) 边线描述。"""
    edges = []
    for child in placed.children:
        width = 2.4 if placed.depth == 0 else 1.8
        edges.append(
            (
                placed.box.right,
                placed.box.center_y,
                child.box.left,
                child.box.center_y,
                child.accent,
                width,
            )
        )
        edges.extend(node_edges(child))
    return edges


def bezier_points(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    steps: int = 24,
) -> List[float]:
    """用贝塞尔采样点近似连接线，返回扁平坐标序列。"""
    dx = x2 - x1
    c1x, c1y = x1 + dx * 0.5, y1
    c2x, c2y = x2 - dx * 0.5, y2
    points: List[float] = []
    for index in range(steps + 1):
        t = index / steps
        mt = 1 - t
        x = mt**3 * x1 + 3 * mt**2 * t * c1x + 3 * mt * t**2 * c2x + t**3 * x2
        y = mt**3 * y1 + 3 * mt**2 * t * c1y + 3 * mt * t**2 * c2y + t**3 * y2
        points.extend((x, y))
    return points
