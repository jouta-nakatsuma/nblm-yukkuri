# -*- coding: utf-8 -*-
from __future__ import annotations
import io
import math
import wave
from pathlib import Path
from typing import List, Dict, Tuple

import numpy as np
import requests


def _ensure_dir(p: Path):
    p.parent.mkdir(parents=True, exist_ok=True)


def _wav_bytes_to_np(wav_bytes: bytes) -> Tuple[int, np.ndarray]:
    """VOICEVOXの合成結果(WAV)バイト列を (sample_rate, int16 ndarray) に変換"""
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        ch = wf.getnchannels()
        sr = wf.getframerate()
        sampwidth = wf.getsampwidth()
        n = wf.getnframes()
        pcm = wf.readframes(n)
    if sampwidth != 2:
        raise RuntimeError(f"Unsupported sample width: {sampwidth}")
    arr = np.frombuffer(pcm, dtype=np.int16)
    if ch == 2:
        # モノラル化（平均）
        arr = ((arr[0::2].astype(np.int32) + arr[1::2].astype(np.int32)) // 2).astype(np.int16)
    return sr, arr


def _write_wav(path: Path, sr: int, data: np.ndarray):
    _ensure_dir(path)
    data = np.asarray(data, dtype=np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(data.tobytes())


def _make_silence(sr: int, ms: int) -> np.ndarray:
    length = int(sr * ms / 1000.0)
    return np.zeros(length, dtype=np.int16)


def _safe_chunks(text: str, max_len: int = 120) -> List[str]:
    """
    VOICEVOXの /audio_query は text をクエリに乗せる仕様のため、
    URLが長くなり過ぎるのを防ぐ目的でテキストを安全長に分割。
    句点や改行で優先的に分割し、最後の保険としてmax_lenで強制分割。
    """
    t = " ".join(text.replace("\r", "\n").split())  # 改行/連続空白→単一空白
    if len(t) <= max_len:
        return [t] if t else []

    out = []
    buf = ""
    breakers = set("。．.!？?、,，\n")
    for ch in t:
        buf += ch
        if ch in breakers and len(buf) >= max_len * 0.6:
            out.append(buf.strip())
            buf = ""
        elif len(buf) >= max_len:
            out.append(buf.strip())
            buf = ""
    if buf.strip():
        out.append(buf.strip())
    return out


def _request_audio(engine_url: str, text: str, speaker: int,
                   speed_scale: float, pitch_scale: float, intonation_scale: float) -> Tuple[int, np.ndarray]:
    """
    単一チャンクを VOICEVOX で合成して (sr, pcm int16) を返す。
    audio_query と synthesis の両方に speaker を確実に付ける。
    """
    # audio_query: POST + params (text, speaker)
    q = requests.post(
        f"{engine_url}/audio_query",
        params={"text": text, "speaker": int(speaker)},
        timeout=30,
    )
    # 400 は text が長すぎ・不正などで起こりうるので、ここで例外化
    q.raise_for_status()
    query = q.json()

    # パラメータ反映
    query["speedScale"] = float(speed_scale)
    query["pitchScale"] = float(pitch_scale)
    query["intonationScale"] = float(intonation_scale)

    # synthesis: POST + params (speaker), json=query
    s = requests.post(
        f"{engine_url}/synthesis",
        params={"speaker": int(speaker)},
        json=query,
        timeout=60,
    )
    s.raise_for_status()
    return _wav_bytes_to_np(s.content)


def voicevox_tts_segments(
    segments: List[Dict],
    engine_url: str = "http://127.0.0.1:50021",
    speed_scale: float = 1.0,
    pitch_scale: float = 0.0,
    intonation_scale: float = 1.0,
    pause_between_sentences_ms: int = 150,
    out_mix_wav: Path = Path("data/tts/narration.wav"),
    out_A_wav: Path = Path("data/tts/charA.wav"),
    out_B_wav: Path = Path("data/tts/charB.wav"),
):
    """
    segments: [{"text": "...", "who": "A" or "B", "speaker_id": 2 など}, ...]
    - 長文は _safe_chunks で小分けしてから合成
    - A/B それぞれの波形には、相手が話している区間の無音を挿入して全体長を揃える
    - 最後に A+B をミックスして narration.wav を作成
    戻り値: (out_mix_wav, out_A_wav, out_B_wav, timings)
      timings: [(who, start_sample, end_sample), ...]（簡易ログ）
    """
    timings = []
    sr_ref = None
    track_A = np.zeros(0, dtype=np.int16)
    track_B = np.zeros(0, dtype=np.int16)

    def _append_tracks(who: str, sr: int, pcm: np.ndarray):
        nonlocal track_A, track_B
        if who == "A":
            track_A = np.concatenate([track_A, pcm])
            track_B = np.concatenate([track_B, np.zeros_like(pcm)])
        else:
            track_A = np.concatenate([track_A, np.zeros_like(pcm)])
            track_B = np.concatenate([track_B, pcm])

    for seg in segments:
        text = str(seg.get("text", "")).strip()
        if not text:
            # 発話なし → そのままポーズだけ入れて次へ
            if sr_ref is not None and pause_between_sentences_ms > 0:
                sil = _make_silence(sr_ref, pause_between_sentences_ms)
                _append_tracks(seg.get("who", "A"), sr_ref, sil)
            continue

        who = seg.get("who", "A")
        spk = int(seg.get("speaker_id", 2))  # 既定=2（例：四国めたん）
        chunks = _safe_chunks(text, max_len=120)
        for i, chunk in enumerate(chunks):
            sr, pcm = _request_audio(
                engine_url=engine_url,
                text=chunk,
                speaker=spk,
                speed_scale=speed_scale,
                pitch_scale=pitch_scale,
                intonation_scale=intonation_scale,
            )
            if sr_ref is None:
                sr_ref = sr
            elif sr != sr_ref:
                # 念のため（VOICEVOXは基本24000固定）
                raise RuntimeError(f"sample rate mismatch: {sr} vs {sr_ref}")

            start = len(track_A)  # 現在のサンプル位置
            _append_tracks(who, sr, pcm)
            end = len(track_A)
            timings.append((who, start, end))

        # セグメント間ポーズ（両トラックに同長の無音を追加）
        if sr_ref is not None and pause_between_sentences_ms > 0:
            sil = _make_silence(sr_ref, pause_between_sentences_ms)
            _append_tracks(who, sr_ref, sil)

    if sr_ref is None:
        # 何も合成しなかった場合（空テキストなど）
        sr_ref = 24000

    # 長さ揃え（保険）
    L = max(len(track_A), len(track_B))
    if len(track_A) < L:
        track_A = np.pad(track_A, (0, L - len(track_A)), constant_values=0)
    if len(track_B) < L:
        track_B = np.pad(track_B, (0, L - len(track_B)), constant_values=0)

    # ミックス（int16クリップ防止）
    mix_i32 = track_A.astype(np.int32) + track_B.astype(np.int32)
    # 簡易リミッタ：最大振幅で正規化（過大ミックス時の歪み軽減）
    peak = np.max(np.abs(mix_i32)) if mix_i32.size else 1
    if peak > 32767:
        mix_i32 = (mix_i32.astype(np.float32) * (32767.0 / peak)).astype(np.int32)
    mix = np.clip(mix_i32, -32768, 32767).astype(np.int16)

    _write_wav(out_A_wav, sr_ref, track_A)
    _write_wav(out_B_wav, sr_ref, track_B)
    _write_wav(out_mix_wav, sr_ref, mix)

    return out_mix_wav, out_A_wav, out_B_wav, timings
