"""通用图形场景模型与思维导图布局。

所有图形（思维导图、鱼骨图、时间轴、组织结构图）最终都归结为同一份场景数据：

* ``Layout.nodes`` —— 已经测量好尺寸的文本框（可以画成圆角矩形、圆点或纯文字）；
* ``Layout.edges`` —— 折线连接（可选箭头），坐标已经是最终画布坐标。

这样 PNG / SVG / Tk / HTML 四套渲染只需要实现一遍「画折线 + 画节点」，
新增图形时只写布局，不用再改渲染代码。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from PIL import ImageFont

from .fonts import fallback_char_count, load_font, run_width
from .parser import Node

__all__ = [
    "ACCENTS",
    "Box",
    "Edge",
    "Layout",
    "LayoutConfig",
    "Measurer",
    "Placed",
    "bezier_points",
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

TEXT_SAFETY = 2.0  # 文本宽度安全余量（像素）
FALLBACK_SLACK = 0.4  # 每个兜底字符（emoji / 缺字符号）额外预留的宽度系数

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
    pad_x: float = 15.0
    pad_y: float = 9.0
    line_spacing: float = 1.42

    @property
    def right(self) -> float:
        return self.left + self.width

    @property
    def bottom(self) -> float:
        return self.top + self.height

    @property
    def center_x(self) -> float:
        return self.left + self.width / 2

    @property
    def center_y(self) -> float:
        return self.top + self.height / 2

    def contains(self, x: float, y: float) -> bool:
        return self.left <= x <= self.right and self.top <= y <= self.bottom


@dataclass
class Placed:
    """画布上的一个节点。"""

    node: Node
    depth: int
    box: Box
    accent: str
    parent: Optional["Placed"] = None
    children: List["Placed"] = field(default_factory=list)
    shape: str = "box"  # box | dot | text
    tone: str = "normal"  # normal | muted | accent
    interactive: bool = True  # False 时不响应点击折叠

    @property
    def text(self) -> str:
        return "\n".join(self.box.lines)


@dataclass
class Edge:
    """一条折线连接（坐标为最终画布坐标，扁平存放 x, y）。"""

    points: List[float]
    color: str
    width: float = 1.8
    arrow: bool = False
    level: int = 2  # 用于主题配色深浅：0 主干 / 1 主分支 / 2 细线
    muted: bool = False  # 主轴等辅助线使用柔和色


@dataclass
class Layout:
    root: Placed
    nodes: List[Placed]
    width: float
    height: float
    config: LayoutConfig
    edges: List[Edge] = field(default_factory=list)
    kind: str = "mindmap"

    def hit_test(self, x: float, y: float) -> Optional[Placed]:
        for placed in reversed(self.nodes):
            if placed.box.contains(x, y):
                return placed
        return None

    def shift(self, dx: float, dy: float) -> "Layout":
        """整体平移（包含连线端点）。"""
        for placed in self.nodes:
            placed.box.left += dx
            placed.box.top += dy
        for edge in self.edges:
            for index in range(0, len(edge.points), 2):
                edge.points[index] += dx
                edge.points[index + 1] += dy
        return self


# --------------------------------------------------------------------------- #
# 文本换行与测量
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


def wrap_text(
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: float,
    size: Optional[int] = None,
    bold: bool = False,
) -> List[str]:
    """按像素宽度换行，同时保留原文中的显式换行。

    传入 ``size`` 时使用兜底字体规则测量，emoji / 符号的宽度与最终绘制一致。
    """

    def measure(value: str) -> float:
        if size is None:
            return font.getlength(value)
        return run_width(value, size, bold)

    result: List[str] = []
    for raw_line in text.split("\n"):
        raw_line = raw_line.strip()
        if not raw_line:
            result.append("")
            continue
        current = ""
        for chunk in _chunks(raw_line):
            candidate = current + chunk
            if not current or measure(candidate) <= max_width:
                current = candidate
            else:
                result.append(current.rstrip())
                current = chunk.lstrip()
        result.append(current.rstrip())
    while result and result[-1] == "":
        result.pop()
    return result or [""]


class Measurer:
    """缓存字体、测量文本框尺寸，供各种图形复用。"""

    def __init__(self, config: Optional[LayoutConfig] = None) -> None:
        self.config = config or LayoutConfig()
        self._fonts: Dict[tuple[int, bool], ImageFont.FreeTypeFont] = {}

    def font(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        size = max(8, int(size))
        key = (size, bold)
        if key not in self._fonts:
            self._fonts[key] = load_font(size, bold)
        return self._fonts[key]

    def text_width(self, text: str, size: int, bold: bool = False) -> float:
        font = self.font(size, bold)
        return max((font.getlength(line) for line in text.split("\n")), default=0.0)

    def box(
        self,
        text: str,
        font_size: int,
        max_width: float,
        pad_x: Optional[float] = None,
        pad_y: Optional[float] = None,
        min_width: float = 0.0,
        line_spacing: Optional[float] = None,
        bold: bool = False,
    ) -> Box:
        config = self.config
        pad_x = config.pad_x if pad_x is None else pad_x
        pad_y = config.pad_y if pad_y is None else pad_y
        line_spacing = config.line_spacing if line_spacing is None else line_spacing
        font = self.font(font_size, bold)
        lines = wrap_text(text, font, max_width, size=int(font_size), bold=bold)
        text_width = max((run_width(line, font_size, bold) for line in lines), default=0.0)
        # 多留安全余量：Pillow、Tk 与浏览器对符号 / emoji 的宽度略有差异，
        # Tk 会把缺字交给系统字体回退，通常比 Pillow 测得更宽
        slack = TEXT_SAFETY + FALLBACK_SLACK * font_size * fallback_char_count(text)
        width = max(min_width, text_width + 2 * pad_x + slack)
        height = len(lines) * line_spacing * font_size + 2 * pad_y
        return Box(
            0.0,
            0.0,
            width,
            height,
            lines,
            int(font_size),
            pad_x=float(pad_x),
            pad_y=float(pad_y),
            line_spacing=float(line_spacing),
        )


# --------------------------------------------------------------------------- #
# 思维导图布局（右向树，父节点垂直居中于子树）
# --------------------------------------------------------------------------- #


def build_layout(
    root: Node,
    config: Optional[LayoutConfig] = None,
    accents: Optional[List[str]] = None,
) -> Layout:
    """计算整棵树的思维导图几何布局。"""
    config = config or LayoutConfig()
    accents = accents or ACCENTS
    measurer = Measurer(config)

    sizes: Dict[int, Box] = {}
    column_width: Dict[int, float] = {}

    def measure(node: Node, depth: int) -> None:
        size = config.font_size_at(depth)
        limit = config.root_max_text_width if depth == 0 else config.max_text_width
        box = measurer.box(
            node.text, size, limit, min_width=config.min_width, bold=depth == 0
        )
        sizes[id(node)] = box
        column_width[depth] = max(column_width.get(depth, 0.0), box.width)
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

    edges: List[Edge] = []

    def collect(placed: Placed) -> None:
        for child in placed.children:
            points = bezier_points(
                placed.box.right,
                placed.box.center_y,
                child.box.left,
                child.box.center_y,
            )
            edges.append(
                Edge(
                    points=points,
                    color=child.accent,
                    width=2.4 if placed.depth == 0 else 1.8,
                )
            )
            collect(child)

    collect(root_placed)

    layout = Layout(
        root=root_placed,
        nodes=placed_nodes,
        width=width,
        height=height,
        config=config,
        edges=edges,
        kind="mindmap",
    )
    if min_top < 0:
        layout.shift(0.0, -min_top)
        layout.height -= min_top
    return layout


def node_edges(placed: Placed) -> List[tuple[float, float, float, float, str, int]]:
    """兼容旧接口：产出 (x1, y1, x2, y2, 颜色, 线宽) 边线描述。"""
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
