#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
img-transcode — 圖片格式轉換
解決問題：圖片格式轉換繁瑣
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

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif", ".gif", ".avif"}

FORMAT_ALIASES = {
    "jpg": "JPEG",
    "jpeg": "JPEG",
    "png": "PNG",
    "webp": "WEBP",
    "bmp": "BMP",
    "tiff": "TIFF",
    "tif": "TIFF",
    "gif": "GIF",
}


def check_pillow() -> bool:
    try:
        from PIL import Image  # noqa
        return True
    except ImportError:
        console.print("[red]Error:[/red] Pillow not installed. pip install Pillow")
        return False


def transcode_image(
    input_file: Path,
    output_file: Path,
    target_format: str,
    quality: int = 90,
    keep_exif: bool = False,
) -> dict:
    """Convert image to target format using Pillow."""
    from PIL import Image
    import io

    try:
        img = Image.open(input_file)
        fmt = FORMAT_ALIASES.get(target_format.lower(), target_format.upper())

        # Handle mode conversion
        if fmt == "JPEG" and img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        elif fmt == "PNG" and img.mode not in ("RGB", "RGBA", "L", "LA", "P"):
            img = img.convert("RGBA")

        save_kwargs: dict = {}
        if fmt == "JPEG":
            save_kwargs = {"quality": quality, "optimize": True}
            if keep_exif and hasattr(img, "info") and "exif" in img.info:
                save_kwargs["exif"] = img.info["exif"]
        elif fmt == "WEBP":
            save_kwargs = {"quality": quality, "method": 6}
        elif fmt == "PNG":
            save_kwargs = {"optimize": True}

        output_file.parent.mkdir(parents=True, exist_ok=True)
        img.save(output_file, format=fmt, **save_kwargs)

        original_kb = input_file.stat().st_size // 1024
        output_kb = output_file.stat().st_size // 1024
        return {
            "status": "ok",
            "output": str(output_file),
            "format": fmt,
            "original_kb": original_kb,
            "output_kb": output_kb,
            "dimensions": f"{img.size[0]}x{img.size[1]}",
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


@click.group()
@click.option("--verbose", "-v", is_flag=True)
@click.pass_context
def cli(ctx, verbose):
    """圖片格式轉換 — convert images between PNG/JPG/WEBP/etc."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


@cli.command()
@click.option("--input-file", "-i", help="Input image file")
@click.option("--input-dir", help="Input directory (batch mode)")
@click.option("--output-file", "-o", default=None, help="Output file")
@click.option("--output-dir", default=None, help="Output directory (batch mode)")
@click.option("--format", "-f", "target_format", required=True,
              type=click.Choice(["jpg", "jpeg", "png", "webp", "bmp", "tiff", "gif"]),
              help="Target format")
@click.option("--quality", "-q", default=90, show_default=True,
              type=click.IntRange(1, 100), help="Output quality (for JPEG/WEBP)")
@click.option("--keep-exif", is_flag=True, help="Preserve EXIF metadata (JPEG only)")
@click.option("--dry-run", is_flag=True, help="Show what would be done")
@click.pass_context
def run(ctx, input_file, input_dir, output_file, output_dir, target_format, quality, keep_exif, dry_run):
    """Convert image(s) to target format."""
    if not check_pillow():
        sys.exit(1)

    results = []
    ext = "." + target_format.lstrip(".")

    if input_dir:
        src_dir = Path(input_dir)
        dst_dir = Path(output_dir) if output_dir else src_dir / target_format
        if not dry_run:
            dst_dir.mkdir(parents=True, exist_ok=True)
        imgs = [f for f in src_dir.iterdir() if f.suffix.lower() in IMAGE_EXTS]
        if not imgs:
            console.print(f"[yellow]No images found in {src_dir}[/yellow]")
            sys.exit(0)
        for img in track(imgs, description=f"Converting to {target_format}..."):
            out = dst_dir / (img.stem + ext)
            if dry_run:
                results.append({"input": str(img), "output": str(out), "dry_run": True})
            else:
                res = transcode_image(img, out, target_format, quality, keep_exif)
                results.append({"input": str(img), **res})

    elif input_file:
        src = Path(input_file)
        if not src.exists():
            console.print(f"[red]File not found:[/red] {src}")
            sys.exit(1)
        out = Path(output_file) if output_file else src.with_suffix(ext)
        if dry_run:
            results.append({"input": str(src), "output": str(out), "dry_run": True})
        else:
            res = transcode_image(src, out, target_format, quality, keep_exif)
            results.append({"input": str(src), **res})
            if res["status"] == "ok":
                console.print(Panel(
                    f"[green]Done![/green]  {out}  "
                    f"({res['original_kb']} KB → {res['output_kb']} KB, {res['dimensions']})",
                    title="img-transcode"
                ))
    else:
        console.print("[red]Error:[/red] Provide --input-file or --input-dir")
        sys.exit(1)

    click.echo(json.dumps({"status": "ok", "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
