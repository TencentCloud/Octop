# 开发指南

从 [README](README_CN.md) 了解用途，从本文了解实现和贡献流程。AI 工作规则只维护在
[AGENTS.md](AGENTS.md)；外部 Agent 的接入方式、已有适配的安装配置和宿主契约统一见[集成指南](docs/integrations.md)。

## 开始开发

要求 Python 3.12+、支持 FTS5 的 SQLite 和 uv。

```bash
git clone https://github.com/TencentCloud/octop-memory.git
cd octop-memory
make install
make install-hooks
make all
```

从 `develop` 创建 `feature/*` 或 `fix/*`，用合成数据复现问题，再添加实现和相关行为测试。
`make all` 包括 format、lint、strict mypy、pytest；format 会改写文件。pre-commit 执行相同门禁。

源码辅助目录各有用途：`examples/basic_usage.py` 是唯一的基础示例，使用临时数据库演示公共 API、
组织树和 prompt recall；`evals/recall/` 是合成数据回归工具，指标局限见测试矩阵。
`scripts/` 保留插件构建、部署和宿主验收入口；部署/E2E 脚本需专用环境，不属于普通单测。
个人工具设置留在被忽略的 `.claude/`、`.codebuddy/`、`.cursor/` 中；共享的发版流程除外（已纳入版本库的 `.cursor/skills/publish` / `.codebuddy/skills/publish`）。项目规则只维护在 AGENTS.md。

## Harness 维护流程

代码相关 bug / 新需求先写明问题、范围和验收，再实现、验证、同步项目认知。已有 Issue / PR 可作为澄清正文，
在 [HANDOFF](docs/agent/HANDOFF.md) 留链接和当前状态即可；尚未开 Issue 的任务直接使用其中的简短模板。
规则集中在 [AGENTS.md](AGENTS.md)，人工开发者也沿用同一闭环。
banner、排版、链接、Python/依赖版本、构建/CI 等常规维护只更新对应文件与必要的用户说明，不写 Harness 记录。
若同时改变运行行为或数据契约，只记录代码影响。

| 文档 | 单一职责 |
|---|---|
| [HANDOFF](docs/agent/HANDOFF.md) | 当前任务的澄清、进度、验证、遗留问题和下一步 |
| [PROJECT_MAP](docs/agent/PROJECT_MAP.md) | 模块入口、调用链、数据流与边界 |
| [DECISIONS](docs/agent/DECISIONS.md) | 架构选择、理由、代价和替代关系 |
| [TEST_MATRIX](docs/agent/TEST_MATRIX.md) | 按改动范围选择验证命令和环境 |
| [KNOWN_RISKS](docs/agent/KNOWN_RISKS.md) | 当前缺口、限制与应对 |
| [GLOSSARY](docs/agent/GLOSSARY.md) | 核心术语 |
| [README_AUDIT](docs/agent/README_AUDIT.md) | 对外声明与实现的核对项 |

仅更新受影响的文档，不为每个任务新建文件；已完成任务的细节由 Issue / PR / Git 保存。
开发从 [项目地图](docs/agent/PROJECT_MAP.md) 开始，验证命令见 [测试矩阵](docs/agent/TEST_MATRIX.md)，
已知限制见 [风险清单](docs/agent/KNOWN_RISKS.md)。

## Checkpoint 维护

SQLite `CompactSqliteSaver` 默认复用较大的 `skills_metadata` 和 `memory_contents`，在同库
`hm_checkpoint_blobs` 保存不可变内容，`harness-checkpoint-v1` checkpoint 保存引用。
内容和 checkpoint 原子提交，读取时恢复原值；旧 inline 仍可读，历史不会自动批量迁移。
独立 reader 使用 `CheckpointSerializer.with_connection(conn)` 获取自身 decoder/cache 和一致事务视图。

