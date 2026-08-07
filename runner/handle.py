"""
runner.handle

一条命令跑完整套流程：

    handle <video_link>

URL → （字幕优先 / 拿不到才 ASR）→ 分段 → LLM 摘要 → output/<短标题>/

产物结构（约定见 README）：
    output/<短标题>/
        <短标题>.md      总结文档（文件名 = 视频标题）
        口播稿.md         字幕/转写文本，带时间戳
        audio.mp3        仅走了「下载转写」路径时才有
        trace.json       审计记录
        memory_suggestions.json

## 两个刻意的设计

**1. LLM 凭证在最前面检查。** 摘要必须调 LLM，而 ASR 可能要跑几十分钟。
如果等跑完 ASR 才发现没 key，那几十分钟就白烧了。所以开跑前先检查。

**2. 字幕优先，ASR 是最后手段。** B 站字幕接口要登录态，匿名一律返回空——
那是「没登录」，不是「没字幕」。默认不会因为没登录就去跑 ASR，会直接报错
提示补登录态；确认真没字幕才用 --allow-asr。
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.global_summary_agent import GlobalSummaryAgent
from agents.segment_summary_agent import SegmentSummaryAgent
from core.llm_client import is_llm_available, short_title
from core.schemas import SubtitleChunk, SubtitleLine
from runner import step1_prepare, step2_finalize
from tools.fetch_video_title import fetch_bilibili_info, fetch_youtube_title
from tools.parse_video_url import parse_video_url


def _sanitize(name: str) -> str:
    for ch in '/\\:*?"<>|':
        name = name.replace(ch, "")
    return name.strip() or "未命名视频"


def run(video_url: str, window_seconds: float = 300.0, output_root: str = "output",
        asr_model: str = "small", allow_asr: bool = False) -> Path:
    # 0) 先检查 LLM——别等 ASR 烧完几十分钟才发现没 key
    if not is_llm_available():
        raise SystemExit(
            "没有可用的 LLM 凭证，摘要这一步无法进行。\n"
            "  请设置 ANTHROPIC_API_KEY，或安装 ant CLI 后跑 `ant auth login`。\n"
            "（提前检查是有意的：ASR 可能要跑几十分钟，不该等跑完才失败。）"
        )

    # 1) 拿标题 → LLM 压成 5~10 字短标题，作为产物目录名
    parsed = parse_video_url(video_url)
    title = (
        fetch_youtube_title(parsed.video_id)
        if parsed.platform == "youtube"
        else fetch_bilibili_info(parsed.video_id)["title"]
    )
    short = _sanitize(short_title(title))
    print(f"[handle] 标题: {title}\n[handle] 短标题(目录名): {short}")

    # 2) 确定性前半段：字幕 / ASR → 清洗 → 分段
    out_dir = step1_prepare.run(
        video_url, window_seconds, output_root=output_root,
        asr_model=asr_model, allow_asr=allow_asr, dir_name=short,
    )
    meta = json.loads((out_dir / "meta.json").read_text(encoding="utf-8"))
    chunks_raw = json.loads((out_dir / "chunks.json").read_text(encoding="utf-8"))
    print(f"[handle] 字幕来源: {meta['subtitle_source']} | {len(chunks_raw)} 段")

    # 3) 摘要（真实 LLM 调用；失败直接抛，不降级成低质量摘要）
    seg_agent = SegmentSummaryAgent()
    segment_summaries = []
    for c in chunks_raw:
        chunk = SubtitleChunk(
            chunk_id=c["chunk_id"], start=c["start"], end=c["end"],
            lines=[SubtitleLine(start=c["start"], end=c["end"], text=c["text"])],
        )
        summary, mode = seg_agent.run(chunk)
        segment_summaries.append(summary)
        print(f"[handle]   段 {c['chunk_id'] + 1}/{len(chunks_raw)} 摘要完成")

    global_summary, mode = GlobalSummaryAgent().run(segment_summaries, video_title_hint=title)

    (out_dir / "segment_summaries.json").write_text(
        json.dumps([s.model_dump() for s in segment_summaries], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "global_summary.json").write_text(global_summary.model_dump_json(indent=2), encoding="utf-8")

    # 4) 确定性后半段：拼 doc.md + trace + memory
    step2_finalize.run(out_dir.name, output_root=output_root, agent_mode=mode)

    # 5) 按约定重命名：文档用视频标题、转写叫口播稿
    doc = out_dir / "doc.md"
    if doc.exists():
        doc.rename(out_dir / f"{short}.md")
    transcript = out_dir / "transcript.md"
    if transcript.exists():
        transcript.rename(out_dir / "口播稿.md")

    return out_dir


def main():
    p = argparse.ArgumentParser(description="一条命令：视频链接 → output/<短标题>/ 总结")
    p.add_argument("video_url")
    p.add_argument("--window-seconds", type=float, default=300.0)
    p.add_argument("--asr-model", default="small")
    p.add_argument("--output-root", default="output")
    p.add_argument("--allow-asr", action="store_true",
                   help="没登录导致抓不到字幕时，仍允许降级为本地语音识别（很慢，默认关闭）")
    a = p.parse_args()

    out_dir = run(a.video_url, a.window_seconds, output_root=a.output_root,
                  asr_model=a.asr_model, allow_asr=a.allow_asr)
    print(f"\n完成 → {out_dir.resolve()}")
    for f in sorted(out_dir.iterdir()):
        print("  -", f.name)


if __name__ == "__main__":
    main()
