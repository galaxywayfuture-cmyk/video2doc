"""
Agent：GlobalSummaryAgent

职责：聚合所有分段摘要，生成全局摘要、大纲与主题标签。
System prompt 见 global_summary_agent.prompt.md（当无 LLM key 时，
实际执行走 core.llm_client 的抽取式降级方案）。
"""
from __future__ import annotations

from core.llm_client import aggregate_summaries
from core.schemas import GlobalSummary, SegmentSummary


class GlobalSummaryAgent:
    def run(self, segment_summaries: list[SegmentSummary], video_title_hint: str = "") -> tuple[GlobalSummary, str]:
        """返回 (GlobalSummary, mode)。"""
        summaries_text = [s.summary for s in segment_summaries]
        title, overview, outline, topics, mode = aggregate_summaries(summaries_text, video_title_hint)
        result = GlobalSummary(title=title, overview=overview, outline=outline, topics=topics)
        return result, mode
