from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import re

def extract_big_numbers(text: str) -> list[str]:
    cand = re.findall(r"[0-9][0-9,\.]*\s*[万億]?[人件個回％%年度]?", text)
    return list(dict.fromkeys([c.strip() for c in cand]))

def make_number_slide(number_text: str, out_path: Path, size=(1920,1080)):
    W,H = size
    img = Image.new("RGB", size, (20,20,28))
    draw = ImageDraw.Draw(img)
    try:
        font_big = ImageFont.truetype("NotoSansJP-Bold.otf", 220)
        font_small = ImageFont.truetype("NotoSansJP-Regular.otf", 64)
    except:
        font_big = ImageFont.load_default()
        font_small = ImageFont.load_default()
    w,h = draw.textbbox((0,0), number_text, font=font_big)[2:4]
    draw.text(((W-w)//2, (H-h)//2 - 60), number_text, font=font_big, fill=(240,240,255))
    sub = "（NotebookLM要約から自動抽出）"
    w2,h2 = draw.textbbox((0,0), sub, font=font_small)[2:4]
    draw.text(((W-w2)//2, (H-h2)//2 + 180), sub, font=font_small, fill=(180,180,200))
    img.save(out_path)
    return out_path
