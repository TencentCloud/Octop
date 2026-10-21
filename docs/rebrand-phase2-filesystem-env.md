# 白标二期:文件系统、环境变量与协议头改造决策文档

> 状态:决策已定(2026-10-21 与 owner 逐项确认),待开工。
> 前置阅读:`WHITELABEL.md`(一期盘点,其中"三档建议不动"的结论被本文档部分推翻)。
> 基线:main `002a8ff9`,v1.0.3 发布链路全绿。

## 0. 一句话目标

把用户/审查方在**文件系统、shell、浏览器 F12、agent 执行环境**里能看到的全部 `octop` 痕迹改为 `agentbuddy`,仅保留深水区(PyPI 包名、CLI 二进制名、渠道协议归因、技能 frontmatter 命名空间)。

## 1. 决策记录

| # | 决策项 | 裁定 |
|---|--------|------|
| Q1 | 动机与目录名 | 品牌彻底化;家目录 `~/.octop` → **`~/.agentbuddy`** |
| Q2 | 旧数据兼容 | **不做迁移**。交付物均为全新安装;文档写一句"上游升级需手动 `mv ~/.octop ~/.agentbuddy`" |
| Q3 | 范围 | **A + B 层改名 + 请求头/cookie/env 全量改名**;C 层(工作区内部 `{workspace}/.octop/`)本期不动 |
| Q4 | 环境变量名 | `OCTOP_HOME` → **`AGENTBUDDY_HOME`** |
| Q5 | F12 可见面 | **纳入本期**:`X-Octop-*` 头、`octop_sso_state` cookie、`window.__OCTOP_*` 全局、`OCTOP_*` env 前缀,全部硬切改名 |
| Q6 | 发版节奏 | feature 分支开发 → 合 `develop`,作为 **v1.0.4** 交付内容;offline bundle / Docker / desktop 三链路重跑为验收项 |
| Q7 | 新 env 前缀 | **`AGENTBUDDY_`**(与 localStorage `agentbuddy:` 键、发布物命名同构) |
| Q8 | 兼容读取 | 仅 `OCTOP_HOME` 保留 fallback 读取(新名优先,旧名兜底);其余 ~80 个变量**全部硬切**;harness `PROTECTED_ENV_PREFIXES` 新旧前缀都保护 |
| Q9 | 上游包家目录 | 收进主目录派生:`~/.agentbuddy/harness/`、`~/.agentbuddy/memory/`、`~/.agentbuddy/browser/`(各包加 5-10 行派生逻辑;旧目录不迁移) |
| Q10 | `octop-assistant` 技能 | 目录与 frontmatter `name` 改为 **`agentbuddy-assistant`**;正文全面复核更新(见 §3.6);`metadata.octop` frontmatter 键与 `octop` CLI 命令名**保持不动**(见 §2) |

## 2. 明确不改的(深水区,知情保留)

| 项 | 原因 |
|----|------|
| PyPI 包名 `octop` 及四个上游包 `octop-harness/-gateway/-browser/-memory` | 他人发布/发布链契约,改名 = 全仓重写,一期已裁定"强烈建议不做" |
| **CLI 二进制名 `octop`**(console script) | 随 PyPI 包名而来;技能正文、文档中的 `octop run` / `octop config show` 等是真实命令,**禁止顺手改名** |
| 技能 frontmatter `metadata.octop` 键 | skill 包格式契约(harness 解析),非用户可见;C 级保留裁定继续有效 |
| `infra/skills/presentation.py:12` `_EXTENSION_NAMESPACES` 含 `"octop"` | 技能包命名空间白名单,删条目 = 旧技能包不识别 |
| 渠道协议 `source=octop-feishu-bot` 等(`api/routers/channels.py:312-313` 及 gateway 包) | 腾讯侧渠道归因,改了扫码可能被拒(B11 裁定) |
| `stream_errors` 前缀、`ChannelKind` 枚举、`X-` 以外的 API 路径 | C 级保留 |
| `infra/backup/system_archive.py:61` `_MIGRATION_VERSION_SUFFIX = "-migrated-from-lightclaw"` | 会写进备份归档版本名,改了影响迁移识别 |

