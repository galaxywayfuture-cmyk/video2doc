"""
工具：fetch_subtitle_bilibili

职责：获取 Bilibili 视频字幕（人工上传的 CC 字幕，或 UP 主开放的 AI 字幕）。

已知限制：Bilibili 的 AI 自动字幕接口在多数情况下需要登录态（SESSDATA cookie）
才能返回内容，匿名请求经常会得到空字幕列表。当没有可用字幕时，本函数会
返回空列表 + "no_subtitle"，由上层调用方决定如何处理（例如降级为本地ASR，
或提示用户提供登录 cookie）。
"""
from __future__ import annotations

import requests

from core.schemas import SubtitleLine
from tools.fetch_video_title import fetch_bilibili_info

_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com"}


def fetch_subtitle_bilibili(video_id: str) -> tuple[list[SubtitleLine], str]:
    info = fetch_bilibili_info(video_id)
    cid, aid = info["cid"], info["aid"]

    resp = requests.get(
        "https://api.bilibili.com/x/player/v2",
        params={"cid": cid, "aid": aid, "bvid": video_id},
        headers=_HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    payload = resp.json()
    subtitles = payload.get("data", {}).get("subtitle", {}).get("subtitles", [])

    if not subtitles:
        return [], "no_subtitle"

    subtitle_url = subtitles[0]["subtitle_url"]
    if subtitle_url.startswith("//"):
        subtitle_url = "https:" + subtitle_url

    sub_resp = requests.get(subtitle_url, headers=_HEADERS, timeout=10)
    sub_resp.raise_for_status()
    body = sub_resp.json().get("body", [])

    lines = [SubtitleLine(start=item["from"], end=item["to"], text=item["content"]) for item in body]
    lang = subtitles[0].get("lan_doc", "unknown")
    return lines, f"bilibili_subtitle:{lang}"
