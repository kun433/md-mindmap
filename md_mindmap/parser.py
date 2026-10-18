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

__all__ = [
    "Document",
    "MermaidBlock",
    "Node",
    "guess_kind",
    "parse_document",
    "parse_markdown",
    "parse_mermaid_mindmap",
    "parse_mermaid_timeline",
    "extract_mermaid_blocks",
    "extract_mermaid_diagrams",
    "split_period",
]


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
    """把 ``- [x] 事项`` 转成带勾选符号的文本。

    勾选符号用 ``√`` / ``□``：微软雅黑本身就有这两个字形，
    Pillow、Tk 与浏览器渲染一致；``☑`` / ``☐`` / ``✓`` 在中文字体里缺字，
    导出时会变成方块，还会因为字体回退把文字挤出节点框。
    """
    match = _TASK_RE.match(text)
    if not match:
        return text
    mark = "√" if match.group(1).lower() == "x" else "□"
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


def _text_line(text: str) -> str:
    """把多行节点文本压成一行。"""
    return " ".join(part.strip() for part in text.split("\n") if part.strip())


_PERIOD_PATTERNS = [
    r"\d{4}\s*[-/.年]\s*\d{1,2}\s*[-/.月]\s*\d{1,2}\s*日?",
    r"\d{1,2}\s*月\s*\d{1,2}\s*日",
    r"\d{4}\s*[-/.年]\s*\d{1,2}\s*月?",
    r"\d{4}\s*年?(?:\s*(?:上|下)半年)?",
    r"Q[1-4]",
    r"第[一二三四五六七八九十百\d]+(?:阶段|步|周|天|章|部分|季度)",
    r"\d{1,2}\s*月",
]

_PERIOD_RE = re.compile(
    r"^\s*(?P<period>" + "|".join(_PERIOD_PATTERNS) + r")\s*[：:、,，·\-–—\/]?\s*(?P<rest>.*)$"
)


def split_period(text: str) -> tuple[str, str]:
    """把「2024-03 立项」拆成 ("2024-03", "立项")，没有时间前缀时返回空字符串和原文。"""
    line = _text_line(text)
    match = _PERIOD_RE.match(line)
    if not match:
        return "", line
    rest = match.group("rest").strip(" ：:、,，·-–—/")
    if not rest:
        return "", line
    return match.group("period").strip(), rest


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


@dataclass
class MermaidBlock:
    """一段 mermaid 代码块及其图形类型。"""

    kind: str  # mindmap | timeline
    lines: List[str]


def extract_mermaid_diagrams(text: str) -> List[MermaidBlock]:
    """提取文档中所有 mermaid 思维导图 / 时间轴代码块。"""
    raw_blocks: List[List[str]] = []
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
                    raw_blocks.append(current)
                current = None
            continue
        if current is not None:
            current.append(raw.rstrip())

    result: List[MermaidBlock] = []
    for block in raw_blocks:
        body = [line for line in block if line.strip()]
        if not body:
            continue
        first = body[0].strip().lower()
        if first.startswith("mindmap") or first.startswith("mind-map"):
            result.append(MermaidBlock("mindmap", block))
        elif first.startswith("timeline"):
            result.append(MermaidBlock("timeline", block))
    return result


def extract_mermaid_blocks(text: str) -> List[List[str]]:
    """兼容旧接口：只返回 mermaid mindmap 代码块的内容行。"""
    return [block.lines for block in extract_mermaid_diagrams(text) if block.kind == "mindmap"]


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


def parse_mermaid_timeline(lines: List[str], title: str = "") -> Node:
    """解析 mermaid ``timeline`` 代码块。

    ``2024-03 : 立项 : 完成调研`` 会拆成两个时间点节点，节点文本带上时间前缀，
    方便时间轴布局再拆出日期徽章。``section`` 只用于分组，会被平铺忽略。
    """
    root_text = title or "时间轴"
    events: List[tuple[str, str]] = []
    current_period = ""

    for raw in lines:
        line = raw.split("%%")[0].rstrip()
        if not line.strip():
            continue
        stripped = line.strip()
        low = stripped.lower()
        if low.startswith("timeline"):
            continue
        if low.startswith("title"):
            value = clean_inline(stripped[5:].strip())
            if value:
                root_text = value
            continue
        if low.startswith("section"):
            continue

        indent = _indent_width(line)
        if stripped.startswith(":"):
            segments = [clean_inline(part) for part in stripped[1:].split(":")]
            for segment in segments:
                if segment:
                    events.append((current_period, segment))
            continue

        parts = [clean_inline(part) for part in stripped.split(":")]
        parts = [part for part in parts if part]
        if not parts:
            continue
        if len(parts) == 1:
            if indent == 0:
                current_period = parts[0]
                events.append((parts[0], ""))
            else:
                events.append((current_period, parts[0]))
            continue

        period = parts[0]
        current_period = period
        for segment in parts[1:]:
            events.append((period, segment))

    root = Node(text=root_text, kind="root")
    for period, segment in events:
        text = f"{period} {segment}".strip() if segment else period
        if not text:
            continue
        root.add(Node(text=text, kind="item", level=1))
    return root


# --------------------------------------------------------------------------- #
# 对外入口
# --------------------------------------------------------------------------- #


@dataclass
class Document:
    """一次解析的结果：节点树 + 建议的图形类型。"""

    root: Node
    kind: str = "mindmap"
    title: str = ""


def guess_kind(root: Node) -> str:
    """按内容猜图形类型：一级节点大多是日期时用时间轴，否则用思维导图。"""
    children = root.children
    if len(children) < 3:
        return "mindmap"
    dated = sum(1 for child in children if split_period(child.text)[0])
    if dated >= 3 and dated >= len(children) * 0.6:
        return "timeline"
    return "mindmap"


def parse_document(
    text: str,
    title: str = "",
    prefer_mermaid: bool = True,
    diagram: str = "auto",
) -> Document:
    """解析 Markdown，并按需要选择图形类型。

    Args:
        text: Markdown 原文。
        title: 文档标题（通常是文件名）。
        prefer_mermaid: 存在 mermaid 代码块时优先使用它。
        diagram: ``auto`` 或 mindmap / fishbone / timeline / org。
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    requested = (diagram or "auto").strip().lower()
    auto = requested in ("", "auto")

    if not text.strip():
        return Document(
            root=Node(text=title or "思维导图", kind="root"),
            kind="mindmap" if auto else requested,
            title=title,
        )

    if prefer_mermaid:
        blocks = extract_mermaid_diagrams(text)
        if blocks:
            chosen = blocks[0]
            if not auto:
                for block in blocks:
                    if block.kind == requested:
                        chosen = block
                        break
                else:
                    chosen = max(blocks, key=lambda item: len(item.lines))
            tree = (
                parse_mermaid_timeline(chosen.lines, title=title)
                if chosen.kind == "timeline"
                else parse_mermaid_mindmap(chosen.lines, title=title)
            )
            return Document(root=tree, kind=requested if not auto else chosen.kind, title=title)

    tree = _build_tree(_blocks_from_markdown(text.split("\n")), title or "思维导图")
    return Document(root=tree, kind=guess_kind(tree) if auto else requested, title=title)


def parse_markdown(
    text: str,
    title: str = "",
    prefer_mermaid: bool = True,
) -> Node:
    """解析 Markdown 文本，返回节点树（兼容旧接口）。"""
    return parse_document(text, title=title, prefer_mermaid=prefer_mermaid).root
