"""一键构建 Windows 单文件 exe。

用法::

    python build.py            # 生成图标 -> 跑测试 -> 打包 exe
    python build.py --skip-test
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
APP_NAME = "MdMindMap"


def run(command: list[str]) -> None:
    print("$", " ".join(command), flush=True)
    subprocess.run(command, cwd=BASE, check=True)


def ensure_icon() -> None:
    if not os.path.exists(os.path.join(BASE, "assets", "icon.ico")):
        run([sys.executable, os.path.join("tools", "make_icon.py")])


def build() -> str:
    separator = ";" if os.name == "nt" else ":"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        APP_NAME,
        "--icon",
        os.path.join("assets", "icon.ico"),
        "--add-data",
        f"assets{separator}assets",
        "--version-file",
        os.path.join("tools", "version_info.txt"),
        "--exclude-module",
        "pytest",
        "--exclude-module",
        "numpy",
        "--exclude-module",
        "setuptools",
        "main.py",
    ]
    run(command)
    exe = os.path.join(BASE, "dist", APP_NAME + (".exe" if os.name == "nt" else ""))
    if not os.path.exists(exe):
        raise SystemExit("打包失败：未找到输出文件")
    size = os.path.getsize(exe) / 1024 / 1024
    print(f"\n构建完成：{exe}（{size:.1f} MB）")
    return exe


def main() -> int:
    ensure_icon()
    if "--skip-test" not in sys.argv:
        run([sys.executable, os.path.join("tests", "test_core.py")])
    exe = build()

    preview_dir = os.path.join(BASE, "docs")
    os.makedirs(preview_dir, exist_ok=True)
    sample = os.path.join(BASE, "samples", "示例-项目发布计划.md")
    if os.path.exists(sample):
        run(
            [
                sys.executable,
                "main.py",
                sample,
                "--formats",
                "png",
                "-o",
                os.path.join(preview_dir, "preview"),
            ]
        )
    print(f"预览图：{os.path.join(preview_dir, 'preview.png')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
