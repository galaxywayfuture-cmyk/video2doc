"""
core.naming

职责：把视频标题转成人类可读、文件系统安全的输出目录名。
保留中文字符（对中文用户更友好），去掉话题标签/表情符号/非法文件名字符，
并在末尾附加 video_id 以保证唯一性。
"""
from __future__ import annotations

import re

_INVALID_CHARS = r'[\\/:*?"<>|#@]'
_MAX_TITLE_LEN = 40


def build_output_dir_name(platform: str, video_id: str, title: str) -> str:
    cleaned = re.sub(_INVALID_CHARS, "", title)
    cleaned = re.sub(r"\s+", "_", cleaned.strip())
    cleaned = cleaned[:_MAX_TITLE_LEN].strip("_")
    if not cleaned:
        return f"{platform}_{video_id}"
    return f"{platform}_{cleaned}_{video_id}"
