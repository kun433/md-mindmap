"""解析与布局的纯逻辑测试：``python tests/test_core.py``。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:  # Windows 控制台默认 GBK，避免不可编码字符导致崩溃
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

from md_mindmap.exporter import html_document, render_png, render_svg
from md_mindmap.layout import build_layout
from md_mindmap.parser import parse_markdown
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


def test_export(tmp_dir: str) -> None:
    print("[3] 导出 PNG / SVG / HTML")
    tree = parse_markdown(DOC, title="导出测试")
    layout = build_layout(tree)
    png = render_png(layout, os.path.join(tmp_dir, "a.png"), LIGHT)
    svg = render_svg(layout, os.path.join(tmp_dir, "a.svg"), DARK)
    html_path = os.path.join(tmp_dir, "a.html")
    with open(html_path, "w", encoding="utf-8") as handle:
        handle.write(html_document(layout, LIGHT, title="导出测试"))
    for path in (png, svg, html_path):
        check(os.path.getsize(path) > 500, f"{os.path.basename(path)} 已生成且非空")


def main() -> int:
    import tempfile

    test_document_structure()
    test_mermaid()
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_export(tmp_dir)
    print("\n全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