## 3. 范围明细

### 3.1 A 层:安装家目录(估 1-2 人日)

- `src/octop/infra/utils/paths.py:17-20` `PathLayout.from_env()`:读 `AGENTBUDDY_HOME`,fallback `OCTOP_HOME`,默认 `~/.agentbuddy`。
- `PathLayout.db` → `agentbuddy.db`;docstring 里的 `~/.octop/` 全量同步。
- `infra/setup/service.py:225-235`(`resolve_service_home`,systemd/launchd unit 里的 `Environment=` 行)、`infra/setup/self_update.py`(venv 路径)。
- `desktop/portable/templates/start.sh`、`desktop/src/process.go`/`settings.go`(Go 壳的 `octopHome()`)。
- `docker/docker-compose.yml:38`(`OCTOP_DATA:-~/.octop` → `AGENTBUDDY_DATA:-~/.agentbuddy`,容器内 `/data/.octop` 同步)、`scripts/install-offline.sh:26-27`、`scripts/install*.{sh,ps1}`。
- 测试同步:tests 里 `~/.octop` / `OCTOP_HOME` 相关 ~60 处(遵循 AGENTS §7:用 `tmp_path` + env 注入,不假设路径字面量)。

### 3.2 B 层:上游包独立家目录收编(估 1-2 人日)

- `packages/octop-memory/src/octop_memory/_config_io.py:19` `CONFIG_DIR`、`core.py:1827` db_path 默认值 → `~/.agentbuddy/memory/`。
- `packages/octop-browser/src/octop_browser/settings.py:74` `_STATE_DIR` → `~/.agentbuddy/browser/`。
- `packages/octop-harness`:harness 自身无服务器场景家目录依赖;`cli/config/paths.py` 的 `~/.octop-harness` 为 harness 独立 CLI 使用,改为 `~/.agentbuddy/harness/`。
- 各包派生逻辑:优先读 `AGENTBUDDY_HOME`,fallback `OCTOP_HOME`(与主仓一致),否则 `~/.agentbuddy`。
- 注意 memory 的迁移模块(`operations/migration/portable/*`)硬编码了旧路径探测 glob(`~/.octop/agents/*/memory.sqlite` 等)——这是**对旧安装的导入探测**,保留不动。

### 3.3 请求头 / cookie / 浏览器全局(估 1 人日)

| 旧 | 新 | 位置 |
|----|----|------|
| `X-Octop-Access-Token` | `X-Agentbuddy-Access-Token` | `api/deps.py:27`、`api/middleware/jwt_auth.py`、`api/openapi_meta.py:29`、dashboard `api/request.ts:19` + 测试 |
| `X-Octop-Agent-Id` | `X-Agentbuddy-Agent-Id` | `api/routers/mbti.py`(4 处)、`api/middleware/bridge_proxy.py:100,202`、dashboard `request.ts` / `acp.ts` / `subagents.ts` / `connectors.ts` / `mbti.ts` / `AgentContext.tsx` 注释 |
| cookie `octop_sso_state` | `agentbuddy_sso_state` | `api/common/sso_cookie.py:8` |
| `window.__OCTOP_REACT__` / `__OCTOP_JSX__` | `__AGENTBUDDY_REACT__` 等 | dashboard `plugins/toolRenderers/ensureBuiltins.ts:19-20` |
| `window.__OCTOP_EXTERNAL_LINKS_INSTALLED__` | 同风格改名 | desktop `src/openurl.go:114-115` |
| 备份导出前缀 `octop-export-` | `agentbuddy-export-` | `api/routers/backup.py:158` |

- 前后端同船发布、四个上游包零引用,`X-Octop-*` **直接硬切,不做双发过渡**(一期"需过渡期"的判断对 fork 不成立)。
- 顺手同步 OpenAPI 文案中的头名与 `octop-harness`/`octop-memory` 字样(`openapi_meta.py`、`routers/agent_files.py`、`routers/providers.py` 等 description)。

