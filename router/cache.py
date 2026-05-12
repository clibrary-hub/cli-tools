"""
cache.py — 本地 CLI 快取管理

快取位置：~/.clibrary/tools/<cli-name>/
結構：
  ~/.clibrary/
    tools/
      video-download/
        video-download.py
        requirements.txt
        manifest.json
        .meta.json        ← 記錄來源 URL 和下載時間
    index/
      manifests.json      ← 從 clibrary-hub/manifests 同步的完整索引
      last_sync           ← 上次同步時間戳
"""

import json
import time
from pathlib import Path

CACHE_ROOT = Path.home() / ".clibrary"
TOOLS_DIR  = CACHE_ROOT / "tools"
INDEX_DIR  = CACHE_ROOT / "index"


def tool_dir(cli_name: str) -> Path:
    return TOOLS_DIR / cli_name


def is_cached(cli_name: str) -> bool:
    d = tool_dir(cli_name)
    return d.exists() and any(d.glob("*.py"))


def get_meta(cli_name: str) -> dict:
    meta_path = tool_dir(cli_name) / ".meta.json"
    if meta_path.exists():
        return json.loads(meta_path.read_text(encoding="utf-8"))
    return {}


def save_meta(cli_name: str, source_url: str):
    d = tool_dir(cli_name)
    d.mkdir(parents=True, exist_ok=True)
    meta = {"source": source_url, "downloaded_at": time.time()}
    (d / ".meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def get_index() -> list[dict]:
    index_path = INDEX_DIR / "manifests.json"
    if index_path.exists():
        return json.loads(index_path.read_text(encoding="utf-8"))
    return []


def save_index(manifests: list[dict]):
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    (INDEX_DIR / "manifests.json").write_text(
        json.dumps(manifests, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (INDEX_DIR / "last_sync").write_text(str(time.time()), encoding="utf-8")


def index_age_seconds() -> float:
    last_sync = INDEX_DIR / "last_sync"
    if not last_sync.exists():
        return float("inf")
    return time.time() - float(last_sync.read_text())
