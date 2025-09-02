#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_staging_patch.py
----------------------
main_dual.py に「段階実行(staging)」を追加します。

追加される機能:
  --stage {transcribe, tts, render, all}
  --transcript path/to/edited.(srt|json|txt)

使い方:
  1) プロジェクト直下にこのファイルを置く
  2) source .venv311/bin/activate
  3) python apply_staging_patch.py
  4) 以降、--stage / --transcript を付けて main_dual を実行
"""

from __future__ import annotations
import sys, shutil
from pathlib import Path

ROOT = Path(".").resolve()
PKG = ROOT / "nblm_auto"
MAIN = PKG / "main_dual.py"

def must_exist():
    if not PKG.exists():
        print("ERROR: nblm_auto/ not found. Run in project root.", file=sys.stderr)
        sys.exit(1)
    if not MAIN.exists():
        print("ERROR: nblm_auto/main_dual.py not found. Apply the dual-speaker patch first.", file=sys.stderr)
        sys.exit(1)

NEW_MAIN = r"""
from __future__ import annotations
import argparse, json, yaml
from pathlib import Path
from .transcription import transcribe_with_whisper_cli
from .tts_voicevox import voicevox_tts_segments
from .lipsync_rhubarb import rhubarb_visemes, visemes_to_openclose
from .render import render_two_chars_dual
from .utils import split_japanese_sentences
import srt

def load_config(p: Path) -> dict:
    return yaml.safe_load(Path(p).read_text(encoding="utf-8"))

def build_alternate_segments(text: str, cfg: dict) -> list[dict]:
    sentences = [s for s in split_japanese_sentences(text) if s]
    A_id = int(cfg["characters"]["charA"]["speaker_id"])
    B_id = int(cfg["characters"]["charB"]["speaker_id"])
    start_with = cfg.get("dialogue",{}).get("start_with","A")
    turn = start_with
    segs = []
    for s in sentences:
        if turn == "A":
            segs.append({"text": s, "who": "A", "speaker_id": A_id})
            turn = "B"
        else:
            segs.append({"text": s, "who": "B", "speaker_id": B_id})
            turn = "A"
    return segs

def load_text_from_transcript(path: Path) -> str:
    suf = path.suffix.lower()
    if suf == ".json":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return "".join(seg.get("text","") for seg in data.get("segments", []))
    elif suf == ".srt":
        subs = list(srt.parse(Path(path).read_text(encoding="utf-8")))
        return "\n".join((s.content or "").strip() for s in subs)
    else:
        return Path(path).read_text(encoding="utf-8")

def do_transcribe(audio_path: Path, cfg: dict) -> dict:
    return transcribe_with_whisper_cli(
        audio_path, Path("data/transcripts"),
        model=cfg["pipeline"]["model"],
        language=cfg["pipeline"]["language"],
    )

def do_tts(full_text: str, cfg: dict):
    mix_wav, A_wav, B_wav, timings = voicevox_tts_segments(
        build_alternate_segments(full_text, cfg),
        engine_url=cfg["voicevox"]["engine_url"],
        speed_scale=float(cfg["voicevox"]["speed_scale"]),
        pitch_scale=float(cfg["voicevox"]["pitch_scale"]),
        intonation_scale=float(cfg["voicevox"]["intonation_scale"]),
        pause_between_sentences_ms=int(cfg["pipeline"]["pause_between_sentences_ms"]),
        out_mix_wav=Path("data/tts/narration.wav"),
        out_A_wav=Path("data/tts/charA.wav"),
        out_B_wav=Path("data/tts/charB.wav"),
    )
    return mix_wav, A_wav, B_wav

def do_render(mix_wav: Path, charA_dir: Path, charB_dir: Path, out_path: Path):
    visA = rhubarb_visemes(Path("data/tts/charA.wav"), Path("data/visemes/charA.json"))
    visB = rhubarb_visemes(Path("data/tts/charB.wav"), Path("data/visemes/charB.json"))
    timeline_A = visemes_to_openclose(visA)
    timeline_B = visemes_to_openclose(visB)
    out = render_two_chars_dual(
        audio_wav=mix_wav,
        viseme_timeline_A=timeline_A,
        viseme_timeline_B=timeline_B,
        charA_dir=charA_dir,
        charB_dir=charB_dir,
        out_path=out_path,
    )
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="NotebookLM音声ファイル（m4a/mp3/wav）")
    ap.add_argument("--config", default="config.yml")
    ap.add_argument("--charA", default="assets/characters/charA")
    ap.add_argument("--charB", default="assets/characters/charB")
    ap.add_argument("--out", default="output.mp4")
    ap.add_argument("--stage", choices=["all","transcribe","tts","render"], default="all")
    ap.add_argument("--transcript", help="編集済みの文字起こしを指定（.srt/.json/.txt）")
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    audio_path = Path(args.input)

    # Stage: TRANSCRIBE
    if args.stage in ("all","transcribe"):
        whisper_out = do_transcribe(audio_path, cfg)
        if args.stage == "transcribe":
            print("Transcription done:", whisper_out)
            return
    else:
        whisper_out = None

    # Determine full_text
    if args.transcript:
        full_text = load_text_from_transcript(Path(args.transcript))
    else:
        if whisper_out is None:
            whisper_out = do_transcribe(audio_path, cfg)
        data = json.loads(Path(whisper_out["json"]).read_text(encoding="utf-8"))
        full_text = "".join(seg["text"] for seg in data.get("segments", []))

    # Stage: TTS
    if args.stage in ("all","tts"):
        mix_wav, A_wav, B_wav = do_tts(full_text, cfg)
        if args.stage == "tts":
            print("TTS done:", mix_wav, A_wav, B_wav)
            return

    # Stage: RENDER
    mix_wav = Path("data/tts/narration.wav")
    out = do_render(mix_wav, Path(args.charA), Path(args.charB), Path(args.out))
    print("DONE:", out)

if __name__ == "__main__":
    main()
"""

def apply():
    must_exist()
    # Backup existing main_dual.py
    backup = MAIN.with_suffix(".py.bak")
    if not backup.exists():
        shutil.copy2(MAIN, backup)
        print(f"[OK] Backup created: {backup.name}")
    MAIN.write_text(NEW_MAIN, encoding="utf-8")
    print("[OK] Patched nblm_auto/main_dual.py with staging support.")
    print("Usage examples:")
    print("  # 1) Transcribe only")
    print("  python -m nblm_auto.main_dual --stage transcribe --input data/input_audio/sample.m4a --config config.yml")
    print("  # 2) TTS only from edited SRT")
    print("  python -m nblm_auto.main_dual --stage tts --input data/input_audio/sample.m4a --config config.yml --transcript data/transcripts/edited.srt")
    print("  # 3) Render only (use existing data/tts/*.wav)")
    print("  python -m nblm_auto.main_dual --stage render --input data/input_audio/sample.m4a --config config.yml")

if __name__ == "__main__":
    apply()
