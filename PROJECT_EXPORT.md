# Video2DocAgent — 项目复刻说明文档

本文档是项目的复刻/设计说明。原始版本内嵌了全部源码以便在无仓库的情况下复刻；本仓库中源码已就位，因此本文档保留设计理念、目录结构、运行方式与已知限制，代码部分请直接阅读对应源文件。

---

## 1. 项目目标

给定一个视频 URL（YouTube 或 Bilibili），自动生成：

1. 结构化的 Markdown 总结文档（`doc.md`）——含全局概述、主题标签、大纲、分段详情（保留时间戳，可追溯回原视频片段）
2. 审计记录（`trace.json`）——记录每一步工具/Agent调用的输入输出摘要、耗时、模式（是否用了降级方案）
3. 记忆建议（`memory_suggestions.json`）——供未来的长期记忆系统消费的结构化建议

## 2. 设计理念（复刻时必须保留的核心原则）

### 2.1 三层职责边界

```
tools/    确定性操作，不调用LLM（URL解析、拉字幕、清洗、分段、拼文档、下载音频、本地ASR识别）
agents/   唯一可能调用LLM推理的地方（本项目MVP阶段用"Agent-in-loop"代替真实LLM调用，见2.3）
core/     横切关注点：数据契约(schemas)、审计(trace)、记忆(memory)、命名(naming)
```

判断一个功能该放 `tools/` 还是 `agents/` 的标准：**是否涉及"理解/总结"这种需要语义推理的操作**。语音识别（ASR）虽然依赖模型，但只是"识别"文字，不涉及语义理解，因此归类在 `tools/` 而不是 `agents/`。

### 2.2 Agent 设计为"无状态"

`SegmentSummaryAgent.run(chunk)` 和 `GlobalSummaryAgent.run(segment_summaries)` 每次调用都是完全自包含的输入→输出，不依赖上一次调用的隐藏上下文。这是有意为之：**无状态 = 可审计、可单独重放、可并行执行**。跨运行的"记忆"被剥离到 `core/memory.py`，作为独立于 Agent 内部状态的外部产物，而不是让 Agent 内部悄悄攒状态。

### 2.3 Prompt 与代码解耦

每个 Agent 由两个文件配对组成：`xxx_agent.py`（调用逻辑）+ `xxx_agent.prompt.md`（system prompt，纯 Markdown）。目的：prompt 调优和代码逻辑是两种不同变更节奏的东西，解耦后 diff 更干净，且非工程角色也能直接改 `.md` 调 prompt。

### 2.4 "Agent-in-loop"两阶段流水线（当前无 LLM API key 时的关键设计）

当前环境未配置任何 LLM API key，因此无法让 Agent 自动调用真实 LLM 做总结。解决方案：把流水线拆成两个独立可执行的脚本，中间插入一个"由 AI Coding Agent 本人扮演 LLM"的人工步骤：

```
runner/step1_prepare.py <url>
  → 确定性处理：解析URL → 拉字幕(或降级为本地ASR) → 清洗 → 分段
  → 产出 chunks.json（每段的原始文本+时间戳）

  【人工/Agent介入】：读取 chunks.json，参照 agents/*.prompt.md 的规范，
  手写 segment_summaries.json 和 global_summary.json
  （在Cursor等场景下，这一步由发起本次会话的AI编码助手直接完成；
   若要全自动化，把这一步换成对真实LLM API的调用即可，接口不变）

runner/step2_finalize.py <output_dir_name>
  → 读取 segment_summaries.json + global_summary.json
  → 拼装 doc.md，补写trace，生成memory_suggestions.json
```

`trace.json` 里每条记录都有 `mode` 字段（`normal` / `heuristic_fallback` / `agent_in_loop` / `local_asr:...`），**诚实标注这一步是否用了真实LLM**，这是可审计性设计的核心体现。若要接入真实 LLM API，只需替换掉"人工介入"这一步、调用真实 API 生成同样格式的 JSON，`step2_finalize.py` 完全不需要改动。

### 2.5 字幕获取的三级降级链路

```
第一优先：平台官方字幕接口
  YouTube → youtube-transcript-api（通常都能拿到，包括自动生成字幕）
  Bilibili → 官方 x/player/v2 接口（匿名请求经常返回空列表，因为AI字幕
             多数情况需要登录态SESSDATA cookie才能拿到）

降级：本地语音识别
  当上面返回空字幕列表时，自动触发：
  download_audio()（yt-dlp下载音频轨转mp3）
    → transcribe_audio()（faster-whisper本地跑ASR，CPU int8量化，默认small模型）
    → 生成 transcript.md（原始转写全文，供追溯核对，明确标注是本地识别）
    → 继续走正常的 normalize_subtitles → chunk_subtitles 流程
```

### 2.6 输出目录人类可读命名

`output/<平台>_<清洗后的标题片段>_<video_id>/`，例如：
`output/youtube_Deep_Dive_into_LLMs_like_ChatGPT_7xTGNNLPyMI/`

而不是裸的 `output/7xTGNNLPyMI/`，方便人类在文件系统里直接识别每次运行对应哪个视频。

---

## 3. 完整目录结构

