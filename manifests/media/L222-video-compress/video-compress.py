#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
video-compress — 智慧壓縮器
解決問題：影片壓縮品質難拿捏
"""

import json
import sys
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Any
import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import track

console = Console()

RESOLUTION_MAP = {
    "2160p": "3840:2160",
    "1440p": "2560:1440",
    "1080p": "1920:1080",
    "720p": "1280:720",
    "480p": "854:480",
    "360p": "640:360",
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


def get_file_size_mb(path: Path) -> float:
    return path.stat().st_size / (1024 * 1024)


def get_video_duration(path: Path) -> float:
    """Return video duration in seconds via ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
            capture_output=True, text=True, check=True
        )
        import json as _json
        info = _json.loads(result.stdout)
        return float(info["format"].get("duration", 0))
    except Exception:
        return 0.0


def compress_video(
    input_file: Path,
    output_file: Path,
    crf: int = 23,
    resolution: Optional[str] = None,
    target_size_mb: Optional[float] = None,
    preset: str = "medium",
) -> dict:
    """Compress video using ffmpeg H.264 encoding."""
    cmd = ["ffmpeg", "-y", "-i", str(input_file)]

    vf_parts = []
    if resolution and resolution in RESOLUTION_MAP:
        scale = RESOLUTION_MAP[resolution]
        vf_parts.append(f"scale={scale}:force_original_aspect_ratio=decrease")

    if target_size_mb:
        # Two-pass encoding for target size
        duration = get_video_duration(input_file)
        if duration > 0:
            target_bitrate_kbps = int((target_size_mb * 8 * 1024) / duration)
            audio_kbps = 128
            video_kbps = max(target_bitrate_kbps - audio_kbps, 100)
            vf_filter = ",".join(vf_parts) if vf_parts else None
            pass1 = ["ffmpeg", "-y", "-i", str(input_file), "-c:v", "libx264",
                     "-b:v", f"{video_kbps}k", "-pass", "1", "-an", "-f", "null"]
            if vf_filter:
                pass1 += ["-vf", vf_filter]
            pass1 += ["/dev/null" if sys.platform != "win32" else "NUL"]
            pass2 = ["ffmpeg", "-y", "-i", str(input_file), "-c:v", "libx264",
                     "-b:v", f"{video_kbps}k", "-pass", "2",
                     "-c:a", "aac", "-b:a", f"{audio_kbps}k"]
            if vf_filter:
                pass2 += ["-vf", vf_filter]
            pass2 += [str(output_file)]
            try:
                subprocess.run(pass1, check=True, capture_output=True)
                subprocess.run(pass2, check=True, capture_output=True)
            except subprocess.CalledProcessError as e:
                return {"status": "error", "error": e.stderr.decode(errors="replace")}
        else:
            # Fallback to CRF
            target_size_mb = None

    if not target_size_mb:
        vf_filter = ",".join(vf_parts) if vf_parts else None
        cmd += ["-c:v", "libx264", "-crf", str(crf), "-preset", preset,
                "-c:a", "aac", "-b:a", "128k"]
        if vf_filter:
            cmd += ["-vf", vf_filter]
        cmd += [str(output_file)]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            return {"status": "error", "error": e.stderr.decode(errors="replace")}

    original_mb = round(get_file_size_mb(input_file), 2)
    output_mb = round(get_file_size_mb(output_file), 2)
    ratio = round((1 - output_mb / original_mb) * 100, 1) if original_mb > 0 else 0
    return {
        "status": "ok",
        "output": str(output_file),
        "original_mb": original_mb,
        "output_mb": output_mb,
        "reduction_pct": ratio,
    }


@click.group()
@click.option("--verbose", "-v", is_flag=True)
@click.pass_context
def cli(ctx, verbose):
    """智慧壓縮器 — compress videos with quality presets."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


@cli.command()
@click.option("--input-file", "-i", help="Input video file")
@click.option("--input-dir", help="Input directory (batch mode)")
@click.option("--output-file", "-o", help="Output file")
@click.option("--output-dir", help="Output directory (batch mode)")
@click.option("--crf", default=23, show_default=True, help="CRF quality (18=high, 28=low)")
@click.option("--resolution", default=None, help="Target resolution: 1080p, 720p, 480p, etc.")
@click.option("--target-size-mb", default=None, type=float, help="Target file size in MB")
@click.option("--preset", default="medium", show_default=True,
              type=click.Choice(["ultrafast","superfast","veryfast","faster","fast","medium","slow","slower","veryslow"]),
              help="Encoding speed preset")
@click.option("--dry-run", is_flag=True, help="Show what would be done")
@click.pass_context
def run(ctx, input_file, input_dir, output_file, output_dir, crf, resolution, target_size_mb, preset, dry_run):
    """Compress video file(s) using H.264."""
    if not check_ffmpeg():
        sys.exit(1)

    results = []

    if input_dir:
        src_dir = Path(input_dir)
        dst_dir = Path(output_dir) if output_dir else src_dir / "compressed"
        if not dry_run:
            dst_dir.mkdir(parents=True, exist_ok=True)
        video_files = []
        for ext in ("*.mp4", "*.avi", "*.mov", "*.mkv", "*.wmv"):
            video_files.extend(src_dir.glob(ext))
        for vf in track(video_files, description="Compressing..."):
            out = dst_dir / vf.name
            if dry_run:
                results.append({"input": str(vf), "output": str(out), "dry_run": True})
            else:
                res = compress_video(vf, out, crf, resolution, target_size_mb, preset)
                results.append({"input": str(vf), **res})
    elif input_file:
        src = Path(input_file)
        if not src.exists():
            console.print(f"[red]File not found:[/red] {src}")
            sys.exit(1)
        out = Path(output_file) if output_file else src.parent / (src.stem + "_compressed" + src.suffix)
        if dry_run:
            results.append({"input": str(src), "output": str(out), "dry_run": True})
        else:
            res = compress_video(src, out, crf, resolution, target_size_mb, preset)
            results.append({"input": str(src), **res})
            if res["status"] == "ok":
                console.print(Panel(
                    f"[green]Done![/green]  {res['original_mb']} MB → {res['output_mb']} MB  "
                    f"([cyan]-{res['reduction_pct']}%[/cyan])",
                    title="video-compress"
                ))
    else:
        console.print("[red]Error:[/red] Provide --input-file or --input-dir")
        sys.exit(1)

    click.echo(json.dumps({"status": "ok", "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