```bash
# 默认只读预览。
octop-memory db slim /path/to/memory.sqlite
# 停止所有数据库使用者后：自动备份、去重、VACUUM，不删历史。
octop-memory db slim /path/to/memory.sqlite --apply --offline
# 降级 reader 前，显式展开旧格式；备份路径必须不存在。
octop-memory --db /path/to/memory.sqlite db checkpoints \
  --apply --offline --backup /path/to/new-backup.sqlite --expand
```

`--offline` 是操作者声明，不会停止进程。备份包含已提交 WAL，并需要额外磁盘空间。
`OCTOP_MEMORY_CHECKPOINT_DEDUP=0` 仅停止新引用写入，不展开存量；旧 reader 无法直接读取新格式。
迁移分批提交，重跑跳过已转换行；retention 需显式 completed thread、外部引用和依赖闭包。
在线 `slim_live_checkpoints` 由宿主负责暂停新 invocation、协调 reader 和恢复；长 reader 可能延期 WAL 回收。
这些格式维护仅支持 SQLite，明确拒绝 PostgreSQL；PG 使用原 saver，checkpoint_ns 不等于 memory namespace。

## PR 与发布

PR 描述说明问题、改动、验证和剩余限制；用户可见变更更新 `CHANGELOG.md` 的 Unreleased。
代码相关的非平凡改动更新现有 HANDOFF，并按影响同步地图、决策、测试、风险、术语和 README 核对项；不追加日期流水账。

### 分支策略

| 分支 | 角色 |
|------|------|
| `main` | 生产真源；GitHub 默认分支；仅合入 release / hotfix |
| `develop` | 日常集成；**特性 PR 请打向 `develop`** |
| `release/x.y.z` | 临时发版分支；发版完成后删除 |
| `hotfix/*` | 从 `main` 紧急修复；合入 `main` 后再合回 `develop` |

```
feature/* ──PR──► develop ──► release/x.y.z ──PR──► main ──tag v*──► publish
hotfix/* ──PR──► main (+ tag) and ──PR──► develop
```

**规则：**

- 禁止 `develop` 直推/直 merge 到 `main`；禁止直接 push 到 `main` / `develop`（GitHub 分支保护）。
- `release/x.y.z` → `main` 必须用 **merge commit**，不要 squash。
- 生产 `v*` tag 仅在合入 `main` 之后由 Actions 打在 main tip。
- 发版后由 `sync-main-to-develop.yml` 保持 `main` 为 `develop` 的祖先。

从 `develop` 创建 `feature/*` 或 `fix/*`，PR base 选 `develop`。发布从 `release/x.y.z`（或 `hotfix/*`）通过 PR 合入 main，
project version、CHANGELOG 与标签一致。现有 workflow 在合并后创建 `v*` tag 并触发 PyPI/GitHub Release，再 sync 回 develop；
没有发布授权时只验证构建，不推 tag 或上传。
公开发布统一走上述 PR 与 Actions 流程，不在本地用 `make publish` / `twine upload` 代替；
发布前检查版本未占用、Unreleased 归档正确和门禁结果，发布后核对 tag 与产物，再按仓库策略清理发布分支。

Agent 辅助发布：`.cursor/skills/publish` / `.codebuddy/skills/publish`（`/publish <version>`），发版时同步更新 CHANGELOG / README 等。

```bash
uv build --out-dir dist/package-review
uv build --wheel --out-dir dist/package-review/direct
```


首条从 sdist 重建 wheel；比较两种 wheel 解压后的文件名与内容。Python sdist 使用 allowlist，
独立插件另行构建，测试/CI 留在完整 checkout。插件短 README 是分发入口，详细说明只有集成指南一份。

不要提交 `.env`、数据库/WAL、备份、日志、`.hmpkg`、依赖安装目录或私人运维记录。
个人 editor 配置与访问真实库的诊断脚本不属于公共源码；共享 `/publish` skill 属于公共发版流程。
ignore 不删除已跟踪内容，工作树脱敏也不清理 Git 历史或已有附件。漏洞报告见 [SECURITY.md](SECURITY.md)。