```
Video2DocAgent/
├── README.md
├── requirements.txt
├── PROJECT_EXPORT.md          # 本文档
├── agents/
│   ├── __init__.py
│   ├── segment_summary_agent.py
│   ├── segment_summary_agent.prompt.md
│   ├── global_summary_agent.py
│   └── global_summary_agent.prompt.md
├── tools/
│   ├── __init__.py
│   ├── parse_video_url.py
│   ├── fetch_video_title.py
│   ├── fetch_subtitle_youtube.py
│   ├── fetch_subtitle_bilibili.py
│   ├── download_audio.py
│   ├── transcribe_audio.py
│   ├── normalize_subtitles.py
│   ├── chunk_subtitles.py
│   └── generate_markdown_doc.py
├── workflows/
│   └── video2doc.yaml
├── core/
│   ├── __init__.py
│   ├── schemas.py
│   ├── trace.py
│   ├── memory.py
│   ├── naming.py
│   └── llm_client.py
├── runner/
│   ├── __init__.py
│   ├── step1_prepare.py
│   └── step2_finalize.py
└── output/
    └── <平台>_<标题片段>_<video_id>/
        ├── meta.json
        ├── audio.mp3            [仅ASR降级路径]
        ├── transcript.md        [仅ASR降级路径]
        ├── chunks.json
        ├── trace_partial.json
        ├── segment_summaries.json   [Agent产出]
        ├── global_summary.json     [Agent产出]
        ├── doc.md
        ├── trace.json
        └── memory_suggestions.json
```

---

## 4. 依赖清单

见 [`requirements.txt`](requirements.txt)。安装：`pip install -r requirements.txt`

无需系统安装 ffmpeg——`imageio-ffmpeg` 会提供一个便携版 ffmpeg 二进制，`download_audio.py` 通过 `imageio_ffmpeg.get_ffmpeg_exe()` 拿到路径并传给 yt-dlp。

`core/llm_client.py` 说明：这是给 `agents/` 使用的统一 LLM 调用入口，**当前代码路径实际未被使用**（因为项目改用了"Agent-in-loop"两阶段流水线，见第2.4节），但保留此文件作为未来接入真实 LLM API 的预留接口/降级基线。

`workflows/video2doc.yaml` 说明：这是流程的**声明式文档**，当前实现里 `runner/step1_prepare.py` + `step2_finalize.py` 是硬编码执行这个顺序的（不是真正读取此 yaml 动态调度）。保留此文件作为"流程说明书"；如果要做成真正的 yaml 驱动的执行引擎，需要另外写一个 workflow interpreter。

---

## 5. 运行方式

```bash
pip install -r requirements.txt

# 第一步：确定性预处理（URL → 字幕/ASR → 清洗 → 分段）
python runner/step1_prepare.py "<视频URL>" --window-seconds 300

# 【人工/Agent介入】：
#   打开 output/<step1打印出的目录名>/chunks.json
#   为每个 chunk 撰写摘要，写入同目录下的 segment_summaries.json
#   （schema: [{chunk_id, summary, key_points, time_range}, ...]）
#   综合所有分段摘要撰写全局总结，写入 global_summary.json
#   （schema: {title, overview, outline, topics}）
#   参照 agents/*.prompt.md 的输出格式规范

# 第二步：拼装最终文档
python runner/step2_finalize.py "<output_dir_name>"
```

若要实现**全自动**（不需要人工/AI编码助手介入撰写摘要），只需：

1. 在 `agents/segment_summary_agent.py` / `agents/global_summary_agent.py` 中把 `core.llm_client` 换成真实的 LLM API 调用（OpenAI/Anthropic/其他兼容接口均可，保持返回值格式不变）
2. 写一个整合脚本，在 `step1_prepare.py` 产出 `chunks.json` 后，直接调用 Agent 生成 `segment_summaries.json` / `global_summary.json`，再调用 `step2_finalize.py` 的逻辑——即可去掉"人工介入"这一步，实现单命令端到端运行

---

## 6. 已知限制

1. **Bilibili 官方字幕接口在匿名状态下经常拿不到字幕**（AI字幕多数需要登录态SESSDATA cookie）。当前的应对方案是自动降级为本地语音识别（下载音频+faster-whisper转写），已验证可行，但识别准确率不如官方字幕，尤其在中英混杂技术术语上会有错误（如"坐标系"→"作表系"）。如需更高精度可将 `--asr-model` 改为 `medium` 或 `large-v3`（更慢）。
2. **当前未接入真实 LLM API**，`agents/` 的摘要生成靠"Agent-in-loop"人工介入完成（见第2.4节和第5节）。这是本项目MVP阶段的关键设计取舍，不是bug。
3. `chunk_subtitles` 目前是纯时间窗口切分（默认按 `--window-seconds` 参数，YouTube长视频建议600秒/10分钟一段），不是语义边界切分，未来可以优化为按语义/静音间隔切分。
4. `workflows/video2doc.yaml` 目前只是说明性文档，没有真正的动态执行引擎去解析它；`runner/` 下的两个脚本是硬编码执行顺序的。

---

## 7. 已验证过的真实运行案例（可用于复刻后的回归测试）

| 视频 | 平台 | 字幕来源 | 分段数 | 结果 |
|---|---|---|---|---|
| Andrej Karpathy「Deep Dive into LLMs like ChatGPT」(~3.5小时) | YouTube | 官方自动字幕(英文) | 22段(10分钟窗口) | 生成约1.28万字符的结构化中文摘要 |
| 「一条视频建立你的AI概念坐标系」(~9分钟) | Bilibili | 本地ASR降级(faster-whisper-small) | 1段 | 成功识别+总结 |
| 「一条视频搞懂Agent」(~5.5分钟) | Bilibili | 本地ASR降级(faster-whisper-small) | 1段 | 成功识别+总结 |

复刻完成后，建议先用这三个真实 URL 跑一遍验证行为一致。
