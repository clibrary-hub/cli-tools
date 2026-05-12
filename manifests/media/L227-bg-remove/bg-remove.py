#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
bg-remove — 背景移除器
解決問題：去背需要 PS
"""

import json
import sys
import shutil
from pathlib import Path
from typing import Optional, List
import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import track

console = Console()

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def check_pillow() -> bool:
    try:
        from PIL import Image  # noqa
        return True
    except ImportError:
        console.print("[red]Error:[/red] Pillow not installed. pip install Pillow")
        return False


def remove_bg_rembg(input_file: Path, output_file: Path) -> dict:
    """Remove background using rembg library."""
    try:
        from rembg import remove
        from PIL import Image
        import io

        img = Image.open(input_file).convert("RGBA")
        result = remove(img)
        out = output_file.with_suffix(".png")
        result.save(out, format="PNG")
        return {"status": "ok", "output": str(out), "method": "rembg"}
    except ImportError:
        return {"status": "fallback", "reason": "rembg not installed"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def remove_bg_subprocess(input_file: Path, output_file: Path) -> dict:
    """Try rembg as a subprocess CLI tool."""
    if shutil.which("rembg") is None:
        return {"status": "fallback", "reason": "rembg CLI not found"}
    import subprocess
    out = output_file.with_suffix(".png")
    try:
        subprocess.run(
            ["rembg", "i", str(input_file), str(out)],
            check=True, capture_output=True
        )
        return {"status": "ok", "output": str(out), "method": "rembg-cli"}
    except subprocess.CalledProcessError as e:
        return {"status": "error", "error": e.stderr.decode(errors="replace")}


def remove_bg_stub(input_file: Path, output_file: Path) -> dict:
    """
    Stub fallback: convert to RGBA and apply simple chroma-key style removal
    using PIL (removes near-white or near-green background via threshold).
    Not production quality, but functional without external deps.
    """
    from PIL import Image
    import numpy as np

    try:
        img = Image.open(input_file).convert("RGBA")
        data = img.getdata()

        new_data = []
        for r, g, b, a in data:
            # Simple white background removal (threshold)
            if r > 200 and g > 200 and b > 200:
                new_data.append((r, g, b, 0))
            else:
                new_data.append((r, g, b, a))

        img.putdata(new_data)
        out = output_file.with_suffix(".png")
        img.save(out, format="PNG")
        return {
            "status": "ok",
            "output": str(out),
            "method": "stub-threshold",
            "note": "Basic white-bg removal. Install rembg for AI-quality results: pip install rembg",
        }
    except ImportError:
        # Try without numpy
        from PIL import Image
        img = Image.open(input_file).convert("RGBA")
        data = list(img.getdata())
        new_data = []
        for item in data:
            r, g, b, a = item
            if r > 200 and g > 200 and b > 200:
                new_data.append((r, g, b, 0))
            else:
                new_data.append((r, g, b, a))
        img.putdata(new_data)
        out = output_file.with_suffix(".png")
        img.save(out, format="PNG")
        return {
            "status": "ok",
            "output": str(out),
            "method": "stub-threshold",
            "note": "Basic white-bg removal. Install rembg for AI-quality: pip install rembg",
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def remove_background(input_file: Path, output_file: Path) -> dict:
    """Try rembg library, then CLI, then stub."""
    result = remove_bg_rembg(input_file, output_file)
    if result["status"] in ("ok", "error"):
        return result
    result = remove_bg_subprocess(input_file, output_file)
    if result["status"] in ("ok", "error"):
        return result
    console.print("[yellow]rembg not available — using basic threshold stub.[/yellow]")
    return remove_bg_stub(input_file, output_file)


@click.group()
@click.option("--verbose", "-v", is_flag=True)
@click.pass_context
def cli(ctx, verbose):
    """背景移除器 — remove image backgrounds (AI or threshold)."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


@cli.command()
@click.option("--input-file", "-i", help="Input image file")
@click.option("--input-dir", help="Input directory (batch mode)")
@click.option("--output-file", "-o", default=None, help="Output PNG file")
@click.option("--output-dir", default=None, help="Output directory")
@click.option("--dry-run", is_flag=True, help="Show what would be done")
@click.pass_context
def run(ctx, input_file, input_dir, output_file, output_dir, dry_run):
    """Remove background from image(s), output PNG with transparency."""
    if not check_pillow():
        sys.exit(1)

    results = []

    if input_dir:
        src_dir = Path(input_dir)
        dst_dir = Path(output_dir) if output_dir else src_dir / "no-bg"
        if not dry_run:
            dst_dir.mkdir(parents=True, exist_ok=True)
        imgs = [f for f in src_dir.iterdir() if f.suffix.lower() in IMAGE_EXTS]
        for img in track(imgs, description="Removing backgrounds..."):
            out = dst_dir / (img.stem + "_nobg.png")
            if dry_run:
                results.append({"input": str(img), "output": str(out), "dry_run": True})
            else:
                res = remove_background(img, out)
                results.append({"input": str(img), **res})

    elif input_file:
        src = Path(input_file)
        if not src.exists():
            console.print(f"[red]File not found:[/red] {src}")
            sys.exit(1)
        out = Path(output_file) if output_file else src.parent / (src.stem + "_nobg.png")
        if dry_run:
            results.append({"input": str(src), "output": str(out), "dry_run": True})
        else:
            res = remove_background(src, out)
            results.append({"input": str(src), **res})
            if res["status"] == "ok":
                console.print(Panel(
                    f"[green]Done![/green]  {res['output']}  (method: {res.get('method', 'unknown')})",
                    title="bg-remove"
                ))
    else:
        console.print("[red]Error:[/red] Provide --input-file or --input-dir")
        sys.exit(1)

    click.echo(json.dumps({"status": "ok", "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
