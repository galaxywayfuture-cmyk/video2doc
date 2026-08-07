"""
core.schemas

所有工具 / Agent 之间传递数据的统一契约（Pydantic）。
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ParsedVideo(BaseModel):
    platform: Literal["youtube", "bilibili"]
    video_id: str
    original_url: str


class SubtitleLine(BaseModel):
    start: float
    end: float
    text: str


class SubtitleChunk(BaseModel):
    chunk_id: int
    start: float
    end: float
    lines: list[SubtitleLine]

    @property
    def text(self) -> str:
        return " ".join(line.text for line in self.lines)


class SegmentSummary(BaseModel):
    chunk_id: int
    summary: str
    key_points: list[str]
    time_range: tuple[float, float]


class GlobalSummary(BaseModel):
    title: str
    overview: str
    outline: list[str]
    topics: list[str]


class ToolCallRecord(BaseModel):
    step: str
    input_summary: str
    output_summary: str
    duration_ms: float
    mode: str = "normal"  # 例如 heuristic_fallback，表示未使用真实 LLM


class TraceRecord(BaseModel):
    url: str
    platform: str
    subtitle_source: str
    chunk_count: int
    time_range: tuple[float, float]
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)


class MemorySuggestions(BaseModel):
    video_type: str
    key_topics: list[str]
    user_preferences_inferred: list[str]
