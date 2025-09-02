#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse, json, os, re, shutil, subprocess, tempfile
from pathlib import Path

NOTTA_LINE = re.compile(
    r"^\s*話者\s*(\d+)\s+(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\s*$"
)

def to_ms(t):
    h, m, s_ms = t.split(":")
    s, ms = s_ms.split(",")
    return (int(h)*3600 + int(m)*60 + int(s))*1000 + int(ms)

def parse_notta_srt(path):
    txt = Path(path).read_text(encoding="utf-8")
    lines = txt.splitlines()
    i, n = 0, len(lines)
    segs = []
    while i < n:
        # 数字だけのインデックス行をスキップ
        if re.match(r"^\s*\d+\s*$", lines[i]):
            i += 1
            if i >= n: break
        m = NOTTA_LINE.match(lines[i])
        if not m:
            i += 1
            continue
        spk, start, end = m.group(1), m.group(2), m.group(3)
        i += 1
        buf = []
        while i < n and lines[i].strip() != "":
            buf.append(lines[i].strip())
            i += 1
        # 空行スキップ
        while i < n and lines[i].strip() == "":
            i += 1
        text = " ".join(buf).strip()
        if text:
            segs.append({
                "speaker": spk,
                "start_ms": to_ms(start),
                "end_ms": to_ms(end),
                "text": text
            })
    return segs

def which(cmd):
    p = shutil.which(cmd)
    return p if p else None

def run(cmd):
    subprocess.run(cmd, check=True)

def slice_wav(src_audio, start_ms, end_ms, dst_wav):
    # ffmpegで区間切り出し（-ss は入力の前に置くと高速）
    ss = f"{start_ms/1000:.3f}"
    to = f"{end_ms/1000:.3f}"
    run([
        "ffmpeg","-v","error",
        "-ss", ss, "-to", to, "-i", src_audio,
        "-ac","1","-ar","16000","-vn","-y", dst_wav
    ])

def call_rhubarb(wav_path, out_json, bin_name):
    # 代表的な呼び出し：フォーマットJSON、静音トリミング弱め、出力ファイル指定
    # （nhubarb / rhubarb どちらでも同じ引数で動く想定）
    run([bin_name, "-f", "json", wav_path, "-o", out_json])

def merge_with_offset(mouth_json_path, offset_ms):
    data = json.loads(Path(mouth_json_path).read_text(encoding="utf-8"))
    cues = data.get("mouthCues", [])
    out = []
    for c in cues:
        # Rhubarb系のJSONは start/end 秒（float）のことが多い
        # 念のため両対応：存在するキーのみ変換
        cc = dict(c)
        if "start" in cc:
            cc["start"] = float(cc["start"]) + offset_ms/1000.0
        if "end" in cc:
            cc["end"] = float(cc["end"]) + offset_ms/1000.0
        out.append(cc)
    return out

def main():
    ap = argparse.ArgumentParser(
        description="Use original audio + Notta SRT to build lipsync JSON per speaker (A/B) via (n)rhubarb.")
    ap.add_argument("--audio", required=True, help="Original narration audio (wav/m4a/mp3...)")
    ap.add_argument("--srt", required=True, help="Notta SRT with '話者 1/2' lines")
    ap.add_argument("--outdir", default="data/lipsync", help="Output dir for lipsync JSONs")
    ap.add_argument("--map", default="1=A,2=B", help="Mapping like '1=A,2=B' (A=charA, B=charB)")
    ap.add_argument("--min-dur-ms", type=int, default=220, help="Skip too-short segments (default: 220ms)")
    args = ap.parse_args()

    segs = parse_notta_srt(args.srt)
    m = {}
    for kv in args.map.split(","):
        k, v = kv.split("=")
        m[k.strip()] = v.strip().upper()
    if not all(v in {"A","B"} for v in m.values()):
        raise SystemExit("--map は A/B に割り当ててください（例: 1=A,2=B）")

    rhubarb_bin = which("nhubarb") or which("rhubarb")
    if not rhubarb_bin:
        raise SystemExit("nhubarb / rhubarb が見つかりません。PATHを確認してください。")

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    charA, charB = [], []
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for idx, e in enumerate(segs, 1):
            if e["end_ms"] <= e["start_ms"]:
                continue
            if (e["end_ms"] - e["start_ms"]) < args.min_dur_ms:
                continue
            part = "A" if m.get(e["speaker"],"A") == "A" else "B"
            wav = td / f"seg_{idx:05d}.wav"
            js  = td / f"seg_{idx:05d}.json"
            slice_wav(args.audio, e["start_ms"], e["end_ms"], str(wav))
            try:
                call_rhubarb(str(wav), str(js), rhubarb_bin)
            except subprocess.CalledProcessError:
                # 音が極端に小さい/無音で失敗時はスキップ
                continue
            cues = merge_with_offset(str(js), e["start_ms"])
            if part == "A":
                charA.extend(cues)
            else:
                charB.extend(cues)

    def dump(name, cues):
        payload = {
            "metadata": {
                "source_audio": str(Path(args.audio).resolve()),
                "srt": str(Path(args.srt).resolve()),
                "speaker_map": args.map,
                "generator": "notta_srt_to_lipsync_with_nhubarb.py"
            },
            "mouthCues": cues
        }
        Path(outdir / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote {outdir/name}  (cues: {len(cues)})")

    dump("charA.json", charA)
    dump("charB.json", charB)

if __name__ == "__main__":
    main()
