"""
工具：download_audio

职责：当平台官方字幕接口拿不到字幕时的降级方案——用 yt-dlp 下载视频的
音轨并转成 mp3，供后续本地语音识别（transcribe_audio）使用。
确定性操作（下载+转码），不涉及模型推理。
"""
from __future__ import annotations

from pathlib import Path

import imageio_ffmpeg
import yt_dlp


def download_audio(url: str, output_dir: str | Path, filename_stem: str = "audio") -> Path:
    """下载 url 对应视频的音轨，转成 mp3，返回 mp3 文件路径。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_template = str(output_dir / f"{filename_stem}.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": out_template,
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
        "ffmpeg_location": imageio_ffmpeg.get_ffmpeg_exe(),
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    mp3_path = output_dir / f"{filename_stem}.mp3"
    if not mp3_path.exists():
        raise RuntimeError(f"音频下载/转码失败，未找到预期文件: {mp3_path}")
    return mp3_path
