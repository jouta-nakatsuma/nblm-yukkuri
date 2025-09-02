#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
import argparse
from pathlib import Path

NOTTA_LINE = re.compile(
    r"^\s*話者\s*(\d+)\s+(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\s*$"
)

def _to_ms(t):
    h, m, s_ms = t.split(":")
    s, ms = s_ms.split(",")
    return (int(h)*3600 + int(m)*60 + int(s))*1000 + int(ms)

def parse_notta_srt(text):
    lines = text.splitlines()
    i, n = 0, len(lines)
    entries = []
    while i < n:
        # インデックス行 (数字だけ) をスキップ
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
        # 空行まで進める
        while i < n and lines[i].strip() == "":
            i += 1
        if buf:
            entries.append({
                "speaker": spk,
                "start_ms": _to_ms(start),
                "end_ms": _to_ms(end),
                "text": " ".join(buf)
            })
    return entries

def main():
    ap = argparse.ArgumentParser(
        description="Convert Notta SRT (話者1/2) -> A/B tagged text for dual TTS")
    ap.add_argument("--input", "-i", required=True, help="Notta SRT path")
    ap.add_argument("--output", "-o", required=True, help="Tagged TXT path")
    ap.add_argument("--segments-json", help="(optional) dump segments json next to output")
    ap.add_argument("--map", default="1=A,2=B",
                    help="speaker mapping like '1=A,2=B' (default)")
    args = ap.parse_args()

    srt = Path(args.input).read_text(encoding="utf-8")
    segs = parse_notta_srt(srt)

    # mapping
    m = {}
    for kv in args.map.split(","):
        k, v = kv.split("=")
        m[k.strip()] = v.strip().upper()
    if not all(x in {"A","B"} for x in m.values()):
        raise SystemExit("map は A/B に割り当ててください（例: 1=A,2=B）")

    # 連続同話者は結合して軽量化
    merged = []
    for e in segs:
        role = m.get(e["speaker"], "A")
        if merged and merged[-1]["role"] == role:
            merged[-1]["text"] += " " + e["text"]
            merged[-1]["end_ms"] = e["end_ms"]
        else:
            merged.append({
                "role": role,
                "text": e["text"],
                "start_ms": e["start_ms"],
                "end_ms": e["end_ms"],
            })

    # A/Bタグ付きテキスト出力（TTS が拾いやすいシンプル形式）
    out = ["#DUAL_DIALOGUE from Notta SRT (role tags: [A]/[B])"]
    for e in merged:
        out.append(f"[{e['role']}] {e['text']}")
    Path(args.output).write_text("\n".join(out) + "\n", encoding="utf-8")

    # （任意）セグメントJSONも保存
    if args.segments_json:
        import json
        Path(args.segments_json).write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"wrote: {args.output}")
    if args.segments_json:
        print(f"wrote: {args.segments_json}")

if __name__ == "__main__":
    main()
