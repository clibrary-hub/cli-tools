"""
downloader.py — 從 clibrary-hub/manifests 同步索引，從 cli-tools 下載工具

兩個功能：
1. sync_index()    — 把 manifests repo 的所有 JSON 拉下來，存入本地索引
2. download_tool() — 根據 manifest 的 source 欄位，下載整個 CLI 目錄到快取
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import requests

from .cache import (
    INDEX_DIR, TOOLS_DIR,
    get_index, save_index, save_meta, tool_dir,
)

MANIFESTS_API = "https://api.github.com/repos/clibrary-hub/manifests/contents"
CATEGORIES    = ["media", "smart-home", "productivity", "calendar"]

# 把 GitHub tree URL 轉成 raw zip 下載
# https://github.com/clibrary-hub/cli-tools/tree/main/manifests/media/L241-video-download
# → https://api.github.com/repos/clibrary-hub/cli-tools/contents/manifests/media/L241-video-download
_TREE_RE = re.compile(
    r"https://github\.com/([^/]+/[^/]+)/tree/([^/]+)/(.+)"
)


def _gh_headers() -> dict:
    """加 GitHub token 可避免 rate limit（非必要）"""
    import os
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def sync_index(force: bool = False) -> list[dict]:
    """
    從 clibrary-hub/manifests 拉所有 manifest JSON，
    合併成一份本地索引 list[dict]。
    force=False 時若快取不超過 6 小時則跳過。
    """
    from .cache import index_age_seconds
    if not force and index_age_seconds() < 6 * 3600:
        return get_index()

    manifests: list[dict] = []
    for category in CATEGORIES:
        url = f"{MANIFESTS_API}/{category}"
        resp = requests.get(url, headers=_gh_headers(), timeout=10)
        if resp.status_code != 200:
            continue
        for item in resp.json():
            if not item["name"].endswith(".json"):
                continue
            raw = requests.get(item["download_url"], timeout=10)
            if raw.status_code == 200:
                try:
                    data = raw.json()
                    data["_category"] = category
                    manifests.append(data)
                except Exception:
                    pass

    if manifests:
        save_index(manifests)
    return manifests or get_index()


def download_tool(cli_name: str, source_url: str) -> Path:
    """
    把 source_url 指向的 GitHub 目錄整個下載到 ~/.clibrary/tools/<cli_name>/
    回傳工具目錄的 Path。
    """
    m = _TREE_RE.match(source_url)
    if not m:
        raise ValueError(f"無法解析 source URL: {source_url}")

    repo, branch, path = m.group(1), m.group(2), m.group(3)
    api_url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}"

    resp = requests.get(api_url, headers=_gh_headers(), timeout=10)
    resp.raise_for_status()

    dest = tool_dir(cli_name)
    dest.mkdir(parents=True, exist_ok=True)

    for item in resp.json():
        if item["type"] == "file" and not item["name"].startswith("."):
            raw = requests.get(item["download_url"], timeout=30)
            raw.raise_for_status()
            (dest / item["name"]).write_bytes(raw.content)

    save_meta(cli_name, source_url)
    _install_requirements(dest)
    return dest


def _install_requirements(tool_path: Path):
    req = tool_path / "requirements.txt"
    if req.exists():
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "-r", str(req)],
            check=True,
        )
