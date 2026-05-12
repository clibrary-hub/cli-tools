#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
video-recode — 影片重編碼
解決問題：影片格式相容性問題
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

VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".webm", ".m4v", ".ts"}

CODEC_PRESETS = {
    "h264": {"vcodec": "libx264", "acodec": "aac"},
    "h265": {"vcodec": "libx265", "acodec": "aac"},
    "vp9": {"vcodec": "libvpx-vp9", "acodec": "libopus"},
    "av1": {"vcodec": "libaom-av1", "acodec": "libopus"},
    "prores": {"vcodec": "prores_ks", "acodec": "pcm_s16le"},
    "copy": {"vcodec": "copy", "acodec": "copy"},
}

CONTAINER_EXTS = {
    "mp4": ".mp4",
    "mkv": ".mkv",
    "webm": ".webm",
    "mov": ".mov",
    "avi": ".avi",
}


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


def recode_video(
    input_file: Path,
    output_file: Path,
    codec: str = "h264",
    crf: int = 23,
    bitrate: Optional[str] = None,
    container: Optional[str] = None,
    extra_args: Optional[List[str]] = None,
) -> dict:
    """Re-encode video with specified codec."""
    preset = CODEC_PRESETS.get(codec, CODEC_PRESETS["h264"])

    cmd = ["ffmpeg", "-y", "-i", str(input_file),
           "-c:v", preset["vcodec"],
           "-c:a", preset["acodec"]]

    if preset["vcodec"] not in ("copy",):
        if bitrate:
            cmd += ["-b:v", bitrate]
        else:
            cmd += ["-crf", str(crf)]

    if codec in ("h264", "h265"):
        cmd += ["-preset", "medium"]

    if extra_args:
        cmd.extend(extra_args)

    cmd.append(str(output_file))

    try:
        result = subprocess.run(cmd, check=True, capture_output=True)
        size_mb = round(output_file.stat().st_size / (1024 * 1024), 2)
        original_mb = round(input_file.stat().st_size / (1024 * 1024), 2)
        return {
            "status": "ok",
            "output": str(output_file),
            "codec": codec,
            "original_mb": original_mb,
            "output_mb": size_mb,
        }
    except subprocess.CalledProcessError as e:
        return {"status": "error", "error": e.stderr.decode(errors="replace")}


@click.group()
@click.option("--verbose", "-v", is_flag=True)
@click.pass_context
def cli(ctx, verbose):
    """影片重編碼 — re-encode video files to different codecs/containers."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


@cli.command()
@click.option("--input-file", "-i", help="Input video file")
@click.option("--input-dir", help="Input directory (batch mode)")
@click.option("--output-file", "-o", default=None, help="Output file")
@click.option("--output-dir", default=None, help="Output directory (batch mode)")
@click.option("--codec", "-c", default="h264", show_default=True,
              type=click.Choice(list(CODEC_PRESETS.keys())),
              help="Target video codec")
@click.option("--container", default=None,
              type=click.Choice(list(CONTAINER_EXTS.keys())),
              help="Output container format (default: inferred from codec)")
@click.option("--crf", default=23, show_default=True,
              type=click.IntRange(0, 51), help="Constant Rate Factor quality")
@click.option("--bitrate", default=None, help="Target bitrate (e.g. 2M, 500k)")
@click.option("--dry-run", is_flag=True, help="Show what would be done")
@click.pass_context
def run(ctx, input_file, input_dir, output_file, output_dir, codec, container, crf, bitrate, dry_run):
    """Re-encode video(s) to target codec and container."""
    if not check_ffmpeg():
        sys.exit(1)

    # Determine output extension
    if container:
        out_ext = CONTAINER_EXTS[container]
    elif codec in ("vp9", "av1"):
        out_ext = ".webm"
    elif codec == "prores":
        out_ext = ".mov"
    else:
        out_ext = ".mp4"

    results = []

    if input_dir:
        src_dir = Path(input_dir)
        dst_dir = Path(output_dir) if output_dir else src_dir / f"recoded_{codec}"
        if not dry_run:
            dst_dir.mkdir(parents=True, exist_ok=True)
        videos = [f for f in src_dir.iterdir() if f.suffix.lower() in VIDEO_EXTS]
        for vf in track(videos, description=f"Recoding to {codec}..."):
            out = dst_dir / (vf.stem + out_ext)
            if dry_run:
                results.append({"input": str(vf), "output": str(out), "dry_run": True})
            else:
                res = recode_video(vf, out, codec=codec, crf=crf, bitrate=bitrate)
                results.append({"input": str(vf), **res})

    elif input_file:
        src = Path(input_file)
        if not src.exists():
            console.print(f"[red]File not found:[/red] {src}")
            sys.exit(1)
        out = Path(output_file) if output_file else src.with_suffix(out_ext)
        if dry_run:
            results.append({"input": str(src), "output": str(out), "dry_run": True})
        else:
            res = recode_video(src, out, codec=codec, crf=crf, bitrate=bitrate)
            results.append({"input": str(src), **res})
            if res["status"] == "ok":
                console.print(Panel(
                    f"[green]Done![/green]  {out}  "
                    f"({res['original_mb']} MB → {res['output_mb']} MB, codec={codec})",
                    title="video-recode"
                ))
    else:
        console.print("[red]Error:[/red] Provide --input-file or --input-dir")
        sys.exit(1)

    click.echo(json.dumps({"status": "ok", "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
