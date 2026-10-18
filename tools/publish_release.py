r"""把构建产物作为 GitHub Release 附件发布。

需要环境变量 ``GH_TOKEN``（具备 repo 权限的令牌），以及可选的 ``GH_REPO``、``GH_TAG``。

用法::

    set GH_TOKEN=ghp_xxx
    python tools/publish_release.py dist\MdMindMap.exe
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

API = "https://api.github.com"
UPLOADS = "https://uploads.github.com"
REPO = os.environ.get("GH_REPO", "kun433/md-mindmap")
TAG = os.environ.get("GH_TAG", "v1.1.1")
RELEASE_NAME = os.environ.get("GH_RELEASE_NAME", "Markdown 图形工坊 v1.1.1")
NOTES = os.environ.get(
    "GH_RELEASE_NOTES",
    "显示优化：修复节点文字被边框裁切的问题，深色模式覆盖整个界面，"
    "emoji 与缺字符号自动使用系统符号字体，勾选清单在导出图片里可区分 √ / □。",
)


def call(
    url: str,
    token: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    raw: Optional[bytes] = None,
    content_type: str = "application/json",
) -> Tuple[int, bytes]:
    data = raw if raw is not None else (json.dumps(payload).encode("utf-8") if payload else None)
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    request.add_header("User-Agent", "md-mindmap-release")
    if data is not None:
        request.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def find_release(token: str) -> Optional[Dict[str, Any]]:
    status, body = call(f"{API}/repos/{REPO}/releases/tags/{TAG}", token)
    if status == 200:
        return json.loads(body)
    return None


def ensure_release(token: str) -> Dict[str, Any]:
    existing = find_release(token)
    if existing:
        print(f"Release {TAG} 已存在：{existing['html_url']}")
        return existing
    status, body = call(
        f"{API}/repos/{REPO}/releases",
        token,
        method="POST",
        payload={
            "tag_name": TAG,
            "target_commitish": "main",
            "name": RELEASE_NAME,
            "body": NOTES,
            "draft": False,
            "prerelease": False,
        },
    )
    if status not in (200, 201):
        raise SystemExit(f"创建 Release 失败：HTTP {status} {body[:300].decode('utf-8', 'replace')}")
    release = json.loads(body)
    print(f"已创建 Release {TAG}：{release['html_url']}")
    return release


def upload_assets(token: str, release: Dict[str, Any], paths: list[str]) -> None:
    existing = {asset["name"] for asset in release.get("assets", [])}
    for path in paths:
        name = os.path.basename(path)
        if name in existing:
            print(f"附件已存在，跳过：{name}")
            continue
        with open(path, "rb") as handle:
            blob = handle.read()
        status, body = call(
            f"{UPLOADS}/repos/{REPO}/releases/{release['id']}/assets?name={name}",
            token,
            method="POST",
            raw=blob,
            content_type="application/octet-stream",
        )
        if status not in (200, 201):
            raise SystemExit(f"上传 {name} 失败：HTTP {status} {body[:300].decode('utf-8', 'replace')}")
        asset = json.loads(body)
        size_mb = asset["size"] / 1024 / 1024
        print(f"已上传 {name}（{size_mb:.1f} MB）→ {asset['browser_download_url']}")


def main() -> int:
    token = os.environ.get("GH_TOKEN")
    if not token:
        print("缺少 GH_TOKEN 环境变量", file=sys.stderr)
        return 2
    paths = sys.argv[1:]
    if not paths:
        print("用法：python tools/publish_release.py <文件…>", file=sys.stderr)
        return 2
    for path in paths:
        if not os.path.exists(path):
            print(f"找不到文件：{path}", file=sys.stderr)
            return 2
    release = ensure_release(token)
    upload_assets(token, release, paths)
    print(f"\n完成：{release['html_url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
