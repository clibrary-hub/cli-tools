#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
thumb-make — 縮圖產生器
解決問題：縮圖尺寸規格多
"""

import json
import sys
from pathlib import Path
from typing import Optional, List, Tuple
import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import track

console = Console()

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif", ".gif"}

# Common thumbnail presets
PRESETS = {
    "youtube": [(1280, 720)],
    "instagram": [(1080, 1080), (1080, 1350), (1080, 566)],
    "twitter": [(1200, 675)],
    "og": [(1200, 630)],  # Open Graph
    "favicon": [(32, 32), (64, 64), (128, 128), (256, 256)],
    "avatar": [(100, 100), (200, 200)],
}


def check_pillow() -> bool:
    try:
        from PIL import Image  # noqa
        return True
    except ImportError:
        console.print("[red]Error:[/red] Pillow not installed. pip install Pillow")
        return False


def make_thumbnail(
    input_file: Path,
    output_file: Path,
    width: int,
    height: int,
    fit: str = "contain",
    background: str = "white",
    quality: int = 85,
) -> dict:
    """Generate a thumbnail with specified dimensions."""
    from PIL import Image

    try:
        img = Image.open(input_file).convert("RGBA")

        if fit == "contain":
            # Fit inside box, preserve aspect ratio, pad with background
            img.thumbnail((width, height), Image.LANCZOS)
            if background == "transparent":
                bg = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            else:
                bg_color = (255, 255, 255, 255) if background == "white" else (0, 0, 0, 255)
                bg = Image.new("RGBA", (width, height), bg_color)
            offset = ((width - img.width) // 2, (height - img.height) // 2)
            bg.paste(img, offset, img)
            result_img = bg

        elif fit == "cover":
            # Fill entire box, crop center
            ratio = max(width / img.width, height / img.height)
            new_w = int(img.width * ratio)
            new_h = int(img.height * ratio)
            img = img.resize((new_w, new_h), Image.LANCZOS)
            left = (new_w - width) // 2
            top = (new_h - height) // 2
            result_img = img.crop((left, top, left + width, top + height))

        elif fit == "stretch":
            result_img = img.resize((width, height), Image.LANCZOS)

        else:
            result_img = img

        # Save
        output_file.parent.mkdir(parents=True, exist_ok=True)
        ext = output_file.suffix.lower()
        if ext in (".jpg", ".jpeg"):
            final = result_img.convert("RGB")
            final.save(output_file, "JPEG", quality=quality, optimize=True)
        elif ext == ".webp":
            result_img.save(output_file, "WEBP", quality=quality)
        else:
            result_img.save(output_file, "PNG", optimize=True)

        return {
            "status": "ok",
            "output": str(output_file),
            "dimensions": f"{width}x{height}",
            "size_kb": output_file.stat().st_size // 1024,
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


@click.group()
@click.option("--verbose", "-v", is_flag=True)
@click.pass_context
def cli(ctx, verbose):
    """縮圖產生器 — generate thumbnails from images."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


@cli.command()
@click.option("--input-file", "-i", help="Input image file")
@click.option("--input-dir", help="Input directory (batch mode)")
@click.option("--output-dir", "-o", default=None, help="Output directory")
@click.option("--width", "-w", default=300, show_default=True, help="Thumbnail width")
@click.option("--height", "-h", default=300, show_default=True, help="Thumbnail height")
@click.option("--preset", default=None,
              type=click.Choice(list(PRESETS.keys())),
              help="Use a size preset instead of --width/--height")
@click.option("--fit", default="contain", show_default=True,
              type=click.Choice(["contain", "cover", "stretch"]),
              help="Fit mode: contain (pad), cover (crop), stretch")
@click.option("--background", default="white", show_default=True,
              help="Background color for contain mode: white, black, transparent")
@click.option("--quality", "-q", default=85, show_default=True,
              type=click.IntRange(1, 100), help="JPEG/WEBP quality")
@click.option("--format", "out_format", default="jpg", show_default=True,
              type=click.Choice(["jpg", "png", "webp"]),
              help="Output format")
@click.option("--dry-run", is_flag=True, help="Show what would be done")
@click.pass_context
def run(ctx, input_file, input_dir, output_dir, width, height, preset, fit, background, quality, out_format, dry_run):
    """Generate thumbnail(s) from image(s)."""
    if not check_pillow():
        sys.exit(1)

    results = []
    sizes: List[Tuple[int, int]] = []

    if preset:
        sizes = PRESETS[preset]
    else:
        sizes = [(width, height)]

    def process_one(src: Path, dst_dir: Path):
        file_results = []
        for w, h in sizes:
            suffix = f"_{w}x{h}.{out_format}"
            out = dst_dir / (src.stem + suffix)
            if dry_run:
                file_results.append({"input": str(src), "output": str(out), "dry_run": True})
            else:
                res = make_thumbnail(src, out, w, h, fit, background, quality)
                file_results.append({"input": str(src), **res})
        return file_results

    if input_dir:
        src_dir = Path(input_dir)
        dst_dir = Path(output_dir) if output_dir else src_dir / "thumbnails"
        if not dry_run:
            dst_dir.mkdir(parents=True, exist_ok=True)
        imgs = [f for f in src_dir.iterdir() if f.suffix.lower() in IMAGE_EXTS]
        for img in track(imgs, description="Making thumbnails..."):
            results.extend(process_one(img, dst_dir))

    elif input_file:
        src = Path(input_file)
        if not src.exists():
            console.print(f"[red]File not found:[/red] {src}")
            sys.exit(1)
        dst_dir = Path(output_dir) if output_dir else src.parent
        res_list = process_one(src, dst_dir)
        results.extend(res_list)
        ok_count = sum(1 for r in res_list if r.get("status") == "ok")
        if ok_count:
            console.print(Panel(
                f"[green]Done![/green]  {ok_count} thumbnail(s) created in {dst_dir}",
                title="thumb-make"
            ))
    else:
        console.print("[red]Error:[/red] Provide --input-file or --input-dir")
        sys.exit(1)

    click.echo(json.dumps({"status": "ok", "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
