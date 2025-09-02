from __future__ import annotations
import json, subprocess, srt, datetime
from pathlib import Path
from .utils import run, ensure_dir

def transcribe_with_whisper_cli(audio_path: Path, out_dir: Path, model: str="small", language: str="ja") -> dict:
    ensure_dir(out_dir)
    cmd = [
        "whisper", str(audio_path),
        "--model", model,
        "--language", language,
        "--task", "transcribe",
        "--output_format", "json",
        "-o", str(out_dir)
    ]
    run(cmd)
    base = audio_path.name + ".json"
    json_path = out_dir / base
    if not json_path.exists():
        alt = out_dir / (audio_path.stem + ".json")
        if alt.exists():
            json_path = alt
        else:
            raise FileNotFoundError(f"Whisper JSON not found: {json_path} / {alt}")
    data = json.loads(json_path.read_text(encoding="utf-8"))
    srt_path = out_dir / (audio_path.stem + ".srt")
    subs = []
    for i, seg in enumerate(data.get("segments", []), start=1):
        start = datetime.timedelta(seconds=seg["start"])
        end = datetime.timedelta(seconds=seg["end"])
        text = seg["text"].strip()
        subs.append(srt.Subtitle(index=i, start=start, end=end, content=text))
    srt_str = srt.compose(subs)
    srt_path.write_text(srt_str, encoding="utf-8")
    return {"json": str(json_path), "srt": str(srt_path)}
