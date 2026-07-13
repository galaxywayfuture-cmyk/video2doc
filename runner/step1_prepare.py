"""
runner.step1_prepare

流水线的"确定性前半段"：URL → 字幕 → 清洗 → 分段。
不涉及任何 LLM / Agent 调用。产出 chunks.json，交给下一阶段的
Agent（由发起流程的AI编码助手本人担任 SegmentSummaryAgent /
GlobalSummaryAgent 的角色，或替换为真实LLM API调用）去读取并撰写摘要。

当官方字幕接口拿不到字幕时（source=no_subtitle），会自动降级为
「下载音频 → 本地语音识别（faster-whisper）→ 生成 transcript.md」，
再继续正常的清洗/分段流程。这个降级路径耗时更长、准确率也不如官方
字幕，因此 trace 会明确标记 subtitle_source 为 local_asr:... 以便审计。

用法：
    python runner/step1_prepare.py <video_url> [--window-seconds 300] [--asr-model small]

产物（output/<可读目录名>/）：
    meta.json            本次运行的元信息（url/platform/title/subtitle_source）
    audio.mp3             [仅降级路径] 下载的音频
    transcript.md          [仅降级路径] 本地语音识别得到的原始转写文档
    chunks.json           分段后的字幕（每段含 chunk_id/start/end/text）
    trace_partial.json    到分段为止的审计记录，供 step2 续写
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.naming import build_output_dir_name
from core.trace import TraceRecorder
from tools.chunk_subtitles import chunk_subtitles
from tools.download_audio import download_audio
from tools.fetch_subtitle_bilibili import fetch_subtitle_bilibili
from tools.fetch_subtitle_youtube import fetch_subtitle_youtube
from tools.fetch_video_title import fetch_bilibili_info, fetch_youtube_title
from tools.normalize_subtitles import normalize_subtitles
from tools.parse_video_url import parse_video_url
from tools.transcribe_audio import transcribe_audio


def run(video_url: str, window_seconds: float, output_root: str = "output", asr_model: str = "small") -> Path:
    trace = TraceRecorder(url=video_url, platform="")

    parsed = _timed(trace, "parse_video_url", video_url, lambda: parse_video_url(video_url))
    trace._platform = parsed.platform  # noqa: SLF001 -- MVP 简化，内部字段回填

    if parsed.platform == "youtube":
        title = _timed(trace, "fetch_video_title", parsed.video_id, lambda: fetch_youtube_title(parsed.video_id))
        raw_lines, subtitle_source = _timed(
            trace, "fetch_subtitle_youtube", parsed.video_id, lambda: fetch_subtitle_youtube(parsed.video_id)
        )
    else:
        bili_info = _timed(trace, "fetch_video_title", parsed.video_id, lambda: fetch_bilibili_info(parsed.video_id))
        title = bili_info["title"]
        raw_lines, subtitle_source = _timed(
            trace, "fetch_subtitle_bilibili", parsed.video_id, lambda: fetch_subtitle_bilibili(parsed.video_id)
        )

    dir_name = build_output_dir_name(parsed.platform, parsed.video_id, title)
    out_dir = Path(output_root) / dir_name
    out_dir.mkdir(parents=True, exist_ok=True)

    if not raw_lines:
        raw_lines, subtitle_source = _fallback_to_local_asr(trace, video_url, out_dir, asr_model)

    trace.set_subtitle_source(subtitle_source)

    meta = {
        "url": video_url,
        "platform": parsed.platform,
        "video_id": parsed.video_id,
        "title": title,
        "subtitle_source": subtitle_source,
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    if not raw_lines:
        trace.save(out_dir / "trace_partial.json")
        raise RuntimeError(f"未获取到字幕（source={subtitle_source}）。标题: {title!r}。目录: {out_dir}。")

    normalized = _timed(trace, "normalize_subtitles", f"{len(raw_lines)} lines", lambda: normalize_subtitles(raw_lines))
    chunks = _timed(
        trace,
        "chunk_subtitles",
        f"{len(normalized)} lines, window={window_seconds}s",
        lambda: chunk_subtitles(normalized, window_seconds=window_seconds),
    )
    if chunks:
        trace.set_chunk_info(len(chunks), (chunks[0].start, chunks[-1].end))

    chunks_payload = [
        {"chunk_id": c.chunk_id, "start": c.start, "end": c.end, "text": c.text} for c in chunks
    ]
    (out_dir / "chunks.json").write_text(json.dumps(chunks_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    trace.save(out_dir / "trace_partial.json")

    return out_dir


def _fallback_to_local_asr(trace: TraceRecorder, video_url: str, out_dir: Path, asr_model: str):
    """官方字幕拿不到时的降级路径：下载音频 → 本地语音识别 → 落地 transcript.md。"""
    audio_path = _timed(trace, "download_audio", video_url, lambda: download_audio(video_url, out_dir))
    raw_lines, subtitle_source = _timed(
        trace, "transcribe_audio", str(audio_path), lambda: transcribe_audio(audio_path, model_size=asr_model)
    )
    if raw_lines:
        (out_dir / "transcript.md").write_text(_render_transcript_markdown(raw_lines, subtitle_source), encoding="utf-8")
    return raw_lines, subtitle_source


def _render_transcript_markdown(lines, source: str) -> str:
    body = "\n\n".join(f"`[{_fmt_ts(l.start)} - {_fmt_ts(l.end)}]` {l.text}" for l in lines)
    return f"# 原始转写文本\n\n> 来源：{source}（本地语音识别，未经清洗/摘要，仅供参考与追溯）\n\n{body}\n"


def _fmt_ts(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _timed(trace: TraceRecorder, step: str, input_summary: str, fn):
    start_t = time.perf_counter()
    result = fn()
    duration_ms = (time.perf_counter() - start_t) * 1000
    output_summary = str(result[0])[:120] if isinstance(result, tuple) else str(result)[:120]
    trace.record_tool_call(step=step, input_summary=str(input_summary)[:120], output_summary=output_summary, duration_ms=duration_ms)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video_url")
    parser.add_argument("--window-seconds", type=float, default=300.0)
    parser.add_argument("--asr-model", default="small", help="faster-whisper 模型规格：tiny/base/small/medium/large-v3")
    args = parser.parse_args()

    out_dir = run(args.video_url, args.window_seconds, asr_model=args.asr_model)
    print(f"chunks.json 已生成: {out_dir.resolve() / 'chunks.json'}")
    print("下一步：由 Agent 读取 chunks.json，撰写 segment_summaries.json 与 global_summary.json")


if __name__ == "__main__":
    main()
