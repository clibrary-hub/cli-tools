#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
img-shrink — 圖片批壓器
解決問題：圖片批量壓縮
"""

import json
import sys
from pathlib import Path
from typing import Optional, List
import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import track

console = Console()

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}


def check_pillow() -> bool:
    try:
        from PIL import Image  # noqa
        return True
    except ImportError:
        console.print(
            "[red]Error:[/red] Pillow not installed.\n"
            "  pip install Pillow"
        )
        return False


def shrink_image(
    input_file: Path,
    output_file: Path,
    quality: int = 85,
    max_width: Optional[int] = None,
    max_height: Optional[int] = None,
    convert_to: Optional[str] = None,
) -> dict:
    """Compress/resize an image using Pillow."""
    from PIL import Image

    try:
        img = Image.open(input_file)
        original_size = input_file.stat().st_size

        # Convert mode if needed for JPEG
        target_ext = (convert_to or output_file.suffix.lstrip(".")).lower()
        if target_ext in ("jpg", "jpeg") and img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")

        # Resize if needed
        w, h = img.size
        if max_width or max_height:
            mw = max_width or w
            mh = max_height or h
            if w > mw or h > mh:
                img.thumbnail((mw, mh), Image.LANCZOS)

        # Determine output path
        if convert_to:
            output_file = output_file.with_suffix("." + convert_to.lstrip("."))

        save_kwargs: dict = {}
        ext = output_file.suffix.lower()
        if ext in (".jpg", ".jpeg"):
            save_kwargs = {"quality": quality, "optimize": True}
        elif ext == ".png":
            save_kwargs = {"optimize": True, "compress_level": min(9, int((100 - quality) / 11))}
        elif ext == ".webp":
            save_kwargs = {"quality": quality, "method": 6}

        output_file.parent.mkdir(parents=True, exist_ok=True)
        img.save(output_file, **save_kwargs)

        new_size = output_file.stat().st_size
        reduction = round((1 - new_size / original_size) * 100, 1) if original_size > 0 else 0
        return {
            "status": "ok",
            "output": str(output_file),
            "original_kb": original_size // 1024,
            "output_kb": new_size // 1024,
            "reduction_pct": reduction,
            "dimensions": f"{img.size[0]}x{img.size[1]}",
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


@click.group()
@click.option("--verbose", "-v", is_flag=True)
@click.pass_context
def cli(ctx, verbose):
    """圖片批壓器 — batch compress images using Pillow."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


@cli.command()
@click.option("--input-file", "-i", help="Input image file")
@click.option("--input-dir", help="Input directory (batch mode)")
@click.option("--output-file", "-o", help="Output file")
@click.option("--output-dir", help="Output directory")
@click.option("--quality", "-q", default=85, show_default=True,
              type=click.IntRange(1, 100), help="Compression quality (1-100)")
@click.option("--max-width", default=None, type=int, help="Maximum output width")
@click.option("--max-height", default=None, type=int, help="Maximum output height")
@click.option("--convert-to", default=None, help="Convert to format: jpg, png, webp")
@click.option("--dry-run", is_flag=True, help="Show what would be done")
@click.pass_context
def run(ctx, input_file, input_dir, output_file, output_dir, quality, max_width, max_height, convert_to, dry_run):
    """Compress image(s) with optional resize and format conversion."""
    if not check_pillow():
        sys.exit(1)

    results = []

    if input_dir:
        src_dir = Path(input_dir)
        dst_dir = Path(output_dir) if output_dir else src_dir / "shrunk"
        if not dry_run:
            dst_dir.mkdir(parents=True, exist_ok=True)
        imgs = [f for f in src_dir.iterdir() if f.suffix.lower() in IMAGE_EXTS]
        if not imgs:
            console.print(f"[yellow]No images found in {src_dir}[/yellow]")
            sys.exit(0)
        for img in track(imgs, description="Shrinking..."):
            out = dst_dir / img.name
            if dry_run:
                results.append({"input": str(img), "output": str(out), "dry_run": True})
            else:
                res = shrink_image(img, out, quality, max_width, max_height, convert_to)
                results.append({"input": str(img), **res})

    elif input_file:
        src = Path(input_file)
        if not src.exists():
            console.print(f"[red]File not found:[/red] {src}")
            sys.exit(1)
        out = Path(output_file) if output_file else src.parent / (src.stem + "_shrunk" + src.suffix)
        if dry_run:
            results.append({"input": str(src), "output": str(out), "dry_run": True})
        else:
            res = shrink_image(src, out, quality, max_width, max_height, convert_to)
            results.append({"input": str(src), **res})
            if res["status"] == "ok":
                console.print(Panel(
                    f"[green]Done![/green]  {res['original_kb']} KB → {res['output_kb']} KB  "
                    f"([cyan]-{res['reduction_pct']}%[/cyan])",
                    title="img-shrink"
                ))
    else:
        console.print("[red]Error:[/red] Provide --input-file or --input-dir")
        sys.exit(1)

    click.echo(json.dumps({"status": "ok", "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
