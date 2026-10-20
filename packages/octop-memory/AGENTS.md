# AGENTS.md

本文件是所有 coding agent 共用的工作协议。用户入口见 [README_CN.md](README_CN.md)，
贡献入口见 [CONTRIBUTING.md](CONTRIBUTING.md)，项目认知保留在 `docs/agent/`，宿主接入见
[docs/integrations.md](docs/integrations.md)。沿用 Harness 的澄清、实现、验证、文档对齐闭环。

## 项目速览

`octop-memory` 是可独立使用的 Agent 记忆组件，为 Octop / octop-harness 及其他宿主提供记忆能力。
本仓负责证据捕获、事实提炼、召回、存储与迁移；Agent 执行、模型调用调度和用户界面由宿主组织。
核心是 stdlib + SQLite，PostgreSQL、向量索引和 LLM 通过可选后端/接口接入。

- 公共入口：`Memory`（`core.py`）与 `MemoryService`（`service.py`）；共享编排在 `application/`。
- 业务流水线在 `pipeline/`，持久化在 `storage/`；CLI / JSON-RPC 在 `adapters/`。
- `plugins/<host>/` 是外部 Agent 适配目录；当前实现包括 OpenClaw、Hermes，新增宿主复用共享业务逻辑。
- 按任务找代码和验证入口，见 [PROJECT_MAP](docs/agent/PROJECT_MAP.md) 与 [TEST_MATRIX](docs/agent/TEST_MATRIX.md)。

## 工作方式

- 开始前检查 `git status --short` 和相关 diff，保留用户已有改动。
- 非平凡改动先说明目标、涉及文件、预期行为、最小验证和风险；大任务分阶段，保持范围聚焦。
- 代码、测试、配置和文档同步更新；不顺手重构无关模块，不为每次任务新增文档。
- 中文解释设计，保留代码实体、字段、CLI、环境变量与错误信息原文。
- 示例使用通用占位符和临时数据库，不提交私人路径、运行记录、凭据、导出记忆或真实数据库。

## Harness 文档闭环

**记录范围**：`docs/agent/` 用于理解代码和接续开发，记录业务逻辑、架构、public API、数据契约、
召回/写入行为，以及相关 bug、新需求、设计取舍和未解决风险。
banner、排版、措辞、链接、Python 版本、依赖/锁文件、构建/CI 和个人工具配置等常规维护，
只更新对应文件及必要的 README/CONTRIBUTING/CHANGELOG，不写入 Harness，也不为此新建 HANDOFF 或 ADR。
若这类维护同时改变了运行行为或数据契约，仅记录其代码影响，不记录维护操作流水账。
以下回写要求仅适用于上述代码相关范围；判断依据是实际影响，不是改动文件数量或是否修改了代码文件。

1. **入场核对**：快速扫描相关代码、diff 与近期相关提交，对照 [HANDOFF](docs/agent/HANDOFF.md)
   和 [PROJECT_MAP](docs/agent/PROJECT_MAP.md)。核对召回 source/顺序、public API、配置、prompt 与验证命令；
   不依赖日期或提交数推断新鲜度。发现漂移，修正相关描述；范围外缺口记入 [KNOWN_RISKS](docs/agent/KNOWN_RISKS.md)。
2. **文本澄清**：在现有 Issue / PR 或 HANDOFF 中写明 bug 的实际/预期行为、最小复现，
   或需求的使用场景、范围/不做什么、可验证验收条件；列出假设和待澄清问题。
   会改变范围、兼容性或数据安全的未决问题需先澄清；已明确授权的工作继续执行，不重复索要确认。
3. **实现与验证**：按最小可验证闭环实现，运行相关测试及完整门禁。涉及召回/写入或双 backend 时执行下述硬规则。
4. **认知回写**：代码相关的非平凡任务更新 HANDOFF 的当前状态、关键文件、验证结果、风险与下一步；
   模块/调用链/运行策略配置变更更新 PROJECT_MAP；重要代码取舍更新 [DECISIONS](docs/agent/DECISIONS.md)；
   行为验证方式变更更新 [TEST_MATRIX](docs/agent/TEST_MATRIX.md)；代码相关缺口更新 KNOWN_RISKS；
   术语变更更新 [GLOSSARY](docs/agent/GLOSSARY.md)，对外行为变更核对 [README_AUDIT](docs/agent/README_AUDIT.md)。

