"""
core.llm_client

统一的 LLM 调用入口。

当前环境未配置 OPENAI_API_KEY / ANTHROPIC_API_KEY，因此 MVP 阶段使用
基于词频的抽取式摘要作为降级方案（heuristic fallback），保证整条流水线
可以端到端跑通。一旦配置了真实的 API key，`complete()` 会自动切换为
真实 LLM 调用（此处先留出接口，具体 provider 接入待后续实现）。

所有调用都会返回 (输出文本, mode)，mode 用于写入 trace，标明这次调用
是否是降级模式，保证可审计性。
"""
from __future__ import annotations

import os
import re
from collections import Counter

_HAS_LLM_KEY = bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"))

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "to", "of",
    "in", "on", "for", "with", "that", "this", "it", "as", "at", "by", "be", "so",
    "we", "you", "i", "they", "he", "she", "not", "have", "has", "just", "like",
    "our", "your", "us", "if", "then", "there", "what", "when", "how", "can", "do",
}


def is_llm_available() -> bool:
    return _HAS_LLM_KEY


def summarize_text(text: str, max_key_points: int = 3) -> tuple[str, list[str], str]:
    """返回 (summary, key_points, mode)。

    当前无 LLM key 可用时，走抽取式摘要：取前两句作为 summary，
    取词频最高的若干实词句子作为 key_points。
    """
    if _HAS_LLM_KEY:
        raise NotImplementedError("真实 LLM 调用待接入（未配置 provider 客户端）")

    sentences = _split_sentences(text)
    summary = " ".join(sentences[:2]) if sentences else text[:200]
    key_points = _extractive_key_points(sentences, max_key_points)
    return summary, key_points, "heuristic_fallback"


def aggregate_summaries(segment_summaries: list[str], video_title_hint: str) -> tuple[str, list[str], list[str], str]:
    """返回 (title, overview, outline, topics, mode)... 实际返回 4 元组见下。"""
    if _HAS_LLM_KEY:
        raise NotImplementedError("真实 LLM 调用待接入（未配置 provider 客户端）")

    overview = " ".join(segment_summaries[:3])
    outline = [f"第 {i + 1} 段：{s}" for i, s in enumerate(segment_summaries)]
    topics = _top_keywords(" ".join(segment_summaries), top_n=5)
    title = video_title_hint or (topics[0].title() if topics else "Untitled Video Summary")
    return title, overview, outline, topics, "heuristic_fallback"


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|(?<=[。！？])\s*", text)
    return [p.strip() for p in parts if p.strip()]


def _extractive_key_points(sentences: list[str], max_key_points: int) -> list[str]:
    if not sentences:
        return []
    scored = sorted(sentences, key=lambda s: _score_sentence(s), reverse=True)
    return scored[:max_key_points]


def _score_sentence(sentence: str) -> int:
    words = _tokenize(sentence)
    return len([w for w in words if w not in _STOPWORDS])


def _top_keywords(text: str, top_n: int = 5) -> list[str]:
    words = [w for w in _tokenize(text) if w not in _STOPWORDS and len(w) > 2]
    counter = Counter(words)
    return [word for word, _ in counter.most_common(top_n)]


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z']+", text.lower())
