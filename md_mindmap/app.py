"""Tkinter 图形界面：左侧编辑 Markdown，右侧实时查看思维导图。"""

from __future__ import annotations

import math
import os
import sys
import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, ttk
from typing import Dict, List, Optional

from . import __version__
from .exporter import export_all, html_document, render_png, render_svg
from .fonts import tk_font_family
from .layout import Layout, LayoutConfig, Placed, bezier_points, build_layout
from .parser import Node, parse_markdown
from .theme import DARK, LIGHT, THEMES, Theme

APP_NAME = "Markdown 思维导图"
SAMPLE_MD = """# 学习计划思维导图

## 目标
- 提升数学成绩
  - 每天完成 10 道计算题
  - 每周整理一次错题本
- 英语词汇量突破 3500
  - 每天背 30 个新词
  - 复习前一天内容

## 时间安排
- 早上 6:40 - 7:10 背单词
- 晚上 19:30 - 21:00 作业与复习
- 周末 2 小时自由阅读

## 检查方式
- [x] 每日打卡记录
- [ ] 周末自测
- [ ] 每月复盘一次
"""


def resource_path(relative: str) -> str:
    """兼容 PyInstaller 打包后的资源路径。"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, relative)


class MindMapApp:
    """主窗口。"""

    def __init__(
        self,
        root: tk.Tk,
        initial_path: Optional[str] = None,
        initial_text: Optional[str] = None,
    ) -> None:
        self.root = root
        self.md_path: Optional[str] = None
        self.layout: Optional[Layout] = None
        self.tree: Optional[Node] = None
        self.theme: Theme = LIGHT
        self.scale = 1.0
        self.offset_x = 40.0
        self.offset_y = 40.0
        self._drag_origin: Optional[tuple[int, int]] = None
        self._drag_moved = False
        self._node_fonts: Dict[int, "tkfont.Font"] = {}
        self._update_job: Optional[str] = None
        self._pending_render = True
        self.family = tk_font_family()

        root.title(f"{APP_NAME} v{__version__}")
        root.geometry("1280x800")
        root.minsize(900, 560)
        self._set_icon()
        self._build_style()
        self._build_menu()
        self._build_widgets()
        self._bind_events()

        text = initial_text if initial_text is not None else SAMPLE_MD
        self.editor.insert("1.0", text)
        if initial_path:
            self.load_file(initial_path)
        else:
            self.refresh(fit=True)

    # ------------------------------------------------------------------ #
    # 界面搭建
    # ------------------------------------------------------------------ #
    def _set_icon(self) -> None:
        icon = resource_path(os.path.join("assets", "icon.ico"))
        if os.path.exists(icon):
            try:
                self.root.iconbitmap(icon)
            except Exception:
                pass

    def _build_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background="#F6F6F3")
        style.configure("TButton", padding=(10, 6), font=(self.family, 10))
        style.configure("TCheckbutton", background="#F6F6F3", font=(self.family, 10))
        style.configure("TLabel", background="#F6F6F3", font=(self.family, 10))
        style.configure("Hint.TLabel", foreground="#6B7280", font=(self.family, 9))

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root, tearoff=0)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="打开 Markdown…", accelerator="Ctrl+O", command=self.open_file)
        file_menu.add_command(label="粘贴剪贴板内容", accelerator="Ctrl+V", command=self.paste_clipboard)
        file_menu.add_separator()
        file_menu.add_command(label="导出 PNG…", accelerator="Ctrl+S", command=lambda: self.export("png"))
        file_menu.add_command(label="导出 SVG…", command=lambda: self.export("svg"))
        file_menu.add_command(label="导出 HTML…", command=lambda: self.export("html"))
        file_menu.add_command(label="导出全部格式…", command=lambda: self.export("all"))
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.root.destroy)
        menubar.add_cascade(label="文件", menu=file_menu)

        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="适应窗口", accelerator="F", command=lambda: self.fit_view())
        view_menu.add_command(label="放大", accelerator="+", command=lambda: self.zoom(1.15))
        view_menu.add_command(label="缩小", accelerator="-", command=lambda: self.zoom(1 / 1.15))
        view_menu.add_separator()
        view_menu.add_command(label="浅色主题", command=lambda: self.set_theme("light"))
        view_menu.add_command(label="深色主题", command=lambda: self.set_theme("dark"))
        view_menu.add_separator()
        view_menu.add_command(label="侧栏显示/隐藏", accelerator="Ctrl+B", command=self.toggle_editor)
        menubar.add_cascade(label="视图", menu=view_menu)

        tree_menu = tk.Menu(menubar, tearoff=0)
        tree_menu.add_command(label="展开全部", accelerator="Ctrl+E", command=lambda: self.set_all_collapsed(False))
        tree_menu.add_command(label="折叠到二级", accelerator="Ctrl+W", command=self.collapse_to_level_two)
        menubar.add_cascade(label="节点", menu=tree_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="使用说明", command=self.show_help)
        help_menu.add_command(label="关于", command=self.show_about)
        menubar.add_cascade(label="帮助", menu=help_menu)

        self.root.config(menu=menubar)

    def _build_widgets(self) -> None:
        toolbar = ttk.Frame(self.root, padding=(12, 10, 12, 6))
        toolbar.pack(side="top", fill="x")

        ttk.Button(toolbar, text="打开 Markdown", command=self.open_file).pack(side="left")
        ttk.Button(toolbar, text="重新生成", command=lambda: self.refresh(fit=True)).pack(side="left", padx=6)
        ttk.Button(toolbar, text="适应窗口", command=lambda: self.fit_view()).pack(side="left")
        ttk.Label(toolbar, text="  ").pack(side="left")

        self.auto_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            toolbar, text="自动刷新", variable=self.auto_var, command=self._schedule_update
        ).pack(side="left")
        self.mermaid_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            toolbar, text="优先 mermaid", variable=self.mermaid_var, command=lambda: self.refresh(fit=True)
        ).pack(side="left", padx=8)

        ttk.Button(toolbar, text="导出", command=lambda: self.export("all")).pack(side="right")
        ttk.Button(toolbar, text="深色", command=self.toggle_theme).pack(side="right", padx=6)

        self.paned = ttk.PanedWindow(self.root, orient="horizontal")
        self.paned.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        self.editor_frame = ttk.Frame(self.paned)
        ttk.Label(self.editor_frame, text="Markdown 原文", style="Hint.TLabel").pack(anchor="w", pady=(0, 4))
        editor_wrap = ttk.Frame(self.editor_frame)
        editor_wrap.pack(fill="both", expand=True)
        self.editor = tk.Text(
            editor_wrap,
            wrap="none",
            undo=True,
            font=(self.family, 10),
            background="#FFFFFF",
            foreground="#1F2430",
            insertbackground="#002FA7",
            relief="flat",
            padx=10,
            pady=8,
        )
        editor_scroll = ttk.Scrollbar(editor_wrap, orient="vertical", command=self.editor.yview)
        self.editor.configure(yscrollcommand=editor_scroll.set)
        self.editor.pack(side="left", fill="both", expand=True)
        editor_scroll.pack(side="right", fill="y")
        self.paned.add(self.editor_frame, weight=1)

        canvas_frame = ttk.Frame(self.paned)
        self.canvas = tk.Canvas(
            canvas_frame,
            background=LIGHT.bg,
            highlightthickness=0,
            cursor="fleur",
        )
        self.canvas.pack(fill="both", expand=True)
        self.paned.add(canvas_frame, weight=3)

        status = ttk.Frame(self.root, padding=(12, 2, 12, 8))
        status.pack(side="bottom", fill="x")
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(status, textvariable=self.status_var, style="Hint.TLabel").pack(side="left")
        self.zoom_var = tk.StringVar(value="100%")
        ttk.Label(status, textvariable=self.zoom_var, style="Hint.TLabel").pack(side="right")

    def _bind_events(self) -> None:
        self.editor.bind("<<Modified>>", self._on_modified)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>", lambda e: self.zoom(1.12, e.x, e.y))
        self.canvas.bind("<Button-5>", lambda e: self.zoom(1 / 1.12, e.x, e.y))

        self.root.bind("<Control-o>", lambda e: self.open_file())
        self.root.bind("<Control-s>", lambda e: self.export("png"))
        self.root.bind("<Control-e>", lambda e: self.set_all_collapsed(False))
        self.root.bind("<Control-w>", lambda e: self.collapse_to_level_two())
        self.root.bind("<Control-b>", lambda e: self.toggle_editor())
        self.root.bind("<Control-v>", self._on_paste_shortcut)
        self.root.bind("<F5>", lambda e: self.refresh(fit=True))
        self.root.bind("f", self._key_fit)
        self.root.bind("<plus>", lambda e: self._key_zoom(1.15))
        self.root.bind("<equal>", lambda e: self._key_zoom(1.15))
        self.root.bind("<minus>", lambda e: self._key_zoom(1 / 1.15))

    def _editor_focused(self) -> bool:
        try:
            return self.root.focus_get() is self.editor
        except (KeyError, tk.TclError):
            return False

    def _key_fit(self, _event=None) -> None:
        if not self._editor_focused():
            self.fit_view()

    def _key_zoom(self, factor: float) -> None:
        if not self._editor_focused():
            self.zoom(factor)

    # ------------------------------------------------------------------ #
    # 数据流
    # ------------------------------------------------------------------ #
    def _on_modified(self, _event=None) -> None:
        if not self.editor.edit_modified():
            return
        self.editor.edit_modified(False)
        self._schedule_update()

    def _schedule_update(self) -> None:
        if self._update_job is not None:
            self.root.after_cancel(self._update_job)
        self._update_job = self.root.after(450, self._auto_refresh)

    def _auto_refresh(self) -> None:
        self._update_job = None
        if self.auto_var.get():
            self.refresh(fit=False)

    def current_title(self) -> str:
        if self.md_path:
            return os.path.splitext(os.path.basename(self.md_path))[0]
        first = self.editor.get("1.0", "2.0").strip().lstrip("#").strip()
        return first or "思维导图"

    def _parse(self) -> Node:
        text = self.editor.get("1.0", "end")
        return parse_markdown(text, title=self.current_title(), prefer_mermaid=self.mermaid_var.get())

    def refresh(self, fit: bool = False) -> None:
        """重新解析并重绘。"""
        tree = self._parse()
        self.tree = tree
        self.layout = build_layout(tree, LayoutConfig())
        if fit:
            self.fit_view(redraw=False)
        self.redraw()
        nodes = sum(1 for _ in tree.walk())
        label = os.path.basename(self.md_path) if self.md_path else "未保存文档"
        self.status_var.set(f"{label} · {nodes} 个节点 · 点击节点可折叠/展开")

    # ------------------------------------------------------------------ #
    # 绘制
    # ------------------------------------------------------------------ #
    def _font(self, size: int) -> "tkfont.Font":
        size = max(8, int(size))
        if size not in self._node_fonts:
            self._node_fonts[size] = tkfont.Font(family=self.family, size=size)
        return self._node_fonts[size]

    def _to_screen(self, x: float, y: float) -> tuple[float, float]:
        return x * self.scale + self.offset_x, y * self.scale + self.offset_y

    def set_theme(self, name: str) -> None:
        self.theme = THEMES.get(name, LIGHT)
        self.canvas.configure(background=self.theme.bg)
        self.redraw()

    def toggle_theme(self) -> None:
        self.set_theme("dark" if self.theme is LIGHT else "light")

    def redraw(self) -> None:
        self.canvas.delete("all")
        self.zoom_var.set(f"{self.scale * 100:.0f}%")
        if not self.layout:
            return

        for placed in self.layout.nodes:
            for child in placed.children:
                points = bezier_points(
                    placed.box.right, placed.box.center_y, child.box.left, child.box.center_y
                )
                screen: List[float] = []
                for index in range(0, len(points), 2):
                    sx, sy = self._to_screen(points[index], points[index + 1])
                    screen.extend((sx, sy))
                self.canvas.create_line(
                    *screen,
                    fill=self.theme.edge_color(child.accent, placed.depth),
                    width=max(1.0, (2.4 if placed.depth == 0 else 1.8) * self.scale),
                    smooth=False,
                    capstyle="round",
                )

        for placed in self.layout.nodes:
            self._draw_node(placed)

    def _draw_node(self, placed: Placed) -> None:
        box = placed.box
        fill, text_color, border, border_width = self.theme.node_style(placed.depth, placed.accent)
        x1, y1 = self._to_screen(box.left, box.top)
        x2, y2 = self._to_screen(box.right, box.bottom)
        radius = min((y2 - y1) / 2, max(3.0, (box.height / 2) * self.scale))
        tag = f"n{id(placed)}"

        if placed.depth <= 1:
            shadow = self.theme.root_shadow()
            self.canvas.create_polygon(
                self._rounded(x1 + 1.5, y1 + 2.5, x2 + 1.5, y2 + 3, radius),
                fill=shadow,
                outline="",
                tags=tag,
            )

        self.canvas.create_polygon(
            self._rounded(x1, y1, x2, y2, radius),
            fill=fill,
            outline=border if border_width > 0 else fill,
            width=max(1.0, border_width * self.scale),
            tags=tag,
        )

        font = self._font(box.font_size * self.scale)
        line_height = box.font_size * 1.42 * self.scale
        text_x = x1 + 15 * self.scale
        for index, line in enumerate(box.lines):
            if not line:
                continue
            center_y = y1 + 9 * self.scale + line_height * (index + 0.5)
            self.canvas.create_text(
                text_x,
                center_y,
                text=line,
                font=font,
                fill=text_color,
                anchor="w",
                tags=tag,
            )

        if placed.node.children and placed.node.collapsed:
            cx, cy = x2 + 11 * self.scale, (y1 + y2) / 2
            r = max(5.0, 7 * self.scale)
            self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=placed.accent, outline="", tags=tag)
            self.canvas.create_text(
                cx,
                cy,
                text=str(len(placed.node.children)),
                font=self._font(8 * self.scale),
                fill="#FFFFFF",
                tags=tag,
            )

    @staticmethod
    def _rounded(x1: float, y1: float, x2: float, y2: float, radius: float) -> List[float]:
        radius = max(0.0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
        if radius <= 0.5:
            return [x1, y1, x2, y1, x2, y2, x1, y2]
        points: List[float] = []
        corners = [
            (x1 + radius, y1 + radius, 180, 270),
            (x2 - radius, y1 + radius, 270, 360),
            (x2 - radius, y2 - radius, 0, 90),
            (x1 + radius, y2 - radius, 90, 180),
        ]
        for cx, cy, start, end in corners:
            for step in range(7):
                angle = (start + (end - start) * step / 6) * 3.141592653589793 / 180
                points.extend((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        return points

    # ------------------------------------------------------------------ #
    # 交互
    # ------------------------------------------------------------------ #
    def _on_canvas_configure(self, _event=None) -> None:
        if self.layout and self._pending_render:
            self._pending_render = False
            self.root.after_idle(self.fit_view)

    def _hit(self, x: float, y: float) -> Optional[Placed]:
        if not self.layout:
            return None
        lx = (x - self.offset_x) / self.scale
        ly = (y - self.offset_y) / self.scale
        return self.layout.hit_test(lx, ly)

    def _on_press(self, event) -> None:
        self._drag_origin = (event.x, event.y)
        self._drag_moved = False

    def _on_drag(self, event) -> None:
        if self._drag_origin is None:
            return
        dx = event.x - self._drag_origin[0]
        dy = event.y - self._drag_origin[1]
        if abs(dx) + abs(dy) > 3:
            self._drag_moved = True
        self.offset_x += dx
        self.offset_y += dy
        self._drag_origin = (event.x, event.y)
        self.redraw()

    def _on_release(self, event) -> None:
        if not self._drag_moved:
            placed = self._hit(event.x, event.y)
            if placed is not None and placed.node.children and self.tree is not None:
                placed.node.collapsed = not placed.node.collapsed
                self.layout = build_layout(self.tree, LayoutConfig())
                self.redraw()
        self._drag_origin = None

    def _on_wheel(self, event) -> None:
        factor = 1.12 if event.delta > 0 else 1 / 1.12
        self.zoom(factor, event.x, event.y)

    def _on_paste_shortcut(self, event) -> None:
        if event.widget is self.editor:
            return
        self.paste_clipboard()

    def zoom(self, factor: float, cx: Optional[float] = None, cy: Optional[float] = None) -> None:
        if not self.layout:
            return
        cx = self.canvas.winfo_width() / 2 if cx is None else cx
        cy = self.canvas.winfo_height() / 2 if cy is None else cy
        new_scale = max(0.08, min(6.0, self.scale * factor))
        ratio = new_scale / self.scale
        self.offset_x = cx - (cx - self.offset_x) * ratio
        self.offset_y = cy - (cy - self.offset_y) * ratio
        self.scale = new_scale
        self.redraw()

    def fit_view(self, redraw: bool = True) -> None:
        if not self.layout or self.layout.width <= 0:
            return
        view_w = max(200, self.canvas.winfo_width())
        view_h = max(200, self.canvas.winfo_height())
        scale = min((view_w - 48) / self.layout.width, (view_h - 48) / self.layout.height)
        self.scale = max(0.08, min(2.0, scale))
        self.offset_x = (view_w - self.layout.width * self.scale) / 2
        self.offset_y = max(20.0, (view_h - self.layout.height * self.scale) / 2)
        if redraw:
            self.redraw()

    def _rebuild_from_tree(self) -> bool:
        if self.tree is None:
            return False
        self.layout = build_layout(self.tree, LayoutConfig())
        self.redraw()
        return True

    def set_all_collapsed(self, collapsed: bool) -> None:
        if self.tree is None:
            self.refresh()
        if self.tree is None:
            return
        for depth, node in self.tree.walk():
            node.collapsed = collapsed and depth >= 1 and bool(node.children)
        if not collapsed:
            for _depth, node in self.tree.walk():
                node.collapsed = False
        self._rebuild_from_tree()

    def collapse_to_level_two(self) -> None:
        if self.tree is None:
            self.refresh()
        if self.tree is None:
            return
        for depth, node in self.tree.walk():
            node.collapsed = depth >= 2 and bool(node.children)
        self._rebuild_from_tree()

    # ------------------------------------------------------------------ #
    # 文件与导出
    # ------------------------------------------------------------------ #
    def open_file(self, path: Optional[str] = None) -> None:
        if not path:
            path = filedialog.askopenfilename(
                title="选择 Markdown 文件",
                filetypes=[
                    ("Markdown", "*.md *.markdown"),
                    ("文本文件", "*.txt"),
                    ("全部文件", "*.*"),
                ],
            )
        if not path:
            return
        self.load_file(path)

    def load_file(self, path: str) -> None:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                content = handle.read()
        except UnicodeDecodeError:
            with open(path, "r", encoding="gbk", errors="replace") as handle:
                content = handle.read()
        except OSError as error:
            messagebox.showerror(APP_NAME, f"无法打开文件：\n{error}")
            return
        self.md_path = path
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", content)
        self.editor.edit_modified(False)
        self.refresh(fit=True)
        self.status_var.set(f"{os.path.basename(path)} · 已加载")

    def paste_clipboard(self) -> None:
        try:
            content = self.root.clipboard_get()
        except tk.TclError:
            messagebox.showinfo(APP_NAME, "剪贴板里没有文本内容。")
            return
        self.md_path = None
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", content)
        self.refresh(fit=True)
        self.status_var.set("已从剪贴板导入内容")

    def toggle_editor(self) -> None:
        if self.editor_frame.winfo_ismapped():
            self.paned.forget(self.editor_frame)
        else:
            self.paned.insert(0, self.editor_frame, weight=1)

    def export(self, kind: str = "all") -> None:
        if not self.layout:
            return
        base = self.current_title()
        if kind == "all":
            target = filedialog.askdirectory(title="选择导出目录")
            if not target:
                return
            outputs = export_all(
                self.layout,
                os.path.join(target, base),
                self.theme,
                ["png", "svg", "html"],
                title=base,
            )
            self.status_var.set("已导出：" + "、".join(os.path.basename(p) for p in outputs))
            return

        extension = {"png": ".png", "svg": ".svg", "html": ".html"}[kind]
        path = filedialog.asksaveasfilename(
            title=f"导出 {kind.upper()}",
            defaultextension=extension,
            initialfile=base + extension,
            filetypes=[(kind.upper(), "*" + extension)],
        )
        if not path:
            return
        if kind == "png":
            render_png(self.layout, path, self.theme)
        elif kind == "svg":
            render_svg(self.layout, path, self.theme)
        else:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(html_document(self.layout, self.theme, title=base))
        self.status_var.set(f"已导出 {os.path.basename(path)}")

    # ------------------------------------------------------------------ #
    # 帮助
    # ------------------------------------------------------------------ #
    def show_help(self) -> None:
        messagebox.showinfo(
            "使用说明",
            "1. 左侧粘贴或打开 Markdown，右侧自动生成思维导图\n"
            "2. 点击有子节点的节点可以折叠 / 展开\n"
            "3. 滚轮缩放，按住左键拖拽平移，F 键适应窗口\n"
            "4. 文档里的 ```mermaid mindmap 代码块会被优先解析\n"
            "5. 首次导入会询问是否附加初始要点（可选）",
        )

    def show_about(self) -> None:
        messagebox.showinfo(
            "关于",
            f"{APP_NAME} v{__version__}\n\n"
            "把 Markdown 大纲转成可交互思维导图。\n"
            "支持标题、列表、引用、段落与 mermaid mindmap 语法，\n"
            "可导出 PNG / SVG / HTML。",
        )



def launch(path: Optional[str] = None) -> None:
    """启动图形界面。"""
    root = tk.Tk()
    try:
        root.call("tk", "scaling", 1.2)
    except tk.TclError:
        pass
    MindMapApp(root, initial_path=path)
    root.mainloop()