每份文档只承载自己的事实，不重复复制。HANDOFF 保留当前任务/未决项，历史通过 Issue / PR / Git 查阅；
DECISIONS 保留稳定 ADR 编号及替代关系，不追加日期流水账。只改 HANDOFF 而遗漏受影响的地图或测试矩阵不算完成。

## 架构约束

- `Memory` 为公共存储 API；`MemoryService` / `Bridge` 复用 `application.MemoryRuntime`。
- pipeline、storage、domain 不依赖 adapters；storage 不依赖 pipeline；service 不依赖 bridge。
- 新宿主通过 application 接入；现有源码 dashboard 的直接 SQLite 访问不是新模块的模板。
- `AtomCard` 是事实真源，tree leaf 只引用 atom；Chroma/Qdrant 是可选 index，不是关系 backend。
- 不擅自改变 public API、数据格式、配置默认值或增加生产依赖。

## 双 backend gate

SQLite/PostgreSQL 均为正式支持的 memory backend。涉及 public 读写、持久化编排、backend contract、
schema、SQL、transaction、FTS 或 lifecycle 时：

1. 同步维护两种 backend，用同一组行为断言验证，优先扩展 `tests/test_backend_parity.py`。
2. 使用真实专用 PostgreSQL 和 `TEST_POSTGRES_DSN`，确认相关 PG cases 未 skip。
3. 有意的单 backend 能力必须明确拒绝另一 backend，并在 KNOWN_RISKS 中说明原因。
4. backend-specific SQL 留在 `storage/backends/`；不把既有能力缺口当作新代码可以静默分叉的理由。

## 召回与写入敏感路径

| 范围 | 需要说明的影响 |
|---|---|
| `core.py`、`storage/backends/` | 公共写入、事务、schema、索引、namespace |
| `pipeline/extractor/`、`pipeline/promotion/`、`pipeline/episode/` | 哪些内容成为 Candidate、AtomCard 或 Episode |
| `pipeline/recall/`、`pipeline/page/` | source、排序、raw policy、去重、budget、页面内容 |
| `application/runtime.py`、`application/path_projection.py`、`application/host_files.py` | 工具搜索、路径可读内容和 host 文件 |
| `adapters/bridge/handlers.py`、宿主插件 hook | capture/extract、memory_search/memory_get 的宿主行为 |

修改这些行为时，用 `⚠️ 召回/写入路径变更` 明确说明具体影响、受影响 source/layer 和验证命令。
仅编辑说明或构建清单时说明行为未变，不将文档整理描述为 runtime 变更。

## 验证与交付

```bash
make install-hooks    # 每个 clone 一次，提交前不得绕过失败门禁
make all              # format + lint + strict mypy + pytest
```

代码改动先运行最小相关测试，再执行完整门禁；纯文档维护只需相关文档检查，提交前仍执行完整门禁。
失败时找到首个根因、做范围内最小修复并重跑；
环境或既有问题阻止验证时，明确报告失败/skip 和复现命令，不声称通过。
交付前确认实现符合验收、相关文档与代码一致；属于 Harness 记录范围的任务将实际验证和未解决项写入 HANDOFF；
无法通过的门禁必须说明根因及后续命令，不能把未验证状态写成完成验收。
完成回复简述改动、验证和剩余限制即可，不要求固定多节交接模板。

未经用户明确授权，不执行 push、重写 Git 历史、大目录删除、生产部署或密钥修改。
详细验证与双 backend 命令见 [TEST_MATRIX](docs/agent/TEST_MATRIX.md)，分支与发布检查见 [CONTRIBUTING.md](CONTRIBUTING.md)（`develop` 集成 + `/publish` skill）。
