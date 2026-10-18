"""把图形场景（节点 + 连线）导出为 PNG / SVG / 独立 HTML。

渲染层只认识两件事：节点（圆角矩形 / 圆点 / 纯文字）和折线，
因此思维导图、鱼骨图、时间轴、组织结构图共用同一套导出代码。
"""

from __future__ import annotations

import math
import os
from typing import List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw

from .fonts import load_font
from .layout import Layout, Placed
from .theme import LIGHT, Theme

__all__ = [
    "MARGIN",
    "arrow_head",
    "export_all",
    "html_document",
    "render_png",
    "render_svg",
    "svg_document",
]

MARGIN = 36
_FONT_STACK = "'Microsoft YaHei','微软雅黑','PingFang SC','Source Han Sans SC','Segoe UI',sans-serif"


def _pairs(points: Sequence[float]) -> List[Tuple[float, float]]:
    return [(points[index], points[index + 1]) for index in range(0, len(points) - 1, 2)]


def arrow_head(
    points: Sequence[float], size: float
) -> Optional[List[Tuple[float, float]]]:
    """按折线末段方向生成箭头三角形。"""
    if len(points) < 4:
        return None
    x1, y1 = points[-4], points[-3]
    x2, y2 = points[-2], points[-1]
    angle = math.atan2(y2 - y1, x2 - x1)
    if abs(x2 - x1) < 1e-6 and abs(y2 - y1) < 1e-6:
        return None
    left = (x2 - size * math.cos(angle - 0.42), y2 - size * math.sin(angle - 0.42))
    right = (x2 - size * math.cos(angle + 0.42), y2 - size * math.sin(angle + 0.42))
    return [(x2, y2), left, right]


def _node_text_origin(placed: Placed) -> Tuple[float, float, float]:
    """返回 (文字左边, 首行中心 y, 行高)。"""
    box = placed.box
    line_height = box.line_spacing * box.font_size
    return box.left + box.pad_x, box.top + box.pad_y + line_height / 2, line_height


# --------------------------------------------------------------------------- #
# PNG
# --------------------------------------------------------------------------- #


def render_png(
    layout: Layout,
    path: str,
    theme: Theme = LIGHT,
    scale: int = 2,
    transparent: bool = False,
) -> str:
    """渲染为 PNG 图片（默认 2 倍超采样后缩放，边缘更平滑）。"""
    scale = max(1, min(4, int(scale)))
    width = int((layout.width + MARGIN * 2) * scale)
    height = int((layout.height + MARGIN * 2) * scale)
    background = (0, 0, 0, 0) if transparent else theme.bg
    image = Image.new("RGBA" if transparent else "RGB", (max(1, width), max(1, height)), background)
    draw = ImageDraw.Draw(image, "RGBA")

    offset_x = MARGIN * scale
    offset_y = MARGIN * scale

    def sx(value: float) -> float:
        return offset_x + value * scale

    def sy(value: float) -> float:
        return offset_y + value * scale

    for edge in layout.edges:
        points = [(sx(x), sy(y)) for x, y in _pairs(edge.points)]
        if len(points) < 2:
            continue
        color = theme.edge_paint(edge)
        draw.line(
            points,
            fill=color,
            width=max(1, int(round(edge.width * scale))),
            joint="curve",
        )
        if edge.arrow:
            head = arrow_head(edge.points, max(7.0, edge.width * 5.2))
            if head:
                draw.polygon([(sx(x), sy(y)) for x, y in head], fill=color)

    for placed in layout.nodes:
        _draw_node_png(draw, placed, theme, scale, sx, sy)

    image = image.resize((int(width / scale), int(height / scale)), Image.LANCZOS)
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    image.save(path)
    return path


def _draw_node_png(
    draw: ImageDraw.ImageDraw,
    placed: Placed,
    theme: Theme,
    scale: int,
    sx,
    sy,
) -> None:
    box = placed.box
    fill, text_color, border, border_width = theme.paint(placed)
    left, top = sx(box.left), sy(box.top)
    right, bottom = sx(box.right), sy(box.bottom)

    if placed.shape == "dot":
        draw.ellipse([left, top, right, bottom], fill=fill)
        return

    if placed.shape == "box":
        radius = min(box.height / 2, 10) * scale
        if placed.depth <= 1:
            draw.rounded_rectangle(
                [left + 1.5 * scale, top + 2.5 * scale, right + 1.5 * scale, bottom + 3 * scale],
                radius=radius,
                fill="#00000022" if not theme.dark else "#00000066",
            )
        draw.rounded_rectangle(
            [left, top, right, bottom],
            radius=radius,
            fill=fill,
            outline=border if border_width > 0 else None,
            width=max(1, int(border_width * scale)) if border_width > 0 else 0,
        )

    font = load_font(int(box.font_size * scale), bold=placed.shape == "box" and placed.depth == 0)
    text_x = left + box.pad_x * scale
    line_height = box.line_spacing * box.font_size * scale
    for index, line in enumerate(box.lines):
        if not line:
            continue
        center_y = top + box.pad_y * scale + line_height * (index + 0.5)
        draw.text((text_x, center_y), line, font=font, fill=text_color, anchor="lm")


