"""图形界面冒烟测试：构建窗口、切换四种图形、导出后自动关闭。

运行：``python tests/smoke_gui.py``（窗口会短暂出现，用于验证界面不报错）。
"""

from __future__ import annotations

import os
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:  # Windows 控制台默认 GBK，避免不可编码字符导致崩溃
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

import tkinter as tk

from md_mindmap.app import MindMapApp
from md_mindmap.diagrams import DIAGRAM_KINDS
from md_mindmap.exporter import render_png
from md_mindmap.templates import template_for

# 覆盖缺字符号（emoji、⚠）与勾选清单，验证不会出现方块或文字溢出
SYMBOL_DOC = """# 📌 项目进展 ⚠

## 第一阶段
- [x] 需求确认
- [ ] 风险登记
  - 依赖第三方接口
- ⚠ 供应商排期未确认

## 第二阶段
- 灰度发布 😀
- 数据看板 → 上线
"""



def check_text_fit(app: MindMapApp) -> None:
    """校验 Tk 实际渲染的文字宽度没有超出节点框（防止文字被裁切）。"""
    scale = app.scale
    app.scale = 1.0
    try:
        for placed in app.layout.nodes:
            if placed.shape == "dot":
                continue
            bold = placed.shape == "box" and placed.depth == 0
            font = app._font(placed.box.font_size, bold=bold)
            limit = placed.box.width - 2 * placed.box.pad_x
            for line in placed.box.lines:
                if not line:
                    continue
                width = font.measure(line)
                if width > limit + 0.5:
                    raise AssertionError(
                        f"文字溢出节点框：{line[:20]!r} 需要 {width:.1f}px，可用 {limit:.1f}px"
                    )
    finally:
        app.scale = scale


def main() -> int:
    root = tk.Tk()
    root.withdraw()  # 冒烟测试不打扰用户桌面
    error: list[BaseException] = []
    try:
        app = MindMapApp(root)
        root.update_idletasks()
        root.update()
        app.refresh(fit=True)

        for kind in DIAGRAM_KINDS:
            _title, text = template_for(kind)
            app.editor.delete("1.0", "end")
            app.editor.insert("1.0", text)
            app.set_diagram(kind)
            root.update()
            if app.kind != kind:
                raise AssertionError(f"切换到 {kind} 后场景类型是 {app.kind}")
            if app.layout is None or not app.layout.nodes:
                raise AssertionError(f"{kind} 布局为空")
            check_text_fit(app)
            print(f"{kind}: {len(app.layout.nodes)} 个节点 / {len(app.layout.edges)} 条连线，文字未溢出")

        app.editor.delete("1.0", "end")
        app.editor.insert("1.0", SYMBOL_DOC)
        app.set_diagram("mindmap")
        root.update()
        check_text_fit(app)
        print(f"符号与 emoji：{len(app.layout.nodes)} 个节点，文字未溢出")

        app.zoom(1.1)
        app.zoom(1 / 1.1)
        app.collapse_to_level_two()
        app.set_all_collapsed(False)
        app.set_theme("dark")
        check_text_fit(app)
        app.set_theme("light")
        check_text_fit(app)
        app.load_template_cycle()
        app.canvas.event_generate("<ButtonPress-1>", x=0, y=0)
        root.update()

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = render_png(app.layout, os.path.join(tmp_dir, "smoke.png"), app.theme)
            size = os.path.getsize(path)
            print(f"画布节点数: {len(app.layout.nodes)}，导出 PNG: {size} 字节")
            if size < 500:
                raise AssertionError("导出 PNG 异常")
        print(f"画布元素数: {len(app.canvas.find_all())}")
        print(f"当前图形: {app.kind} · {app.status_var.get()}")
    except BaseException as exc:  # noqa: BLE001
        error.append(exc)
        traceback.print_exc()
    finally:
        root.destroy()

    if error:
        print("\n界面冒烟测试失败 ❌")
        return 1
    print("\n界面冒烟测试通过 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
