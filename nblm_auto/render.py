# nblm_auto/render.py

from __future__ import annotations

# Pillow>=10 で削除された Image.ANTIALIAS を MoviePy 用に補う
try:
    from PIL import Image as _PILImage
    if not hasattr(_PILImage, "ANTIALIAS"):
        # Pillow 10+ では Resampling.LANCZOS が相当
        from PIL import Image
        _PILImage.ANTIALIAS = getattr(Image, "LANCZOS", Image.Resampling.LANCZOS)
except Exception:
    pass

from pathlib import Path
from typing import List, Tuple, Optional
from moviepy.editor import (
    AudioFileClip, ImageClip, ColorClip, CompositeVideoClip, TextClip
)
import srt

W, H = 1920, 1080
MARGIN = 40
CHAR_H = int(H * 0.82)
FPS = 30

MOUTH_W = 220   # 仮
MOUTH_H = 120   # 仮
MOUTH_A_OFF = (520, 580)  # baseA の左上から (x, y)
MOUTH_B_OFF = (520, 580)  # baseB の左上から (x, y)

def _img(path: Path, pos: tuple[int, int], height: Optional[int] = None) -> ImageClip:
    clip = ImageClip(str(path)).set_position(pos)
    if height:
        clip = clip.resize(height=height)
    return clip

def mouth_clips_fast(char_dir: Path, timeline: List[tuple], pos_xy=(0,0), mouth_h: Optional[int] = None) -> List[ImageClip]:
    """
    timeline: [(t0,t1,is_open)] or [(t, is_open)] 両対応
    """
    open_png = char_dir / "mouth_open.png"
    close_png = char_dir / "mouth_closed.png"
    if not open_png.exists() or not close_png.exists():
        raise FileNotFoundError(f"mouth PNGs not found under {char_dir}")

    base_open = _img(open_png, pos_xy, mouth_h)
    base_close = _img(close_png, pos_xy, mouth_h)

    clips: List[ImageClip] = []
    for seg in timeline:
        if len(seg) == 3:
            t0, t1, st = seg
            dur = max(0.001, t1 - t0)
            clip = (base_open if st else base_close).set_start(t0).set_duration(dur)
            clips.append(clip)
        elif len(seg) == 2:
            t, st = seg
            # 2要素形式の場合の保険。最小0.06秒など。
            clip = (base_open if st else base_close).set_start(t).set_duration(0.06)
            clips.append(clip)
    return clips

def _subtitle_clips(srt_path: Optional[Path], video_w=W) -> List[TextClip]:
    if not srt_path:
        return []
    txt = srt_path.read_text(encoding="utf-8")
    subs = list(srt.parse(txt))

    clips: List[TextClip] = []
    for it in subs:
        content = it.content.strip()
        if not content:
            continue
        # 2行程度で折り返し
        tclip = (TextClip(content, fontsize=38, color="white", stroke_color="black",
                          stroke_width=2, method="label")
                 .set_start(it.start.total_seconds())
                 .set_duration((it.end - it.start).total_seconds())
                 .set_position(("center", H - 100)))
        clips.append(tclip)
    return clips

def render_two_chars_dual(
    audio_path: Path,
    charA_dir: Path,
    charB_dir: Path,
    viseme_timeline_A: List[tuple],
    viseme_timeline_B: List[tuple],
    out_path: Path,
    srt_path: Optional[Path] = None,
    bg_color=(16, 16, 24),
) -> Path:
    # 構図（必要に応じて調整）
    char_h = 640   # キャラ全体の高さ
    mouth_h = None # 口パーツがキャラと同サイズなら None（個別PNGを口部分だけにしておく推奨）
    posA_base = (60, 60)         # 左
    posB_base = (W - 60 - 500, 60)  # 右（500px幅想定の画像でバランス）

    audio = AudioFileClip(str(audio_path))
    duration = audio.duration

    # 背景
    bg = ColorClip(size=(W, H), color=bg_color).set_duration(duration)

    # キャラ本体
    baseA = (ImageClip(str(charA_dir / "base.png"))
        .resize(height=CHAR_H)
        .set_duration(duration)
        .set_position((MARGIN, (H - CHAR_H) // 2)))

    baseB = (ImageClip(str(charB_dir / "base.png"))
        .resize(height=CHAR_H)
        .set_duration(duration)
        .set_position(lambda t: (W - baseB.w - MARGIN, (H - CHAR_H) // 2)))

    # 口パク（すでに mouthA, mouthB は「ImageClip のリスト」）
    mouthA = mouth_clips_fast(charA_dir, viseme_timeline_A, posA_base, mouth_h)
    mouthB = mouth_clips_fast(charB_dir, viseme_timeline_B, posB_base, mouth_h)

    # 字幕（リスト）
    subs = _subtitle_clips(srt_path)

    # ここ重要：フラットな配列にする
    clips = [bg, baseA, baseB] + mouthA + mouthB + subs

    final = CompositeVideoClip(clips, size=(W, H)).set_audio(audio)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    final.write_videofile(
        str(out_path),
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        preset="faster",
        threads=4,
        verbose=False,
        logger=None,
    )
    audio.close()
    final.close()
    return out_path
