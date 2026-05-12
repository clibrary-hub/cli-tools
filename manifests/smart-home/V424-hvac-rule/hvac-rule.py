#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
hvac-rule — 空調規則器
解決問題：溫度與冷氣聯動
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

CONFIG_DIR = Path(__file__).parent / "config"
CONFIG_DIR.mkdir(exist_ok=True)

@dataclass
class HvacRuleConfig:
    """設定模型"""
    device_id: str
    name: str
    enabled: bool = True
    schedule: str = "* * * * *"
    last_run: str = ""
    
    def to_dict(self) -> dict:
        return asdict(self)

class HvacRuleCore:
    """
    核心邏輯類別。
    問題：溫度與冷氣聯動
    解法：透過設定管理與排程模擬實現自動化處理。
    """
    
    def __init__(self, config_file: Optional[Path] = None):
        self.config_file = config_file or (CONFIG_DIR / "hvac-rule.json")
        self.devices: List[Dict[str, Any]] = []
        self._load()
    
    def _load(self):
        if self.config_file.exists():
            self.devices = json.loads(self.config_file.read_text(encoding="utf-8"))
        else:
            self.devices = []
    
    def _save(self):
        self.config_file.write_text(json.dumps(self.devices, ensure_ascii=False, indent=2), encoding="utf-8")
    
    def register(self, device_id: str, name: str, **kwargs) -> dict:
        device = {
            "device_id": device_id,
            "name": name,
            "enabled": kwargs.get("enabled", True),
            "schedule": kwargs.get("schedule", "0 * * * *"),
            "last_run": "",
            "registered_at": datetime.now().isoformat()
        }
        self.devices.append(device)
        self._save()
        return {"status": "ok", "data": device, "message": f"已註冊 {name}"}
    
    def status(self) -> dict:
        return {"status": "ok", "data": self.devices, "count": len(self.devices)}
    
    def toggle(self, device_id: str) -> dict:
        for d in self.devices:
            if d.get("device_id") == device_id:
                d["enabled"] = not d.get("enabled", True)
                d["toggled_at"] = datetime.now().isoformat()
                self._save()
                state = "啟用" if d["enabled"] else "停用"
                return {"status": "ok", "data": d, "message": f"{device_id} 已{state}"}
        return {"status": "error", "message": f"找不到 {device_id}"}
    
    def run(self, device_id: Optional[str] = None) -> dict:
        targets = [d for d in self.devices if d.get("enabled")]
        if device_id:
            targets = [d for d in targets if d.get("device_id") == device_id]
        for d in targets:
            d["last_run"] = datetime.now().isoformat()
            d["last_result"] = "ok"
        self._save()
        return {"status": "ok", "data": targets, "message": f"已執行 {len(targets)} 個裝置"}
    
    def logs(self, device_id: Optional[str] = None) -> dict:
        logs = [d for d in self.devices if d.get("last_run")]
        if device_id:
            logs = [d for d in logs if d.get("device_id") == device_id]
        return {"status": "ok", "data": logs, "count": len(logs)}

@click.group()
@click.option("--verbose", "-v", is_flag=True)
@click.option("--config", type=click.Path(), help="設定檔路徑")
@click.pass_context
def cli(ctx, verbose, config):
    """空調規則器"""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["config"] = Path(config) if config else None

@cli.command()
@click.pass_context
@click.argument("device_id")
@click.argument("name")
@click.option("--enabled/--disabled", default=True, help="是否啟用")
@click.option("--schedule", default="0 * * * *", help="排程 (cron 格式)")
def register(ctx, device_id, name, enabled, schedule):
    """註冊裝置"""
    core = HvacRuleCore(ctx.obj.get("config"))
    result = core.register(device_id, name, enabled=enabled, schedule=schedule)
    console.print(Panel(f"[green]✓[/green] {result['message']}", title="空調規則器"))
    click.echo(json.dumps(result, ensure_ascii=False, indent=2))

@cli.command()
@click.pass_context
def status(ctx):
    """查看狀態"""
    core = HvacRuleCore(ctx.obj.get("config"))
    result = core.status()
    table = Table(title="空調規則器")
    table.add_column("裝置 ID", style="cyan")
    table.add_column("名稱", style="green")
    table.add_column("狀態", style="yellow")
    table.add_column("最後執行", style="dim")
    for d in result["data"]:
        state = "[green]●[/green]" if d.get("enabled") else "[red]○[/red]"
        table.add_row(d.get("device_id", ""), d.get("name", ""), state, d.get("last_run", "從未")[:19])
    console.print(table)
    click.echo(json.dumps(result, ensure_ascii=False, indent=2))

@cli.command()
@click.pass_context
@click.argument("device_id")
def toggle(ctx, device_id):
    """切換啟用狀態"""
    core = HvacRuleCore(ctx.obj.get("config"))
    result = core.toggle(device_id)
    console.print(Panel(f"[green]✓[/green] {result['message']}" if result["status"] == "ok" else f"[red]✗[/red] {result['message']}", title="切換"))
    click.echo(json.dumps(result, ensure_ascii=False, indent=2))

@cli.command()
@click.pass_context
@click.argument("device_id", required=False)
def run(ctx, device_id):
    """執行裝置任務"""
    core = HvacRuleCore(ctx.obj.get("config"))
    result = core.run(device_id)
    console.print(Panel(f"[green]✓[/green] {result['message']}", title="執行"))
    click.echo(json.dumps(result, ensure_ascii=False, indent=2))

@cli.command()
@click.pass_context
@click.argument("device_id", required=False)
def logs(ctx, device_id):
    """查看執行紀錄"""
    core = HvacRuleCore(ctx.obj.get("config"))
    result = core.logs(device_id)
    table = Table(title="執行紀錄")
    table.add_column("裝置", style="cyan")
    table.add_column("最後執行", style="dim")
    table.add_column("結果", style="green")
    for d in result["data"]:
        table.add_row(d.get("name", ""), d.get("last_run", "")[:19], d.get("last_result", "ok"))
    console.print(table)
    click.echo(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    cli()
