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
