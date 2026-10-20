# 搜索引擎扩展改造计划（豆包 / DeepSeek / Exa，同步移除 Brave / Google）

> 状态：待确认（未动代码）。确认后按 §6 顺序执行。
> 日期：2026-10-20

## 0. 背景与目标

在现有四个内置搜索引擎（Tavily、Brave、Google CSE、Kimi）基础上，新增三个引擎：
**豆包搜索（火山引擎，Global 版）、DeepSeek 网页搜索、Exa**。

同时**移除 Brave Search 与 Google CSE** 两个引擎：国内环境（尤其政务内网）无法访问
其 API，保留只会让设置页出现永远配不通的卡片。移除与新增在同一个改造内完成。

搜索引擎工具的实现位于上游依赖 `octop-harness`；Octop 本体只负责 Key 管理、
连通性探测、工具目录与设置页 UI。本次改造同时把四个上游包
（harness / gateway / memory / browser）源码收进 Octop monorepo，
为后续白标改名铺路。

## 1. 已确认的决策

| # | 决策 | 结论 |
|---|------|------|
| Q1 | 扩展与改名顺序 | **先扩展、后改名**。本次以现包名 `octop-harness` 落地，包名迁移另行规划 |
| Q2 | 豆包版本 | **Global 版**（零配置面，一个 Key 即用）；Custom 版的正文/rerank 能力将来按独立需求评估 |
| Q3 | 环境变量命名 | `DOUBAO_SEARCH_API_KEY`、`DEEPSEEK_API_KEY`、`EXA_API_KEY` |
| Q4 | 工具参数面 | **最小面**：仅 `query` + `max_results`，高级过滤走默认；docstring 保留一句话提示（如 DeepSeek 支持 `site:` 语法） |
| Q5 | 实现方式 | **三个引擎全部 httpx 直连**，不引入官方 SDK，harness 零新增依赖 |
| Q6 | harness 消费方式 | 无 PyPI 发布权 → **收进 monorepo**，uv workspace 路径依赖 |
| Q7 | 测试策略 | mock 全覆盖；真 Key 只做一次性人工冒烟，不进 CI |
| Q8 | 仓库布局 | `~/source2026/octop-harness` 已检出（release/1.0.4，与 PyPI 安装版一致）→ 迁入 `Octop/packages/octop-harness` |
| Q9 | 设置页 logo | 先用文字/首字母占位图标，素材后补 |
| Q10 | 文档边界 | 本计划只覆盖搜索扩展；四包改名仅附录一句带过 |
| Q11 | 验收口径 | 见 §7 |
| Q12 | 移除 Brave / Google | **本次同步移除**（国内/政务环境不可达）；见 §3.3、§4.1–4.3 |
| Q13 | monorepo 范围 | **四个上游包一次全部迁入**（避免 PyPI/本地混合来源）；见 §2 |
| Q14 | 部署代码保护 | 本次不做编译/pyc 化；wheel 即源码的事实记录在案，政务交付走合同条款 + 交付纪律，编译部署另立计划 |

## 2. 仓库布局变更（前置步骤）

**现状**：Octop 通过 uv.lock 从 PyPI 镜像安装四个上游包
（`octop-harness[all]>=1.0.4`、`octop-gateway>=1.0.3`、`octop-memory>=1.0.2`、
`octop-browser>=1.0.0`）；四个包的源码已分别检出在
`~/source2026/octop-{harness,gateway,memory,browser}`，均为干净的
release/版本检出，版本与锁文件一致：

| 包 | 检出版本 | 依赖关系 |
|----|---------|---------|
| octop-harness | 1.0.4（release/1.0.4） | 依赖 octop-memory、octop-browser |
| octop-gateway | 1.0.3（release/1.0.3） | 独立叶子包 |
| octop-memory | 1.0.2（release/1.0.2） | 被 harness 依赖 |
| octop-browser | 1.0.0（release/1.0.0） | 被 harness 依赖 |

**决策（Q13）**：**四个包一次全部迁入 monorepo**。依赖图是
Octop → {harness, gateway, memory, browser}、harness → {memory, browser}；
只收 harness 会留下"workspace 包从 PyPI 拉兄弟包"的混合来源，锁文件不自包含，
且 memory/browser 上游发版可能与本地 harness 代码错配。四个一起收，
锁文件完全自包含，离线部署 wheel 全部本地构建。

