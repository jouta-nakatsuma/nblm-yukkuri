from __future__ import annotations
import re, subprocess
from pathlib import Path

def run(cmd: list[str], check: bool=True) -> None:
    print("[RUN]", " ".join(cmd))
    subprocess.run(cmd, check=check)

def which(bin_name: str) -> str | None:
    from shutil import which as _which
    return _which(bin_name)

JP_SENT_SPLIT = re.compile(r"(?<=[。！？\?])\s*")

def split_japanese_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in JP_SENT_SPLIT.split(text) if p.strip()]
    return parts

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)
