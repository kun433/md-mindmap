"""字体解析：优先使用系统中文字体，保证中文导出不出现方框。"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Optional

from PIL import ImageFont

__all__ = ["resolve_font_path", "load_font", "tk_font_family"]

_WINDOWS_FONTS = [
    r"C:\Windows\Fonts\msyh.ttc",  # 微软雅黑
    r"C:\Windows\Fonts\msyh.ttf",
    r"C:\Windows\Fonts\msyhl.ttc",
    r"C:\Windows\Fonts\simhei.ttf",  # 黑体
    r"C:\Windows\Fonts\simsun.ttc",  # 宋体
    r"C:\Windows\Fonts\Deng.ttf",  # 等线
    r"C:\Windows\Fonts\arial.ttf",
]

_TK_CANDIDATES = ["Microsoft YaHei UI", "Microsoft YaHei", "微软雅黑", "SimHei", "SimSun"]


def _bundled_truetype() -> Optional[str]:
    try:
        from PIL import fonts  # type: ignore

        path = os.path.join(os.path.dirname(fonts.__file__), "DejaVuSans.ttf")
        if os.path.exists(path):
            return path
    except Exception:  # pragma: no cover - 仅作兜底
        pass
    return None


@lru_cache(maxsize=1)
def resolve_font_path() -> str:
    """返回可用的字体文件路径，找不到时回退到 Pillow 自带字体。"""
    for path in _WINDOWS_FONTS:
        if os.path.exists(path):
            return path
    bundled = _bundled_truetype()
    if bundled:
        return bundled
    return ""


@lru_cache(maxsize=64)
def load_font(size: int) -> ImageFont.FreeTypeFont:
    """按字号加载字体（带缓存）。"""
    size = max(6, int(size))
    path = resolve_font_path()
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:  # pragma: no cover
            pass
    try:  # pragma: no cover
        return ImageFont.load_default(size)
    except Exception:
        return ImageFont.load_default()


@lru_cache(maxsize=1)
def tk_font_family() -> str:
    """在 Tk 中挑选一个含有中文字形的字体族名。"""
    try:
        from tkinter import font as tkfont

        available = {name.lower() for name in tkfont.families()}
        for name in _TK_CANDIDATES:
            if name.lower() in available:
                return name
    except Exception:  # pragma: no cover - 无 Tk 环境时忽略
        pass
    return "TkDefaultFont"


def measure(text: str, size: int) -> float:
    """测量文本宽度（像素）。"""
    if not text:
        return 0.0
    return float(load_font(size).getlength(text))


def line_height(size: int, spacing: float = 1.45) -> float:
    return size * spacing


def font_names() -> List[str]:  # pragma: no cover - 调试辅助
    path = resolve_font_path()
    return [path] if path else []