**目标**：

```
Octop/
├── pyproject.toml            # 增 [tool.uv.workspace] members + [tool.uv.sources]
├── uv.lock                   # 重新生成，四个包全部变为 workspace 来源
└── packages/
    ├── octop-harness/        # version 1.0.4 → 1.0.5（本次有代码变更）
    ├── octop-gateway/        # version 1.0.3 不变（本次无代码变更）
    ├── octop-memory/         # version 1.0.2 不变（本次无代码变更）
    └── octop-browser/        # version 1.0.0 不变（本次无代码变更）
```

操作要点：

1. 四个工作树分别复制为 `Octop/packages/<name>`（原仓库先打
   `pre-monorepo-migration` tag，历史查旧仓库，见开放项 O3）。
2. Octop `pyproject.toml` 增加：
   - `[tool.uv.workspace]` `members = ["packages/*"]`
   - `[tool.uv.sources]` 四条 `<name> = { workspace = true }`
   （依赖声明范围不变，workspace 成员版本均满足现有 specifier）
3. `uv lock` 重新生成锁文件；`uv sync` 后验证四个包均指向本地路径。
4. 删除/忽略 `packages/*/uv.lock`（workspace 只有根锁文件）；各成员自带的
   CI 配置（GitHub Actions）不迁移、不生效。
5. 各成员自带测试不并入 Octop 的 `make all`，单独在成员目录下跑
   `uv run pytest`（避免拖慢 ship bar；后续如需可加独立 make 目标）。
6. 本次只有 harness 有代码变更（版本 bump 1.0.5），其余三包原样迁入；
   后续任一包有改动需求时，在 workspace 内直接改 + bump 版本即可。

## 3. Harness 侧改动（`packages/octop-harness`）

### 3.1 新增三个工具模块（照 `tavily.py` 模式）

| 文件 | 引擎 | Endpoint | 认证 |
|------|------|----------|------|
| `src/octop_harness/builtin/tools/web_search/doubao.py` | 豆包搜索 Global 版 | `POST https://open.feedcoopapi.com/search_api/global_search` | `Authorization: Bearer $DOUBAO_SEARCH_API_KEY` |
| `src/octop_harness/builtin/tools/web_search/deepseek.py` | DeepSeek | `POST https://api.deepseek.com/v1/tools/search` | `Authorization: Bearer $DEEPSEEK_API_KEY` |
| `src/octop_harness/builtin/tools/web_search/exa.py` | Exa | `POST https://api.exa.ai/search` | `x-api-key: $EXA_API_KEY` |

统一模式：

- LangChain `@tool`，异步；签名统一为 `(query: str, max_results: int = 5)`；
- Key 从 `os.getenv()` 读取，缺失时返回 `"Error: … not set."` 字符串（与现有一致）；
- httpx 直连；返回裁剪后的 JSON 字符串（标题/URL/摘要，`ensure_ascii=False`）；
- 引擎差异化默认值写在函数体内：DeepSeek `need_content=True`（取 `summary` 长摘要）、
  Exa 带 `contents: {highlights: true}`、豆包按官方默认并裁剪结果字段；
- docstring 一句话提示：DeepSeek 支持 `site:` / `-site:` 语法。

豆包 Global 版实现细节（依据官方 API 文档，2026-10-20 核实；可对照
bytedance/agentkit-samples 的 `byted-web-search` skill 参考实现，Apache-2.0）：

- 请求体字段为帕斯卡命名：`Query`（1~100 字符，过长截断）、`SearchType: "web"`、
  `DocCount`（≤20，默认 10）、`MaxSnippetLength`（≤3000，取 1000）；
  高级过滤（`Filter.IcpHostOnly`、文搜图/图搜图）本次不暴露；
- 响应解析：`Result.Documents[]`，每条取 `Title`、`Url`、`Snippet[]` 中
  `Type == "text"` 的 `Text` 拼接（这是摘要片段数组，不是纯字符串）、
  `HostInfo.AuthorityLevel`；错误读 `ResponseMetadata.Error`（`Code`/`Message`），
  业务层错误另看 `Result.ErrorCode/ErrorMsg`；
