#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
sub-translate — 字幕翻譯器
解決問題：字幕翻譯
"""

import json
import sys
import re
import os
from pathlib import Path
from typing import List, Optional, Tuple
import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import track

console = Console()

# Language name mapping for display
LANG_NAMES = {
    "zh": "Chinese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "ru": "Russian",
    "ar": "Arabic",
    "vi": "Vietnamese",
    "th": "Thai",
}


def parse_srt(content: str) -> List[dict]:
    """Parse SRT content into list of subtitle blocks."""
    blocks = []
    pattern = re.compile(
        r"(\d+)\s*\n"
        r"(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*\n"
        r"([\s\S]*?)(?=\n\n\d+\s*\n|\Z)",
        re.MULTILINE
    )
    for m in pattern.finditer(content.strip() + "\n\n"):
        blocks.append({
            "index": int(m.group(1)),
            "start": m.group(2),
            "end": m.group(3),
            "text": m.group(4).strip(),
        })
    return blocks


def blocks_to_srt(blocks: List[dict]) -> str:
    """Convert subtitle blocks back to SRT string."""
    lines = []
    for b in blocks:
        lines.append(str(b["index"]))
        lines.append(f"{b['start']} --> {b['end']}")
        lines.append(b["text"])
        lines.append("")
    return "\n".join(lines)


def translate_with_api(texts: List[str], target_lang: str, source_lang: str = "auto") -> List[str]:
    """
    Translate text list using an LLM API if MOONSHOT_API_KEY or OPENAI_API_KEY is set.
    Falls back to a stub that marks text as [untranslated] if no key is configured.
    """
    api_key = os.environ.get("MOONSHOT_API_KEY") or os.environ.get("OPENAI_API_KEY")

    if api_key:
        try:
            import httpx
            batch = "\n---\n".join(texts)
            lang_name = LANG_NAMES.get(target_lang, target_lang)
            prompt = (
                f"Translate the following subtitle lines to {lang_name}. "
                f"Keep one translation per segment, separated by '---'. "
                f"Preserve line breaks within each segment. Output only translations:\n\n{batch}"
            )
            # Try Moonshot/OpenAI-compatible endpoint
            base_url = "https://api.moonshot.cn/v1" if os.environ.get("MOONSHOT_API_KEY") else "https://api.openai.com/v1"
            resp = httpx.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": "moonshot-v1-8k" if "moonshot" in base_url else "gpt-3.5-turbo",
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=60,
            )
            resp.raise_for_status()
            translated = resp.json()["choices"][0]["message"]["content"]
            parts = translated.split("---")
            return [p.strip() for p in parts][:len(texts)]
        except Exception as exc:
            console.print(f"[yellow]API translation failed ({exc}), using stub.[/yellow]")

    # Stub: prefix each line with target lang tag
    return [f"[{target_lang.upper()}] {t}" for t in texts]


def translate_srt(
    input_file: Path,
    output_file: Path,
    target_lang: str,
    source_lang: str = "auto",
    batch_size: int = 20,
) -> dict:
    """Translate an SRT file to the target language."""
    content = input_file.read_text(encoding="utf-8")
    blocks = parse_srt(content)
    if not blocks:
        return {"status": "error", "error": "No subtitle blocks found in file"}

    # Translate in batches
    for i in range(0, len(blocks), batch_size):
        batch = blocks[i:i + batch_size]
        texts = [b["text"] for b in batch]
        translated = translate_with_api(texts, target_lang, source_lang)
        for j, block in enumerate(batch):
            if j < len(translated):
                block["text"] = translated[j]

    output_file.write_text(blocks_to_srt(blocks), encoding="utf-8")
    return {
        "status": "ok",
        "output": str(output_file),
        "subtitle_count": len(blocks),
        "target_lang": target_lang,
    }


@click.group()
@click.option("--verbose", "-v", is_flag=True)
@click.pass_context
def cli(ctx, verbose):
    """字幕翻譯器 — translate SRT subtitle files between languages."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


@cli.command()
@click.option("--input-file", "-i", required=True, help="Input SRT file")
@click.option("--output-file", "-o", default=None, help="Output SRT file")
@click.option("--target-lang", "-t", required=True,
              help="Target language code (e.g. zh, en, ja, fr)")
@click.option("--source-lang", "-s", default="auto", show_default=True,
              help="Source language code or 'auto'")
@click.option("--batch-size", default=20, show_default=True,
              help="Number of subtitles per API call")
@click.option("--dry-run", is_flag=True, help="Show what would be done")
@click.pass_context
def run(ctx, input_file, output_file, target_lang, source_lang, batch_size, dry_run):
    """Translate SRT subtitle file to target language."""
    src = Path(input_file)
    if not src.exists():
        console.print(f"[red]File not found:[/red] {src}")
        sys.exit(1)

    out = Path(output_file) if output_file else src.parent / f"{src.stem}.{target_lang}.srt"

    if dry_run:
        result = {"status": "ok", "dry_run": True, "input": str(src), "output": str(out), "target_lang": target_lang}
    else:
        console.print(f"[cyan]Translating[/cyan] {src.name} → {target_lang}...")
        result = translate_srt(src, out, target_lang=target_lang, source_lang=source_lang, batch_size=batch_size)
        if result["status"] == "ok":
            console.print(Panel(
                f"[green]Done![/green]  {result['subtitle_count']} subtitles → {out}",
                title="sub-translate"
            ))

    click.echo(json.dumps({"status": "ok", "data": result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
