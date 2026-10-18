"""解析与布局的纯逻辑测试：``python tests/test_core.py``。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:  # Windows 控制台默认 GBK，避免不可编码字符导致崩溃
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

from md_mindmap.diagrams import DIAGRAM_KINDS, build_diagram
from md_mindmap.exporter import html_document, render_png, render_svg
from md_mindmap.layout import build_layout
from md_mindmap.parser import parse_document, parse_markdown, split_period
from md_mindmap.theme import DARK, LIGHT

DOC = """# 发布计划

## 准备工作

- 一级要点
  - 二级要点
    - 三级要点
- 并列要点

> 发布窗口：每周二 20:00

## 执行步骤

1. 合并发布分支
2. 部署静态资源

| 概念 | 说明 |
| --- | --- |
| 回滚 | 恢复上一版本 |
"""

MERMAID_DOC = """# 文档标题

```mermaid
mindmap
  root((中心<br/>主题))
    分支A
      叶子1
      叶子2
    分支B
      B1
```
"""

TIMELINE_MERMAID = """# 项目大事记

```mermaid
timeline
    title 产品历程
    2021 : 立项 : 完成调研
    2022 : 内测
    2023 : 正式发布
```
"""

FISH_DOC = """# 数学成绩下滑

## 学习方法
- 只看不练
- 错题不复盘
- 刷题贪多求快

## 时间安排
- 作业拖到很晚
- 睡眠不足

## 基础薄弱
- 计算粗心
- 概念混淆

## 心理状态
- 考试紧张
- 目标不明确
"""

TIME_DOC = """# 项目里程碑

## 2024-01 立项启动
- 完成需求调研
- 组建团队

## 2024-03 设计定稿
- 交互稿评审通过

## 2024-06 内测上线
- 灰度 10% 用户
- 修复 32 个问题

## 2024-09 正式发布
- 全量上线
"""

ORG_DOC = """# 学生会组织架构

## 主席团
- 主席
- 副主席

## 学习部
- 部长
- 学习委员

## 宣传部
- 部长
- 设计组