- 错误分类映射：`700901`（APIKey 无效）→ auth_error；`10403` → auth_error；
  `700429`（QPS 限流）→ rate/auth 类；`10500`/`10501` → network_error 可重试；
  限流默认 10 QPS，工具层不做重试，直接返回错误信息；
- 计费提示：每火山账号每月 500 次免费额度（与 Custom 版共用），probe 和冒烟
  会消耗该额度。

### 3.2 注册表 `_registry.py`

- `WebSearchToolName` 增加三个字面量；
- `WEB_SEARCH_PROVIDERS` 增加三条：
  `doubao → (("DOUBAO_SEARCH_API_KEY",), _load_doubao)` 等；
- 懒加载器 `_load_doubao() / _load_deepseek() / _load_exa()` 照现有模式。

注册后，`web_search_tools` 默认策略 `"auto"` 自动生效：用户在设置页填好 Key，
agent 重建时即自动挂载新工具，无需额外配置。

### 3.3 移除 Brave 与 Google（harness 侧）

- 删除 `brave.py`、`google.py` 两个工具模块；
- `_registry.py`：`WebSearchToolName` 去掉 `"brave"`、`"google"` 字面量，
  `WEB_SEARCH_PROVIDERS` 删除两条及对应懒加载器；
- 模块 docstring 中提及 Google/Brave 的策略示例文字同步清理。

**兼容性注意**：若某 agent 的 `web_search_tools` 显式列了 `"brave"`/`"google"`，
装载时会因未知名字抛 `ValueError`（agent 构建失败）。处置见 §4.7 兼容策略。

### 3.4 Harness 测试

- `tests/` 下为三个新工具各加单测：手写 `httpx.MockTransport`（或仓库既有 mock
  惯例），覆盖：成功、401/403、超时、Key 缺失、响应裁剪字段；
- registry 测试补：显式列表装载、`auto` 策略下按 env 出现与否挂载；
- 移除 brave/google 的既有断言（可用性表、`"all"` 策略工具数等）同步更新。

## 4. Octop 侧改动（五处联动 + 测试）

### 4.1 Key 白名单 — `src/octop/infra/utils/env_file.py`

`SEARCH_ENV_KEYS` 增加 `DOUBAO_SEARCH_API_KEY`、`DEEPSEEK_API_KEY`、
`EXA_API_KEY`，同时删除 `BRAVE_API_KEY`、`GOOGLE_API_KEY`、`GOOGLE_CSE_ID`。
`search_env_changed()` 随之生效：Key 变更（含删除）会触发 agent 重建。

**存量清理**：老用户 `~/.octop/env` 里已写入的 `BRAVE_API_KEY` /
`GOOGLE_API_KEY` / `GOOGLE_CSE_ID` 不做自动删除（env 文件是用户数据）；
它们留在文件里不再被任何引擎读取，属无害残留。设置页 env 管理界面仍可
手动删除（env API 不按白名单过滤删除能力，见 `api/routers/envs.py`）。

### 4.2 连通性探测 — `src/octop/infra/utils/search_probe.py`

- `_KNOWN` 增加三个 id、删除 `brave`/`google`；`_REQUIRED` 相应增删；
  删除 `_brave` / `_google` 两个 probe 函数与 `_from_brave` / `_from_google`
  解析函数；
- 各加一个 `_probe` 分支（httpx 直连，与 harness 侧同 endpoint/同认证），
  响应解析复用 `_from_response`（DeepSeek/Exa/豆包均含 results 型列表）或
  按实际返回微调；
- probe 错误分类沿用现有 `auth_error / timeout / network_error / …`；
- `api/routers/search.py` 路由描述文字里的引擎枚举同步更新。

### 4.3 工具目录 — `src/octop/infra/agents/settings/tool_catalog.py`

- `_WEB_SEARCH_TOOLS` 增加 `doubao_search`、`deepseek_search`、`exa_search`，
  删除 `brave_search`、`google_search`；
- `BUILTIN_TOOL_CATALOG` 增删对应 `BuiltinToolEntry`。

**存量 agent 兼容**：`tools_disabled`（agent 配置里被显式关闭的工具名单）
或 `web_search_tools` 显式列表里若出现已移除的名字：