# --------------------------------------------------------------------------- #
# SVG
# --------------------------------------------------------------------------- #


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def svg_document(layout: Layout, theme: Theme = LIGHT, padding: int = MARGIN) -> str:
    """生成 SVG 字符串。"""
    width = layout.width + padding * 2
    height = layout.height + padding * 2
    parts: List[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
        f'viewBox="0 0 {width:.2f} {height:.2f}" font-family="{_FONT_STACK}">'
    )
    parts.append(f'<rect width="{width:.2f}" height="{height:.2f}" fill="{theme.bg}"/>')
    parts.append(f'<g transform="translate({padding},{padding})">')

    for edge in layout.edges:
        pairs = _pairs(edge.points)
        if len(pairs) < 2:
            continue
        stroke = theme.edge_paint(edge)
        d = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pairs)
        parts.append(
            f'<path d="{d}" fill="none" stroke="{stroke}" stroke-width="{edge.width:.2f}" '
            f'stroke-linecap="round" stroke-linejoin="round"/>'
        )
        if edge.arrow:
            head = arrow_head(edge.points, max(7.0, edge.width * 5.2))
            if head:
                points = " ".join(f"{x:.2f},{y:.2f}" for x, y in head)
                parts.append(f'<polygon points="{points}" fill="{stroke}"/>')

    for placed in layout.nodes:
        parts.append(_node_svg(placed, theme))

    parts.append("</g></svg>")
    return "".join(parts)


def _node_svg(placed: Placed, theme: Theme) -> str:
    box = placed.box
    fill, text_color, border, border_width = theme.paint(placed)
    chunks: List[str] = []

    if placed.shape == "dot":
        radius = min(box.width, box.height) / 2
        chunks.append(
            f'<circle cx="{box.center_x:.2f}" cy="{box.center_y:.2f}" r="{radius:.2f}" '
            f'fill="{fill}"/>'
        )
    elif placed.shape == "box":
        radius = min(box.height / 2, 10)
        stroke = f' stroke="{border}" stroke-width="{border_width}"' if border_width > 0 else ""
        chunks.append(
            f'<rect x="{box.left:.2f}" y="{box.top:.2f}" width="{box.width:.2f}" '
            f'height="{box.height:.2f}" rx="{radius:.2f}" fill="{fill}"{stroke}/>'
        )

    if placed.shape == "dot":
        return "".join(chunks)

    line_height = box.line_spacing * box.font_size
    for index, line in enumerate(box.lines):
        if not line:
            continue
        center_y = box.top + box.pad_y + line_height * (index + 0.5)
        weight = ' font-weight="600"' if placed.depth == 0 and placed.shape == "box" else ""
        chunks.append(
            f'<text x="{box.left + box.pad_x:.2f}" y="{center_y:.2f}" fill="{text_color}" '
            f'font-size="{box.font_size}"{weight} dominant-baseline="central" '
            f'xml:space="preserve">{_escape(line)}</text>'
        )
    return "".join(chunks)


def render_svg(layout: Layout, path: str, theme: Theme = LIGHT) -> str:
    svg = svg_document(layout, theme)
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(svg)
    return path


# --------------------------------------------------------------------------- #
# HTML
# --------------------------------------------------------------------------- #

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{title} · {kind_label}</title>
<style>
  :root {{ color-scheme: {scheme}; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:{bg}; color:{ink};
         font-family:{font_stack}; }}
  header {{ display:flex; flex-wrap:wrap; gap:10px; align-items:center;
            padding:14px 20px; border-bottom:1px solid {line}; }}
  h1 {{ font-size:16px; margin:0; font-weight:600; letter-spacing:.01em; }}
  .meta {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:11px;
           color:{muted}; text-transform:uppercase; letter-spacing:.08em; }}
  .spacer {{ flex:1; }}
  button {{ font:inherit; font-size:13px; padding:6px 12px; border-radius:8px;
            border:1px solid {line}; background:{chip}; color:{ink}; cursor:pointer; }}
  button:hover {{ border-color:{accent}; color:{accent}; }}
  main {{ overflow:hidden; height:calc(100vh - 57px); cursor:grab; }}
  main.dragging {{ cursor:grabbing; }}
  #stage {{ transform-origin:0 0; }}
  #stage svg {{ display:block; }}
  footer {{ position:fixed; right:14px; bottom:12px; font-size:11px; color:{muted};
            font-family:ui-monospace,monospace; }}
