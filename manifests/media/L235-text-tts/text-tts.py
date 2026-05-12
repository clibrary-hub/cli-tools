#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
text-tts — 文字轉語音
解決問題：文字轉語音麻煩
"""

import json
import sys
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional
import click
from rich.console import Console
from rich.panel import Panel

console = Console()


def tts_pyttsx3(text: str, output_file: Path, rate: int = 150, volume: float = 1.0) -> dict:
    """TTS via pyttsx3 (offline, uses system voices)."""
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", rate)
        engine.setProperty("volume", volume)
        engine.save_to_file(text, str(output_file))
        engine.runAndWait()
        return {"status": "ok", "output": str(output_file), "engine": "pyttsx3"}
    except ImportError:
        return {"status": "fallback", "reason": "pyttsx3 not installed"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def tts_espeak(text: str, output_file: Path, lang: str = "en", speed: int = 150) -> dict:
    """TTS via espeak-ng subprocess."""
    if shutil.which("espeak-ng") is None and shutil.which("espeak") is None:
        return {"status": "fallback", "reason": "espeak/espeak-ng not found"}
    binary = shutil.which("espeak-ng") or shutil.which("espeak")
    try:
        subprocess.run(
            [binary, "-v", lang, "-s", str(speed), "-w", str(output_file), text],
            check=True, capture_output=True
        )
        return {"status": "ok", "output": str(output_file), "engine": "espeak-ng"}
    except subprocess.CalledProcessError as e:
        return {"status": "error", "error": e.stderr.decode(errors="replace")}


def tts_say(text: str, output_file: Path, voice: Optional[str] = None, rate: int = 175) -> dict:
    """TTS via macOS 'say' command."""
    if shutil.which("say") is None:
        return {"status": "fallback", "reason": "say command not found (macOS only)"}
    cmd = ["say", "-r", str(rate), "-o", str(output_file), "--data-format=LEF32@22050"]
    if voice:
        cmd += ["-v", voice]
    cmd.append(text)
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return {"status": "ok", "output": str(output_file), "engine": "macos-say"}
    except subprocess.CalledProcessError as e:
        return {"status": "error", "error": e.stderr.decode(errors="replace")}


def tts_powershell(text: str, output_file: Path, rate: int = 0) -> dict:
    """TTS via Windows PowerShell Speech Synthesizer."""
    if shutil.which("powershell") is None and shutil.which("pwsh") is None:
        return {"status": "fallback", "reason": "PowerShell not found"}
    ps = shutil.which("powershell") or shutil.which("pwsh")
    # PowerShell TTS script — saves to WAV
    wav_out = output_file.with_suffix(".wav")
    script = (
        f"Add-Type -AssemblyName System.Speech; "
        f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.Rate = {rate}; "
        f"$s.SetOutputToWaveFile('{wav_out}'); "
        f"$s.Speak('{text.replace(chr(39), chr(96))}'); "
        f"$s.SetOutputToDefaultAudioDevice()"
    )
    try:
        subprocess.run([ps, "-Command", script], check=True, capture_output=True)
        return {"status": "ok", "output": str(wav_out), "engine": "windows-sapi"}
    except subprocess.CalledProcessError as e:
        return {"status": "error", "error": e.stderr.decode(errors="replace")}


def text_to_speech(
    text: str,
    output_file: Path,
    lang: str = "en",
    rate: int = 150,
    volume: float = 1.0,
    voice: Optional[str] = None,
) -> dict:
    """Try multiple TTS backends in order of preference."""
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # 1. pyttsx3 (cross-platform, offline)
    result = tts_pyttsx3(text, output_file, rate=rate, volume=volume)
    if result["status"] in ("ok", "error"):
        return result

    # 2. macOS say
    result = tts_say(text, output_file, voice=voice, rate=rate)
    if result["status"] in ("ok", "error"):
        return result

    # 3. Windows PowerShell SAPI
    result = tts_powershell(text, output_file, rate=max(-10, min(10, (rate - 150) // 25)))
    if result["status"] in ("ok", "error"):
        return result

    # 4. espeak-ng
    result = tts_espeak(text, output_file, lang=lang, speed=rate)
    if result["status"] in ("ok", "error"):
        return result

    return {
        "status": "error",
        "error": "No TTS engine available. Install one of:\n"
                 "  pip install pyttsx3\n"
                 "  brew install espeak-ng  (macOS)\n"
                 "  sudo apt install espeak-ng  (Linux)",
    }


@click.group()
@click.option("--verbose", "-v", is_flag=True)
@click.pass_context
def cli(ctx, verbose):
    """文字轉語音 — convert text to speech audio file."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


@cli.command()
@click.option("--text", "-t", default=None, help="Text to synthesize")
@click.option("--input-file", "-i", default=None, help="Text file to read and synthesize")
@click.option("--output-file", "-o", required=True, help="Output audio file (WAV/MP3)")
@click.option("--lang", "-l", default="en", show_default=True, help="Language code (e.g. en, zh, ja)")
@click.option("--rate", default=150, show_default=True, help="Speech rate (words per minute)")
@click.option("--volume", default=1.0, show_default=True, type=click.FloatRange(0.0, 1.0),
              help="Volume (0.0-1.0)")
@click.option("--voice", default=None, help="Voice name (engine-specific)")
@click.option("--dry-run", is_flag=True, help="Show what would be done")
@click.pass_context
def run(ctx, text, input_file, output_file, lang, rate, volume, voice, dry_run):
    """Convert text to speech and save as audio file."""
    if not text and not input_file:
        console.print("[red]Error:[/red] Provide --text or --input-file")
        sys.exit(1)

    if input_file:
        src = Path(input_file)
        if not src.exists():
            console.print(f"[red]File not found:[/red] {src}")
            sys.exit(1)
        content = src.read_text(encoding="utf-8").strip()
    else:
        content = text

    if not content:
        console.print("[red]Error:[/red] Text is empty")
        sys.exit(1)

    out = Path(output_file)

    if dry_run:
        result = {
            "dry_run": True,
            "text_length": len(content),
            "output": str(out),
            "lang": lang,
            "rate": rate,
        }
    else:
        console.print(f"[cyan]Synthesizing[/cyan] {len(content)} chars → {out.name}...")
        result = text_to_speech(content, out, lang=lang, rate=rate, volume=volume, voice=voice)
        if result["status"] == "ok":
            console.print(Panel(
                f"[green]Done![/green]  {result['output']}  (engine: {result.get('engine', 'unknown')})",
                title="text-tts"
            ))

    click.echo(json.dumps({"status": "ok", "data": result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
