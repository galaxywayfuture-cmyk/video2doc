"""
core.llm_client

统一的 LLM 调用入口（Anthropic Claude）。

## 为什么删掉了原来的「启发式抽取式降级」

原实现在没有 API key 时会退化成基于词频的抽取式摘要。那套代码用
`re.findall(r"[A-Za-z']+", text)` 分词——**匹配不到任何中文字符**。对中文视频，
它产出的 `topics` 恒为空、`key_points` 近乎无意义，`summary` 只是原文前两句。
也就是说，它会生成一份「看起来像总结、实则是垃圾」的文档，而 trace 里只标一个
`heuristic_fallback` 就算交代过了——这种静默的低质量比直接失败更糟。

现在的策略：**没有可用的 LLM 就直接抛错**，明确告诉调用方去配 key，
而不是假装完成了工作。

需要 `ANTHROPIC_API_KEY`（或 `ant auth login` 后的 profile，SDK 会自动读取）。
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

_MODEL = "claude-opus-4-8"
_PROMPT_DIR = Path(__file__).resolve().parent.parent / "agents"


class _SegmentOut(BaseModel):
    summary: str = Field(description="该分段的核心内容概述（连贯中文段落，真正提炼要点，不是原句摘抄）")
    key_points: list[str] = Field(description="2~4 条要点")


class _GlobalOut(BaseModel):
    title: str = Field(description="文档标题（概括主旨，不照抄原标题的营销话术/话题标签）")
    overview: str = Field(description="全局概述（连贯中文段落，串联各分段的核心逻辑）")
    outline: list[str] = Field(description="大纲条目，标注对应分段编号/时间范围")
    topics: list[str] = Field(description="有意义的主题标签，不是高频词统计")


class _TitleOut(BaseModel):
    short_title: str = Field(description="5~10 个字的短标题；中文视频用中文，英文视频用英文；不含文件名非法字符")


class LLMUnavailableError(RuntimeError):
    """没有可用的 LLM 凭证时抛出——绝不静默降级成低质量摘要。"""


@lru_cache(maxsize=1)
def _client():
    try:
        import anthropic
    except ImportError as e:  # pragma: no cover
        raise LLMUnavailableError("未安装 anthropic SDK：pip install -r requirements.txt") from e
    try:
        return anthropic.Anthropic()
    except Exception as e:
        raise LLMUnavailableError(
            "无法初始化 Anthropic 客户端。请设置 ANTHROPIC_API_KEY，或先跑 `ant auth login`。"
        ) from e


def is_llm_available() -> bool:
    """有 API key 或已登录的 profile 时返回 True。

    注意：不能用「`anthropic.Anthropic()` 能不能构造成功」来判断——**构造器根本
    不校验凭证**，无 key 时它照样返回一个客户端，直到真正发请求才抛
    `TypeError: Could not resolve authentication method`。用构造成功当作可用，
    会让流水线跑到摘要那一步才炸（此时音频/ASR 的时间已经花掉了）。
    所以这里直接检查凭证来源本身。
    """
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    # `ant auth login` 会把 profile 写到 ~/.config/anthropic/credentials/，SDK 自动读取
    cfg_dir = os.environ.get("ANTHROPIC_CONFIG_DIR")
    base = Path(cfg_dir) if cfg_dir else Path.home() / ".config" / "anthropic"
    creds = base / "credentials"
    return creds.is_dir() and any(creds.glob("*.json"))


@lru_cache(maxsize=4)
def _prompt(name: str) -> str:
    path = _PROMPT_DIR / f"{name}.prompt.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _parse(system: str, user: str, schema: type[BaseModel], max_tokens: int = 8000):
    """调用 Claude 并解析成结构化对象。失败直接抛，不降级。"""
    resp = _client().messages.parse(
        model=_MODEL,
        max_tokens=max_tokens,
        thinking={"type": "adaptive"},
        system=system,
        messages=[{"role": "user", "content": user}],
        output_format=schema,
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"模型拒绝了该请求: {resp.stop_details}")
    return resp.parsed_output


def summarize_text(text: str, max_key_points: int = 3) -> tuple[str, list[str], str]:
    """返回 (summary, key_points, mode)。"""
    out = _parse(
        system=_prompt("segment_summary_agent"),
        user=f"请对以下视频分段的字幕文本做结构化摘要（最多 {max_key_points} 条要点）：\n\n{text}",
        schema=_SegmentOut,
    )
    return out.summary, out.key_points[:max_key_points], f"llm:{_MODEL}"


def aggregate_summaries(
    segment_summaries: list[str], video_title_hint: str
) -> tuple[str, str, list[str], list[str], str]:
    """返回 (title, overview, outline, topics, mode)。"""
    joined = "\n".join(f"第 {i + 1} 段：{s}" for i, s in enumerate(segment_summaries))
    out = _parse(
        system=_prompt("global_summary_agent"),
        user=f"视频原标题（仅作参考）：{video_title_hint}\n\n以下是各分段摘要：\n\n{joined}",
        schema=_GlobalOut,
    )
    return out.title, out.overview, out.outline, out.topics, f"llm:{_MODEL}"


def short_title(video_title: str) -> str:
    """把长标题压成 5~10 字的短标题，用作输出文件夹名。

    这一步必须由 LLM 做：要判断哪些是栏目名/话题标签该丢、哪些是主旨该留，
    正则做不到（原来的 build_output_dir_name 是硬截断，产出的目录名很难看）。
    """
    out = _parse(
        system=(
            "你负责把视频标题压缩成简短的文件夹名。规则：\n"
            "- 控制在 5~10 个字，抓住视频主旨\n"
            "- 原标题是中文就用中文，英文就用英文\n"
            "- 丢掉栏目名、话题标签、【】里的修饰（如【视频播客】）、UP 主名等噪声\n"
            '- 不能含 / \\ : * ? " < > | 等文件名非法字符'
        ),
        user=f"视频标题：{video_title}",
        schema=_TitleOut,
        max_tokens=2000,
    )
    return out.short_title.strip()
