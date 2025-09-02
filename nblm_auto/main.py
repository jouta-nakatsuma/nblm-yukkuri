from __future__ import annotations
import argparse, json, yaml
from pathlib import Path
from .transcription import transcribe_with_whisper_cli
from .tts_voicevox import voicevox_tts
from .lipsync_rhubarb import rhubarb_visemes, visemes_to_openclose
from .render import render_two_chars

def load_config(p: Path) -> dict:
    return yaml.safe_load(Path(p).read_text(encoding="utf-8"))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="NotebookLM音声ファイル（m4a/mp3/wav）")
    ap.add_argument("--config", default="config.yml")
    ap.add_argument("--charA", default="assets/characters/charA")
    ap.add_argument("--charB", default="assets/characters/charB")
    ap.add_argument("--out", default="output.mp4")
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    whisper_out = transcribe_with_whisper_cli(Path(args.input), Path("data/transcripts"), model=cfg["pipeline"]["model"], language=cfg["pipeline"]["language"])

    data = json.loads(Path(whisper_out["json"]).read_text(encoding="utf-8"))
    full_text = "".join(seg["text"] for seg in data.get("segments", []))

    wav = voicevox_tts(
        full_text,
        speaker_id=int(cfg["voicevox"]["narrator_speaker_id"]),
        engine_url=cfg["voicevox"]["engine_url"],
        speed_scale=float(cfg["voicevox"]["speed_scale"]),
        pitch_scale=float(cfg["voicevox"]["pitch_scale"]),
        intonation_scale=float(cfg["voicevox"]["intonation_scale"]),
        pause_between_sentences_ms=int(cfg["pipeline"]["pause_between_sentences_ms"]),
        out_wav=Path("data/tts/narration.wav")
    )
    vis = rhubarb_visemes(wav, Path("data/visemes/narration.json"))
    timeline = visemes_to_openclose(vis)

    out = render_two_chars(
        audio_wav=wav,
        viseme_timeline=timeline,
        charA_dir=Path(args.charA),
        charB_dir=Path(args.charB),
        out_path=Path(args.out),
    )
    print("DONE:", out)

if __name__ == "__main__":
    main()
