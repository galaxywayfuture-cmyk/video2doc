"""
工具：fetch_subtitle_youtube

职责：调用 youtube-transcript-api 获取原始字幕（含时间戳）。
确定性操作（结果取决于外部数据源，但不涉及 LLM 推理）。
"""
from __future__ import annotations

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    CouldNotRetrieveTranscript,
    NoTranscriptFound,
    TranscriptsDisabled,
)

from core.schemas import SubtitleLine

# 优先尝试的语言顺序：英文、中文简/繁体
_PREFERRED_LANGUAGES = ["en", "zh-Hans", "zh-CN", "zh", "zh-Hant", "zh-TW"]


def fetch_subtitle_youtube(video_id: str) -> tuple[list[SubtitleLine], str]:
    """返回 (字幕行列表, 实际使用的字幕来源标记)。若无字幕，返回空列表 + "no_subtitle"。"""
    api = YouTubeTranscriptApi()

    try:
        transcript_list = api.list(video_id)
    except (TranscriptsDisabled, CouldNotRetrieveTranscript):
        return [], "no_subtitle"

    transcript = None
    try:
        transcript = transcript_list.find_transcript(_PREFERRED_LANGUAGES)
    except NoTranscriptFound:
        # 降级：拿列表里第一个可用的字幕（不管语言）
        available = list(transcript_list)
        if available:
            transcript = available[0]

    if transcript is None:
        return [], "no_subtitle"

    fetched = transcript.fetch()
    lines = [
        SubtitleLine(start=snippet.start, end=snippet.start + snippet.duration, text=snippet.text)
        for snippet in fetched
    ]
    source = f"youtube_captions:{transcript.language_code}"
    if transcript.is_generated:
        source += ":auto_generated"
    return lines, source
