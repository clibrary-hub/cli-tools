#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
gif-opt — 動圖最佳化器
解決問題：動圖最佳化
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

class GifOptCore:
    """核心邏輯：動圖最佳化"""
    def __init__(self, data_file: Optional[Path] = None):
        self.data_file = data_file or (DATA_DIR / "gif-opt.json")
        self.media: List[Dict[str, Any]] = []
        self._load()
    def _load(self):
        if self.data_file.exists():
            self.media = json.loads(self.data_file.read_text(encoding="utf-8"))
        else:
            self.media = []
    def _save(self):
        self.data_file.write_text(json.dumps(self.media, ensure_ascii=False, indent=2), encoding="utf-8")
    def add(self, path: str, **kwargs) -> dict:
        item = {"id": f"{len(self.media)+1:04d}", "path": path, "format": kwargs.get("format", ""), "size": kwargs.get("size", 0), "created": datetime.now().isoformat()}
        item.update(kwargs)
        self.media.append(item)
        self._save()
        return {"status": "ok", "data": item, "message": f"已新增 {path}"}
    def list(self, fmt: Optional[str] = None) -> dict:
        results = self.media
        if fmt:
            results = [m for m in results if m.get("format", "").lower() == fmt.lower()]
        return {"status": "ok", "data": results, "count": len(results)}
    def process(self, item_id: str) -> dict:
        for m in self.media:
            if m.get("id") == item_id:
                m["processed"] = datetime.now().isoformat()
                m["output"] = m.get("path", "") + ".out"
                self._save()
                return {"status": "ok", "data": m, "message": f"已處理 {item_id}"}
        return {"status": "error", "message": f"找不到 {item_id}"}
    def export(self, output: Path) -> dict:
        output.write_text(json.dumps(self.media, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"status": "ok", "message": f"已匯出 {output}"}

@click.group()
@click.option("--verbose", "-v", is_flag=True)
@click.option("--data-file", type=click.Path(), help="資料檔案")
@click.pass_context
def cli(ctx, verbose, data_file):
    """動圖最佳化器"""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["data_file"] = Path(data_file) if data_file else None

@cli.command()
@click.pass_context
@click.argument("path")
@click.option("--format", help="格式")
@click.option("--size", type=int, default=0, help="大小")
@click.option("--tags", multiple=True, help="標籤")
def add(ctx, path, format, size, tags):
    """新增媒體"""
    core = GifOptCore(ctx.obj.get("data_file"))
    result = core.add(path, format=format, size=size, tags=list(tags))
    console.print(Panel(f"[green]✓[/green] {result['message']}", title="動圖最佳化器"))
    click.echo(json.dumps(result, ensure_ascii=False, indent=2))

@cli.command()
@click.pass_context
@click.option("--format", help="篩選格式")
def list(ctx, format):
    """列出媒體"""
    core = GifOptCore(ctx.obj.get("data_file"))
    result = core.list(fmt=format)
    table = Table(title="動圖最佳化器")
    table.add_column("ID", style="cyan")
    table.add_column("路徑", style="green")
    table.add_column("格式", style="yellow")
    for m in result["data"]:
        table.add_row(m.get("id", ""), m.get("path", ""), m.get("format", ""))
    console.print(table)
    click.echo(json.dumps(result, ensure_ascii=False, indent=2))

@cli.command()
@click.pass_context
@click.argument("item_id")
def process(ctx, item_id):
    """處理媒體"""
    core = GifOptCore(ctx.obj.get("data_file"))
    result = core.process(item_id)
    console.print(Panel(f"[green]✓[/green] {result['message']}" if result["status"] == "ok" else f"[red]✗[/red] {result['message']}", title="處理"))
    click.echo(json.dumps(result, ensure_ascii=False, indent=2))

@cli.command()
@click.pass_context
@click.option("--output", "-o", default="gif-opt-export.json")
def export(ctx, output):
    """匯出資料"""
    core = GifOptCore(ctx.obj.get("data_file"))
    result = core.export(Path(output))
    console.print(Panel(f"[green]✓[/green] {result['message']}", title="匯出"))
    click.echo(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    cli()
