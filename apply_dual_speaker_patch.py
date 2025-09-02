#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_dual_speaker_patch.py
---------------------------------
安全に「2話者掛け合い」対応を追加するパッチ適用スクリプト。
- 既存ファイルは破壊的に書き換えず、追加関数や main_dual.py を新設する方針。
- 何度実行しても冪等に近い動作を目指す。

使い方:
1) 本ファイルをプロジェクトルート（config.yml と nblm_auto/ がある場所）に置く。
2) `python apply_dual_speaker_patch.py` を実行。
3) 実行後は次のように起動：
   python -m nblm_auto.main_dual \
     --input data/input_audio/nblm.m4a \
     --config config.yml \
     --charA assets/characters/charA \
     --charB assets/characters/charB \
     --out output.mp4
"""

from __future__ import annotations
import sys, json, re, os
from pathlib import Path

try:
    import yaml
except Exception as e:
    print("[ERROR] PyYAML が必要です。`pip install PyYAML` を先に実行してください。", file=sys.stderr)
    raise

ROOT = Path(".").resolve()
PKG = ROOT / "nblm_auto"
CFG = ROOT / "config.yml"

def must_exist():
    if not PKG.exists():
        print("ERROR: nblm_auto/ が見つかりません。プロジェクト直下で実行してください。", file=sys.stderr)
        sys.exit(1)
    if not CFG.exists():
        print("ERROR: config.yml が見つかりません。プロジェクト直下で実行してください。", file=sys.stderr)
        sys.exit(1)

def extend_config():
    data = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    changed = False

    # characters
    if "characters" not in data:
        data["characters"] = {
            "charA": {"name": "metan", "speaker_id": 3},
            "charB": {"name": "kenzaki_shiyu", "speaker_id": 13},
        }
        changed = True
    else:
        if "charA" not in data["characters"]:
            data["characters"]["charA"] = {"name": "metan", "speaker_id": 3}
            changed = True
        if "charB" not in data["characters"]:
            data["characters"]["charB"] = {"name": "kenzaki_shiyu", "speaker_id": 13}
            changed = True

    # dialogue
    if "dialogue" not in data:
        data["dialogue"] = {"enabled": True, "mode": "alternate", "start_with": "A"}
        changed = True

    if changed:
        CFG.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        print("[OK] config.yml を拡張: characters.charA/charB, dialogue.* を追加/補完しました。")
    else:
        print("[SKIP] config.yml は既に必要なキーを含んでいます。")

def append_if_missing(path: Path, marker: str, chunk: str):
    text = path.read_text(encoding="utf-8")
    if marker in text:
        print(f"[SKIP] {path.name}: 既に {marker} が存在。")
        return
    text = text.rstrip() + "\n\n" + chunk.strip() + "\n"
    path.write_text(text, encoding="utf-8")
    print(f"[OK] {path.name}: 追記完了 ({marker})。")

def patch_tts_voicevox():
    p = PKG / "tts_voicevox.py"
    if not p.exists():
        print("[ERROR] nblm_auto/tts_voicevox.py が見つかりません。", file=sys.stderr); sys.exit(1)
    marker = "def voicevox_tts_segments("
    chunk = """
