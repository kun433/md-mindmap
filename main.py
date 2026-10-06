"""md-mindmap 入口：不带参数打开图形界面，带文件参数可直接命令行转换。"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional

from md_mindmap import __version__
from md_mindmap.exporter import export_all, render_png
from md_mindmap.layout import LayoutConfig, build_layout
from md_mindmap.parser import parse_markdown
from md_mindmap.theme import THEMES

FORMATS = ["png", "svg", "html"]


def _read_text(path: str) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gbk"):
        try:
            with open(path, "r", encoding=encoding) as handle:
                return handle.read()
        except UnicodeDecodeError:
            continue
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def convert(
    markdown_path: str,
    output: Optional[str] = None,
    formats: str = "png,svg,html",
    theme: str = "light",
    prefer_mermaid: bool = True,
    scale: int = 2,
) -> List[str]:
    """把 Markdown 文件转换成语义化图片，返回输出文件列表。"""
    text = _read_text(markdown_path)
    title = os.path.splitext(os.path.basename(markdown_path))[0]
    tree = parse_markdown(text, title=title, prefer_mermaid=prefer_mermaid)
    layout = build_layout(tree, LayoutConfig())
    selected = [item.strip().lower() for item in formats.split(",") if item.strip()]
    unknown = [item for item in selected if item not in FORMATS]
    if unknown:
        raise SystemExit(f"不支持的格式：{', '.join(unknown)}（可选 png / svg / html）")

    base = output or os.path.splitext(markdown_path)[0]
    if base.endswith(os.sep) or os.path.isdir(base):
        base = os.path.join(base, title)
    active_theme = THEMES.get(theme, THEMES["light"])

    outputs: List[str] = []
    for kind in selected:
        if kind == "png":
            outputs.append(render_png(layout, base + ".png", active_theme, scale=scale))
        else:
            outputs.extend(export_all(layout, base, active_theme, [kind], title=title))
    return outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="md-mindmap",
        description="把 Markdown 大纲转换成思维导图（PNG / SVG / HTML）。",
    )
    parser.add_argument("markdown", nargs="?", help="Markdown 文件路径；不带参数则打开图形界面")
    parser.add_argument("-o", "--output", help="输出文件前缀或目录，默认与源文件同名同目录")
    parser.add_argument("--formats", default="png,svg,html", help="导出格式，逗号分隔（png,svg,html）")
    parser.add_argument("--theme", default="light", choices=sorted(THEMES), help="配色主题")
    parser.add_argument("--scale", type=int, default=2, help="PNG 超采样倍数（1-4）")
    parser.add_argument("--document-structure", action="store_true", help="忽略 mermaid 代码块，按文档结构解析")
    parser.add_argument("--gui", action="store_true", help="强制打开图形界面")
    parser.add_argument("--selftest", action="store_true", help="打包自检：渲染并导出一次示例图")
    parser.add_argument("--version", action="version", version=f"md-mindmap {__version__}")
    return parser


def _ensure_streams() -> None:
    """无控制台模式下 sys.stdout/sys.stderr 为 None，防止 print 报错。"""
    for name in ("stdout", "stderr"):
        if getattr(sys, name, None) is None:
            try:
                setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
            except OSError:
                pass


def _attach_console() -> bool:
    """PyInstaller 打包为无控制台程序后，命令行模式把输出写回调用它的终端。"""
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return True
    try:
        import ctypes

        if not ctypes.windll.kernel32.AttachConsole(-1):
            return False
        sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1)  # noqa: SIM115
        sys.stderr = open("CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1)  # noqa: SIM115
        return True
    except Exception:
        return False


def _notify(message: str, title: str = "Markdown 思维导图") -> None:
    """没有控制台时（例如把 .md 拖到 exe 上）用弹窗告知结果。"""
    if os.environ.get("MDMINDMAP_NO_DIALOG"):
        print(message)
        return
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, title, 0x40)
            return
        except Exception:
            pass
    print(message)


def _selftest() -> int:
    """验证打包后的 exe 能创建窗口、渲染并导出图片。"""
    import tempfile

    import tkinter as tk

    from md_mindmap.app import MindMapApp

    root = tk.Tk()
    root.withdraw()
    try:
        app = MindMapApp(root)
        root.update_idletasks()
        root.update()
        app.refresh(fit=True)
        if app.layout is None:
            raise RuntimeError("布局为空")
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = os.path.join(tmp_dir, "selftest.png")
            render_png(app.layout, target, app.theme)
            size = os.path.getsize(target)
        message = (
            f"自检通过：{len(app.layout.nodes)} 个节点，"
            f"画布元素 {len(app.canvas.find_all())} 个，测试 PNG {size} 字节"
        )
        print(message)
        return 0
    except Exception as error:  # noqa: BLE001
        print(f"自检失败：{error}")
        return 1
    finally:
        root.destroy()


def main(argv: Optional[List[str]] = None) -> int:
    _ensure_streams()
    args = build_parser().parse_args(argv)

    if args.selftest:
        attached = _attach_console()
        code = _selftest()
        if not attached:
            _notify("自检通过" if code == 0 else "自检失败，请查看日志", "MdMindMap 自检")
        return code

    if args.gui or not args.markdown:
        from md_mindmap.app import launch

        launch(args.markdown)
        return 0

    attached = _attach_console()
    if not os.path.exists(args.markdown):
        print(f"找不到文件：{args.markdown}", file=sys.stderr)
        if not attached:
            _notify(f"找不到文件：\n{args.markdown}")
        return 2

    outputs = convert(
        args.markdown,
        output=args.output,
        formats=args.formats,
        theme=args.theme,
        prefer_mermaid=not args.document_structure,
        scale=args.scale,
    )
    summary = "\n".join(f"已生成 {path}" for path in outputs)
    if attached:
        print(summary)
    else:
        _notify(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
