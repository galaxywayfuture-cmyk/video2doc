"""
工具：chunk_subtitles

职责：按固定时间窗口将字幕切分为若干段（chunk）。
MVP 版本使用简单的时间窗口切分；未来可替换为语义边界切分。
"""
from __future__ import annotations

from core.schemas import SubtitleChunk, SubtitleLine

_DEFAULT_WINDOW_SECONDS = 90.0


def chunk_subtitles(
    lines: list[SubtitleLine], window_seconds: float = _DEFAULT_WINDOW_SECONDS
) -> list[SubtitleChunk]:
    if not lines:
        return []

    chunks: list[SubtitleChunk] = []
    current_lines: list[SubtitleLine] = []
    window_start = lines[0].start

    for line in lines:
        if current_lines and (line.start - window_start) >= window_seconds:
            chunks.append(_build_chunk(len(chunks), current_lines))
            current_lines = []
            window_start = line.start
        current_lines.append(line)

    if current_lines:
        chunks.append(_build_chunk(len(chunks), current_lines))

    return chunks


def _build_chunk(chunk_id: int, lines: list[SubtitleLine]) -> SubtitleChunk:
    return SubtitleChunk(
        chunk_id=chunk_id,
        start=lines[0].start,
        end=lines[-1].end,
        lines=lines,
    )