### 3.4 `OCTOP_*` 环境变量全量前缀替换(估 2-4 人日)

- 主仓源码 ~80 个变量 / ~200 处:`OCTOP_` → `AGENTBUDDY_`(sed 级机械替换,无逻辑改动)。
- **必须动代码的一处(安全边界)**:`packages/octop-harness/src/octop_harness/runtime_env.py:57` `PROTECTED_ENV_PREFIXES = ("OCTOP_",)` → `("AGENTBUDDY_", "OCTOP_")`。漏掉 = agent 工作区 `.env` 可劫持 `AGENTBUDDY_HOME` 等变量。
- agent 执行环境注入(`infra/agents/workspace/execute_env.py:86-89` 注入的 `OCTOP_HOME`/`OCTOP_AGENT_ID`/`OCTOP_AUTH_DIR`/`OCTOP_SKILLS_DIR`)随前缀改——agent 跑 `env` 即可见,与 F12 同暴露等级。
- desktop Go 壳(~15 处)、compose/install 脚本(~150 行,含脚本内部变量 `OCTOP_VENV`/`OCTOP_BIN` 顺带改)。
- harness 包内读 `OCTOP_HOME` 的 2 处改为读 `AGENTBUDDY_HOME`(fallback 旧名)。
- tests 310 行同步。
- 保留兼容读取的仅 `AGENTBUDDY_HOME` ← `OCTOP_HOME` 一条(主仓 + desktop Go + harness 三处读取点)。

### 3.5 连带小项(建议随本期一并做)

- `infra/backend/docker_spec.py` `DEFAULT_SANDBOX_PREFIX = "octop_sandbox"` → `agentbuddy_sandbox`(`docker ps` 在宿主机可见,同类暴露;配置键已存在,老配置行不受影响)。**待 owner 开工前确认。**
- sandbox 镜像名 `agentbuddy-sandbox` 已是现名,无需动。

### 3.6 `octop-assistant` 技能改造(估 1-2 人日)

现状:正文已做过一轮白标(产品名"政务伙伴"、安装命令占位符 `<INSTALL_SCRIPT_BASE>`),残留 129 处 `octop` 字样。改动:

1. **改名**:`experts/library/general-assistant/skills/octop-assistant/` → `agentbuddy-assistant/`;frontmatter `name:` 同步。代码里无目录名硬引用(`composer_files.py` 按 slug 动态拼 `skills/{slug}`),改名无代码波及。
2. **正文复核更新**(重点,不是盲替):
   - 路径类:`~/.octop/` → `~/.agentbuddy/`、`octop.db`、`cli_state.json` 所在路径——随 A 层改。
   - env 类:`OCTOP_AGENT` → `AGENTBUDDY_AGENT`(`:235`)——随 §3.4 改。
   - **命令类保留**:所有 `octop <subcommand>` 是真实 CLI 命令(Pypi 包名深水区保留),**不改**。
   - **内容时效复核**(owner 提示"改了不少内容"):逐节核对技能描述与当前产品是否一致——安装方式(现在是 offline bundle / Docker / desktop 三链路,不再是 `curl | bash`)、`octop user login` 等已废弃流程(AGENTS.md 明确"No `octop user login`")、文档链接(无自有文档站,相关章节一期已删,确认无回潮)、新目录/env 写法。
   - `metadata.octop` frontmatter 键不动(§2)。
3. **既有 agent 工作区**:已种子化的 agent 工作区里是 `skills/octop-assistant/` 旧副本,按"不迁移"决策,新 agent 用新名,老工作区不处理。

## 4. 实施顺序(建议单分支 `feature/rebrand-filesystem-env`)