- `tools_disabled` 里的死名字无害（归一化后自然失效）；
- `web_search_tools` 显式列表含 `"brave"`/`"google"` 会在 agent 构建时抛
  `ValueError`。处置：Octop 侧在构建 `HarnessAgentConfig` 前对显式列表做一次
  过滤（丢弃已不存在的引擎名；若过滤后为空则回落 `"auto"`），并在启动日志
  提示一次。先确认 Octop 是否真有写入显式列表的路径——若全库均为默认
  `"auto"`，则该过滤逻辑可以不做，只在 CHANGELOG 里注明破坏性变更。

### 4.4 设置页 — `dashboard/src/pages/Settings/SearchConfig/index.tsx`

`SEARCH_PROVIDERS`：增加三张卡片（id、名称、docs_url、required_keys），
删除 brave、google 两张；i18n 键 `setupWizard.search.providers.{doubao,deepseek,exa}.desc`
同步加入 `dashboard/src/locales/en.json` 与 `zh.json`，删除
`providers.brave.*` / `providers.google.*` 两棵 key（两棵 key 树必须一致）；
logo 用文字/首字母占位（`assets/connectors` 的 `getProviderLogo` 无命中时
已有 customProviderLogo 兜底，占位图后补）；删除 brave/google 的 logo 资源。

### 4.5 前端产物

UI 改完执行 `make build-frontend`（产物落 `src/octop/dashboard/`）。

### 4.6 Octop 测试

- `tests/unit/utils/test_search_probe.py`：三新引擎 probe 分支（mock httpx），
  删除 brave/google 的用例；
- `tests/unit/test_env_file.py`：新 Key 属于 `SEARCH_ENV_KEYS`、旧 Key 已移除的断言；
- `tests/integration/test_search_api.py`：`POST /api/search/{id}/test` 三条新增，
  brave/google 的用例删除（或改为断言 404/unknown）；
- `dashboard/src/pages/Settings/SearchConfig/index.test.tsx`：三张新卡片渲染、
  brave/google 卡片不再出现；
- `uv run pytest tests/unit/i18n -q`：前后端 i18n key 奇偶校验（含删除的 key）；
- 跨平台注意：新测试遵循 §7 惯例（`tmp_path`/`Path` 拼接、无 POSIX 字面量），
  保证 Linux + Windows CI 通过。

## 5. 不做的事

- 不接 Exa 的 MCP 托管服务（走设置页统一配置，保持体验一致）；
- 不做四包白标改名（另行规划）；
- 不为豆包 Custom 版开配置表单；
- 不加官方 SDK 依赖；
- 真 Key 冒烟不进 CI；
- 不自动清理用户 `~/.octop/env` 里残留的 Brave/Google Key（无害残留，可手动删）；
- 不做配置迁移脚本（存量 agent 显式列表过滤见 §4.3 兼容策略）；
- 不做部署产物编译/pyc 化（代码保护另立计划，见 Q14 / R6）。

## 6. 执行顺序

1. §2 四包迁入 monorepo + workspace 配置 → `uv sync` 验证四个包均指向本地路径、`uv run pytest -m "not live"` 全绿（此时行为零变化）；
2. §3 harness 三工具 + 注册表增删 + harness 单测（含 brave/google 移除断言更新）；
3. §4 Octop 五处联动（含移除）+ 测试 → `make all`；
4. §4.4–4.5 dashboard + `npx tsc -b` + `make build-frontend`；
5. §7 真 Key 人工冒烟（新增三引擎测试通过 + Brave/Google 卡片消失、旧 agent 正常重建）；
6. 更新 `CHANGELOG.md`（注明 Brave/Google 移除的破坏性变更）。

## 7. 验收标准（Q11 + Q12）

1. `packages/octop-harness` 三新工具单测（mock）通过；brave/google 工具在
   registry 中不可见；
2. Octop `make all` 绿（含新增/删除后的 probe/env/catalog 测试）；
3. dashboard `npx tsc -b` + 组件测试绿；
4. 本地真 Key 人工冒烟：设置页三张新卡各"测试"一次成功；agent 对话中
   三个新引擎各实际搜索一次并返回结果；Brave/Google 卡片不再出现；
   升级前创建的存量 agent 重启后正常挂载搜索工具（无 `ValueError`）；
