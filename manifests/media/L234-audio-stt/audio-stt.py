#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
audio-stt — 語音轉文字
解決問題：語音轉文字麻煩
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

AUDIO_EXTS = {".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg", ".opus", ".wma", ".mp4", ".mov", ".mkv"}


def check_whisper() -> bool:
    if shutil.which("whisper") is None:
        console.print(
            "[red]Error:[/red] whisper CLI not found. Install it:\n"
            "  pip install openai-whisper\n"
            "  Also requires ffmpeg"
        )
        return False
    return True


def transcribe_audio(
    input_file: Path,
    output_dir: Path,
    language: str = "auto",
    model: str = "base",
    output_format: str = "txt",
    task: str = "transcribe",
) -> dict:
    """Transcribe audio to text using whisper CLI."""
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "whisper", str(input_file),
        "--model", model,
        "--output_dir", str(output_dir),
        "--output_format", output_format,
        "--task", task,
    ]
    if language != "auto":
        cmd += ["--language", language]

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        out_file = output_dir / (input_file.stem + "." + output_format)
        transcript = out_file.read_text(encoding="utf-8") if out_file.exists() else ""
        return {
            "status": "ok",
            "output": str(out_file),
            "format": output_format,
            "model": model,
            "task": task,
            "preview": transcript[:500] + ("..." if len(transcript) > 500 else ""),
        }
    except subprocess.CalledProcessError as e:
        return {"status": "error", "error": e.stderr}


@click.group()
@click.option("--verbose", "-v", is_flag=True)
@click.pass_context
def cli(ctx, verbose):
    """語音轉文字 — transcribe audio/video to text using Whisper."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


@cli.command()
@click.option("--input-file", "-i", required=True, help="Input audio or video file")
@click.option("--output-dir", "-o", default=None, help="Output directory for transcript")
@click.option("--output-file", default=None, help="Output transcript file path")
@click.option("--language", "-l", default="auto", show_default=True,
              help="Language code (e.g. zh, en, ja) or 'auto'")
@click.option("--model", "-m", default="base", show_default=True,
              type=click.Choice(["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"]),
              help="Whisper model size (larger = more accurate but slower)")
@click.option("--format", "output_format", default="txt", show_default=True,
              type=click.Choice(["txt", "srt", "vtt", "tsv", "json"]),
              help="Output format")
@click.option("--task", default="transcribe", show_default=True,
              type=click.Choice(["transcribe", "translate"]),
              help="Task: transcribe (original lang) or translate (to English)")
@click.option("--dry-run", is_flag=True, help="Show what would be done")
@click.pass_context
def run(ctx, input_file, output_dir, output_file, language, model, output_format, task, dry_run):
    """Transcribe audio/video file to text."""
    if not check_whisper():
        sys.exit(1)

    src = Path(input_file)
    if not src.exists():
        console.print(f"[red]File not found:[/red] {src}")
        sys.exit(1)

    if output_file:
        dst_dir = Path(output_file).parent
    elif output_dir:
        dst_dir = Path(output_dir)
    else:
        dst_dir = src.parent

    if dry_run:
        out_name = src.stem + "." + output_format
        result = {
            "dry_run": True,
            "input": str(src),
            "output": str(dst_dir / out_name),
            "model": model,
            "language": language,
            "task": task,
        }
    else:
        console.print(f"[cyan]Transcribing[/cyan] {src.name} (model={model}, lang={language})...")
        result = transcribe_audio(src, dst_dir, language=language, model=model,
                                  output_format=output_format, task=task)
        if result["status"] == "ok":
            console.print(Panel(
                f"[green]Done![/green]  {result['output']}\n\n{result.get('preview', '')}",
                title="audio-stt"
            ))

    click.echo(json.dumps({"status": "ok", "data": result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
