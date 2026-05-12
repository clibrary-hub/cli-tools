#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
auto-subtitle — 自動字幕產生器
解決問題：字幕產生與時間軸對齊
"""

import json
import sys
import shutil
import subprocess
from pathlib import Path
from typing import Optional
import click
from rich.console import Console
from rich.panel import Panel

console = Console()


def check_whisper() -> bool:
    if shutil.which("whisper") is None:
        console.print(
            "[red]Error:[/red] whisper CLI not found. Install it:\n"
            "  pip install openai-whisper\n"
            "  (also requires ffmpeg)"
        )
        return False
    return True


def check_ffmpeg() -> bool:
    if shutil.which("ffmpeg") is None:
        console.print(
            "[red]Error:[/red] ffmpeg not found. Install it:\n"
            "  macOS:   brew install ffmpeg\n"
            "  Ubuntu:  sudo apt install ffmpeg"
        )
        return False
    return True


def extract_audio(input_file: Path, audio_file: Path) -> bool:
    """Extract audio track from video."""
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(input_file), "-vn", "-acodec", "pcm_s16le",
             "-ar", "16000", "-ac", "1", str(audio_file)],
            check=True, capture_output=True
        )
        return True
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Audio extraction failed:[/red] {e.stderr.decode(errors='replace')}")
        return False


def generate_subtitles(
    input_file: Path,
    output_dir: Path,
    language: str = "auto",
    model: str = "base",
    output_format: str = "srt",
) -> dict:
    """Generate subtitle file using whisper CLI."""
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "whisper", str(input_file),
        "--model", model,
        "--output_dir", str(output_dir),
        "--output_format", output_format,
    ]
    if language != "auto":
        cmd += ["--language", language]

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        # whisper outputs <stem>.<format> in output_dir
        out_file = output_dir / (input_file.stem + "." + output_format)
        return {
            "status": "ok",
            "output": str(out_file),
            "format": output_format,
            "model": model,
        }
    except subprocess.CalledProcessError as e:
        return {"status": "error", "error": e.stderr}


@click.group()
@click.option("--verbose", "-v", is_flag=True)
@click.pass_context
def cli(ctx, verbose):
    """自動字幕產生器 — generate subtitles from video/audio using Whisper."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


@cli.command()
@click.option("--input-file", "-i", required=True, help="Input video or audio file")
@click.option("--output-dir", "-o", default=None, help="Output directory for subtitle file")
@click.option("--language", "-l", default="auto", show_default=True,
              help="Language code (e.g. zh, en, ja) or 'auto' for detection")
@click.option("--model", "-m", default="base", show_default=True,
              type=click.Choice(["tiny", "base", "small", "medium", "large"]),
              help="Whisper model size")
@click.option("--format", "output_format", default="srt", show_default=True,
              type=click.Choice(["srt", "vtt", "tsv", "json", "txt"]),
              help="Output subtitle format")
@click.option("--dry-run", is_flag=True, help="Show what would be done")
@click.pass_context
def run(ctx, input_file, output_dir, language, model, output_format, dry_run):
    """Generate subtitle file from video or audio."""
    if not check_ffmpeg() or not check_whisper():
        sys.exit(1)

    src = Path(input_file)
    if not src.exists():
        console.print(f"[red]File not found:[/red] {src}")
        sys.exit(1)

    dst_dir = Path(output_dir) if output_dir else src.parent

    if dry_run:
        out_file = dst_dir / (src.stem + "." + output_format)
        result = {"status": "ok", "dry_run": True, "output": str(out_file), "model": model}
    else:
        console.print(f"[cyan]Transcribing[/cyan] {src.name} with model={model} lang={language}...")
        result = generate_subtitles(src, dst_dir, language=language, model=model, output_format=output_format)
        if result["status"] == "ok":
            console.print(Panel(f"[green]Done![/green]  {result['output']}", title="auto-subtitle"))

    click.echo(json.dumps({"status": "ok", "data": result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
