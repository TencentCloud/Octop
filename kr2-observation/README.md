# KR2 · Subagent 上下文与前缀缓存实测数据

> 观测时间：2026-07-15 ~ 07-16 · 模型：`glm-5.2`（OpenAI 兼容网关）· 追踪：本地 Langfuse v3

回答两个问题：

1. **一次 `task(subagent_type=…)` 委派中，子 agent 命中了父 agent 上下文的多少？**
2. **provider 侧的前缀缓存在 agent 多轮/委派流量下的真实行为是什么？**

方法：隔离仿真（workspace 复制自真实 Agent，剔除 memory/checkpoint），HarnessAgent 配置与线上一致，
全链路经 Langfuse 追踪；再用请求重放和布局探针做对照实验。**不触碰线上实例。**

---

## TL;DR

| # | 发现 | 证据 |
|---|------|------|
| 1 | 子 agent 对父 **system prompt** 的命中为**零**：公共前缀 0 字符；内容仅 10% 复现且全为框架样板。父的人格 / 记忆文件 / 对话历史对子完全不可见 | `context/*.system-prompt.md` 逐字符比对（`analyze_trace.py`） |
| 2 | 但请求拍平后的真实布局是 **[工具 schema 区][system][对话]** —— 工具在最前。子继承父工具（仅去掉 `task`），前 8 个工具逐字节相同 → 父子请求存在 ~3.4k token 公共前缀 | 布局探针 X：换掉整个 system，工具区 7,808 tok 照样命中（`layout_probe.py`） |
| 3 | 前缀缓存**严格按位置**匹配：第 1 个工具改一个词 / 前两工具换序 → 命中归零；分叉点之后即使内容相同（位置偏移）也全部失效 | 探针 P3 / P4 / Y（`layout_probe_results.md`） |
| 4 | 缓存**异步分块提交**（64-token 块）：相同请求重放 3 次命中 0 → 2,624 → 17,024；暖缓存后前缀扩展（多轮追加）可命中 17,088/17,291，时延 6.5s → 2.9s（**−55%**） | `cache_probe.py` |
| 5 | 命中**不稳定**：相同请求的 prompt_tokens 在 7766~7845 间抖动 → 网关后有 ≥2 种模板/副本轮转，无会话亲和时命中近乎抽签 | 探针原始输出 |
| 6 | 委派时间结构：单次委派 25.5s，子 episode 13.9s（54%），父全程阻塞 | Langfuse trace `dda8dc3e…` |

## 对 KR1 / KR2 的行动项

1. **一行级优化**：子 agent 工具列表保持父的顺序、把 `task` 挪到父列表**末尾** → 父子公共前缀从 ~3.4k 扩到整个工具区（~7.7k），命中翻倍以上（改动点在 deepagents 填充子 agent 工具处）。
2. **编排原则**：稳定内容前置（工具 schema、框架指令），易变内容后置（记忆、时间戳、对话）；禁止在请求前部做动态注入。
3. **服务端协同**：与网关侧确认缓存提交延迟与会话亲和（sticky routing）——这是把 −55% 时延稳定拿到手的前提。
4. **KR1 挂钩**：PolicyRouter 将"缓存亲和度"纳入路由决策；把 `cached_tokens` 命中率记为 provider 健康指标。
5. 子 agent 继承了 `memory_search`/`memory_get` 工具 → 静态上下文零命中，但存在**运行时主动查父记忆**的通道，KR3/KR4 记忆隔离设计需覆盖。

## 文件清单

| 文件 | 说明 |
|------|------|
| `index.html` | 可视化观测报告（时间线 / token 构成 / prompt 重叠图），浏览器直接打开 |
| `sim_task_langfuse.py` | 仿真：构建同配置 HarnessAgent + Langfuse 回调，触发一次真实 task 委派 |
| `analyze_trace.py` | 从 Langfuse API 拉 trace，计算父/子 system prompt 重叠 |
| `cache_probe.py` | 缓存探针：A/A 重放 + 前缀扩展重放（发现 4 的复现脚本） |
| `layout_probe.py` | 布局探针：W/X/Y/P3/P4 五组对照实验（发现 2、3、5 的复现脚本） |
| `layout_probe_results.md` | 布局探针的完整数据与结论 |
| `bench_subagents.py` | subagent 扫描/解析/图编译分段计时（本地后端：扫描 1.9ms / 整图编译 45ms） |
| `trace_analysis.json` | *（本地生成，不入库）* 3 次 GENERATION 的分析数据（含完整 system prompt） |
| `context/` | *（本地生成，不入库）* 三次调用的完整上下文导出：`*.system-prompt.md` / `*.messages.txt` / `*.raw.json` |

> `context/` 与 `trace_analysis.json` 含完整会话转录，已通过 `.gitignore` 排除，不随仓库分发；
> 运行 `sim_task_langfuse.py` + `analyze_trace.py` 可在本地重新生成。`cache_probe.py` / `layout_probe.py`
> 依赖 `context/parent-turn1.raw.json`，需先完成上述生成步骤。

## 复现

前置：一个可用的 OpenAI 兼容 provider（脚本从 `~/.octop/octop.db` 读取配置）；
`sim_task_langfuse.py` 额外需要本地 Langfuse（`docker-compose` 起 langfuse v3，keys 见脚本头部，均为本地自建实例的占位 key）。

```bash
.venv/bin/python kr2-observation/layout_probe.py    # 布局与位移实验（约 15 次调用 × ~8k tok）
.venv/bin/python kr2-observation/cache_probe.py     # 缓存提交/前缀扩展实验（4 次调用 × ~17k tok）
.venv/bin/python kr2-observation/sim_task_langfuse.py  # 完整委派仿真（需 Langfuse）
```

## 注意事项

- 所有脚本**不包含任何密钥**，运行时从本地 `octop.db` 读取 provider 配置。
- `context/` 中的记忆区（关于我/关于用户）为**未填写的空模板**，已人工确认无个人信息。
- 单次探针受"副本抽签"影响显著，结论均基于多次取样（取最大值）；复现时请以趋势为准。
- token 尺寸按字符估算与实测有 ~40% 偏差（schema JSON 的 token 密度更高），以 `cached_tokens` 实测为准。
