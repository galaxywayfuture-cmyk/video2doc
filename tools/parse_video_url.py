"""
工具：parse_video_url

职责：解析视频 URL，识别平台（youtube / bilibili），提取 video_id。
确定性操作，不调用 LLM。
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from core.schemas import ParsedVideo

_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
_BILIBILI_HOSTS = {"bilibili.com", "www.bilibili.com", "b23.tv"}


def parse_video_url(url: str) -> ParsedVideo:
    parsed = urlparse(url)
    host = parsed.netloc.lower()

    if host in _YOUTUBE_HOSTS:
        video_id = _extract_youtube_id(parsed)
        if not video_id:
            raise ValueError(f"无法从 URL 中解析出 YouTube video_id: {url}")
        return ParsedVideo(platform="youtube", video_id=video_id, original_url=url)

    if host in _BILIBILI_HOSTS:
        video_id = _extract_bilibili_id(parsed)
        if not video_id:
            raise ValueError(f"无法从 URL 中解析出 Bilibili video_id: {url}")
        return ParsedVideo(platform="bilibili", video_id=video_id, original_url=url)

    raise ValueError(f"不支持的平台，无法识别 host: {host!r}（url={url}）")


def _extract_youtube_id(parsed) -> str | None:
    if parsed.netloc.lower() == "youtu.be":
        return parsed.path.lstrip("/").split("/")[0] or None

    qs = parse_qs(parsed.query)
    if "v" in qs and qs["v"]:
        return qs["v"][0]

    # 兼容 /embed/<id> 或 /shorts/<id> 形式
    match = re.search(r"/(embed|shorts)/([A-Za-z0-9_-]{6,})", parsed.path)
    if match:
        return match.group(2)

    return None


def _extract_bilibili_id(parsed) -> str | None:
    match = re.search(r"/video/((BV[0-9A-Za-z]+)|(av\d+))", parsed.path)
    if match:
        return match.group(1)
    return None
