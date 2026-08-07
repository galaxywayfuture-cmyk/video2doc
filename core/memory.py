"""
core.memory

职责：基于本次运行的摘要结果，生成记忆建议（memory_suggestions.json）。
这是一个独立于 Agent 内部状态的"外部记忆产物"——Agent 本身无状态，
记忆建议由 pipeline 结束后统一生成，供未来的记忆系统消费。
"""
from __future__ import annotations

import json
from pathlib import Path

from core.schemas import GlobalSummary, MemorySuggestions, SegmentSummary


def generate_memory_suggestions(
    global_summary: GlobalSummary, segment_summaries: list[SegmentSummary]
) -> MemorySuggestions:
    video_type = _infer_video_type(global_summary)
    preferences = ["偏好结构化总结（按分段+大纲呈现）", "偏好保留时间戳引用以便追溯原片段"]
    return MemorySuggestions(
        video_type=video_type,
        key_topics=global_summary.topics,
        user_preferences_inferred=preferences,
    )


def _infer_video_type(global_summary: GlobalSummary) -> str:
    text = f"{global_summary.title} {global_summary.overview}".lower()
    if any(k in text for k in ("tutorial", "how to", "教程", "guide")):
        return "教程/指南类"
    if any(k in text for k in ("news", "新闻", "report")):
        return "新闻/资讯类"
    if any(k in text for k in ("talk", "keynote", "演讲", "conference")):
        return "演讲/分享类"
    return "未分类"


def save_memory_suggestions(suggestions: MemorySuggestions, output_path: str | Path) -> None:
    Path(output_path).write_text(suggestions.model_dump_json(indent=2), encoding="utf-8")
