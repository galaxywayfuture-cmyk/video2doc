"""
core.trace

职责：记录并持久化每次运行的审计信息（trace.json）。
"""
from __future__ import annotations

import json
from pathlib import Path

from core.schemas import ToolCallRecord, TraceRecord


class TraceRecorder:
    def __init__(self, url: str, platform: str):
        self._url = url
        self._platform = platform
        self._subtitle_source = ""
        self._chunk_count = 0
        self._time_range: tuple[float, float] = (0.0, 0.0)
        self._tool_calls: list[ToolCallRecord] = []

    def set_subtitle_source(self, source: str) -> None:
        self._subtitle_source = source

    def set_chunk_info(self, chunk_count: int, time_range: tuple[float, float]) -> None:
        self._chunk_count = chunk_count
        self._time_range = time_range

    def record_tool_call(
        self, step: str, input_summary: str, output_summary: str, duration_ms: float, mode: str = "normal"
    ) -> None:
        self._tool_calls.append(
            ToolCallRecord(
                step=step,
                input_summary=input_summary,
                output_summary=output_summary,
                duration_ms=duration_ms,
                mode=mode,
            )
        )

    def build(self) -> TraceRecord:
        return TraceRecord(
            url=self._url,
            platform=self._platform,
            subtitle_source=self._subtitle_source,
            chunk_count=self._chunk_count,
            time_range=self._time_range,
            tool_calls=self._tool_calls,
        )

    def save(self, output_path: str | Path) -> None:
        record = self.build()
        Path(output_path).write_text(record.model_dump_json(indent=2), encoding="utf-8")
