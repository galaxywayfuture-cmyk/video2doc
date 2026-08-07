"""
runner.step2_finalize

流水线的"确定性后半段"：读取 Agent（人工或真实LLM API）撰写好的
segment_summaries.json / global_summary.json，拼装最终文档，
并把 agent 调用记录补写进 trace，最后生成 memory_suggestions。

用法：
    python runner/step2_finalize.py <output_dir_name> [--output-root output]

<output_dir_name> 是 step1_prepare.py 打印出的目录名（形如
platform_标题片段_video_id）。

前置条件（由 step1_prepare.py 和 Agent 手工撰写产生）：
    output/<dir_name>/meta.json
    output/<dir_name>/chunks.json
    output/<dir_name>/trace_partial.json
    output/<dir_name>/segment_summaries.json   [{chunk_id, summary, key_points, time_range}, ...]
    output/<dir_name>/global_summary.json      {title, overview, outline, topics}
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.memory import generate_memory_suggestions, save_memory_suggestions
from core.schemas import GlobalSummary, SegmentSummary, TraceRecord
from core.trace import TraceRecorder
from tools.generate_markdown_doc import generate_markdown_doc


def run(output_dir_name: str, output_root: str = "output", agent_mode: str = "agent_in_loop") -> Path:
    # agent_mode 如实标注 segment/global 摘要是怎么来的：
    #   "agent_in_loop"      —— 两阶段流水线里由人工/AI编码助手撰写
    #   "heuristic_fallback" —— run_all.py 一条命令端到端时走的启发式抽取式降级
    out_dir = Path(output_root) / output_dir_name

    meta = json.loads((out_dir / "meta.json").read_text(encoding="utf-8"))
    partial_trace = TraceRecord.model_validate_json((out_dir / "trace_partial.json").read_text(encoding="utf-8"))

    segment_summaries_raw = json.loads((out_dir / "segment_summaries.json").read_text(encoding="utf-8"))
    segment_summaries = [SegmentSummary.model_validate(s) for s in segment_summaries_raw]

    global_summary_raw = json.loads((out_dir / "global_summary.json").read_text(encoding="utf-8"))
    global_summary = GlobalSummary.model_validate(global_summary_raw)

    trace = TraceRecorder(url=partial_trace.url, platform=partial_trace.platform)
    trace._subtitle_source = partial_trace.subtitle_source  # noqa: SLF001
    trace._chunk_count = partial_trace.chunk_count  # noqa: SLF001
    trace._time_range = partial_trace.time_range  # noqa: SLF001
    trace._tool_calls = list(partial_trace.tool_calls)  # noqa: SLF001

    for seg in segment_summaries:
        trace.record_tool_call(
            step=f"SegmentSummaryAgent[chunk={seg.chunk_id}]",
            input_summary=f"chunk_id={seg.chunk_id}",
            output_summary=seg.summary[:120],
            duration_ms=0.0,
            mode=agent_mode,
        )

    trace.record_tool_call(
        step="GlobalSummaryAgent",
        input_summary=f"{len(segment_summaries)} segment summaries",
        output_summary=global_summary.title,
        duration_ms=0.0,
        mode=agent_mode,
    )

    doc_meta = {
        "url": meta["url"],
        "platform": meta["platform"],
        "subtitle_source": meta["subtitle_source"],
        "mode": agent_mode,
    }
    start_t = time.perf_counter()
    doc_markdown = generate_markdown_doc(global_summary, segment_summaries, doc_meta)
    duration_ms = (time.perf_counter() - start_t) * 1000
    trace.record_tool_call(
        step="generate_markdown_doc",
        input_summary=f"title={global_summary.title}",
        output_summary=f"{len(doc_markdown)} chars",
        duration_ms=duration_ms,
    )

    memory_suggestions = generate_memory_suggestions(global_summary, segment_summaries)

    (out_dir / "doc.md").write_text(doc_markdown, encoding="utf-8")
    trace.save(out_dir / "trace.json")
    save_memory_suggestions(memory_suggestions, out_dir / "memory_suggestions.json")

    return out_dir


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir_name")
    parser.add_argument("--output-root", default="output")
    args = parser.parse_args()

    out_dir = run(args.output_dir_name, args.output_root)
    print(f"完成。最终产物: {out_dir.resolve()}")


if __name__ == "__main__":
    main()
