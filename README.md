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
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**必须是 `.venv`。** `./handle` 写死了用 `.venv/bin/python` 启动（这样 ASR 那套重依赖
不会污染系统环境），所以虚拟环境目录名就得叫 `.venv`、且装在仓库根目录。

无需系统安装 ffmpeg——`imageio-ffmpeg` 会提供便携版 ffmpeg 二进制。

## 运行（推荐：一条命令）

```bash
export ANTHROPIC_API_KEY=sk-ant-...        # 摘要要调 LLM，没有它跑不了
./handle "https://www.bilibili.com/video/BV1Ji9aB4Eu2"
```

产物落在 `output/<短标题>/`（短标题由 LLM 从原标题压成 5~10 字）：

```
output/探秘Claude Code/
├── 探秘Claude Code.md   # 总结（文件名 = 视频标题）
├── 口播稿.md             # 字幕/转写文本，带时间戳
├── audio.mp3            # 仅走了「下载转写」路径时才有
├── trace.json           # 审计记录
└── memory_suggestions.json
```

**B 站需要登录态。** 字幕接口匿名一律返回空——那是「没登录」，不是「没字幕」。
在浏览器登录 bilibili.com 即可（会自动读取 cookie），或 `export BILIBILI_SESSDATA=...`。
没登录时 `handle` **不会**默默去跑几十分钟的 ASR，而是直接报错提示；
确认某视频真的没字幕，再加 `--allow-asr`。

### 无字幕视频怎么跑

有些视频 UP 主没传 CC 字幕、也没有 AI 字幕。这类视频只能走「下载音频 → 本地
语音识别」的降级路径：

```bash
export ANTHROPIC_API_KEY=sk-ant-...
# 浏览器登录 bilibili.com（自动读 cookie），或 export BILIBILI_SESSDATA=...
./handle "https://www.bilibili.com/video/BV1kvMe6dEVb" --allow-asr
```

- **为什么要加 `--allow-asr`**：没登录时抓不到字幕会被标成 `no_subtitle:not_logged_in`，
  这是「补个登录态几秒钟就能解决」的情况，默认**不**烧几十分钟 CPU，所以直接报错。
  只有你明确加 `--allow-asr`，才允许在这种情况下也降级去跑 ASR。
  （已登录、且确认视频真没字幕时，来源是 `no_subtitle:none_verified`，会**自动**走 ASR，
  这个 flag 加不加都行——但加上最稳妥，省得纠结当前是哪种情况。）
- **慢**：`faster-whisper` 在 CPU 上按 int8 跑，十几分钟的视频通常要几分钟到十几分钟；
  想更快/更准可调 `--asr-model tiny|base|small|medium|large-v3`（默认 `small`）。
- **产物多一份 `audio.mp3`**，`trace.json` 里的 `subtitle_source` 会如实标成
  `local_asr:...`，`口播稿.md` 是未经清洗的原始转写，仅供追溯参考。
- **精度**：本地 ASR 不如官方字幕，专有名词/英文术语易出错；要高精度可拿产物里的
  `口播稿.md` 和其它转写交叉比对。

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

1. **B 站字幕接口偶发串台**——同一个 `(aid, cid, bvid)` 连续请求，实测出现过 3 种不同 `sub_id`，其中有的内容和时长跟目标视频毫无关系（一份 54:35 的字幕混进 47:45 的视频），还会返回空列表或空 `subtitle_url`。危险在于**它是静默的**：你会拿到一份语法完全正常、但属于另一个视频的字幕。`fetch_subtitle_bilibili` 因此**强制用视频时长双向校验**（字幕末尾时间戳必须落在时长的 90%–102% 区间，上下限都要卡——只卡下限会放过「比视频还长」的串台字幕），最多重试 12 次；校验不过宁可返回空让上层降级，也不返回不可信的字幕。
2. **B 站字幕需要登录态**，匿名一律为空。这不是「没字幕」，是没登录——`no_subtitle:not_logged_in` 与 `no_subtitle:none_available` 是分开标注的，处置完全不同。
3. **摘要必须有 LLM 凭证**，没有就直接报错，不再降级。（原来的启发式抽取式降级用 `[A-Za-z']+` 分词，匹配不到任何中文字符，对中文视频只会产出「看着像总结的垃圾」——静默的低质量比直接失败更糟，故已删除。）
4. 官方 AI 字幕本身也非人工校对，英文术语仍有误差（Claude Code→「可靠 code」、agent→「AH」）。需要高精度时可与 Whisper 转写交叉比对。
5. `chunk_subtitles` 是纯时间窗口切分，不是语义边界切分。
6. `workflows/video2doc.yaml` 只是说明性文档，没有动态执行引擎；`runner/` 下的脚本硬编码执行顺序。
