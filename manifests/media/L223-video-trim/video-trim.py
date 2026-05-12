#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
video-trim — 批次剪輯器
解決問題：多軌剪輯麻煩
"""

import json
import sys
import shutil
import subprocess
from pathlib import Path
from typing import Optional, List
import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import track

console = Console()


def check_ffmpeg() -> bool:
    if shutil.which("ffmpeg") is None:
        console.print(
            "[red]Error:[/red] ffmpeg not found. Install it:\n"
            "  macOS:   brew install ffmpeg\n"
            "  Ubuntu:  sudo apt install ffmpeg\n"
            "  Windows: https://ffmpeg.org/download.html"
        )
        return False
    return True


def trim_video(
    input_file: Path,
    output_file: Path,
    start: Optional[str] = None,
    end: Optional[str] = None,
    trim_start: Optional[float] = None,
) -> dict:
    """Trim a video file using ffmpeg stream copy."""
    cmd = ["ffmpeg", "-y"]
    ss = start or (str(trim_start) if trim_start is not None else None)
    if ss:
        cmd += ["-ss", ss]
    cmd += ["-i", str(input_file)]
    if end:
        cmd += ["-to", end]
    cmd += ["-c", "copy", str(output_file)]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        size_mb = round(output_file.stat().st_size / (1024 * 1024), 2)
        return {"status": "ok", "output": str(output_file), "size_mb": size_mb}
    except subprocess.CalledProcessError as e:
        return {"status": "error", "error": e.stderr.decode(errors="replace")}


def parse_chapters_file(chapters_file: Path) -> List[dict]:
    """
    Parse chapters file. Each line: START END label
    Example:  00:00:00 00:05:30 intro
    """
    chapters: List[dict] = []
    with open(chapters_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                label = parts[2] if len(parts) > 2 else f"chapter_{len(chapters) + 1}"
                chapters.append({"start": parts[0], "end": parts[1], "label": label})
    return chapters


@click.group()
@click.option("--verbose", "-v", is_flag=True)
@click.pass_context
def cli(ctx, verbose):
    """批次剪輯器 — trim and split video files."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


@cli.command()
@click.option("--input-file", "-i", help="Input video file")
@click.option("--input-dir", help="Input directory (batch mode)")
@click.option("--output-file", "-o", help="Output file")
@click.option("--output-dir", help="Output directory")
@click.option("--start", "-s", default=None, help="Start time (HH:MM:SS)")
@click.option("--end", "-e", default=None, help="End time (HH:MM:SS)")
@click.option("--trim-start", default=None, type=float, help="Skip N seconds from start")
@click.option("--chapters-file", default=None, help="Chapters file for splitting into segments")
@click.option("--dry-run", is_flag=True, help="Show what would be done")
@click.pass_context
def run(ctx, input_file, input_dir, output_file, output_dir, start, end, trim_start, chapters_file, dry_run):
    """Trim video(s) to specified time ranges."""
    if not check_ffmpeg():
        sys.exit(1)

    results = []

    if chapters_file and input_file:
        src = Path(input_file)
        if not src.exists():
            console.print(f"[red]File not found:[/red] {src}")
            sys.exit(1)
        ch_file = Path(chapters_file)
        if not ch_file.exists():
            console.print(f"[red]Chapters file not found:[/red] {ch_file}")
            sys.exit(1)
        chapters = parse_chapters_file(ch_file)
        dst_dir = Path(output_dir) if output_dir else src.parent / (src.stem + "_chapters")
        if not dry_run:
            dst_dir.mkdir(parents=True, exist_ok=True)
        for ch in track(chapters, description="Splitting chapters..."):
            out = dst_dir / f"{ch['label']}{src.suffix}"
            if dry_run:
                results.append({"chapter": ch["label"], "output": str(out), "dry_run": True})
            else:
                res = trim_video(src, out, start=ch["start"], end=ch["end"])
                results.append({"chapter": ch["label"], **res})

    elif input_dir:
        src_dir = Path(input_dir)
        dst_dir = Path(output_dir) if output_dir else src_dir / "trimmed"
        if not dry_run:
            dst_dir.mkdir(parents=True, exist_ok=True)
        video_files: List[Path] = []
        for ext in ("*.mp4", "*.avi", "*.mov", "*.mkv"):
            video_files.extend(src_dir.glob(ext))
        for vf in track(video_files, description="Trimming..."):
            out = dst_dir / vf.name
            if dry_run:
                results.append({"input": str(vf), "output": str(out), "dry_run": True})
            else:
                res = trim_video(vf, out, start=start, end=end, trim_start=trim_start)
                results.append({"input": str(vf), **res})

    elif input_file:
        src = Path(input_file)
        if not src.exists():
            console.print(f"[red]File not found:[/red] {src}")
            sys.exit(1)
        out = Path(output_file) if output_file else src.parent / (src.stem + "_trimmed" + src.suffix)
        if dry_run:
            results.append({"input": str(src), "output": str(out), "dry_run": True})
        else:
            res = trim_video(src, out, start=start, end=end, trim_start=trim_start)
            results.append({"input": str(src), **res})
            if res["status"] == "ok":
                console.print(Panel(f"[green]Done![/green]  {out}  ({res['size_mb']} MB)", title="video-trim"))
    else:
        console.print("[red]Error:[/red] Provide --input-file or --input-dir")
        sys.exit(1)

    click.echo(json.dumps({"status": "ok", "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