</style>
</head>
<body>
<header>
  <div>
    <div class="meta">md-mindmap</div>
    <h1>{title}</h1>
  </div>
  <div class="spacer"></div>
  <button id="zoom-out">缩小 −</button>
  <button id="zoom-in">放大 ＋</button>
  <button id="fit">适应窗口</button>
  <button id="download">下载 SVG</button>
</header>
<main id="viewport"><div id="stage">{svg}</div></main>
<footer>{count} 个节点 · {kind_label} · 滚轮缩放 · 拖拽平移</footer>
<script>
(function () {{
  var viewport = document.getElementById('viewport');
  var stage = document.getElementById('stage');
  var scale = 1, tx = 0, ty = 0, dragging = false, startX = 0, startY = 0;
  function apply() {{
    stage.style.transform = 'translate(' + tx + 'px,' + ty + 'px) scale(' + scale + ')';
  }}
  function fit() {{
    var svg = stage.querySelector('svg');
    if (!svg) return;
    var w = parseFloat(svg.getAttribute('width'));
    var h = parseFloat(svg.getAttribute('height'));
    var vw = viewport.clientWidth, vh = viewport.clientHeight;
    scale = Math.min((vw - 24) / w, (vh - 24) / h, 2);
    tx = (vw - w * scale) / 2;
    ty = Math.max(12, (vh - h * scale) / 2);
    apply();
  }}
  function zoom(factor, cx, cy) {{
    var next = Math.min(6, Math.max(0.08, scale * factor));
    var ratio = next / scale;
    tx = cx - (cx - tx) * ratio;
    ty = cy - (cy - ty) * ratio;
    scale = next;
    apply();
  }}
  viewport.addEventListener('wheel', function (event) {{
    event.preventDefault();
    var rect = viewport.getBoundingClientRect();
    zoom(event.deltaY < 0 ? 1.12 : 1 / 1.12, event.clientX - rect.left, event.clientY - rect.top);
  }}, {{ passive: false }});
  viewport.addEventListener('pointerdown', function (event) {{
    dragging = true; startX = event.clientX - tx; startY = event.clientY - ty;
    viewport.classList.add('dragging');
  }});
  window.addEventListener('pointermove', function (event) {{
    if (!dragging) return;
    tx = event.clientX - startX; ty = event.clientY - startY; apply();
  }});
  window.addEventListener('pointerup', function () {{
    dragging = false; viewport.classList.remove('dragging');
  }});
  document.getElementById('zoom-in').onclick = function () {{
    zoom(1.2, viewport.clientWidth / 2, viewport.clientHeight / 2);
  }};
  document.getElementById('zoom-out').onclick = function () {{
    zoom(1 / 1.2, viewport.clientWidth / 2, viewport.clientHeight / 2);
  }};
  document.getElementById('fit').onclick = fit;
  document.getElementById('download').onclick = function () {{
    var svg = stage.querySelector('svg').outerHTML;
    var blob = new Blob([svg], {{ type: 'image/svg+xml;charset=utf-8' }});
    var link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = {filename} + '.svg';
    link.click();
  }};
  fit();
  window.addEventListener('resize', fit);
}})();
</script>
</body>
</html>
"""


def html_document(
    layout: Layout,
    theme: Theme = LIGHT,
    title: str = "思维导图",
    kind_label: str = "",
) -> str:
    """生成自带缩放/平移/下载的独立 HTML。"""
    from .diagrams import DIAGRAM_LABELS

    svg = svg_document(layout, theme)
    filename = os.path.splitext(os.path.basename(title))[0] or "mindmap"
    return _HTML_TEMPLATE.format(
        title=_escape(title),
        svg=svg,
        count=len(layout.nodes),
        kind_label=kind_label or DIAGRAM_LABELS.get(layout.kind, "思维导图"),
        bg=theme.bg,
        ink=theme.ink,
        muted=theme.muted,
        line="#FFFFFF1F" if theme.dark else "#00000014",
        chip="#FFFFFF0D" if theme.dark else "#FFFFFF",
        accent=theme.accents[0],
        scheme="dark" if theme.dark else "light",
        font_stack=_FONT_STACK,
        filename=filename,
    )


def export_all(
    layout: Layout,
    base_path: str,
    theme: Theme = LIGHT,
    formats: Optional[List[str]] = None,
    title: str = "思维导图",
) -> List[str]:
    """按需导出多种格式，返回生成的文件路径列表。"""
    formats = formats or ["png", "svg", "html"]
    outputs: List[str] = []
    root, _ = os.path.splitext(base_path)
    for kind in formats:
        kind = kind.lower().lstrip(".")
        if kind == "png":
            outputs.append(render_png(layout, root + ".png", theme))
        elif kind == "svg":
            outputs.append(render_svg(layout, root + ".svg", theme))
        elif kind == "html":
            path = root + ".html"
            directory = os.path.dirname(os.path.abspath(path))
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(html_document(layout, theme, title=title))
            outputs.append(path)
    return outputs