def voicevox_tts_segments(
    segments: list[dict],
    engine_url: str="http://127.0.0.1:50021",
    speed_scale: float=1.0,
    pitch_scale: float=0.0,
    intonation_scale: float=1.0,
    pause_between_sentences_ms: int=150,
    out_mix_wav: Path | None=None,
    out_A_wav: Path | None=None,
    out_B_wav: Path | None=None,
) -> tuple[Path, Path, Path, list[dict]]:
    \"\"\"
    segments: [{\"text\": \"...\", \"who\": \"A\"|\"B\", \"speaker_id\": int}, ...]
    Returns: (mix_wav, A_wav, B_wav, timings)
      timings = [{\"start\":float,\"end\":float,\"who\":\"A\"|\"B\",\"text\":str}, ...]
    \"\"\"
    from pydub import AudioSegment
    import requests, io
    from .utils import ensure_dir
    ensure_dir(Path(\"data/tts\"))
    A = AudioSegment.silent(duration=0)
    B = AudioSegment.silent(duration=0)
    MIX = AudioSegment.silent(duration=0)
    timings = []
    t_cur = 0
    for seg in segments:
        text = (seg.get(\"text\") or \"\").strip()
        if not text:
            continue
        spk  = int(seg[\"speaker_id\"])
        who  = seg.get(\"who\",\"A\")
        # Query
        q = requests.post(f\"{engine_url}/audio_query\",
                          params={\"text\": text, \"speaker\": spk}, timeout=30)
        q.raise_for_status()
        qj = q.json()
        qj[\"speedScale\"] = speed_scale
        qj[\"pitchScale\"] = pitch_scale
        qj[\"intonationScale\"] = intonation_scale
        s = requests.post(f\"{engine_url}/synthesis\",
                          params={\"speaker\": spk, \"enable_interrogative_upspeak\": True},
                          json=qj, timeout=120)
        s.raise_for_status()
        wav = AudioSegment.from_wav(io.BytesIO(s.content))
        # Append with optional inter-sentence pause
        if who == \"A\":
            A += wav
            B += AudioSegment.silent(duration=len(wav))
        else:
            B += wav
            A += AudioSegment.silent(duration=len(wav))
        MIX += wav
        t_start = t_cur / 1000.0
        t_cur += len(wav)
        # pause
        if pause_between_sentences_ms > 0:
            A += AudioSegment.silent(duration=pause_between_sentences_ms)
            B += AudioSegment.silent(duration=pause_between_sentences_ms)
            MIX += AudioSegment.silent(duration=pause_between_sentences_ms)
            t_end = t_cur / 1000.0
            t_cur += pause_between_sentences_ms
        else:
            t_end = t_cur / 1000.0
        timings.append({\"start\": t_start, \"end\": t_end, \"who\": who, \"text\": text})

    if out_mix_wav is None: out_mix_wav = Path(\"data/tts/narration.wav\")
    if out_A_wav is None:   out_A_wav   = Path(\"data/tts/charA.wav\")
    if out_B_wav is None:   out_B_wav   = Path(\"data/tts/charB.wav\")
    ensure_dir(out_mix_wav.parent)
    MIX.export(out_mix_wav, format=\"wav\")
    A.export(out_A_wav, format=\"wav\")
    B.export(out_B_wav, format=\"wav\")
    return out_mix_wav, out_A_wav, out_B_wav, timings
"""
    append_if_missing(p, marker, chunk)

def patch_render():
    p = PKG / "render.py"
    if not p.exists():
        print("[ERROR] nblm_auto/render.py が見つかりません。", file=sys.stderr); sys.exit(1)
    marker = "def render_two_chars_dual("
    chunk = """
from moviepy.editor import (AudioFileClip, ImageClip, CompositeVideoClip, ColorClip)
def render_two_chars_dual(
    audio_wav: Path,
    viseme_timeline_A: list[tuple[float, str]],
    viseme_timeline_B: list[tuple[float, str]],
    charA_dir: Path,
    charB_dir: Path,
    out_path: Path,
    width: int=1920,
    height: int=1080,
    fps: int=30,
    bg_color=(250,250,250)
) -> Path:
    audio = AudioFileClip(str(audio_wav))
    duration = audio.duration

    baseA = ImageClip(str(Path(charA_dir) / "base.png")).set_duration(duration).set_position((int(width*0.1), int(height*0.25)))
    baseB = ImageClip(str(Path(charB_dir) / "base.png")).set_duration(duration).set_position((int(width*0.6), int(height*0.25)))
    mouthA_open = ImageClip(str(Path(charA_dir) / "mouth_open.png")).set_position((int(width*0.22), int(height*0.52)))
    mouthA_closed = ImageClip(str(Path(charA_dir) / "mouth_closed.png")).set_position((int(width*0.22), int(height*0.52)))
    mouthB_open = ImageClip(str(Path(charB_dir) / "mouth_open.png")).set_position((int(width*0.72), int(height*0.52)))
    mouthB_closed = ImageClip(str(Path(charB_dir) / "mouth_closed.png")).set_position((int(width*0.72), int(height*0.52)))

    bg = ColorClip(size=(width, height), color=bg_color).set_duration(duration)

    def mouth_clips(open_img: ImageClip, closed_img: ImageClip, timeline):
        clips = []
        last_t = 0.0
        state = "closed"
        for t, st in timeline:
            if t > last_t:
                img = open_img if state == "open" else closed_img
                clips.append(img.set_start(last_t).set_end(t))
            state = st
            last_t = t
        img = open_img if state == "open" else closed_img
        clips.append(img.set_start(last_t).set_end(duration))
        return clips

    mouthA_clips = mouth_clips(mouthA_open, mouthA_closed, viseme_timeline_A)
    mouthB_clips = mouth_clips(mouthB_open, mouthB_closed, viseme_timeline_B)

    comp = CompositeVideoClip([bg, baseA, baseB, *mouthA_clips, *mouthB_clips], size=(width, height))
    comp = comp.set_audio(audio)
    comp.write_videofile(str(out_path), codec="libx264", audio_codec="aac", fps=fps, threads=4)
    return out_path
"""
    append_if_missing(p, marker, chunk)

def write_main_dual():
    p = PKG / "main_dual.py"
    if p.exists():
        print("[SKIP] main_dual.py は既に存在します。")
        return
    code = """
from __future__ import annotations
import argparse, json, yaml
from pathlib import Path
from .transcription import transcribe_with_whisper_cli
from .tts_voicevox import voicevox_tts_segments
from .lipsync_rhubarb import rhubarb_visemes, visemes_to_openclose
from .render import render_two_chars_dual
from .utils import split_japanese_sentences

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

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="NotebookLM音声ファイル（m4a/mp3/wav）")
    ap.add_argument("--config", default="config.yml")
    ap.add_argument("--charA", default="assets/characters/charA")
    ap.add_argument("--charB", default="assets/characters/charB")
    ap.add_argument("--out", default="output.mp4")
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    whisper_out = transcribe_with_whisper_cli(Path(args.input), Path("data/transcripts"),
                                             model=cfg["pipeline"]["model"], language=cfg["pipeline"]["language"])

    data = json.loads(Path(whisper_out["json"]).read_text(encoding="utf-8"))
    full_text = "".join(seg["text"] for seg in data.get("segments", []))

    if not cfg.get("dialogue",{}).get("enabled", False):
        print("dialogue.enabled が false のため、この main_dual は何もしません。config.yml を確認してください。")
        return

    segs = build_alternate_segments(full_text, cfg)
    mix_wav, A_wav, B_wav, timings = voicevox_tts_segments(
        segs,
        engine_url=cfg["voicevox"]["engine_url"],
        speed_scale=float(cfg["voicevox"]["speed_scale"]),
        pitch_scale=float(cfg["voicevox"]["pitch_scale"]),
        intonation_scale=float(cfg["voicevox"]["intonation_scale"]),
        pause_between_sentences_ms=int(cfg["pipeline"]["pause_between_sentences_ms"]),
        out_mix_wav=Path("data/tts/narration.wav"),
        out_A_wav=Path("data/tts/charA.wav"),
        out_B_wav=Path("data/tts/charB.wav"),
    )
    visA = rhubarb_visemes(A_wav, Path("data/visemes/charA.json"))
    visB = rhubarb_visemes(B_wav, Path("data/visemes/charB.json"))
    timeline_A = visemes_to_openclose(visA)
    timeline_B = visemes_to_openclose(visB)

    out = render_two_chars_dual(
        audio_wav=mix_wav,
        viseme_timeline_A=timeline_A,
        viseme_timeline_B=timeline_B,
        charA_dir=Path(args.charA),
        charB_dir=Path(args.charB),
        out_path=Path(args.out),
    )
    print("DONE:", out)

if __name__ == "__main__":
    main()
"""
    p.write_text(code, encoding="utf-8")
    print("[OK] main_dual.py を作成しました.")

def main():
    must_exist()
    extend_config()
    patch_tts_voicevox()
    patch_render()
    write_main_dual()
    print("\n[READY] 2話者掛け合い対応の準備ができました。実行例:\n"
          "  python -m nblm_auto.main_dual --input data/input_audio/nblm.m4a --config config.yml "
          "--charA assets/characters/charA --charB assets/characters/charB --out output.mp4\n")

if __name__ == "__main__":
    main()
# (Removed erroneous lines causing unterminated string literal error)
