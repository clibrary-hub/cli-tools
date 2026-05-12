"""
runner.py — 執行已快取的 CLI 工具

流程：
  1. 找到工具目錄裡的 .py 主程式
  2. 把 params dict 轉成 CLI 參數
  3. subprocess 執行，回傳 stdout
"""

import json
import subprocess
import sys
from pathlib import Path


def _params_to_args(params: dict) -> list[str]:
    """把 {'input_file': 'a.mp4', 'quality': '1080p'} 轉成 ['--input-file', 'a.mp4', '--quality', '1080p']"""
    args = []
    for key, val in params.items():
        if key == "action":
            continue
        flag = "--" + key.replace("_", "-")
        if isinstance(val, bool):
            if val:
                args.append(flag)
        elif val is not None:
            args.extend([flag, str(val)])
    return args


def run(tool_dir: Path, cli_name: str, params: dict, timeout: int = 60) -> str:
    """
    執行工具，回傳 stdout 字串。
    找尋順序：<cli-name>.py → main.py → 目錄內唯一的 .py
    """
    candidates = [
        tool_dir / f"{cli_name}.py",
        tool_dir / "main.py",
    ]
    script = next((p for p in candidates if p.exists()), None)
    if script is None:
        py_files = [p for p in tool_dir.glob("*.py") if not p.name.startswith("_")]
        if not py_files:
            raise FileNotFoundError(f"找不到 {cli_name} 的執行腳本")
        script = py_files[0]

    action = params.get("action", "run")
    extra  = _params_to_args(params)
    cmd    = [sys.executable, str(script), action] + extra

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if result.returncode != 0:
        raise RuntimeError(f"{cli_name} 執行失敗：\n{result.stderr.strip()}")

    return result.stdout.strip()
