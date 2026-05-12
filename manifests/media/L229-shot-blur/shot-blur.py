#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
shot-blur — 敏感區塊模糊
解決問題：截圖中敏感資訊需模糊
"""

import json
import sys
from pathlib import Path
from typing import List, Tuple, Optional
import click
from rich.console import Console
from rich.panel import Panel

console = Console()


def check_pillow() -> bool:
    try:
        from PIL import Image, ImageFilter  # noqa
        return True
    except ImportError:
        console.print("[red]Error:[/red] Pillow not installed. pip install Pillow")
        return False


def blur_regions(
    input_file: Path,
    output_file: Path,
    regions: List[dict],
    blur_radius: int = 15,
    method: str = "gaussian",
) -> dict:
    """
    Blur specified rectangular regions in an image.
    Each region: {"x": int, "y": int, "w": int, "h": int}
    """
    from PIL import Image, ImageFilter

    try:
        img = Image.open(input_file).convert("RGB")

        for region in regions:
            x = int(region.get("x", 0))
            y = int(region.get("y", 0))
            w = int(region.get("w", 100))
            h = int(region.get("h", 50))
            box = (x, y, x + w, y + h)

            # Crop region, blur it, paste back
            region_img = img.crop(box)

            if method == "pixelate":
                # Pixelate effect: downscale then upscale
                factor = max(1, blur_radius // 2)
                small = region_img.resize(
                    (max(1, region_img.width // factor), max(1, region_img.height // factor)),
                    Image.NEAREST
                )
                blurred = small.resize(region_img.size, Image.NEAREST)
            else:
                # Gaussian blur
                blurred = region_img.filter(ImageFilter.GaussianBlur(radius=blur_radius))

            img.paste(blurred, box)

        output_file.parent.mkdir(parents=True, exist_ok=True)
        img.save(output_file)
        return {
            "status": "ok",
            "output": str(output_file),
            "regions_blurred": len(regions),
            "method": method,
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


@click.group()
@click.option("--verbose", "-v", is_flag=True)
@click.pass_context
def cli(ctx, verbose):
    """敏感區塊模糊 — blur sensitive regions in screenshots."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


@cli.command()
@click.option("--input-file", "-i", required=True, help="Input image file")
@click.option("--output-file", "-o", default=None, help="Output image file")
@click.option("--regions", "-r", default=None,
              help='JSON array of regions: [{"x":0,"y":0,"w":100,"h":50},...]')
@click.option("--region", multiple=True,
              help="Region as x,y,w,h (can repeat for multiple regions)")
@click.option("--blur-radius", default=15, show_default=True, help="Blur radius (Gaussian)")
@click.option("--method", default="gaussian", show_default=True,
              type=click.Choice(["gaussian", "pixelate"]),
              help="Blur method: gaussian or pixelate")
@click.option("--dry-run", is_flag=True, help="Show what would be done")
@click.pass_context
def run(ctx, input_file, output_file, regions, region, blur_radius, method, dry_run):
    """Blur sensitive rectangular regions in an image."""
    if not check_pillow():
        sys.exit(1)

    src = Path(input_file)
    if not src.exists():
        console.print(f"[red]File not found:[/red] {src}")
        sys.exit(1)

    out = Path(output_file) if output_file else src.parent / (src.stem + "_blurred" + src.suffix)

    region_list: List[dict] = []

    if regions:
        try:
            region_list = json.loads(regions)
        except json.JSONDecodeError:
            console.print("[red]Error:[/red] --regions must be valid JSON array")
            sys.exit(1)

    for r in region:
        parts = r.split(",")
        if len(parts) != 4:
            console.print(f"[red]Error:[/red] --region must be x,y,w,h — got: {r}")
            sys.exit(1)
        region_list.append({
            "x": int(parts[0]), "y": int(parts[1]),
            "w": int(parts[2]), "h": int(parts[3]),
        })

    if not region_list:
        console.print("[yellow]No regions specified. Use --region x,y,w,h or --regions JSON[/yellow]")
        sys.exit(0)

    if dry_run:
        result = {"dry_run": True, "input": str(src), "output": str(out),
                  "regions": region_list, "method": method}
    else:
        result = blur_regions(src, out, region_list, blur_radius=blur_radius, method=method)
        if result["status"] == "ok":
            console.print(Panel(
                f"[green]Done![/green]  {out}  ({result['regions_blurred']} region(s) blurred)",
                title="shot-blur"
            ))

    click.echo(json.dumps({"status": "ok", "data": result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
