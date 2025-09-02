# nblm_auto/lipsync_rhubarb.py
from __future__ import annotations
import json
from pathlib import Path
from typing import List, Tuple

def _load_rhubarb_json(path: Path) -> dict:
    """
    Rhubarb の JSON は通常1オブジェクトだが、ツールやリダイレクト経由で
    複数JSONが連結される事故に備えて最後の {"mouthCues": ...} を拾う。
    """
    raw = Path(path).read_text(encoding="utf-8").strip()
    # 純粋JSONなら普通に読む
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 連結対策：最後の mouthCues を含むオブジェクトを抽出
    last = raw.rfind('{"mouthCues"')
    if last == -1:
        raise ValueError(f"Invalid rhubarb json: {path}")
    # ざっくり波括弧マッチ（末尾まで）
    chunk = raw[last:]
    # 最初の ']}'' までで切る
    end = chunk.find("]}")
    if end == -1:
        raise ValueError(f"Truncated rhubarb json: {path}")
    chunk = chunk[: end + 2]
    return json.loads(chunk)

def visemes_to_openclose(in_json: Path, min_dur: float = 0.05) -> List[Tuple[float, float, bool]]:
    """
    Rhubarb JSON -> [(t0, t1, is_open), ...]
    簡易規則: value != 'X' を「口開き」とみなす。
    min_dur より短いブロックは隣接とマージしてノイズ低減。
    """
    data = _load_rhubarb_json(in_json)
    cues = data.get("mouthCues", [])
    if not cues:
        return []

    # まず生の open/close に落とす
    raw = []
    for c in cues:
        t0 = float(c["start"])
        t1 = float(c["end"])
        val = str(c["value"])
        is_open = (val != "X")
        if t1 > t0:
            raw.append((t0, t1, is_open))

    if not raw:
        return []

    # 連続する同状態を結合
    merged: List[Tuple[float, float, bool]] = []
    cur_t0, cur_t1, cur_state = raw[0]
    for t0, t1, st in raw[1:]:
        if st == cur_state and t0 <= cur_t1 + 1e-4:
            cur_t1 = t1
        else:
            merged.append((cur_t0, cur_t1, cur_state))
            cur_t0, cur_t1, cur_state = t0, t1, st
    merged.append((cur_t0, cur_t1, cur_state))

    # 短すぎる区間を隣接へマージ
    def append_smart(buf: List[Tuple[float, float, bool]], seg):
        if not buf:
            buf.append(seg); return
        t0, t1, st = seg
        if (t1 - t0) < min_dur and len(buf) > 0:
            bt0, bt1, bst = buf[-1]
            if bst == st:
                buf[-1] = (bt0, t1, bst)
            else:
                # 直前と別状態なら「より長い方へ」寄せる（単純に直前延長）
                buf[-1] = (bt0, t1, bst)
        else:
            buf.append(seg)

    cleaned: List[Tuple[float, float, bool]] = []
    for seg in merged:
        append_smart(cleaned, seg)

    return cleaned
