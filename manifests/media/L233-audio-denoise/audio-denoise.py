#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
audio-denoise — 音訊降噪器
解決問題：錄音背景噪音明顯
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

AUDIO_EXTS = {".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg", ".opus", ".wma"}


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


def denoise_audio(
    input_file: Path,
    output_file: Path,
    noise_level: float = 0.21,
    highpass: int = 80,
    lowpass: int = 16000,
    normalize: bool = True,
) -> dict:
    """
    Denoise audio using ffmpeg filters:
    - afftdn: FFT-based noise reduction
    - highpass/lowpass: frequency filtering
    - dynaudnorm: dynamic normalization
    """
    filters = []

    # High-pass to remove rumble/hum below highpass Hz
    if highpass > 0:
        filters.append(f"highpass=f={highpass}")

    # FFT-based noise reduction
    filters.append(f"afftdn=nf={-int(noise_level * 97 + 3)}")

    # Low-pass to remove high-frequency noise
    if lowpass < 22000:
        filters.append(f"lowpass=f={lowpass}")

    # Normalize audio levels
    if normalize:
        filters.append("dynaudnorm=f=150:g=15")

    filter_str = ",".join(filters)

    cmd = [
        "ffmpeg", "-y", "-i", str(input_file),
        "-af", filter_str,
        str(output_file),
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        original_kb = input_file.stat().st_size // 1024
        output_kb = output_file.stat().st_size // 1024
        return {
            "status": "ok",
            "output": str(output_file),
            "original_kb": original_kb,
            "output_kb": output_kb,
            "filters_applied": filter_str,
        }
    except subprocess.CalledProcessError as e:
        return {"status": "error", "error": e.stderr.decode(errors="replace")}


@click.group()
@click.option("--verbose", "-v", is_flag=True)
@click.pass_context
def cli(ctx, verbose):
    """音訊降噪器 — denoise audio files using ffmpeg filters."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


@cli.command()
@click.option("--input-file", "-i", help="Input audio file")
@click.option("--input-dir", help="Input directory (batch mode)")
@click.option("--output-file", "-o", default=None, help="Output file")
@click.option("--output-dir", default=None, help="Output directory")
@click.option("--noise-level", default=0.21, show_default=True,
              type=click.FloatRange(0.0, 1.0),
              help="Noise reduction level 0.0-1.0 (higher = more aggressive)")
@click.option("--highpass", default=80, show_default=True,
              help="High-pass filter cutoff Hz (removes rumble, 0=off)")
@click.option("--lowpass", default=16000, show_default=True,
              help="Low-pass filter cutoff Hz (removes hiss, 22000=off)")
@click.option("--no-normalize", is_flag=True, help="Disable dynamic normalization")
@click.option("--dry-run", is_flag=True, help="Show what would be done")
@click.pass_context
def run(ctx, input_file, input_dir, output_file, output_dir, noise_level, highpass, lowpass, no_normalize, dry_run):
    """Remove noise from audio file(s) using ffmpeg filters."""
    if not check_ffmpeg():
        sys.exit(1)

    results = []

    if input_dir:
        src_dir = Path(input_dir)
        dst_dir = Path(output_dir) if output_dir else src_dir / "denoised"
        if not dry_run:
            dst_dir.mkdir(parents=True, exist_ok=True)
        audio_files = [f for f in src_dir.iterdir() if f.suffix.lower() in AUDIO_EXTS]
        for af in track(audio_files, description="Denoising..."):
            out = dst_dir / af.name
            if dry_run:
                results.append({"input": str(af), "output": str(out), "dry_run": True})
            else:
                res = denoise_audio(af, out, noise_level, highpass, lowpass, not no_normalize)
                results.append({"input": str(af), **res})

    elif input_file:
        src = Path(input_file)
        if not src.exists():
            console.print(f"[red]File not found:[/red] {src}")
            sys.exit(1)
        out = Path(output_file) if output_file else src.parent / (src.stem + "_denoised" + src.suffix)
        if dry_run:
            results.append({"input": str(src), "output": str(out), "dry_run": True})
        else:
            res = denoise_audio(src, out, noise_level, highpass, lowpass, not no_normalize)
            results.append({"input": str(src), **res})
            if res["status"] == "ok":
                console.print(Panel(
                    f"[green]Done![/green]  {out}",
                    title="audio-denoise"
                ))
    else:
        console.print("[red]Error:[/red] Provide --input-file or --input-dir")
        sys.exit(1)

    click.echo(json.dumps({"status": "ok", "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
