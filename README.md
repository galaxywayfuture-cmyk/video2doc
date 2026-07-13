# Video2DocAgent

给定一个视频 URL（YouTube 或 Bilibili），自动生成：

1. **结构化 Markdown 总结文档**（`doc.md`）——含全局概述、主题标签、大纲、分段详情（保留时间戳，可追溯回原视频片段）
2. **审计记录**（`trace.json`）——记录每一步工具/Agent 调用的输入输出摘要、耗时、模式（是否用了降级方案）
3. **记忆建议**（`memory_suggestions.json`）——供未来的长期记忆系统消费的结构化建议

完整的设计理念与复刻说明见 [`PROJECT_EXPORT.md`](PROJECT_EXPORT.md)。

## 架构：三层职责边界

```
tools/    确定性操作，不调用LLM（URL解析、拉字幕、清洗、分段、拼文档、下载音频、本地ASR识别）
agents/   唯一可能调用LLM推理的地方（MVP阶段用"Agent-in-loop"代替真实LLM调用）
core/     横切关注点：数据契约(schemas)、审计(trace)、记忆(memory)、命名(naming)
```

- **Agent 无状态**：每次调用完全自包含，可审计、可单独重放、可并行执行；跨运行记忆剥离到 `core/memory.py`
- **Prompt 与代码解耦**：每个 Agent = `xxx_agent.py`（调用逻辑）+ `xxx_agent.prompt.md`（system prompt）
- **字幕三级降级链路**：平台官方字幕 → （拿不到时）yt-dlp 下载音频 + faster-whisper 本地 ASR

## 安装

```bash
pip install -r requirements.txt
```

无需系统安装 ffmpeg——`imageio-ffmpeg` 会提供便携版 ffmpeg 二进制。

## 运行（"Agent-in-loop" 两阶段流水线）

当前环境未接入真实 LLM API，流水线拆成两个独立脚本，中间由 AI 编码助手（或未来的真实 LLM API 调用）撰写摘要：

```bash
# 第一步：确定性预处理（URL → 字幕/ASR → 清洗 → 分段）
python runner/step1_prepare.py "<视频URL>" --window-seconds 300

# 【人工/Agent介入】：
#   读取 output/<step1打印出的目录名>/chunks.json，
#   参照 agents/*.prompt.md 的规范，撰写同目录下的
#   segment_summaries.json（[{chunk_id, summary, key_points, time_range}, ...]）
#   和 global_summary.json（{title, overview, outline, topics}）

# 第二步：拼装最终文档 + 补写 trace + 生成记忆建议
python runner/step2_finalize.py "<output_dir_name>"
```

输出目录采用人类可读命名：`output/<平台>_<清洗后的标题片段>_<video_id>/`。

若要实现全自动：把 `agents/` 中对 `core.llm_client` 的调用换成真实 LLM API（保持返回值格式不变），再写一个整合脚本串联两步即可，`step2_finalize.py` 无需改动。

## 已知限制

1. **Bilibili 官方字幕接口在匿名状态下经常拿不到字幕**（AI 字幕多数需要登录态 SESSDATA cookie）。当前自动降级为本地语音识别，准确率不如官方字幕；如需更高精度可将 `--asr-model` 改为 `medium` 或 `large-v3`（更慢）。
2. **当前未接入真实 LLM API**，摘要生成靠 "Agent-in-loop" 人工介入完成——这是 MVP 阶段的关键设计取舍，不是 bug。`trace.json` 中每条记录的 `mode` 字段（`normal` / `heuristic_fallback` / `agent_in_loop` / `local_asr:...`）诚实标注该步是否用了真实 LLM。
3. `chunk_subtitles` 目前是纯时间窗口切分（YouTube 长视频建议 600 秒/段），不是语义边界切分。
4. `workflows/video2doc.yaml` 只是说明性文档，没有动态执行引擎；`runner/` 下的两个脚本硬编码执行顺序。
