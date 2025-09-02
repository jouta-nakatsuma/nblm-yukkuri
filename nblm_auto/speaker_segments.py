# nblm_auto/speaker_segments.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple

@dataclass
class Segment:
    start: float
    end: float
    speaker: str  # "A" / "B"

def dummy_single_speaker(total_dur: float) -> List[Segment]:
    # 使わない想定（NotebookLMの単一音声を前提）
    return [Segment(0.0, total_dur, "A")]
