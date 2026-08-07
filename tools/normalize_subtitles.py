"""
工具：normalize_subtitles

职责：清洗字幕 —— 去除空行/噪声标记、合并过短的碎句、统一空白格式。
"""
from __future__ import annotations

import re

from core.schemas import SubtitleLine

# 常见的非语音噪声标记，例如 [Music]、[Applause]、（笑声）等
_NOISE_PATTERN = re.compile(r"^[\[\(（【].*?[\]\)）】]$")

_MIN_MERGE_LEN = 8  # 短于该字符数的行会尝试与下一行合并


def normalize_subtitles(lines: list[SubtitleLine]) -> list[SubtitleLine]:
    cleaned: list[SubtitleLine] = []

    for line in lines:
        text = re.sub(r"\s+", " ", line.text).strip()
        if not text:
            continue
        if _NOISE_PATTERN.match(text):
            continue
        cleaned.append(SubtitleLine(start=line.start, end=line.end, text=text))

    return _merge_short_lines(cleaned)


def _merge_short_lines(lines: list[SubtitleLine]) -> list[SubtitleLine]:
    merged: list[SubtitleLine] = []
    for line in lines:
        if merged and len(merged[-1].text) < _MIN_MERGE_LEN:
            prev = merged.pop()
            merged.append(
                SubtitleLine(
                    start=prev.start,
                    end=line.end,
                    text=f"{prev.text} {line.text}".strip(),
                )
            )
        else:
            merged.append(line)
    return merged
