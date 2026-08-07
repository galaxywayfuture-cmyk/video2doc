"""
runner.run_all

单命令端到端：URL → 字幕/ASR → 清洗 → 分段 → 摘要 → doc.md + trace.json + memory_suggestions.json。

与两阶段流水线（step1_prepare + 人工/AI介入 + step2_finalize）的区别：
本脚本用 agents/ 里的 SegmentSummaryAgent / GlobalSummaryAgent 自动生成摘要，
无需中途人工介入，真正做到「一条命令跑完」。

当前环境未配置 LLM API key 时，摘要走 core.llm_client 的启发式抽取式降级
（extractive summary），trace.json 会如实标注 mode=heuristic_fallback。
这种降级摘要是「抽取式」的（挑原文里的句子），不是真正的语义提炼，质量有限，
尤其对中文只做句子级抽取；若想要高质量语义摘要，请：
  (a) 用两阶段流水线让真正的 LLM / AI 助手撰写摘要，或
  (b) 在 core/llm_client.py 接入真实 LLM API（接口不变，run_all 会自动切换）。

用法：
    python runner/run_all.py <video_url> [--window-seconds 300] [--asr-model small]

无字幕视频会自动走「下载音频 → faster-whisper 本地识别」降级路径，耗时较长
（长视频在 CPU 上可能要几十分钟到数小时）；首次运行会自动下载 ASR 模型。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.global_summary_agent import GlobalSummaryAgent
from agents.segment_summary_agent import SegmentSummaryAgent
from core.schemas import SubtitleChunk, SubtitleLine
from runner import step1_prepare, step2_finalize


def run(video_url: str, window_seconds: float, output_root: str = "output", asr_model: str = "small") -> Path:
    # 1) 确定性前半段（复用 step1）：URL → 字幕/ASR → 清洗 → 分段
    out_dir = step1_prepare.run(video_url, window_seconds, output_root=output_root, asr_model=asr_model)

    chunks_raw = json.loads((out_dir / "chunks.json").read_text(encoding="utf-8"))
    meta = json.loads((out_dir / "meta.json").read_text(encoding="utf-8"))

    # 2) 摘要（自动调用 Agent；无 LLM key 时走启发式降级）
    seg_agent = SegmentSummaryAgent()
    segment_summaries = []
    modes: set[str] = set()
    for c in chunks_raw:
        chunk = SubtitleChunk(
            chunk_id=c["chunk_id"],
            start=c["start"],
            end=c["end"],
            lines=[SubtitleLine(start=c["start"], end=c["end"], text=c["text"])],
        )
        summary, mode = seg_agent.run(chunk)
        segment_summaries.append(summary)
        modes.add(mode)

    global_summary, gmode = GlobalSummaryAgent().run(segment_summaries, video_title_hint=meta.get("title", ""))
    modes.add(gmode)

    (out_dir / "segment_summaries.json").write_text(
        json.dumps([s.model_dump() for s in segment_summaries], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "global_summary.json").write_text(global_summary.model_dump_json(indent=2), encoding="utf-8")

    # 3) 确定性后半段（复用 step2）：拼装 doc.md + 补写 trace + 生成 memory
    #    如实标注摘要来源：全部走启发式降级则标 heuristic_fallback，否则视为真实推理
    agent_mode = "heuristic_fallback" if modes == {"heuristic_fallback"} else "agent_in_loop"
    step2_finalize.run(out_dir.name, output_root=output_root, agent_mode=agent_mode)

    return out_dir


def main():
    parser = argparse.ArgumentParser(description="视频 URL → 结构化文档（单命令端到端）")
    parser.add_argument("video_url")
    parser.add_argument("--window-seconds", type=float, default=300.0)
    parser.add_argument("--asr-model", default="small", help="faster-whisper 模型规格：tiny/base/small/medium/large-v3")
    parser.add_argument("--output-root", default="output")
    args = parser.parse_args()

    out_dir = run(args.video_url, args.window_seconds, output_root=args.output_root, asr_model=args.asr_model)
    print("\n完成。最终产物目录:", out_dir.resolve())
    for name in ("doc.md", "trace.json", "memory_suggestions.json"):
        print("  -", out_dir / name)


if __name__ == "__main__":
    main()