5. `uv lock` 后四个上游包均为 workspace 来源（锁文件无 PyPI 上游条目），
   `uv build` 可从 workspace 产出全部 wheel。

## 8. 风险与开放项

| # | 项 | 说明 / 处置 |
|---|-----|------------|
| O2 | DeepSeek 搜索 API 的正式可用性 | `POST /v1/tools/search` 为文档确认的独立搜索工具 API；动手时以账号实际开通情况为准 |
| O3 | 四包迁入是否带 git 历史 | subtree 可保留历史但操作重；直接复制最简单。推荐：各原仓库打 `pre-monorepo-migration` tag 后直接复制，历史查旧仓库 |
| O4 | 存量 agent 是否存在显式 `web_search_tools` 列表 | 决定 §4.3 兼容过滤逻辑做不做。动手前先全库检索（DB `agents` 表 config + 代码写入路径）；若全为默认 `"auto"` 则不做过滤，仅 CHANGELOG 注明 |
| R1 | uv workspace 对 CI 的影响 | 锁文件自包含、路径在树内，Linux/Windows CI 均无需目录布局假设；四包全收后无 PyPI/本地混合来源；风险低 |
| R2 | 离线（政务内网）部署 | 四个上游包 wheel 全部从 monorepo `uv build` 产出，现有 save/load 流程不变 |
| R3 | probe 与 harness 行为漂移 | 两侧行为一致性靠"同 endpoint 同认证同裁剪"约定维持，不做共享代码（跨包依赖反向耦合，不值得） |
| R4 | 包名迁移 | 本次以 `octop-*` 现名落地；四包改名另行出计划，届时在 workspace 内原地重构 |
| R5 | 移除 Brave/Google 的破坏性 | `auto` 策略用户无感（Key 不在则工具本来就没挂载）；仅显式列表用户受影响，由 O4 决定兼容层 |
| R6 | 部署产物即源码 | Python wheel 内是明文 `.py`（四包现状已核实，无编译步骤）；技术加固（pyc 化/Nuitka）与合同条款另立计划，本次不做（Q14） |

## 附录：上游引擎 API 要点（已核实）

- **豆包 Global 版**（2026-10-20 官方文档核实，O1 已闭合）：
  `POST https://open.feedcoopapi.com/search_api/global_search`，
  仅支持 API Key 接入（`Authorization: Bearer`，不支持 TOP 网关 AK/SK）；
  仅按量后付费；每账号每月 500 次免费额度（与 Custom 版共用）；
  默认 10 QPS。文搜文请求：`Query`（1~100 字符）、`SearchType: "web"`、
  `DocCount`（≤20 默认 10）、`MaxSnippetLength`（≤3000）、
  `Filter.IcpHostOnly`；响应：`Result.Documents[]`（`Title`/`Url`/
  `Snippet[]`（`Type: text|image`）/`DocumentInfo.PublishTime`/
  `HostInfo.AuthorityLevel`），错误在 `ResponseMetadata.Error` 与
  `Result.ErrorCode/ErrorMsg`。主要错误码：10403 权限、700901 Key 无效、
  700429 QPS 超限、10406 免费额度用尽（Custom 文档同列）。
- **DeepSeek**：`POST https://api.deepseek.com/v1/tools/search`；参数
  `query`(1–128 字符，支持 `site:`)、`count`(1–50)、`ori_question`、
  `localization`、`need_content`；返回 `results[]` 含 `rerank_score`(0–3)、
  `title`、`url`、`snippet`、`summary`(600–800 字)、`content`(需 need_content)、
  `authority`(0–4)。
- **Exa**：`POST https://api.exa.ai/search`，`x-api-key` 头；`query` +
  `contents: {highlights: true}`；返回 `results[]` 含 `title`、`url`、
  `highlights`。
- **参考实现**：bytedance/agentkit-samples `byted-web-search` skill
  （Apache-2.0）——其 `web_search.py` 调的是 Custom 版 endpoint
  （`search_api/web_search`），字段解析（`WebResults`/`Summary` 回退
  `Snippet`、错误码提示映射）可借鉴；它走 AK/SK 优先，我们只用 Bearer Key。
  注意两版响应结构不同（Custom 是 `WebResults`，Global 是 `Documents`），
  不可直接套用其解析代码。
