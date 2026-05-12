"""
execute.py — 完整執行流程

route() 找到 CLI → 本地快取檢查 → 需要時下載 → 執行 → 回傳結果

對外只暴露兩個函式：
  execute(query)  — 一句話搞定：路由 + 下載 + 執行
  sync()          — 手動強制同步 manifests 索引
"""

from __future__ import annotations

from .cache      import is_cached, tool_dir
from .downloader import download_tool, sync_index
from .router     import route
from .runner     import run


def sync(force: bool = True) -> int:
    """同步 manifests 索引，回傳取得的 manifest 數量"""
    manifests = sync_index(force=force)
    return len(manifests)


def execute(query: str, auto_download: bool = True) -> dict:
    """
    一句話執行：路由 → 快取檢查 → 下載 → 執行

    回傳：
      {
        "cli":        str,           # 命中的 CLI 名稱
        "params":     dict,          # 推斷的參數
        "output":     str,           # 執行結果
        "confidence": float,
        "source":     "A"|"B",       # A=example查表 B=Kimi API
        "cache_hit":  bool,          # 是否使用本地快取
        "latency_ms": float,
      }

    若需要澄清（信心分數過低），回傳：
      {"action": "clarify", "choices": [...]}
    """
    import time
    t0 = time.perf_counter()

    # 1. 路由
    result = route(query)
    if result.get("action") == "clarify":
        return result

    cli_name   = result["cli"]
    params     = result["params"]
    cli_meta   = result["cli_meta"]
    source_url = cli_meta.get("source", "")

    # 2. 本地快取檢查
    cache_hit = is_cached(cli_name)

    if not cache_hit:
        if not auto_download:
            return {
                "action":    "download_required",
                "cli":       cli_name,
                "source":    source_url,
                "message":   f"工具 {cli_name} 未在本地，請呼叫 execute() 並設定 auto_download=True",
            }
        if not source_url:
            return {
                "action":  "error",
                "cli":     cli_name,
                "message": f"工具 {cli_name} 尚無實作（status=spec）",
            }
        # 3. 下載
        download_tool(cli_name, source_url)

    # 4. 執行
    tool_path = tool_dir(cli_name)
    try:
        output = run(tool_path, cli_name, params)
    except Exception as e:
        output = f"[執行錯誤] {e}"

    total_ms = round((time.perf_counter() - t0) * 1000, 1)

    return {
        "cli":        cli_name,
        "params":     params,
        "output":     output,
        "confidence": result["confidence"],
        "source":     result["source"],
        "cache_hit":  cache_hit,
        "latency_ms": total_ms,
    }