## 体育部
- 部长
- 赛事组
"""


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"  [ok] {message}")


def test_document_structure() -> None:
    print("[1] 普通 Markdown 结构")
    tree = parse_markdown(DOC, title="发布计划")
    check(tree.text == "发布计划", "根节点取自首个一级标题")
    titles = [child.text for child in tree.children]
    check(titles[0] == "准备工作" and "执行步骤" in titles, "二级标题成为根的子节点")
    lesson = tree.children[0]
    check(lesson.children[0].text == "一级要点", "列表项挂到所属标题下")
    check(lesson.children[0].children[0].children[0].text == "三级要点", "缩进层级正确嵌套")
    check(any(node.kind == "quote" for _d, node in tree.walk()), "引用被识别为节点")
    laid_out = build_layout(tree)
    check(laid_out.width > 0 and laid_out.height > 0, "布局尺寸有效")
    check(len(laid_out.edges) > 0, "生成的场景包含连线")
    deepest = max(depth for depth, _node in laid_out.root.node.walk())
    check(deepest >= 4, f"节点深度达到 {deepest} 层")


def test_mermaid() -> None:
    print("[2] mermaid mindmap")
    tree = parse_markdown(MERMAID_DOC, title="文档标题", prefer_mermaid=True)
    check(tree.text.startswith("中心"), "优先使用 mermaid 代码块")
    check("\n" in tree.text, "<br/> 被转换为换行")
    check([c.text for c in tree.children] == ["分支A", "分支B"], "一级分支顺序正确")
    check(tree.children[0].children[0].text == "叶子1", "叶子节点挂载正确")
    fallback = parse_markdown(MERMAID_DOC, title="文档标题", prefer_mermaid=False)
    check(fallback.text == "文档标题", "关闭 mermaid 后按文档结构解析")


def test_mermaid_timeline() -> None:
    print("[3] mermaid timeline 与自动识别")
    document = parse_document(TIMELINE_MERMAID, title="项目大事记")
    check(document.kind == "timeline", "识别出 mermaid timeline")
    events = [child.text for child in document.root.children]
    check(len(events) == 4, f"时间点拆分正确（{len(events)} 个）")
    check(split_period(events[0]) == ("2021", "立项"), "冒号分隔的事件带时间前缀")
    check(split_period(events[-1])[0] == "2023", "后续事件保留时间")
    check(parse_document(TIME_DOC).kind == "timeline", "日期型大纲自动判定为时间轴")
    check(parse_document(ORG_DOC).kind == "mindmap", "普通大纲默认仍是思维导图")
    forced = parse_document(ORG_DOC, diagram="org")
    check(forced.kind == "org", "显式指定图形类型时优先使用参数")


def test_split_period() -> None:
    print("[4] 时间前缀拆分")
    cases = [
        ("2024-03 立项", ("2024-03", "立项")),
        ("2024年6月 内测", ("2024年6月", "内测")),
        ("Q3 复盘", ("Q3", "复盘")),
        ("第三阶段 上线", ("第三阶段", "上线")),
        ("没有日期", ("", "没有日期")),
        ("2024", ("", "2024")),
    ]
    for text, expected in cases:
        check(split_period(text) == expected, f"{text} → {expected}")


def _box_overlap(layout, tolerance: float = 2.0) -> list[str]:
    """返回互相重叠的矩形节点对（纯文字 / 圆点节点不参与）。"""
    boxes = [p for p in layout.nodes if p.shape == "box"]
    problems = []
    for index, first in enumerate(boxes):
        for second in boxes[index + 1 :]:
            a, b = first.box, second.box
            if (
                a.left < b.right - tolerance
                and b.left < a.right - tolerance
                and a.top < b.bottom - tolerance
                and b.top < a.bottom - tolerance
            ):
                problems.append(f"{first.text[:12]!r} × {second.text[:12]!r}")
    return problems


def test_new_diagrams() -> None:
    print("[5] 鱼骨图 / 时间轴 / 组织结构图")
    samples = {"fishbone": FISH_DOC, "timeline": TIME_DOC, "org": ORG_DOC}
    for kind, text in samples.items():
        document = parse_document(text, title="测试", diagram=kind)
        layout = build_diagram(document.root, kind)
        check(layout.kind == kind, f"{kind} 场景类型正确")
        check(len(layout.nodes) >= 8, f"{kind} 生成 {len(layout.nodes)} 个节点")
        check(len(layout.edges) >= 3, f"{kind} 生成 {len(layout.edges)} 条连线")
        check(layout.width > 200 and layout.height > 100, f"{kind} 画布尺寸合理")
        problems = _box_overlap(layout)
        check(not problems, f"{kind} 节点矩形不重叠" + (f"（{problems[:3]}）" if problems else ""))
        inside = all(
            -1 <= placed.box.left and placed.box.right <= layout.width + 1
            and -1 <= placed.box.top and placed.box.bottom <= layout.height + 1
            for placed in layout.nodes
        )
        check(inside, f"{kind} 所有节点都在画布内")
        edges_inside = all(
            -1 <= min(edge.points[0::2]) and max(edge.points[0::2]) <= layout.width + 1
            and -1 <= min(edge.points[1::2]) and max(edge.points[1::2]) <= layout.height + 1
            for edge in layout.edges
        )
        check(edges_inside, f"{kind} 连线端点不越界")


def test_exports(tmp_dir: str) -> None:
    print("[6] 四种图形的 PNG / SVG / HTML 导出")
    samples = {
        "mindmap": DOC,
        "fishbone": FISH_DOC,
        "timeline": TIME_DOC,
        "org": ORG_DOC,
    }
    for kind in DIAGRAM_KINDS:
        document = parse_document(samples[kind], title="导出测试", diagram=kind)
        layout = build_diagram(document.root, document.kind)
        png = render_png(layout, os.path.join(tmp_dir, f"{kind}.png"), LIGHT)
        svg = render_svg(layout, os.path.join(tmp_dir, f"{kind}.svg"), DARK)
        html_path = os.path.join(tmp_dir, f"{kind}.html")
        with open(html_path, "w", encoding="utf-8") as handle:
            handle.write(html_document(layout, LIGHT, title="导出测试"))
        for path in (png, svg, html_path):
            check(os.path.getsize(path) > 500, f"{os.path.basename(path)} 已生成且非空")
    transparent = render_png(
        build_diagram(parse_document(TIME_DOC, title="t").root, "timeline"),
        os.path.join(tmp_dir, "transparent.png"),
        LIGHT,
        transparent=True,
    )
    check(os.path.getsize(transparent) > 500, "透明背景 PNG 可导出")


def main() -> int:
    import tempfile

    test_document_structure()
    test_mermaid()
    test_mermaid_timeline()
    test_split_period()
    test_new_diagrams()
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_exports(tmp_dir)
    print("\n全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
