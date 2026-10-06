"""图形界面冒烟测试：构建窗口、渲染画布、导出后自动关闭。

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
from md_mindmap.exporter import render_png


def main() -> int:
    root = tk.Tk()
    root.withdraw()  # 冒烟测试不打扰用户桌面
    error: list[BaseException] = []
    try:
        app = MindMapApp(root)
        root.update_idletasks()
        root.update()
        app.refresh(fit=True)
        app.zoom(1.1)
        app.zoom(1 / 1.1)
        app.collapse_to_level_two()
        app.set_all_collapsed(False)
        app.set_theme("dark")
        app.set_theme("light")
        if app.layout is None:
            raise AssertionError("布局为空")
        placed = app.layout.nodes[1]
        app.canvas.event_generate("<ButtonPress-1>", x=0, y=0)
        root.update()
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = render_png(app.layout, os.path.join(tmp_dir, "smoke.png"), app.theme)
            size = os.path.getsize(path)
            print(f"画布节点数: {len(app.layout.nodes)}，导出 PNG: {size} 字节")
            if size < 500:
                raise AssertionError("导出 PNG 异常")
        print(f"画布元素数: {len(app.canvas.find_all())}")
        print(f"首个节点: {placed.node.text[:20]}")
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
