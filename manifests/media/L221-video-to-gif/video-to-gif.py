#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
video-to-gif — 影片轉 GIF
解決問題：影片轉 GIF 步驟多
"""

import json
import sys
import shutil
import subprocess
from pathlib import Path
from typing import Optional, List, Any
import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import track

console = Console()


def check_ffmpeg() -> bool:
    """Check if ffmpeg is available."""
    if shutil.which("ffmpeg") is None:
        console.print(
            "[red]Error:[/red] ffmpeg not found. Install it:\n"
            "  macOS:   brew install ffmpeg\n"
            "  Ubuntu:  sudo apt install ffmpeg\n"
            "  Windows: https://ffmpeg.org/download.html"
        )
        return False
    return True


def convert_video_to_gif(
    input_file: Path,
    output_file: Path,
    start: Optional[str] = None,
    end: Optional[str] = None,
    width: int = 480,
    fps: int = 10,
) -> dict:
    """Convert a video file to GIF using ffmpeg."""
    cmd = ["ffmpeg", "-y"]

    if start:
        cmd += ["-ss", start]
    if end:
        cmd += ["-to", end]

    cmd += ["-i", str(input_file)]

    # Two-pass palette for better quality
    palette_file = output_file.with_suffix(".palette.png")
    palette_cmd = cmd + [
        "-vf", f"fps={fps},scale={width}:-1:flags=lanczos,palettegen",
        str(palette_file),
    ]
    gif_cmd = cmd + [
        "-i", str(palette_file),
        "-filter_complex", f"fps={fps},scale={width}:-1:flags=lanczos[x];[x][1:v]paletteuse",
        str(output_file),
    ]

    try:
        subprocess.run(palette_cmd, check=True, capture_output=True)
        subprocess.run(gif_cmd, check=True, capture_output=True)
        palette_file.unlink(missing_ok=True)
        size_kb = output_file.stat().st_size // 1024
        return {"output": str(output_file), "size_kb": size_kb, "status": "ok"}
    except subprocess.CalledProcessError as e:
        return {"output": str(output_file), "status": "error", "error": e.stderr.decode(errors="replace")}


@click.group()
@click.option("--verbose", "-v", is_flag=True)
@click.pass_context
def cli(ctx, verbose):
    """影片轉 GIF — convert video clips to animated GIFs."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


@cli.command()
@click.option("--input-file", "-i", help="Input video file")
@click.option("--input-dir", help="Input directory (batch mode)")
@click.option("--output-file", "-o", help="Output GIF file")
@click.option("--output-dir", help="Output directory (batch mode)")
@click.option("--start", "-s", default=None, help="Start time (HH:MM:SS or seconds)")
@click.option("--end", "-e", default=None, help="End time (HH:MM:SS or seconds)")
@click.option("--width", "-w", default=480, show_default=True, help="Output width in pixels")
@click.option("--fps", default=10, show_default=True, help="Frames per second")
@click.option("--dry-run", is_flag=True, help="Show what would be done without executing")
@click.pass_context
def run(ctx, input_file, input_dir, output_file, output_dir, start, end, width, fps, dry_run):
    """Convert video(s) to GIF."""
    if not check_ffmpeg():
        sys.exit(1)

    results = []

    if input_dir:
        src_dir = Path(input_dir)
        dst_dir = Path(output_dir) if output_dir else src_dir / "gifs"
        if not dry_run:
            dst_dir.mkdir(parents=True, exist_ok=True)
        video_files = list(src_dir.glob("*.mp4")) + list(src_dir.glob("*.avi")) + \
                      list(src_dir.glob("*.mov")) + list(src_dir.glob("*.mkv"))
        if not video_files:
            console.print(f"[yellow]No video files found in {src_dir}[/yellow]")
            sys.exit(0)
        for vf in track(video_files, description="Converting..."):
            out = dst_dir / (vf.stem + ".gif")
            if dry_run:
                results.append({"input": str(vf), "output": str(out), "dry_run": True})
            else:
                res = convert_video_to_gif(vf, out, start, end, width, fps)
                results.append({"input": str(vf), **res})
    elif input_file:
        src = Path(input_file)
        if not src.exists():
            console.print(f"[red]File not found:[/red] {src}")
            sys.exit(1)
        out = Path(output_file) if output_file else src.with_suffix(".gif")
        if dry_run:
            results.append({"input": str(src), "output": str(out), "dry_run": True})
        else:
            res = convert_video_to_gif(src, out, start, end, width, fps)
            results.append({"input": str(src), **res})
            if res["status"] == "ok":
                console.print(Panel(
                    f"[green]Done![/green] {out}  ({res['size_kb']} KB)",
                    title="video-to-gif"
                ))
    else:
        console.print("[red]Error:[/red] Provide --input-file or --input-dir")
        sys.exit(1)

    click.echo(json.dumps({"status": "ok", "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
