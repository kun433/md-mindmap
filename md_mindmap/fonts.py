"""字体解析：优先使用系统中文字体，保证中文导出不出现方框。"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Optional

from PIL import ImageFont

__all__ = [
    "fallback_font_paths",
    "text_runs",
    "load_font",
    "load_fallback_font",
    "resolve_font_path",
    "supports_char",
    "tk_font_family",
]

_WINDOWS_FONTS = [
    r"C:\Windows\Fonts\msyh.ttc",  # 微软雅黑
    r"C:\Windows\Fonts\msyh.ttf",
    r"C:\Windows\Fonts\msyhl.ttc",
    r"C:\Windows\Fonts\simhei.ttf",  # 黑体
    r"C:\Windows\Fonts\simsun.ttc",  # 宋体
    r"C:\Windows\Fonts\Deng.ttf",  # 等线
    r"C:\Windows\Fonts\arial.ttf",
]

_WINDOWS_BOLD_FONTS = [
    r"C:\Windows\Fonts\msyhbd.ttc",  # 微软雅黑 Bold
    r"C:\Windows\Fonts\simhei.ttf",  # 黑体（本身较粗）
]

_TK_CANDIDATES = ["Microsoft YaHei UI", "Microsoft YaHei", "微软雅黑", "SimHei", "SimSun"]

# 中文字体缺少的符号 / emoji 由这些字体兜底（顺序即优先级）
_FALLBACK_FONTS = [
    r"C:\Windows\Fonts\seguisym.ttf",  # Segoe UI Symbol：符号兜底
    r"C:\Windows\Fonts\seguiemj.ttf",  # Segoe UI Emoji：彩色 emoji
    r"C:\Windows\Fonts\arial.ttf",
]


def _bundled_truetype() -> Optional[str]:
    try:
        from PIL import fonts  # type: ignore

        path = os.path.join(os.path.dirname(fonts.__file__), "DejaVuSans.ttf")
        if os.path.exists(path):
            return path
    except Exception:  # pragma: no cover - 仅作兜底
        pass
    return None


@lru_cache(maxsize=2)
def resolve_font_path(bold: bool = False) -> str:
    """返回可用的字体文件路径，找不到时回退到 Pillow 自带字体。"""
    candidates = _WINDOWS_BOLD_FONTS if bold else []
    for path in candidates + _WINDOWS_FONTS:
        if os.path.exists(path):
            return path
    bundled = _bundled_truetype()
    if bundled:
        return bundled
    return ""


@lru_cache(maxsize=128)
def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """按字号加载字体（带缓存），bold 为真时优先使用粗体字形。"""
    size = max(6, int(size))
    path = resolve_font_path(bold)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:  # pragma: no cover
            pass
    try:  # pragma: no cover
        return ImageFont.load_default(size)
    except Exception:
        return ImageFont.load_default()


def text_runs(text: str, size: int, bold: bool = False):
    """把一行文本拆成 ``(片段, 字体)`` 序列：中文字体缺字时用兜底字体。

    微软雅黑没有 ☑ ✓ ⚠ 😀 这类符号的字形，直接绘制会变成方块；
    这里按字符拆成多个片段，交给 Segoe UI Symbol / Emoji 渲染。
    """
    primary = load_font(size, bold)
    runs = []
    buffer = ""
    current = primary
    for char in text:
        font = _char_font(char, size, bold)
        if font is not current and buffer:
            runs.append((buffer, current))
            buffer = ""
        current = font
        buffer += char
    if buffer:
        runs.append((buffer, current))
    return runs or [(text, primary)]


@lru_cache(maxsize=8192)
def _char_font(char: str, size: int, bold: bool):
    """为单个字符挑选字体：主字体有字形就用主字体，否则用第一个支持的兜底字体。"""
    if char.isspace() or supports_char(char):
        return load_font(size, bold)
    for index in range(len(fallback_font_paths())):
        font = load_fallback_font(size, index)
        if font is not None and _font_supports(font.path, char):
            return font
    return load_font(size, bold)


@lru_cache(maxsize=4096)
def _font_supports(path: str, char: str) -> bool:
    try:
        font = ImageFont.truetype(path, 24)
        mask = font.getmask(char)
        if mask.size[0] == 0 or mask.size[1] == 0:
            return False
        reference = font.getmask(chr(0xFFFF))
        return not (mask.size == reference.size and bytes(mask) == bytes(reference))
    except Exception:  # pragma: no cover
        return False


def run_width(text: str, size: int, bold: bool = False) -> float:
    """按兜底规则测量一行文本的像素宽度。"""
    return sum(font.getlength(chunk) for chunk, font in text_runs(text, size, bold))


@lru_cache(maxsize=4096)
def fallback_char_count(text: str) -> int:
    """统计需要兜底字体的字符个数（emoji、中文字体缺字的符号）。"""
    return sum(1 for char in text if not char.isspace() and not supports_char(char))


@lru_cache(maxsize=1)
def fallback_font_paths() -> tuple:
    """返回可用的兜底字体路径（符号 / emoji）。"""
    return tuple(path for path in _FALLBACK_FONTS if os.path.exists(path))


@lru_cache(maxsize=256)
def load_fallback_font(size: int, index: int = 0):
    """加载兜底字体（index 指定候选顺序，越界时返回 None）。"""
    size = max(6, int(size))
    paths = fallback_font_paths()
    if not paths:
        return None
    path = paths[min(index, len(paths) - 1)]
    try:
        return ImageFont.truetype(path, size)
    except Exception:  # pragma: no cover
        return None


@lru_cache(maxsize=4096)
def supports_char(char: str) -> bool:
    """判断主字体是否有该字符的字形（缺字时 Pillow 会画成方块）。"""
    if not char or char.isspace():
        return True
    font = load_font(24)
    try:
        mask = font.getmask(char)
        if mask.size[0] == 0 or mask.size[1] == 0:
            return False
        reference = font.getmask(chr(0xFFFF))
        return not (mask.size == reference.size and bytes(mask) == bytes(reference))
    except Exception:  # pragma: no cover
        return True


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
