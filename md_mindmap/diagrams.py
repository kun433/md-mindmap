"""多种图形布局：思维导图、鱼骨图、时间轴、组织结构图。

每个布局函数都返回统一的 :class:`~md_mindmap.layout.Layout` 场景
（``nodes`` + ``edges``），渲染层不需要知道具体是哪一种图形。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from .layout import ACCENTS, Box, Edge, Layout, LayoutConfig, Measurer, Placed, build_layout
from .parser import Node, split_period

__all__ = [
    "DIAGRAM_KINDS",
    "DIAGRAM_LABELS",
    "build_diagram",
    "build_fishbone",
    "build_org",
    "build_timeline",
    "split_period",
]

# 顺序即界面里下拉框的顺序
DIAGRAM_KINDS: Tuple[str, ...] = ("mindmap", "fishbone", "timeline", "org")

DIAGRAM_LABELS: Dict[str, str] = {
    "mindmap": "思维导图",
    "fishbone": "鱼骨图",
    "timeline": "时间轴",
    "org": "组织结构图",
}

_DIAGRAM_ALIASES = {
    "mindmap": "mindmap",
    "mind-map": "mindmap",
    "map": "mindmap",
    "思维导图": "mindmap",
    "fishbone": "fishbone",
    "ishikawa": "fishbone",
    "鱼骨图": "fishbone",
    "因果图": "fishbone",
    "timeline": "timeline",
    "时间轴": "timeline",
    "时间线": "timeline",
    "org": "org",
    "tree": "org",
    "orgchart": "org",
    "组织结构图": "org",
    "组织架构图": "org",
    "结构图": "org",
}


def normalize_kind(kind: Optional[str]) -> str:
    """把命令行 / 界面里的图形名称归一化成标准值，无法识别时回退思维导图。"""
    if not kind:
        return "mindmap"
    return _DIAGRAM_ALIASES.get(kind.strip().lower(), "mindmap")


# --------------------------------------------------------------------------- #
# 公共工具
# --------------------------------------------------------------------------- #


def _flatten(root: Node, depth: int = 0) -> List[Tuple[int, Node]]:
    """深度优先展开子树，跳过折叠节点。"""
    items: List[Tuple[int, Node]] = []
    for child in root.children:
        items.append((depth + 1, child))
        if not child.collapsed:
            items.extend(_flatten(child, depth + 1))
    return items


def _visible_children(root: Node) -> List[Node]:
    return [] if root.collapsed else list(root.children)


def _text_line(text: str) -> str:
    """节点文本压成单行，用于时间轴 / 鱼骨图的条目。"""
    return " ".join(part.strip() for part in text.split("\n") if part.strip())


def _empty_layout(root: Node, config: LayoutConfig, accents: Sequence[str], kind: str) -> Layout:
    """只有根节点的退化场景。"""
    measurer = Measurer(config)
    box = measurer.box(
        root.text, config.root_font_size, config.root_max_text_width, min_width=120, bold=True
    )
    box.left = 0.0
    box.top = 0.0
    placed = Placed(node=root, depth=0, box=box, accent=accents[0])
    return Layout(
        root=placed,
        nodes=[placed],
        width=box.width,
        height=box.height,
        config=config,
        edges=[],
        kind=kind,
    )


# --------------------------------------------------------------------------- #
# 组织结构图（自上而下的层级树，肘形连线）
# --------------------------------------------------------------------------- #


def build_org(
    root: Node,
    config: Optional[LayoutConfig] = None,
    accents: Optional[Sequence[str]] = None,
) -> Layout:
    """自上而下的组织结构图 / 层级树。"""
    config = config or LayoutConfig()
    accents = list(accents or ACCENTS)
    if not _visible_children(root):
        return _empty_layout(root, config, accents, "org")

    measurer = Measurer(config)
    sizes: Dict[int, Box] = {}
    level_height: Dict[int, float] = {}

    def node_font(depth: int) -> int:
        if depth == 0:
            return config.root_font_size
        return max(config.min_font_size, config.root_font_size - 5)

    def measure(node: Node, depth: int) -> None:
        limit = 300 if depth == 0 else 210
        box = measurer.box(node.text, node_font(depth), limit, min_width=96, bold=depth == 0)
        sizes[id(node)] = box
        level_height[depth] = max(level_height.get(depth, 0.0), box.height)
        if not node.collapsed:
            for child in node.children:
                measure(child, depth + 1)

    measure(root, 0)

    h_gap = config.gap_x * 0.66
    v_gap = 46.0

    span: Dict[int, float] = {}

    def measure_span(node: Node) -> float:
        own = sizes[id(node)].width
        kids = _visible_children(node)
        if not kids:
            span[id(node)] = own
            return own
        total = sum(measure_span(child) for child in kids) + h_gap * (len(kids) - 1)
        span[id(node)] = max(own, total)
        return span[id(node)]

    measure_span(root)

    level_top: Dict[int, float] = {0: 0.0}
    depth = 0
    while depth in level_height:
        level_top[depth + 1] = level_top[depth] + level_height[depth] + v_gap
        depth += 1

    nodes: List[Placed] = []
    edges: List[Edge] = []

    def place(node: Node, depth: int, left: float, accent: str) -> Placed:
        box = sizes[id(node)]
        band = level_height[depth]
        box.left = left + (span[id(node)] - box.width) / 2
        box.top = level_top[depth] + (band - box.height) / 2
        placed = Placed(node=node, depth=depth, box=box, accent=accent)
        nodes.append(placed)

        kids = _visible_children(node)
        if kids:
            total = sum(span[id(child)] for child in kids) + h_gap * (len(kids) - 1)
            x = left + (span[id(node)] - total) / 2
            mid_y = box.bottom + v_gap / 2
            for index, child in enumerate(kids):
                child_accent = accents[index % len(accents)] if depth == 0 else accent
                child_placed = place(child, depth + 1, x, child_accent)
                child_placed.parent = placed
                placed.children.append(child_placed)
                edges.append(
                    Edge(
                        points=[
                            box.center_x,
                            box.bottom,
                            box.center_x,
                            mid_y,
                            child_placed.box.center_x,
                            mid_y,
                            child_placed.box.center_x,
                            child_placed.box.top,
                        ],
                        color=child_accent,
                        width=2.2 if depth == 0 else 1.6,
                    )
                )
                x += span[id(child)] + h_gap
        return placed

    root_placed = place(root, 0, 0.0, accents[0])

    width = max((p.box.right for p in nodes), default=0.0)
    height = max((p.box.bottom for p in nodes), default=0.0)
    return Layout(
        root=root_placed,
        nodes=nodes,
        width=width,
        height=height,
        config=config,
        edges=edges,
        kind="org",
    )


# --------------------------------------------------------------------------- #
# 鱼骨图（水平主骨 + 上下交替的垂直分支 + 子因）
# --------------------------------------------------------------------------- #


def build_fishbone(
    root: Node,
    config: Optional[LayoutConfig] = None,
    accents: Optional[Sequence[str]] = None,
) -> Layout:
    """鱼骨图：右侧是结果（鱼头），主骨上交替伸出主因，主因上挂子因。

    结构映射：根节点 = 要分析的结果，一级子节点 = 主因，更深层 = 子因。
    骨刺略微向右倾斜，子因从主骨一侧依次排开，标签固定在骨刺末端。
    """
    config = config or LayoutConfig()
    accents = list(accents or ACCENTS)
    categories = _visible_children(root)
    if not categories:
        return _empty_layout(root, config, accents, "fishbone")

    measurer = Measurer(config)
    head = measurer.box(root.text, config.root_font_size, 260, min_width=132, bold=True)
    label_font = max(config.min_font_size + 1, config.root_font_size - 4)
    row_font = config.min_font_size

    row_step = 26.0
    row_start = 26.0
    tick_len = 15.0
    slant = 0.34  # 骨刺倾斜度：越靠外越偏右，更接近经典鱼骨

    class Branch:
        def __init__(self, index: int, node: Node) -> None:
            self.index = index
            self.node = node
            self.label = measurer.box(
                node.text, label_font, 230, pad_x=12, pad_y=7, min_width=96
            )
            self.rows: List[Tuple[str, Box]] = []
            if not node.collapsed:
                for child in node.children:
                    self._collect(child, 0)
            self.bone_len = max(88.0, 34.0 + row_step * len(self.rows))
            row_width = max((box.width for _text, box in self.rows), default=0.0)
            self.slot = max(
                self.label.width + 30,
                row_width + tick_len + 24 + slant * self.bone_len,
                150.0,
            )

        def _collect(self, node: Node, indent: int) -> None:
            prefix = "" if indent == 0 else "  " * indent + "› "
            text = prefix + _text_line(node.text)
            if text.strip():
                self.rows.append((text, measurer.box(text, row_font, 260, pad_x=0, pad_y=0)))
            if not node.collapsed:
                for child in node.children:
                    self._collect(child, indent + 1)

    branches = [Branch(index, node) for index, node in enumerate(categories)]
    slot = max(branch.slot for branch in branches)

    max_up = max(
        (branch.bone_len + branch.label.height + 30 for branch in branches if branch.index % 2 == 0),
        default=120.0,
    )
    max_down = max(
        (branch.bone_len + branch.label.height + 30 for branch in branches if branch.index % 2 == 1),
        default=120.0,
    )
    spine_y = max_up + 12
    height = spine_y + max_down + 12

    nodes: List[Placed] = []
    edges: List[Edge] = []

    root_placed = Placed(node=root, depth=0, box=head, accent=accents[0])
    nodes.append(root_placed)

    stations: List[float] = []
    for branch in branches:
        x = 36.0 + slot * branch.index
        stations.append(x)
        up = branch.index % 2 == 0
        sign = -1.0 if up else 1.0
        accent = accents[branch.index % len(accents)]

        tip_x = x + slant * branch.bone_len
        tip_y = spine_y + sign * branch.bone_len
        edges.append(
            Edge(points=[x, spine_y, tip_x, tip_y], color=accent, width=2.2, level=1)
        )

        label = branch.label
        label.left = tip_x - label.width / 2
        label.top = tip_y - label.height - 10 if up else tip_y + 10
        placed_label = Placed(node=branch.node, depth=1, box=label, accent=accent)
        nodes.append(placed_label)
        root_placed.children.append(placed_label)

        for row_index, (text, text_box) in enumerate(branch.rows):
            # 上方骨刺自上而下阅读，顺序与原文一致；下方骨刺由主骨向外阅读
            order = len(branch.rows) - 1 - row_index if up else row_index
            offset = row_start + row_step * order
            bone_x = x + slant * offset
            row_y = spine_y + sign * offset
            edges.append(
                Edge(
                    points=[bone_x, row_y, bone_x + tick_len, row_y],
                    color=accent,
                    width=1.2,
                    level=2,
                )
            )
            text_box.left = bone_x + tick_len + 5
            text_box.top = row_y - text_box.height / 2
            nodes.append(
                Placed(
                    node=Node(text=text, kind="item"),
                    depth=2,
                    box=text_box,
                    accent=accent,
                    shape="text",
                )
            )

    last_x = stations[-1] if stations else 36.0
    spine_end = last_x + slot + 10.0
    head.left = spine_end + 34.0
    head.top = spine_y - head.height / 2
    edges.append(
        Edge(
            points=[0.0, spine_y, head.left - 14, spine_y],
            color=accents[0],
            width=3.2,
            level=0,
            arrow=True,
        )
    )

    layout = Layout(
        root=root_placed,
        nodes=nodes,
        width=head.right,
        height=height,
        config=config,
        edges=edges,
        kind="fishbone",
    )
    min_top = min((p.box.top for p in nodes), default=0.0)
    min_left = min((p.box.left for p in nodes), default=0.0)
    if min_top < 0 or min_left < 0:
        layout.shift(-min(min_left, 0.0), -min(min_top, 0.0))
        layout.width -= min(min_left, 0.0)
        layout.height -= min(min_top, 0.0)
    return layout


# --------------------------------------------------------------------------- #
# 时间轴
# --------------------------------------------------------------------------- #

def build_timeline(
    root: Node,
    config: Optional[LayoutConfig] = None,
    accents: Optional[Sequence[str]] = None,
) -> Layout:
    """水平时间轴：每个一级节点是一个时间点，二级及更深的节点作为该时间点的细目。"""
    config = config or LayoutConfig()
    accents = list(accents or ACCENTS)
    events = _visible_children(root)
    if not events:
        return _empty_layout(root, config, accents, "timeline")

    measurer = Measurer(config)
    title_font = config.root_font_size
    event_font = max(config.min_font_size + 1, config.root_font_size - 4)
    detail_font = config.min_font_size

    root_box = measurer.box(root.text, title_font, 520, min_width=140, bold=True)

    class Event:
        def __init__(self, index: int, node: Node) -> None:
            self.index = index
            self.node = node
            self.period, title = split_period(node.text)
            self.title = measurer.box(
                title or node.text, event_font, 240, pad_x=13, pad_y=8, min_width=110
            )
            self.detail: Optional[Box] = None
            lines: List[str] = []
            if not node.collapsed:
                self._detail_lines(node, 0, lines)
            if lines:
                self.detail = measurer.box(
                    "\n".join(lines), detail_font, 250, pad_x=11, pad_y=7, line_spacing=1.6
                )
            self.badge_width = (
                measurer.text_width(self.period, detail_font) + 18 if self.period else 0.0
            )
            self.width = max(self.title.width, self.detail.width if self.detail else 0.0, 132.0)

        def _detail_lines(self, node: Node, depth: int, lines: List[str]) -> None:
            for child in node.children:
                prefix = "· " if depth == 0 else "  " * depth + "› "
                lines.append(prefix + _text_line(child.text))
                if not child.collapsed:
                    self._detail_lines(child, depth + 1, lines)

        @property
        def block_height(self) -> float:
            height = self.title.height
            if self.detail:
                height += 8 + self.detail.height
            return height

    items = [Event(index, node) for index, node in enumerate(events)]
    slot = max(max(item.width for item in items) + 46, 176.0)
    content_height = max(item.block_height for item in items)

    axis_y = root_box.height + 40 + content_height + 40
    width = max(slot * len(items) + 24, root_box.width + 48)
    height = axis_y + 48

    root_box.left = 0.0
    root_box.top = 0.0
    root_placed = Placed(node=root, depth=0, box=root_box, accent=accents[0])
    nodes: List[Placed] = [root_placed]
    edges: List[Edge] = []

    first_center = slot * 0.5
    last_center = slot * (len(items) - 0.5)
    edges.append(
        Edge(
            points=[max(0.0, first_center - slot * 0.5), axis_y, last_center + slot * 0.5, axis_y],
            color=accents[0],
            width=2.6,
            level=3,
            muted=True,
            arrow=True,
        )
    )

    for item in items:
        center = slot * (item.index + 0.5)
        accent = accents[item.index % len(accents)]

        dot_size = 11.0
        dot = Box(center - dot_size / 2, axis_y - dot_size / 2, dot_size, dot_size, [""], 10, 0, 0)
        nodes.append(
            Placed(node=item.node, depth=1, box=dot, accent=accent, shape="dot")
        )

        badge_bottom = axis_y - 20
        if item.period:
            badge = Box(
                center - item.badge_width / 2,
                badge_bottom - 17,
                item.badge_width,
                17,
                [item.period],
                detail_font,
                0,
                0,
            )
            nodes.append(
                Placed(
                    node=item.node,
                    depth=1,
                    box=badge,
                    accent=accent,
                    shape="text",
                    tone="accent",
                )
            )
            badge_top = badge.top
        else:
            badge_top = badge_bottom
        stem_top = badge_bottom

        cursor = badge_top - 10
        if item.detail:
            item.detail.left = center - item.detail.width / 2
            item.detail.top = cursor - item.detail.height
            nodes.append(
                Placed(
                    node=item.node,
                    depth=2,
                    box=item.detail,
                    accent=accent,
                    shape="box",
                    interactive=False,
                )
            )
            cursor = item.detail.top - 8

        item.title.left = center - item.title.width / 2
        item.title.top = cursor - item.title.height
        placed_title = Placed(node=item.node, depth=1, box=item.title, accent=accent)
        nodes.append(placed_title)
        root_placed.children.append(placed_title)

        edges.append(
            Edge(
                points=[center, axis_y, center, stem_top],
                color=accent,
                width=1.6,
            )
        )

    return Layout(
        root=root_placed,
        nodes=nodes,
        width=width,
        height=height,
        config=config,
        edges=edges,
        kind="timeline",
    )


# --------------------------------------------------------------------------- #
# 统一入口
# --------------------------------------------------------------------------- #


def build_diagram(
    root: Node,
    kind: str = "mindmap",
    config: Optional[LayoutConfig] = None,
    accents: Optional[Sequence[str]] = None,
) -> Layout:
    """按图形类型构建场景，未知类型回退为思维导图。"""
    name = normalize_kind(kind)
    config = config or LayoutConfig()
    accents = list(accents or ACCENTS)
    if name == "fishbone":
        return build_fishbone(root, config, accents)
    if name == "timeline":
        return build_timeline(root, config, accents)
    if name == "org":
        return build_org(root, config, accents)
    return build_layout(root, config, accents)
