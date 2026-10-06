"""把 Markdown 文本解析成思维导图树。

支持两类输入：

1. 普通 Markdown 结构：标题（# ~ ######）、无序/有序列表、引用、段落；
2. ```mermaid 代码块中的 ``mindmap`` 语法（含 ``root((标题))``、``A[文本]`` 等形状）。
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import List, Optional

__all__ = ["Node", "parse_markdown", "parse_mermaid_mindmap", "extract_mermaid_blocks"]


@dataclass
class Node:
    """思维导图节点。"""

    text: str
    kind: str = "item"  # root | heading | item | quote | para | table
    level: int = 0  # 原始层级：标题为 # 的数量，列表为缩进级
    children: List["Node"] = field(default_factory=list)
    collapsed: bool = False

    def add(self, child: "Node") -> "Node":
        self.children.append(child)
        return child

    def walk(self, depth: int = 0):
        """深度优先遍历，产出 (depth, node)。"""
        yield depth, self
        for child in self.children:
            yield from child.walk(depth + 1)

    def count(self) -> int:
        """返回子树节点总数（含自身）。"""
        return 1 + sum(child.count() for child in self.children)


# --------------------------------------------------------------------------- #
# 文本清理
# --------------------------------------------------------------------------- #

_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_FOOTNOTE_RE = re.compile(r"\[\^[^\]]*\]")
_EMPHASIS_RE = re.compile(r"(\*\*\*|\*\*|\*|___|__|_|~~|`)")
_TASK_RE = re.compile(r"^\[([ xX])\]\s+(.*)$")
_ENTITY_MAP = {
    "&nbsp;": " ",
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&#39;": "'",
    "&mdash;": "—",
    "&hellip;": "…",
}


def clean_inline(text: str) -> str:
    """去掉行内 Markdown 标记，保留可读文本。"""
    text = _IMAGE_RE.sub(lambda m: m.group(1) or "图片", text)
    text = _LINK_RE.sub(lambda m: m.group(1), text)
    text = _FOOTNOTE_RE.sub("", text)
    text = text.replace("<br/>", "\n").replace("<br />", "\n").replace("<br>", "\n")
    for entity, char in _ENTITY_MAP.items():
        text = text.replace(entity, char)
    text = _EMPHASIS_RE.sub("", text)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def _task_prefix(text: str) -> str:
    """把 ``- [x] 事项`` 转成带勾选符号的文本。"""
    match = _TASK_RE.match(text)
    if not match:
        return text
    mark = "☑" if match.group(1).lower() == "x" else "☐"
    return f"{mark} {match.group(2).strip()}"


def _indent_width(line: str) -> int:
    space = 0
    for char in line:
        if char == "\t":
            space += 4
        elif char == " ":
            space += 1
        else:
            break
    return space


# --------------------------------------------------------------------------- #
# 结构解析
# --------------------------------------------------------------------------- #

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_UL_RE = re.compile(r"^([-*+])\s+(.*)$")
_OL_RE = re.compile(r"^(\d{1,3})[.)]\s+(.*)$")
_QUOTE_RE = re.compile(r"^>\s?(.*)$")
_FENCE_RE = re.compile(r"^(\s*)(```+|~~~+)\s*([^\s`]*)")


@dataclass
class _Block:
    kind: str  # heading | item | quote | para | table
    depth: int
    text: str


def _pre_scan_unit(lines: List[str]) -> int:
    """推断列表缩进的一个层级对应多少空格。"""
    indents = []
    for line in lines:
        if not line.strip():
            continue
        stripped = line.lstrip()
        if _UL_RE.match(stripped) or _OL_RE.match(stripped):
            width = _indent_width(line)
            if width > 0:
                indents.append(width)
    if not indents:
        return 2
    return max(1, min(indents))


def _blocks_from_markdown(lines: List[str]) -> List[_Block]:
    """把 Markdown 行序列转换成扁平的结构块序列。"""
    unit = _pre_scan_unit(lines)
    blocks: List[_Block] = []
    heading_depth = 0
    heading_base: Optional[int] = None
    first_heading_consumed = False
    in_fence = False

    for raw in lines:
        line = raw.rstrip("\n").rstrip()
        fence = _FENCE_RE.match(line)
        if fence:
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        stripped = line.strip()
        if not stripped:
            continue
        if re.fullmatch(r"([-*_])\1{2,}", stripped):  # 分隔线
            continue
        if stripped.startswith("<!--"):
            continue

        heading = _HEADING_RE.match(stripped)
        if heading:
            level = len(heading.group(1))
            text = clean_inline(heading.group(2))
            if heading_base is None:
                heading_base = level
            if not first_heading_consumed:
                first_heading_consumed = True
                blocks.append(_Block("title", 0, text))
                heading_depth = 0
                continue
            depth = max(1, level - heading_base + 1)
            heading_depth = depth
            blocks.append(_Block("heading", depth, text))
            continue

        quote = _QUOTE_RE.match(stripped)
        if quote:
            inner = clean_inline(quote.group(1))
            if inner:
                blocks.append(_Block("quote", heading_depth + 1, inner))
            continue

        item = _UL_RE.match(stripped) or _OL_RE.match(stripped)
        if item:
            body = item.group(2)
            text = clean_inline(_task_prefix(body))
            if not text:
                continue
            base = heading_depth + 1
            extra = _indent_width(line) // unit
            blocks.append(_Block("item", base + extra, text))
            continue

        if stripped.startswith("|"):
            cells = [clean_inline(cell) for cell in stripped.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", cell or "-") for cell in cells):
                continue
            text = " ｜ ".join(cell for cell in cells if cell)
            if text:
                blocks.append(_Block("table", heading_depth + 1, text))
            continue

        text = clean_inline(stripped)
        if text:
            blocks.append(_Block("para", heading_depth + 1, text))

    return blocks


def _build_tree(blocks: List[_Block], title: str) -> Node:
    root = Node(text=title, kind="root")
    stack: List[tuple[int, Node]] = [(0, root)]

    for block in blocks:
        text = block.text
        if block.kind == "title":
            if stack[0][1].text in ("", title):
                root.text = text
            else:
                stack = [(0, root)]
                root.add(Node(text=text, kind="heading", level=1))
            continue
        if not text:
            continue

        depth = max(1, block.depth)
        while len(stack) > 1 and stack[-1][0] >= depth:
            stack.pop()
        parent = stack[-1][1]
        node = Node(text=text, kind=block.kind, level=depth)
        parent.add(node)
        stack.append((depth, node))

    return root


# --------------------------------------------------------------------------- #
# mermaid mindmap
# --------------------------------------------------------------------------- #

_SHAPE_PAIRS = [
    ("((", "))"),
    ("{{", "}}"),
    ("[[", "]]"),
    ("([", "])"),
    ("[(", ")]"),
    ("[", "]"),
    ("(", ")"),
    (">", "]"),
    (")", "("),
]


def _mermaid_text(raw: str) -> str:
    """从 ``id((文本))`` / ``id[文本]`` 之类写法里取出节点文本。"""
    text = raw.strip()
    if not text:
        return ""
    if "-->" in text:  # 兼容误写的连线语法
        text = text.split("-->")[-1].strip()

    start, opener, closer = -1, "", ""
    for open_tok, close_tok in _SHAPE_PAIRS:
        index = text.find(open_tok)
        if index == -1:
            continue
        if start == -1 or index < start:
            start, opener, closer = index, open_tok, close_tok
    if start == -1:
        return clean_inline(text)

    end = text.rfind(closer)
    if end <= start:
        body = text[start + len(opener) :]
    else:
        body = text[start + len(opener) : end]
    body = clean_inline(html.unescape(body))
    return body or clean_inline(text)


def extract_mermaid_blocks(text: str) -> List[List[str]]:
    """提取文档中所有 ```mermaid mindmap 代码块的内容行。"""
    blocks: List[List[str]] = []
    current: Optional[List[str]] = None
    fence_open = False
    language = ""

    for raw in text.splitlines():
        fence = _FENCE_RE.match(raw.rstrip())
        if fence:
            if not fence_open:
                fence_open = True
                language = (fence.group(3) or "").lower()
                current = [] if language in ("mermaid", "mmd") else None
            else:
                fence_open = False
                if current is not None:
                    blocks.append(current)
                current = None
            continue
        if current is not None:
            current.append(raw.rstrip())

    result = []
    for block in blocks:
        body = [line for line in block if line.strip()]
        if not body:
            continue
        first = body[0].strip().lower()
        if first.startswith("mindmap") or first.startswith("mind-map"):
            result.append(block)
    return result


def parse_mermaid_mindmap(lines: List[str], title: str = "") -> Node:
    """解析 mermaid ``mindmap`` 代码块。"""
    root: Optional[Node] = None
    stack: List[tuple[int, Node]] = []

    for raw in lines:
        line = raw.split("%%")[0].rstrip()
        if not line.strip():
            continue
        stripped = line.strip()
        if stripped.lower().startswith("mindmap"):
            continue

        indent = _indent_width(line)
        text = _mermaid_text(stripped)
        if not text:
            continue

        node = Node(text=text, kind="item")
        if root is None:
            node.kind = "root"
            node.level = 0
            root = node
            stack = [(indent, node)]
            continue

        while len(stack) > 1 and stack[-1][0] >= indent:
            stack.pop()
        node.level = stack[-1][1].level + 1
        stack[-1][1].add(node)
        stack.append((indent, node))

    if root is None:
        root = Node(text=title or "思维导图", kind="root")

    if title and root.text in ("", "思维导图"):
        root.text = title
    return root


# --------------------------------------------------------------------------- #
# 对外入口
# --------------------------------------------------------------------------- #


def parse_markdown(
    text: str,
    title: str = "",
    prefer_mermaid: bool = True,
) -> Node:
    """解析 Markdown 文本，返回思维导图树。

    Args:
        text: Markdown 原文。
        title: 文档标题（通常是文件名），文档缺少标题时使用。
        prefer_mermaid: 存在 mermaid mindmap 代码块时优先使用它。
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        return Node(text=title or "思维导图", kind="root")

    if prefer_mermaid:
        blocks = extract_mermaid_blocks(text)
        if blocks:
            largest = max(blocks, key=len)
            return parse_mermaid_mindmap(largest, title=title)

    lines = text.split("\n")
    blocks = _blocks_from_markdown(lines)
    return _build_tree(blocks, title or "思维导图")