```
① A 层家目录 + env 前缀(主仓)  → uv run pytest tests/unit -x -q
② B 层上游包家目录 + harness 保护前缀 → packages 内各自 pytest
③ 请求头/cookie/浏览器全局      → cd dashboard && npx tsc -b && 前后端联调
④ octop-assistant 技能改名+正文复核 → uv run pytest tests/unit/agents -q
⑤ make all(ship bar)+ 双平台关注 Windows CI
⑥ 三链路重跑:offline bundle、Docker(含 sandbox)、desktop package
⑦ 文档收尾:WHITELABEL.md 残留计数更新、README/docker/README_CN、AGENTS.md 中 ~/.octop 表述
```

## 5. 验证清单(Definition of Done)

- `make all` 绿(含 mypy --strict)。
- 全仓残留扫描:`grep -rn "\.octop" src/octop packages/*/src` 仅剩 §2 深水区项;`grep -rn "OCTOP_" src/octop packages/*/src` 仅剩兼容 fallback 与 `PROTECTED_ENV_PREFIXES` 的旧名保护;`X-Octop` 零残留。
- F12 人工核查:登录→滑动续期(响应头)→切换 agent(请求头)→SSO 登录(cookie)→控制台 `Object.keys(window)` 过滤 OCTOP → 备份导出文件名。
- 新装 `octop init` 后检查 `~/.agentbuddy` 布局与旧版一致(目录树 diff)。
- agent 会话内跑 `env` 确认注入变量为新前缀;工作区 `.env` 写 `AGENTBUDDY_HOME=...` 确认被拒(harness 保护生效)。
- v1.0.4 三条交付链路全绿。

## 6. 未决项

- §3.5 sandbox 前缀 `octop_sandbox` 是否随本期改——待 owner 一句话确认(建议:改)。
- wheel/sdist 的 `octop` PyPI 名是否从 Release 撤下(一期遗留,独立决策,与本任务无阻塞关系)。

## 7. 验证结论(2026-10-22 补充)

| 端 | 验证方式 | 结果 |
|----|---------|------|
| 本地 ship bar | `make all`(ruff + mypy strict + pytest 4961 + dashboard build) | ✅ 全绿 |
| CI 双平台 | PR #1 run 39643493727(Linux + Windows / Python 3.12) | ✅ 全绿 |
| Desktop 四平台 | run 39643493826(windows/darwin × amd64/arm64) | ✅ 全绿 |
| Docker 主镜像 | 分支代码本地 `docker build -f docker/Dockerfile`(arm64);起容器 + `AGENTBUDDY_DEFAULT_PASSWORD` 走 entrypoint init 路径 | ✅ 构建成功;`/data/.agentbuddy/` 布局正确(agentbuddy.db(+wal/shm)、config.json、credential.txt、.initialized、logs/agentbuddy.log);`/api/health` 200;镜像内 `ACCESS_TOKEN_RESPONSE_HEADER = X-Agentbuddy-Access-Token`、`PathLayout.from_env().root = /data/.agentbuddy`;dashboard 产物扫描 `X-Octop`/`__OCTOP_` 均 0 处 |
| Docker 沙箱镜像 | 分支代码本地 `docker build -f docker/Dockerfile.sandbox`;`--network none` 重跑自检层 | ✅ 构建成功,sandbox image OK(Python 3.12.15);镜像按设计不含 octop_harness(运行期注入),保护前缀逻辑在主仓测试覆盖 |
| Offline Wheel Bundle | 从分支 dispatch workflow run 39654043867(amd64 + arm64) | ✅ 双平台 bundle 成功(各 ~200MB);下载 amd64 产物校验:SHA256 一致,202 个文件,`offline/octop-1.0.3-py3-none-any.whl` 内含 `.agentbuddy` 家目录默认、`AGENTBUDDY_HOME` 读取与 `OCTOP_HOME` 兼容 fallback(包名保持深水区 `octop`) |
| Compose | `docker compose config`(主 + cn) | ✅ 解析通过,`AGENTBUDDY_DATA:-~/.agentbuddy` → `/data/.agentbuddy` 挂载一致 |

至此三端(桌面 / Docker / 离线 wheel 包)的分支级验证全部完成,后续打 `v*` tag 时各 publish workflow 以 tag 构建即为同一代码。
