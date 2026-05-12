"""
cli.py — pip install 後的命令列入口

用法：
  clibrary "幫我把這個影片轉成 GIF"
  clibrary sync
  clibrary --list
"""

import argparse
import json
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="clibrary",
        description="CLIbrary router — 用自然語言找到並執行正確的 CLI 工具",
    )
    parser.add_argument("query", nargs="?", help="自然語言指令")
    parser.add_argument("--sync",   action="store_true", help="強制同步 manifests 索引")
    parser.add_argument("--list",   action="store_true", help="列出所有可用工具")
    parser.add_argument("--dry-run", action="store_true", help="只路由不執行")
    parser.add_argument("--json",   action="store_true", help="以 JSON 格式輸出")
    args = parser.parse_args()

    from router import execute, sync
    from router.downloader import sync_index
    from router.router import route

    if args.sync:
        count = sync(force=True)
        print(f"已同步 {count} 個工具")
        return

    if args.list:
        manifests = sync_index()
        for m in sorted(manifests, key=lambda x: x.get("name", "")):
            status = "✅" if m.get("status") == "available" else "📝"
            print(f"{status}  {m['name']:<25}  {m.get('description','')}")
        return

    if not args.query:
        parser.print_help()
        sys.exit(1)

    if args.dry_run:
        result = route(args.query)
    else:
        result = execute(args.query)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if result.get("action") == "clarify":
        print("不確定你要用哪個工具，請選擇：")
        for i, c in enumerate(result["choices"], 1):
            print(f"  {i}. {c['name']} — {c.get('description','')}")
        return

    if result.get("action") == "error":
        print(f"錯誤：{result['message']}", file=sys.stderr)
        sys.exit(1)

    # 正常輸出
    cache_icon = "💾" if result.get("cache_hit") else "⬇️ "
    print(f"{cache_icon} {result['cli']}  (信心 {result['confidence']:.2f}，{result['latency_ms']} ms)")
    if result.get("params"):
        print(f"參數：{json.dumps(result['params'], ensure_ascii=False)}")
    if result.get("output"):
        print(f"\n{result['output']}")
