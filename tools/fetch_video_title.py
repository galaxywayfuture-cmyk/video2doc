"""
工具：fetch_video_title

职责：获取视频标题，用于生成人类可读的输出目录名。
YouTube 通过公开的 oEmbed 接口（无需 API key）；Bilibili 通过公开的
web-interface/view 接口（同时可拿到 cid，供字幕获取复用）。
"""
from __future__ import annotations

import requests

_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com"}


def fetch_youtube_title(video_id: str) -> str:
    url = "https://www.youtube.com/oembed"
    resp = requests.get(url, params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"}, timeout=10)
    resp.raise_for_status()
    return resp.json().get("title", "")


def fetch_bilibili_info(video_id: str) -> dict:
    """返回 {"title": str, "cid": int, "aid": int}。"""
    resp = requests.get(
        "https://api.bilibili.com/x/web-interface/view", params={"bvid": video_id}, headers=_HEADERS, timeout=10
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"Bilibili API 返回错误: {payload.get('message')}")
    data = payload["data"]
    return {"title": data.get("title", ""), "cid": data.get("cid"), "aid": data.get("aid")}
