"""
工具：transcribe_audio

职责：当官方字幕接口不可用时，用本地语音识别（faster-whisper）从音频
生成带时间戳的字幕行，作为 fetch_subtitle_* 的降级替代数据源。
确定性程度低于纯规则工具（依赖ASR模型输出），但仍不涉及LLM语义总结，
属于"识别"而非"理解"，因此归类在 tools/ 而不是 agents/。
"""
from __future__ import annotations

from pathlib import Path

from faster_whisper import WhisperModel

from core.schemas import SubtitleLine

_DEFAULT_MODEL_SIZE = "small"


def transcribe_audio(
    audio_path: str | Path, language: str | None = None, model_size: str = _DEFAULT_MODEL_SIZE
) -> tuple[list[SubtitleLine], str]:
    """返回 (字幕行列表, 来源标记，含模型规格便于审计)。"""
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(audio_path), language=language, vad_filter=True)

    lines = [SubtitleLine(start=seg.start, end=seg.end, text=seg.text.strip()) for seg in segments if seg.text.strip()]
    source = f"local_asr:faster-whisper-{model_size}:{info.language}"
    return lines, source
