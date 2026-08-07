"""
Agent：SegmentSummaryAgent

职责：对单个 SubtitleChunk 生成结构化摘要。
System prompt 见 segment_summary_agent.prompt.md（当无 LLM key 时，
实际执行走 core.llm_client 的抽取式降级方案，但输出 schema 保持一致，
以保证未来切换为真实 LLM 时下游代码无需改动）。
"""
from __future__ import annotations

from core.llm_client import summarize_text
from core.schemas import SegmentSummary, SubtitleChunk


class SegmentSummaryAgent:
    def run(self, chunk: SubtitleChunk) -> tuple[SegmentSummary, str]:
        """返回 (SegmentSummary, mode)。"""
        summary, key_points, mode = summarize_text(chunk.text)
        result = SegmentSummary(
            chunk_id=chunk.chunk_id,
            summary=summary,
            key_points=key_points,
            time_range=(chunk.start, chunk.end),
        )
        return result, mode
