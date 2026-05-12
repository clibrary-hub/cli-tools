#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
shot-annotate — 截圖標註器
解決問題：截圖標記費時
"""

import json
import sys
from pathlib import Path
from typing import Optional, List, Tuple
import click
from rich.console import Console
from rich.panel import Panel

console = Console()


def check_pillow() -> bool:
    try:
        from PIL import Image, ImageDraw, ImageFont  # noqa
        return True
    except ImportError:
        console.print("[red]Error:[/red] Pillow not installed. pip install Pillow")
        return False


def parse_color(color_str: str) -> Tuple[int, int, int]:
    """Parse 'R,G,B' or named color string."""
    if "," in color_str:
        parts = color_str.split(",")
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    named = {
        "red": (255, 0, 0), "green": (0, 200, 0), "blue": (0, 0, 255),
        "yellow": (255, 220, 0), "orange": (255, 140, 0), "white": (255, 255, 255),
        "black": (0, 0, 0), "purple": (128, 0, 128), "cyan": (0, 200, 200),
    }
    return named.get(color_str.lower(), (255, 0, 0))


def draw_arrow(draw, start: Tuple[int, int], end: Tuple[int, int], color: Tuple, width: int = 3):
    """Draw an arrow from start to end."""
    import math
    draw.line([start, end], fill=color, width=width)
    # Arrowhead
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    head_len = 15
    head_angle = math.pi / 6
    ax = end[0] - head_len * math.cos(angle - head_angle)
    ay = end[1] - head_len * math.sin(angle - head_angle)
    bx = end[0] - head_len * math.cos(angle + head_angle)
    by = end[1] - head_len * math.sin(angle + head_angle)
    draw.polygon([end, (int(ax), int(ay)), (int(bx), int(by))], fill=color)


def annotate_image(
    input_file: Path,
    output_file: Path,
    annotations: List[dict],
) -> dict:
    """
    Apply annotations to an image.
    Each annotation is a dict with:
      type: "text" | "arrow" | "rect" | "circle"
      x, y: position
      text: text content (for type=text)
      x2, y2: end position (for arrow/rect)
      color: color name or "R,G,B"
      size: font size or line width
    """
    from PIL import Image, ImageDraw, ImageFont

    try:
        img = Image.open(input_file).convert("RGBA")
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        for ann in annotations:
            ann_type = ann.get("type", "text")
            x = int(ann.get("x", 0))
            y = int(ann.get("y", 0))
            color_str = ann.get("color", "red")
            color = parse_color(color_str)
            size = int(ann.get("size", 20))

            if ann_type == "text":
                text = ann.get("text", "")
                try:
                    font = ImageFont.truetype("arial.ttf", size)
                except Exception:
                    font = ImageFont.load_default()
                # Draw text shadow
                draw.text((x + 1, y + 1), text, fill=(0, 0, 0, 180), font=font)
                draw.text((x, y), text, fill=(*color, 255), font=font)

            elif ann_type == "arrow":
                x2 = int(ann.get("x2", x + 50))
                y2 = int(ann.get("y2", y + 50))
                draw_arrow(draw, (x, y), (x2, y2), (*color, 255), width=max(2, size // 10))

            elif ann_type == "rect":
                x2 = int(ann.get("x2", x + 100))
                y2 = int(ann.get("y2", y + 100))
                lw = max(2, size // 10)
                draw.rectangle([x, y, x2, y2], outline=(*color, 255), width=lw)

            elif ann_type == "circle":
                r = int(ann.get("radius", 30))
                lw = max(2, size // 10)
                draw.ellipse([x - r, y - r, x + r, y + r], outline=(*color, 255), width=lw)

        combined = Image.alpha_composite(img, overlay).convert("RGB")
        output_file.parent.mkdir(parents=True, exist_ok=True)
        combined.save(output_file)
        return {"status": "ok", "output": str(output_file), "annotations_applied": len(annotations)}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


@click.group()
@click.option("--verbose", "-v", is_flag=True)
@click.pass_context
def cli(ctx, verbose):
    """截圖標註器 — annotate screenshots with arrows, text and shapes."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


@cli.command()
@click.option("--input-file", "-i", required=True, help="Input screenshot image")
@click.option("--output-file", "-o", default=None, help="Output annotated image")
@click.option("--annotations", "-a", default=None,
              help="JSON string or path to JSON file with annotation list")
@click.option("--text", default=None, help="Quick: add text annotation")
@click.option("--text-x", default=10, type=int, help="Text X position")
@click.option("--text-y", default=10, type=int, help="Text Y position")
@click.option("--color", default="red", show_default=True, help="Annotation color (name or R,G,B)")
@click.option("--font-size", default=24, show_default=True, help="Font size")
@click.option("--arrow", nargs=4, type=int, default=None, metavar="X1 Y1 X2 Y2",
              help="Draw arrow from (X1,Y1) to (X2,Y2)")
@click.option("--rect", nargs=4, type=int, default=None, metavar="X1 Y1 X2 Y2",
              help="Draw rectangle")
@click.option("--dry-run", is_flag=True, help="Show what would be done")
@click.pass_context
def run(ctx, input_file, output_file, annotations, text, text_x, text_y, color, font_size, arrow, rect, dry_run):
    """Annotate a screenshot with text, arrows, and shapes."""
    if not check_pillow():
        sys.exit(1)

    src = Path(input_file)
    if not src.exists():
        console.print(f"[red]File not found:[/red] {src}")
        sys.exit(1)

    out = Path(output_file) if output_file else src.parent / (src.stem + "_annotated" + src.suffix)

    ann_list: List[dict] = []

    # Load from JSON file or string
    if annotations:
        ann_path = Path(annotations)
        if ann_path.exists():
            ann_list = json.loads(ann_path.read_text(encoding="utf-8"))
        else:
            try:
                ann_list = json.loads(annotations)
            except json.JSONDecodeError:
                console.print("[red]Error:[/red] --annotations must be valid JSON or a JSON file path")
                sys.exit(1)

    # Quick annotation flags
    if text:
        ann_list.append({"type": "text", "x": text_x, "y": text_y,
                         "text": text, "color": color, "size": font_size})
    if arrow:
        ann_list.append({"type": "arrow", "x": arrow[0], "y": arrow[1],
                         "x2": arrow[2], "y2": arrow[3], "color": color, "size": font_size})
    if rect:
        ann_list.append({"type": "rect", "x": rect[0], "y": rect[1],
                         "x2": rect[2], "y2": rect[3], "color": color, "size": font_size})

    if not ann_list:
        console.print("[yellow]No annotations specified. Use --text, --arrow, --rect, or --annotations[/yellow]")
        sys.exit(0)

    if dry_run:
        result = {"dry_run": True, "input": str(src), "output": str(out),
                  "annotations": ann_list}
    else:
        result = annotate_image(src, out, ann_list)
        if result["status"] == "ok":
            console.print(Panel(
                f"[green]Done![/green]  {out}  ({result['annotations_applied']} annotations)",
                title="shot-annotate"
            ))

    click.echo(json.dumps({"status": "ok", "data": result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
