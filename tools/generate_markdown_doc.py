"""
工具：generate_markdown_doc

职责：将全局摘要 + 分段摘要 + 元信息拼装成最终 Markdown 文档。
"""
from __future__ import annotations

from core.schemas import GlobalSummary, SegmentSummary


def _format_timestamp(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def generate_markdown_doc(
    global_summary: GlobalSummary,
    segment_summaries: list[SegmentSummary],
    meta: dict,
) -> str:
    lines: list[str] = []
    lines.append(f"# {global_summary.title}")
    lines.append("")
    lines.append(f"> 来源：{meta.get('url', '')}  ")
    lines.append(f"> 平台：{meta.get('platform', '')} · 字幕来源：{meta.get('subtitle_source', '')}  ")
    lines.append(f"> 生成模式：{meta.get('mode', '')}")
    lines.append("")
    lines.append("## 概述")
    lines.append("")
    lines.append(global_summary.overview)
    lines.append("")
    lines.append("## 主题标签")
    lines.append("")
    lines.append(", ".join(f"`{t}`" for t in global_summary.topics))
    lines.append("")
    lines.append("## 大纲")
    lines.append("")
    for item in global_summary.outline:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## 分段详情")
    lines.append("")
    for seg in segment_summaries:
        start_ts = _format_timestamp(seg.time_range[0])
        end_ts = _format_timestamp(seg.time_range[1])
        lines.append(f"### 分段 {seg.chunk_id + 1} [{start_ts} - {end_ts}]")
        lines.append("")
        lines.append(seg.summary)
        if seg.key_points:
            lines.append("")
            lines.append("要点：")
            for kp in seg.key_points:
                lines.append(f"- {kp}")
        lines.append("")

    return "\n".join(lines)
