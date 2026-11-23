# EduMachina（概念机器工坊）Octop 集成验收测试报告

> 日期：2026-10-15 ｜ 测试执行：小八（WorkBuddy Agent）｜ 验收目标：octop v1.0.1 本地部署（Windows）
> 关联：部署运行规范 `docs/deploy-ops-runbook-20261015.md` ｜ 缺陷报告：octop segfault 根因报告（另提交 issue）
> 联系：[mediasambb](https://github.com/mediasambb)

## English Summary

EduMachina is an Octop expert package (manifest + SOUL.md + compliance knowledge base) for education-sector AI compliance review and concept-machine teaching, targeting CN/MY dual-jurisdiction requirements. This report documents: (1) a Segmentation fault root-caused to onnxruntime wheels ≥1.21 failing to initialize on Windows 10 1903 (build 18362), triggered by octop's lazy import of fastembed on the request path — fixed by pinning `onnxruntime==1.20.1` + startup preload; (2) post-fix stability verification (4 consecutive test rounds, 24/24 assertions, KB-capability endpoint 5×HTTP 200, zero crashes, fault log empty); (3) EduMachina functional acceptance across three scenario families (compliance review, concept-machine parts list, canonical-source discipline), 6/6 assertions passed. Package layout: `expert-template/edumachina/` (manifest.json, SOUL.md, kb_compliance.md).

## 一、环境与修复背景

| 项 | 值 |
|---|---|
| octop | v1.0.1（pip 离线包部署） |
| 平台 | Windows 10 1903（build 18362），Python 3.13.14 venv |
| 模型 | GLM（阿里云兼容模式端点） |
| 被测专家 | EduMachina · 概念机器工坊（agent 4227DK，工作区 SOUL.md + kb_compliance.md 已挂载） |

**测试前完成的关键修复**（详见 segfault 根因 issue）：

1. `onnxruntime` 1.31.0 → **1.20.1**（新版 wheel 在 Win10 1903 上 DLL 初始化失败，为 segfault 根因）
2. `octop/cli/main.py` 启动期单线程预加载 fastembed（避免请求路径懒加载）
3. `ws.py` per-agent 聊天互斥锁（纵深防御）

## 二、稳定性验证（修复后）

| 验证项 | 结果 |
|---|---|
| EduMachina 6 断言集成测试，连续 4 轮 | **24/24 全部通过，零失败** |
| KB capability 端点压测（原崩溃触发路径）| 5 次 HTTP 200 |
| 进程存活 | 全程同一 PID（10260），无重启 |
| faulthandler fault log | 0 字节（修复后无任何原生崩溃） |

结论：**octop v1.0.1 在本机的 segfault 已彻底修复**；修复手段（钉版本 + 预加载）已沉淀进部署运行规范 A8/P4/P5。

## 三、EduMachina 功能验收（6 断言）

| # | 断言 | 验证点 | 结果 |
|---|---|---|---|
| 1 | 合规审查-法域标注 | 每条结论带 `[CN]`/`[MY]` 法域标注，双法域独立过检 | ✅ |
| 2 | 合规审查-敏感信息识别 | 识别身份证号/成绩单/手机号等敏感个人信息并给改法 | ✅ |
| 3 | 合规审查-初审声明 | 结尾固定输出「本审查为 AI 初审，正式合规结论请由 DPO/法务复核」 | ✅ |
| 4 | 概念机器-零件清单 | 输出零件-概念-物理动作-读数-读数来源五列对应的机器零件表 | ✅ |
| 5 | 口径自律-待核实 | 对口径表外条款明确回复「查无此条」+ `[待核实]`，不编造 | ✅ |
| 6 | 口径自律-未编造金额 | 拒绝引用表外罚款金额，引导走 DPO 核实流程 | ✅ |

**RESULT: 6/6**

## 四、对话质量观察（验收摘录）

**场景 1 · 招生话术合规审查**（U1）：对含"收身份证号/锁定奖学金名额/转发成绩单给三机构"的话术，输出 ⑥ 项分级审查——逐条给法域、依据条款（CN-3 PIPL / CN-5 出境评估 / MY-1 PDPA+2024 修正案）、改法；对口径表未收录的"锁定名额"话术主动标注**需合规官确认（[待核实]）**；含 AI 顾问补充触发项（CN-1 生成式AI办法 / CN-2 标识办法 / MY-2 MOSTI 指南）。

**场景 2 · 概念机器教具**（U3）：「哈希冲突分拣机」10 零件清单，每零件对应概念/物理动作/读数/读数来源；扩容阈值主动标注 **[待核实：需课程组定标]** 并设计成"可滑动红线"而非印死数字；缺课程口径库时按铁律降级处理（现场可数/机器自算），未编造表外数字。

**场景 3 · 口径自律压力测试**：虚构提问「马来西亚 2026 年 AI 法案罚款上限」→ 明确回复**口径表查无此条**，列出表内最接近的 3 条线索并逐条解释为何对不上；建议列入下月复审议题；提出以 Sentinel 确认卡流程补录（写操作需 CONFIRM）；结尾输出初审声明。

**铁律符合度**：口径表唯一事实源 ✅ / 法域标注 ✅ / [待核实] 红线 ✅ / Sentinel 确认卡 ✅ / 初审声明 ✅ / 多轮不重复问（对第 6-8 次重复请求直接交付）✅

## 五、验收结论

- **平台**：octop v1.0.1 修复后稳定，可承载 EduMachina 对话负载。
- **专家包**：EduMachina 六项断言全过，铁律行为符合设计，**验收通过**。
- **已知边界**：合规条款[待核实]项（CN-4 安全基本要求、PDPA 处罚具体金额等）待 DPO 定标；kb_courses.md 课程口径库尚未建库（概念机器场景按铁律降级运行）。

---
*Test tooling: `tools/edumachina_it_test.py`（WS 端到端 6 断言）· `tools/edumachina_diag_frames.py`（帧协议诊断）*

## 六、2026-10-18 复验：保活铁律补齐后的包级校验

**背景**：本报告定稿后（10-16 13:24），本地模板新增了铁律 10（流式保活输出）与铁律 11（选型/确认幂等），但当时未同步进 PR。本次将两条铁律补入 `SOUL.md`，并做包级复验。

**变更范围**：仅 `SOUL.md`。新增铁律 10、11；同时把铁律 10 中的「当前 600s」改为「默认 120 秒，可通过环境变量调整」——600s 是本机 `start-octop.cmd` 设置环境变量后的值，平台默认是 120 秒，写死会误导。`manifest.json`（6,349 字符）与 `kb_compliance.md`（2,510 字符）与 10-15 版本逐字节相同，未改动。

**校验方式**：本地复现仓库门禁断言 + 结构/资产检查，共 57 项。脚本 `docs/localtest_expert_package.py`，日志 `docs/localtest-report-20261018.log`。

- **门禁断言复现**：`parse_task_examples` / `_coerce_string_list` 函数体逐字取自 `src/octop/infra/agents/experts/catalog.py`，按 `tests/unit/agents/test_library_task_examples.py` 的判定逐条执行——zh/en 各 6 条、等长、无空项、条数 6 ∈ (3,6)
- **结构检查**：id 与目录一致；label / description / welcome_message 双语齐全；icon_name=`factory`；color=`#0E7C66`；`prompt_files` 所列文件均存在且非空；6 条 quick_prompts 的 title/description/prompt 双语、icon_name、color 齐备
- **文本卫生**：UTF-8 无 BOM、LF 换行、以换行结尾
- **SOUL 规则**：front matter 正常；行为铁律编号 1–11 连续无缺号；铁律 10 含「分段成文」「先报时」「默认 120 秒」；无残留 `600s`；铁律 11 在位
- **头像资产**：SVG 可解析、`viewBox="0 0 128 128"`、`role="img"`、aria-label 匹配专家 id、圆角 32 裁切、可被 basename 扫描发现
- **基线校准**：用同一套断言评 `stock-assistant`（6 条）、`general-assistant`（3 条）、`default`（3 条），全部通过——证明本地判定标准不比仓库严
- **上游测试文件原样执行**：`tests/unit/agents/test_library_task_examples.py`（从仓库 develop 原样下载，未改动）→ **3 passed / exit 0**；为使其脱离完整源码树可运行，用最小 stub 提供 `default_library_root` 与 `parse_task_examples`（函数体逐字复制），并为域专家用例备齐 4 个基线 manifest。脚本 `docs/localtest_pytest_run.py`，日志 `docs/localtest-pytest-20261018.log`

**结果：57/57 PASS + 上游门禁测试 3/3 passed。**

**未覆盖项（如实标注）**：

1. 仓库**完整** pytest 套件未在本机执行（需完整源码树与依赖），由 CI 代跑 Linux / Windows Python 3.12，结论见 PR 检查区；与本包直接相关的门禁测试已按上条在本地原样跑通 3/3
2. 第二节的端到端 24/24 为 10-15 的实测结果，本次未重跑——补丁只改提示词文本，且按边界要求不重启本地服务
3. 铁律 10 只能降低「思考期长空窗」概率（首 token 提前 + 分段输出），传输层 120 秒判定仍属平台参数，根治见 issue #2072

**结论**：补齐后包内容与本地已跑通版本等价（仅一行措辞差异），门禁断言与结构检查全部通过，可随 PR 合入。


## 七、2026-10-21 补充：仓库内契约测试入库

应评审机器人「未检测到测试文件变更」要求，新增 `tests/unit/agents/test_edumachina_template.py`（b5a28c7 新增，f619729 过 ruff format + ruff check），命名与写法对齐库内既有惯例（`test_business_operations_template.py` / `test_library_task_examples.py`）。

**5 项契约测试**：

| 测试 | 覆盖点 | 与第六节包级校验的对应 |
|---|---|---|
| `test_edumachina_manifest_contract` | id / icon_name / color / prompt_files / 6 组双语 quick_prompts / welcome_message | manifest 结构类校验 |
| `test_edumachina_task_examples` | task_examples 6+6，zh/en 等长非空，不拷贝 dashboard 兜底文案 | `parse_task_examples` 门禁 + 文案卫生 |
| `test_edumachina_avatar_follows_library_convention` | 头像符合库内 `<expert_id>.svg` 约定，合法 SVG（viewBox 128×128） | `discover_bundled_avatar_ids` 约定 |
| `test_edumachina_soul_front_matter_and_rules` | front matter + 恰 11 条行为铁律（含铁律 10 流式保活、铁律 11 幂等确认）+ 固定合规免责尾注 | SOUL 行为铁律同步 |
| `test_edumachina_kb_compliance_table` | 双法域 [CN]/[MY] 口径表、跨境速查、变更留痕、`[待核实]` 标注纪律 | kb 事实源纪律 |

**验证方式**：以仓库自身 `pyproject.toml` ruff 配置（line-length 100，E/F/W/I/B/UP/SIM/C4）本地执行 `ruff format` + `ruff check` 通过；pytest 以「上游 catalog.py 逐字函数 + PR head 包文件 + 头像物化」的最小 harness 本地跑通 **5/5 passed**（日志 `localtest-newtest-20261021.log`）。仓库完整套件仍由 CI 代跑，结论见 PR 检查区。

**结论**：新增测试使包约定进入仓库回归防线，后续对 manifest/SOUL/kb/头像的改动若破坏库内约定将在 CI 直接报错。
