"""
工具：fetch_subtitle_bilibili

职责：获取 Bilibili 视频字幕（UP 主上传的 CC 字幕，或 AI 自动字幕）。

## 两个必须处理的坑

**坑一：字幕接口需要登录态。** 匿名请求一律返回空字幕列表，这不是 bug，是 B 站
的接口设计。本模块按以下顺序寻找 SESSDATA：

    1. 显式传入的 sessdata 参数
    2. 环境变量 BILIBILI_SESSDATA
    3. 本机浏览器 cookie（safari / chrome / edge / brave / firefox）

拿不到时返回 (空列表, "no_subtitle:not_logged_in")，由上层决定是否降级为
「下载音频 + 本地 ASR」。ASR 很慢，字幕能走通就绝不该走 ASR。

**坑二：`/x/player/v2` 偶发串台，会返回别的视频的字幕。** 这是实测确认的：
对同一个 (aid, cid, bvid) 连续请求 6 次，出现过 3 种不同的 sub_id，其中两种
的内容和时长跟目标视频毫无关系（一个 1351 秒、一个 275 秒，目标视频 2866 秒），
另外还有「空列表」和「subtitle_url 为空字符串」两种异常返回。

串台的危险在于**它是静默的**——你会拿到一份语法完全正常、但属于另一个视频的
字幕，然后基于它生成一份看起来煞有介事、实则彻底错误的总结。因此本模块**强制
用视频时长校验字幕覆盖范围**：字幕最后一条的结束时间必须达到视频时长的
`_MIN_COVERAGE` 以上，否则视为无效，重试。校验不通过宁可返回空、让上层降级，
也不返回不可信的字幕。
"""
from __future__ import annotations

import os
import time

import requests

from core.schemas import SubtitleLine
from tools.fetch_video_title import fetch_bilibili_info

_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com"}
_BROWSERS = ("safari", "chrome", "edge", "brave", "firefox")

_MAX_ATTEMPTS = 12     # 实测命中率约 2/3，偶尔连续 6 次全是串台/空返回，故留足重试

# 字幕末尾时间戳 / 视频时长 必须落在这个区间内。
# **上下限都必须查**：只查下限会放过「比视频还长」的串台字幕——实测遇到过
# 一份 54:35 的字幕混进 47:45 的视频（ratio=1.14），只设 >=0.9 时它照样通过。
_MIN_COVERAGE = 0.90
_MAX_COVERAGE = 1.02


def _sessdata_from_browsers() -> str | None:
    """从本机浏览器 cookie 里找 bilibili 的 SESSDATA；找不到返回 None。"""
    try:
        from yt_dlp.cookies import extract_cookies_from_browser
    except ImportError:
        return None

    for browser in _BROWSERS:
        try:
            jar = extract_cookies_from_browser(browser)
        except Exception:
            continue  # 该浏览器没装 / cookie 库读不了，换下一个
        for cookie in jar:
            if cookie.name == "SESSDATA" and (cookie.domain or "").endswith("bilibili.com") and cookie.value:
                return cookie.value
    return None


def resolve_sessdata(sessdata: str | None = None) -> tuple[str | None, str]:
    """按 显式参数 → 环境变量 → 浏览器 cookie 的顺序解析 SESSDATA。

    返回 (sessdata, 来源说明)，便于 trace 如实记录登录态是哪来的。
    """
    if sessdata:
        return sessdata, "explicit_arg"
    env = os.environ.get("BILIBILI_SESSDATA", "").strip()
    if env:
        return env, "env:BILIBILI_SESSDATA"
    from_browser = _sessdata_from_browsers()
    if from_browser:
        return from_browser, "browser_cookie"
    return None, "none"


def _try_once(cid: int, aid: int, video_id: str, cookies: dict, duration: int | None):
    """请求一次并校验。返回 (lines, lan_doc, sub_id) 或 None（本次无效）。"""
    resp = requests.get(
        "https://api.bilibili.com/x/player/v2",
        params={"cid": cid, "aid": aid, "bvid": video_id},
        headers=_HEADERS,
        cookies=cookies,
        timeout=10,
    )
    resp.raise_for_status()
    subtitles = resp.json().get("data", {}).get("subtitle", {}).get("subtitles", [])
    if not subtitles:
        return None

    sub = subtitles[0]
    url = sub.get("subtitle_url") or ""
    if not url:  # 接口偶发返回空 URL
        return None
    if url.startswith("//"):
        url = "https:" + url

    body = requests.get(url, headers=_HEADERS, cookies=cookies, timeout=15).json().get("body", [])
    if not body:
        return None

    # 关键校验：字幕的时间跨度必须和视频时长基本吻合。
    # 太短 = 残缺或别家短视频的字幕；太长 = 别家长视频的字幕。两头都要卡。
    if duration:
        coverage = body[-1]["to"] / duration
        if not (_MIN_COVERAGE <= coverage <= _MAX_COVERAGE):
            return None

    lines = [SubtitleLine(start=i["from"], end=i["to"], text=i["content"]) for i in body]
    return lines, sub.get("lan_doc", "unknown"), sub.get("id")


def fetch_subtitle_bilibili(video_id: str, sessdata: str | None = None) -> tuple[list[SubtitleLine], str]:
    """返回 (字幕行列表, 来源标记)。拿不到**可信**字幕时返回 ([], "no_subtitle:<原因>")。"""
    info = fetch_bilibili_info(video_id)
    cid, aid, duration = info["cid"], info["aid"], info.get("duration")

    sessdata, sess_origin = resolve_sessdata(sessdata)
    if not sessdata:
        # 没登录时 B 站必然返回空，直接短路，不必浪费 6 次重试
        return [], "no_subtitle:not_logged_in"
    cookies = {"SESSDATA": sessdata}

    for attempt in range(_MAX_ATTEMPTS):
        try:
            result = _try_once(cid, aid, video_id, cookies, duration)
        except (requests.RequestException, ValueError, KeyError):
            result = None
        if result:
            lines, lan, sub_id = result
            return lines, f"bilibili_subtitle:{lan}(auth={sess_origin},sub_id={sub_id},verified_vs_duration)"
        if attempt < _MAX_ATTEMPTS - 1:
            time.sleep(1)

    # 重试若干次仍拿不到「覆盖到片尾」的字幕：可能该视频确实没有完整 AI 字幕。
    # 此时返回空，让上层去走 ASR——绝不返回没通过校验的字幕。
    return [], "no_subtitle:none_verified"
