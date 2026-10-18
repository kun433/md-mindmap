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
            print(f"{kind}: {len(app.layout.nodes)} 个节点 / {len(app.layout.edges)} 条连线")

        app.zoom(1.1)
        app.zoom(1 / 1.1)
        app.collapse_to_level_two()
        app.set_all_collapsed(False)
        app.set_theme("dark")
        app.set_theme("light")
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
