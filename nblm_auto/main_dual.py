# nblm_auto/main_dual.py
from __future__ import annotations
import argparse
from pathlib import Path
from typing import Optional
from .lipsync_rhubarb import visemes_to_openclose
from .render import render_two_chars_dual

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, help="NotebookLM出力の音声（mix.wav 等）")
    p.add_argument("--config", default="config.yml")  # 未使用だが互換のため残す
    p.add_argument("--charA", required=True, help="assets/characters/charA")
    p.add_argument("--charB", required=True, help="assets/characters/charB")
    p.add_argument("--out", required=True, help="出力mp4")
    p.add_argument("--stage", choices=["render"], default="render")
    p.add_argument("--transcript", help="NottaのSRT（final_std.srt 推奨）")
    return p.parse_args()

def find_viseme_json(default_path: Path) -> Path:
    """
    既定は data/lipsync/*.json。
    互換のため data/visemes/*.json があればそれも許容。
    """
    if default_path.exists():
        return default_path
    alt = Path("data/visemes") / default_path.name
    if alt.exists():
        return alt
    raise FileNotFoundError(f"Viseme JSON not found: {default_path} or {alt}")

def main():
    args = parse_args()
    assert args.stage == "render"

    audio = Path(args.input)
    charA_dir = Path(args.charA)
    charB_dir = Path(args.charB)
    out_path = Path(args.out)
    srt_path: Optional[Path] = Path(args.transcript) if args.transcript else None

    # ここでWhisperなどは呼ばない
    jsonA = find_viseme_json(Path("data/lipsync/charA.json"))
    jsonB = find_viseme_json(Path("data/lipsync/charB.json"))

    visA = visemes_to_openclose(jsonA, min_dur=0.05)
    visB = visemes_to_openclose(jsonB, min_dur=0.05)

    # デバッグ出力
    def _summ(tl):
        opens = sum(1 for *_, st in tl if st)
        closes = len(tl) - opens
        return f"{len(tl)} segs (open={opens}, close={closes})"
    print(f"[LIPSYNC] A: {jsonA} -> { _summ(visA) }")
    print(f"[LIPSYNC] B: {jsonB} -> { _summ(visB) }")

    render_two_chars_dual(
        audio_path=audio,
        charA_dir=charA_dir,
        charB_dir=charB_dir,
        viseme_timeline_A=visA,
        viseme_timeline_B=visB,
        out_path=out_path,
        srt_path=srt_path,
    )
    print(f"[DONE] {out_path}")

if __name__ == "__main__":
    main()
