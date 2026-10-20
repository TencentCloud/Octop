# Octop 白标化改造报告（品牌痕迹清理）

调研日期：2026-10-15 · 代码版本：`main` @ `f685a853`（1.0.2b8）· 盘点时为只读，未改动任何源文件
**2026-10-16 进度：P1–P8 已按你的决策落码（工作树未提交），执行结果与剩余待办见 §8；§2/§3/附录 A 中被本轮推翻的事实结论已就地更正。**
**2026-10-16 第二轮：§8.5 的 12 个待决策项你已逐条答复，落点见 §8.5.1（仓库地址回填、发布通道收敛到 GHCR、`CompanyName` 改道晟科技），需要你以后处理的两件事记在 §8.7（Gitea 制品库恢复自动更新 + 统一镜像源）。**
本文所有行号均已逐条实读核实；与 `RESEARCH.md`（2026-10-08 政务底座可行性评估）互补，那篇讲架构与合规缺口，这篇只讲"怎么让它看起来是你的"。

---

## 0. 一句话结论

**能做到"最终用户看不出来源"，成本约 1–2 人周；做不到"彻底不是 Octop"，因为真正的 Agent 运行时在四个别人发布的 PyPI 包里，且包名/环境变量/数据目录是深层契约，动它们的性价比极低。**

痕迹分三个难度档，先看清它们的性质完全不同：

| 档 | 内容 | 改法 | 风险 | 工作量 |
|---|---|---|---|---|
| **一档：品牌外观** | 名称、logo、菜单外链、版权行、窗口标题、图标、文案 | 替换字符串 + 重打包 | 无 | **2–4 人日** |
| **二档：出网链路** | 更新检查拉 PyPI `octop`、SkillHub 市场、`curl \| bash` 装第三方脚本、作者 COS 桶 | 关闭或换成自有服务 | **不改会有供应链风险** | 3–5 人日（含自建 index/桶） |
| **三档：深层约定** | `octop` 包名、`OCTOP_*` ×90、`~/.octop`、`octop.db`、`X-Octop-*` 头、`ChannelKind` 枚举、四个上游依赖包 | 建议不动 | 动了破坏数据兼容与既有部署 | 数周～不可行 |

另外必须知道的两个事实：

- **没有任何遥测/埋点**（`posthog|sentry|mixpanel|telemetry|analytics` 在 `src/octop/` 与依赖包里零真实命中）。白标不用摘上报代码，只有"出网取东西"，这点对私有化部署是好消息。
- **许可证是 MIT**，`LICENSE:3` 写的是 `Copyright (c) 2026 Octop`（不是公司名，也没有个人署名）。改名换 logo 合法，但 **MIT 要求保留版权声明**——源码仓库里的 `LICENSE` 不能删；`fnos/*/LICENSE` 会随 `.fpk` 分发给用户，那两处也要一并处理（见 §4）。

---

## 1. 痕迹地图：按"谁看得到"分级

全仓库第三方品牌相关字符串共 **3318 处命中 / 381 个文件**（含 `weixin|feishu|dingtalk|github|tencent` 等功能词）。但绝大多数不是"品牌问题"，而是"功能本来就对接这些服务"。真正需要判断的是下面按可见性分层的清单。

### L1 · 最终用户在浏览器/客户端里直接看到（最高优先级）

| # | 位置（已核实） | 实际内容 | 出现场景 |
|---|---|---|---|
| 1 | `dashboard/src/components/AvatarDropdown.tsx:58-59`，渲染在 `:372-392` | `GITHUB_URL = "https://github.com/TencentCloud/Octop"`、`HELP_FEEDBACK_URL = "https://octop.cloud"` | **头像下拉菜单两项**：「项目地址」（带 GitHub 图标）、「帮助与反馈」 |
| 2 | `dashboard/src/pages/Settings/AdvancedSettings/UpdateConfig.tsx:30-31` | `curl -fsSL https://finnie-1258344699.cos.ap-guangzhou.myqcloud.com/octop/install.sh \| bash`、`.ps1` | 设置 → 高级 → 更新：「手动升级指南」里可直接复制的命令 |
| 3 | `dashboard/src/components/BrowserWorkspace/index.tsx:42`<br>`dashboard/src/pages/RemoteBrowser/index.tsx:124` | `DEFAULT_URL = "https://cloud.tencent.com"` | 内置浏览器/远程浏览器的**默认起始页**，用户一开就看见 |
| 4 | `dashboard/src/pages/Agent/Channels/components/constants.ts:153-162` | `octopbot: "https://octop.cloud.tencent.com"`、`qq: "https://q.qq.com/qqbot/openclaw/"`、`yuanbao: "https://yuanbao.tencent.com/bot"`、`feishu`/`dingtalk`/`wecom` 各自开放平台 | 渠道抽屉的「创建机器人」引导外链 |
| 5 | `dashboard/src/pages/Agent/Skills/components/SkillHubTab.tsx:381` | `https://skillhub.tencent.com/` | 技能页「SkillHub」按钮 |
| 6 | `dashboard/src/pages/Settings/Environments/components/PageHeader.tsx:23` | `https://console.cloud.tencent.com/cam/capi` | 环境变量页「需要腾讯云密钥？」 |
| 7 | `dashboard/src/components/BackendBuilder.tsx:103` | `label: "Tencent Cloud COS"` | 存储后端下拉选项 |
| 8 | `dashboard/src/assets/providers/index.ts:91-93` | `hunyuan.cloud.tencent.com/#/app/subscription`、`cloud.tencent.com/document/product/1721` | 模型设置「获取 API Key」外链 |
| 9 | `dashboard/src/pages/Settings/Models/presetUtils.ts:11` | 排序优先列表把 `"tencent"` 置顶 | **模型页第一眼就是腾讯云预设** |
| 10 | `dashboard/src/pages/Login/captchaAdapters.ts:59-60` | `slug: "tencent"` + `https://turing.captcha.qcloud.com/TJCaptcha.js` | 登录页验证码（腾讯防水墙）选项，另有 `CaptchaSettings.tsx:70,171` |
| 11 | `src/octop/infra/voice/presets.py:37-43` | `"name": "Tencent Cloud"`, `"description": "Tencent ASR + TTS with free trial quota…"` | 设置 → 语音 预设卡片 |
| 12 | `src/octop/infra/connectors/catalog.json`（726 行 / 28 条） | 14 个腾讯系条目：`tencent-docs/ima/meeting/news/lexiang/weiyun/ardot`、`qq-mail`、`qq-music`、`wechat-reading`、`feishu-cli`、`wecom-cli`、`agently-cli`、`weknora`；其中 8 处 `doc_url`/`guide_url` 指向 `qclaw.qq.com/docs/…`（`:46,96,131,138,237,281,413,420`） | 连接器市场页的名称、说明、图标与文档链 |
| 13 | `src/octop/infra/agents/experts/library/`（**现 19 个内置专家**；P1-B 删 3 个前实测 22 个目录，此前我写的「24」把 `LICENSE`/`README.md` 两条也算进去了，已更正） | 已删 `cvm-ai-doctor`、`cvm-cluster-doctor`、`tencentcloud-api`；**留** `wechat-ops`、`meituan-living-assistant`、`cowork-plugin-management`、`design`、`engineering`、`productivity`（详见附录 A3 #15/#17） | 「专家」画廊直接展示 |
| 14 | `.../general-assistant/skills/octop-assistant/SKILL.md:130,135` | 同 #2 的 `finnie-…myqcloud.com` 管道命令，**写在随 wheel 分发的技能正文里** | 通用助手会向用户复述这条上游安装命令 |
| 15 | `src/octop/api/routers/skills.py:76-78` + `:296-316` | `_SKILLHUB_INSTALL_URL = "https://skillhub-1388575217.cos.ap-guangzhou.myqcloud.com/install/install.sh"`，`curl` 的 stdout 直接喂给 `bash` 执行 | 技能页一键安装 SkillHub CLI |
| 16 | `dashboard/index.html:29,32`、`public/manifest.json:3-5`、`public/offline.html:9,71-73`、`src/App.tsx:63` | 页面 `<title>`、PWA 名称、离线页文案、`document.title` | 标签页/手机桌面图标/断网提示 |
| 17 | `dashboard/public/` 全套视觉资产 | `favico.svg`、`apple-touch-icon.png`、`pwa-192/512.png`、`logo_horizontal_{dark,white}.png`、`logo_vertical_*.svg`、`octop-mascot-empty.png`（`src/assets/mascot.ts:5`）、`octop-mascot-type.webp`（打字动画）、`octop-mascot-peek.webp`（欢迎页） | 首屏、加载动画、空状态吉祥物 |
| 18 | `src/octop/api/app.py:110,111,309`、`src/octop/api/openapi_meta.py:13,86,110,149` | `title="Octop API"`、介绍文案里的 `**Octop** is a smarter…`、`~/.octop/env`、`Skill Hub` | `/api/docs`  Scalar 页（默认 `enable_api_docs=False`，见 `config.py:135`，但开启即暴露） |
| 19 | `src/octop/api/routers/update.py:324,426` | `summary="Upgrade Octop"`、报错文案 `"service restart is only available when OCTOP_SERVICE_MODE is set"`（**把环境变量名印进 UI**）；`:1` 模块首行 docstring `mirrors finnie/octop dashboard update flow` | 更新功能与 API 文档 |
| 20 | 桌面壳（若使用） | `desktop/src/build/config.yml:10` `productIdentifier: "com.tencent.octop"`、`darwin/Info.plist:12`、`windows/wails.exe.manifest:3` 同一 ID；`main.go:339,365,389,433` `Name/Title/托盘提示 = "Octop"`；`assets/index.html:6,494,509` 启动页 `<title>`、加载品牌行、「Octop 设置」；`Taskfile.yml:10` `APP_NAME: "Octop"`；`build/appicon*.png`、`tray-icon.png`、`dmg-background.jpeg`、`octop-mascot-*.webp` | Dock/菜单栏/托盘/窗口标题/exe 属性页/安装目录/快捷方式 |
| 21 | 飞牛 NAS 应用中心（若打包 FPK） | `fnos/docker/manifest:4` 描述原文以 **「腾讯开源的多用户多智能体 AI 助手平台…」** 开头、`:7 maintainer=TencentCloud`、`:8 maintainer_url=https://github.com/TencentCloud/Octop`；`fnos/native/manifest:7-8` 同；`fnos/docker/app/docker/docker-compose.yaml:3 image: ghcr.io/tencentcloud/octop:1.0.2b8` | 应用中心详情页逐字渲染；NAS 上真实 `docker pull` 的地址 |

### L2 · 安装 / 运维过程可见（复制粘贴就会暴露）

| 位置 | 内容 |
|---|---|
| `README.md:192,198,204`、`README_CN.md:194,200,206`、`docs/user-guide.md:74,80,86`、`docs/user-guide.html:201,204,207`、`scripts/README.md:13,14` | 首屏快速开始就是 `finnie-1258344699.cos…` 的 `curl \| bash` / `irm \| iex` / `.bat` |
| `README.md:8-24`（`README_CN.md` 同） | Trendshift badge（repo **95504**）、`img.shields.io/github/stars\|forks/TencentCloud/Octop`、license/releases badge、PyPI badge、**Discord `discord.gg/QnWdhJxq9h`** |
| `README.md:310-312` | 腾讯云轻量/CVM 一键购买 deep link（含 `imageId=img-n3gxkolf`、`blueprintOfficialId=lhbp-nxq7695q`）、`zenith.hosting/host/octop` |
| `README.md:571`、`:595-596` | 原作者个人仓库 `github.com/jubaoliang/OctopPet`、`graphs/contributors` + `contrib.rocks/image?repo=tencentcloud/octop` 贡献者墙 |
| `README.md:573-585`、`docs/user-guide.md:454,456,480` | 企业微信客服群 `docs/assets/qrcode.png`，文档自己标注 **有效期至 2026-08-03（已过期）** |
| `SECURITY.md:14-15` | 安全通告指向 `github.com/TencentCloud/Octop/security/advisories/new`，**并列原作者个人邮箱 `jubaoliang@gmail.com`** |
| `scripts/install.sh:18-22`、`scripts/install-octop.sh:18`、`scripts/install.ps1:23` | `OCTOP_REPO` 默认克隆 `TencentCloud/Octop.git`，并派生 `octop-harness/-gateway/-browser` 三个仓库地址；`install.sh:144,233` 默认 pip 镜像首位是 `mirrors.cloud.tencent.com` |
| `scripts/release_download_links.py:15-16` | `GITHUB_REPO = "TencentCloud/Octop"` + `DOWNLOAD_BASE=…/releases/download`（发布说明里的下载直链表） |
| `docker/Dockerfile:66,69` | `LABEL maintainer="OrcaKit Team"`、`org.opencontainers.image.source="https://github.com/TencentCloud/**orca**"`（连仓库名都写错，且与 `fnos/docker/Dockerfile:40,43` 的 `TencentCloud/Octop` 自相矛盾）→ `docker inspect` 任何人可读 |
| `docker/docker-compose.cn.yml:4-5,18` | 国内默认走 `ghcr.nju.edu.cn/tencentcloud/octop:latest`；`docker/README{,_CN}.md:15,49-52` 同 |
| `fnos/{docker,native}/LICENSE:3` | MIT 副本被打进 `.fpk` 双层 tar，用户解包可见 |
| `desktop/src/build/stamp_version.py:15,98` | 用字面量正则匹配 `name="com\.tencent\.octop"` —— **改 bundle id 必须同步改正则**，否则打包直接失败 |
| `desktop/src/build/windows/info.json`、`darwin/Info.plist:8,10,16,25`、`nsis/project.nsi:23-27,49,58-60,76-77` | exe 属性页 CompanyName/ProductName/LegalCopyright；NSIS 快捷方式与 `Program Files\Octop` 安装目录 |
| `desktop/src/build/config.yml:14`、`windows/info.json`、`Info.plist` | 桌面版本 `0.9.26` 与 `pyproject` 的 `1.0.2b8` **漂移 20+ 版**，靠 `stamp_version.py` 打包时覆盖；自建脚本漏跑就会显示旧版本号 |

### L3 · 只有读代码/读仓库才看得到（不影响用户观感，但决定"别人能否一眼认出是 fork"）

| 类别 | 命中量 | 代表位置 |
|---|---|---|
| 上游旧代号 **`finnie`** | 统计命令见 §6：**P1 前 35 → P1 后 33 行** | 集中在：`docs/user-guide.md` 3、`scripts/README.md` 2、`scripts/install.sh` / `install-octop.sh` 各 1、通用助手 `SKILL.md` 2、`api/routers/{update.py:1,skills.py:2}`、`cli/support/qr.py:1`、`experts/catalog.py:1`、`providers/codex_oauth.py:1`，以及 dashboard 8 个文件 13 行（`Settings/AdvancedSettings/UpdateConfig.tsx` 2、`Settings/Models/components/…` 4、`Experts/components/iconForName.tsx` 2、`Agent/Skills/useSkills.ts` 2、`Agent/Channels/useChannels.ts` 2、`api/modules/auth.ts` 2、`context/AgentContext.tsx` 1、`components/AuthGuard.tsx` 1）；测试 2 行 |
| 兄弟代号 `lightclaw` | **P1 前 97 → P1 后 7 行**（90 行**全部**来自三个腾讯云专家目录；实测 `fnos/` 里 0 行，所以 P1-A 对代号数没影响） | 只剩 5 个源文件：活代码 `infra/backup/system_archive.py:61` `_MIGRATION_VERSION_SUFFIX = "-migrated-from-lightclaw"`（**会写进备份归档版本名，改了影响迁移识别**，2 行）、`infra/skills/presentation.py:12` `_EXTENSION_NAMESPACES = ("octop","harness","lightclaw","orca","openclaw")`（**技能包命名空间白名单，删条目即不识别**）、`providers/codex_oauth.py`、通用助手 `SKILL.md`；另有 `tests/unit/backup/test_system_archive.py` 1 行 + `tests/integration/test_memory_api.py` 1 行 |
| `openclaw` | **P1 前 48 → P1 后 34 行**（−12 来自三个专家目录、−2 来自 P1-D 删的 `api/modules/workspace.ts` + `api/types/workspace.ts`） | 剩下的主要是 A3 判定**保留**的活功能：保留专家 `meituan-living-assistant/…/plugin_version_lite.py` 6 行 + `wechat-ops/…/SKILL.md` 1 行、`connectors/catalog.json` 5 行（微云/飞书文档 URL）、`MigrateMemory.tsx` 4 行 + `api/routers/memory_portable.py` 1 行（记忆互操作）、`skills/skills_hub.py` 2 行、`codex_oauth.py` 2 行（wire 契约常量）、`presentation.py` 命名空间 1 行、`connectors/gateway/cli_install.py` 1 行、渠道外链 `constants.ts` 1 行、`locales/{en,zh}.json` 各 1 行、`api/types/provider.ts` 1 行；测试 5 行 |
| **OpenClaw 迁移向导 = 孤儿代码**（2026-10-15 实测新发现，**同日已删**） | — | 删除前：文案在 `dashboard/src/locales/{en,zh}.json` 的 `setupWizard.stepMigrate` + `setupWizard.migrate` 整块，后端**没有** `sync-from` 路由，前端 `workspace.ts syncFromOpenClaw` 无调用方 → 死代码。**已执行**：删两份 locale 的 `stepMigrate`/`migrate` 块、`api/modules/workspace.ts` 的 import 与 `syncFromOpenClaw`、`api/types/workspace.ts` 的 `SyncFromOpenClawRequest/Response`。**未碰**：`MigrateMemory.tsx` + `api/routers/memory_portable.py:52-86`（活的 openclaw/hermes 记忆互操作） |
| `.workbuddy` 遗留路径 | **P1 前 26 → P1 后 18 行**（大小写不敏感则 39 → 29，多出的 11 行是 `WORKBUDDY_*` 环境变量与 `WorkBuddy.app` 探测） | Octop 自身代码仅 1 处注释（`infra/gateway/media/tool_media.py:137`）；其余全在 `meituan-living-assistant/**`（**保留**，见附录 A3 #15）。**不改** |
| 改名兼容层（现成的改名模板） | — | `infra/agents/plugins/legacy_imports.py:20-21`：`_PREFIX="harness_agent"` → `_TARGET="octop_harness"`，历史上做过一次重命名，机制可直接复用 |
| `.github/`（10 个 workflow + 模板） | 全部 | `release.yml`（发 PyPI）、`docker-publish.yml`（GHCR/Docker Hub）、`upload-release-cos.yml`（腾讯 COS 发布）、`fnos-build-fpk.yml`、`sync-main-to-develop.yml`、`anti-spam-issues.yml`、`codeql.yml`、`ci.yml`、`octop-desktop.yml`、`auto-tag-on-release.yml` |
| 开发文档 | — | `CONTRIBUTING.md:10,93` `git clone https://github.com/TencentCloud/Octop.git`、`:41-56` GitFlow；`AGENTS.md:379,389-409`；`.cursor/skills/publish/SKILL.md:209-210,295-312`（发版 checklist 要求核对 `ghcr.io/tencentcloud/octop` tag） |
| `git` 元数据 | — | `origin=https://github.com/kolehank/Octop.git`、`upstream=https://github.com/TencentCloud/Octop.git`；`git log` 满是 `Merge pull request #2041 from TencentCloud/…` |

> **好消息**：`openapi_meta.py` 里没有任何 `http` 外链；DB 迁移 SQL（`001`…`019`）里 URL 零命中，`_schema_version` 不含品牌；没有商业代码签名/公证链路（macOS 走 ad-hoc `codesign -s -`，Windows 无 Authenticode）——脱 GitHub 后不会因为拿不到证书而卡住，反而可以直接换上你自己的签名。

---

## 2. 决策取向（2026-10-15 已定部分）与剩余待拍板项

> **用户取向（已确认）**：第三方模型预设**不砍**，只要"支持自定义 + 有得选"即可；通用能力（连接器、语音、搜索等第三方服务对接）**保留**；腾讯云自带/专属的项目**要逐项列出来**再决定 → 清单见 **附录 A**。

**决策 1（已定）：模型预设保留，但要把"可选"补上。**
现状核实：
- **自定义 provider 已经支持，无需改动** —— `POST/PUT/DELETE /api/providers`（`api/routers/providers.py:266,289,315`，另有 `:346` 草稿测试、`:376` 拉取模型列表），dashboard 有「自定义提供商」分组（`pages/Settings/Models/index.tsx:228,381,392`）。
- **真正缺的是预设不可选** —— `GET /api/providers/presets`（`providers.py:195-201`）把 `load_provider_presets()` 的结果**全量直出，无任何查询参数**；`providers/presets.py:214-221` 用 `importlib.resources` 硬编码读 harness 的 `provider_template.json`，**无 env 覆盖、无过滤入口**；前端 `pages/Settings/Models/presetUtils.ts:10-19` 的 `PRESET_GROUP_ORDER` 把 `"tencent"` 写死在首位。
- 所以"有得选"是**要新增的能力**，最小实现面（一处收口，前端/CLI/安装向导同时生效）：
  1. `providers/presets.py:214` 增加过滤与覆盖：读一个可选的 `~/.octop/provider_presets.json`（隐藏哪些 `vendor`/`id`、分组顺序、自定义分组名、可追加自有预设），或直接支持 `OCTOP_PROVIDER_PRESET_HIDDEN` / `OCTOP_PROVIDER_PRESET_ORDER` 两个 env。
  2. `providers.py:195` 路由透传（保持返回结构不变，前端零改动）。
  3. `presetUtils.ts:10-19` 把写死的 `PRESET_GROUP_ORDER` 改成用后端下发的顺序（或允许界面本地设置覆盖）。
  - 工作量：后端 0.5 人日 + 前端 0.5 人日。**不触碰 C 类深层约定，零数据风险。**
- **✅ 已落地（2026-10-16，走的是"`~/.octop/provider_presets.json` + 后端排序"这条，未加 env 变量）**：`providers/presets.py:17-89` 新增 `DEFAULT_GROUP_ORDER` / `preset_overrides_path()` / `load_preset_overrides()` / `apply_preset_overrides()`，`load_provider_presets()` 末尾统一收口（`:363`）→ API `GET /api/providers/presets`、安装向导 `api/routers/setup.py`、CLI `octop models presets` 三条链路同时生效，**响应结构未变**。前端 `presetUtils.ts` 删掉写死的 `PRESET_GROUP_ORDER` 与 `comparePresetGroups`，`groupPresets()` 改为尊重后端数组的首现顺序。测试：`tests/unit/agents/test_provider_preset_overrides.py`（8 条）。用法与字段见 §8.1 的 P4 行。
- 附带清理项（属于品牌痕迹而非功能）：`assets/providers/index.ts:91-93` 的「获取 API Key」外链改为可配置或指向自有文档；`voice/presets.py:37-43` 的 `"name": "Tencent Cloud"` 描述文案随品牌口径调整（服务本身保留）。

**决策 2（建议按"保留"处理）：IM 渠道（微信/企微/飞书/钉钉/QQ/元宝）。**
按上面确立的取向，渠道属于"通用能力"，**建议全留**，只做附录 A 里的品牌痕迹清理（`octopbot: "https://octop.cloud.tencent.com"`、`q.qq.com/qqbot/openclaw/` 这类指向原作者/旧代号的链接）。技术上也要提醒：渠道枚举 `ChannelKind` **不是本仓库定义的**（`infra/gateway/gateway.py:14` `from octop_gateway.channels import ChannelKind`，`:50-56` 只是 re-export），实现主体在 `octop_gateway` 包里；真要删一个渠道需动 8–12 处（`channels/qr_bind.py:14-129` 扫码轮询、`bot_creators/feishu_bot_creator.py` / `yuanbao_bot_creator.py` 子进程、`api/routers/channels.py:27,37,50,55,267-272,568-586`、`cli/commands/channel.py:382`、`i18n/domains/channel.py` + 两份 JSON），且已入库的 `channels.kind` 字符串会变孤儿数据 —— **没有"只删配置"的路子，这也是建议保留的现实理由**。
SSO 登录（`infra/auth/sso/providers/{wecom,feishu,dingtalk}.py`）与 IM 渠道是两套，互不影响。
→ 选项：A 全留（当第三方服务看待）/ B 只留飞书钉钉企微 / C 全砍（工作量最大）。

**决策 3：改名改到哪一层？**
- 只改**显示层**（UI 名称、标题、logo、窗口标题、包元数据 description）：安全，1–2 天。
- 改 **CLI 程序名**：`pyproject.toml` 的 `[project.scripts]` 可以增加别名入口（`cli/main.py:83` 的 prog_name 是隐式的），可行、低风险。
- 改 **Python 包名 `octop`**：等于重写全仓 import + 四个上游依赖名（`pyproject.toml:24,25,27,36` = `octop-harness`/`octop-memory`/`octop-gateway`/`octop-browser`，别人发布的包，你无权改名）→ **强烈建议不做**。
- 改 **`~/.octop` / `octop.db` / 90 个 `OCTOP_*` 变量 / `X-Octop-*` 头 / systemd `octop.service`**：会让既有部署和已落盘数据找不到，必须配一次性迁移脚本；且 `X-Octop-Access-Token`（`api/deps.py:27`）是 JWT 滑动续期契约，改名需新旧双发一个过渡期。
→ 建议：显示层改名 + 数据目录**先不改**（`paths.py:16-20` 已把 `OCTOP_HOME` 作为第一优先级，将来改名时只换默认值即可，迁移成本被这个 env 抽象挡住了）。

**决策 4：更新 / 发布链路怎么自持？**
`infra/setup/self_update.py:31-47` 的「一键升级」逻辑：`_PACKAGE_NAME="octop"` → 查 `https://pypi.org/pypi/octop/json`，并按 `mirrors.cloud.tencent.com` → 阿里 → 清华 → 中科大 顺序探测安装（`rank_install_indexes` 一次并发 5 个源）。
**这是本次盘点里唯一的真·安全问题**：白标后如果这条链路还在跑，它会去公共 PyPI 上取**上游（或任何人抢注的）`octop` 包**覆盖安装你自己的产品；而且 `release_notes` 是用 `parse_changelog_for_version()`（`self_update.py:283-298`）从那个包的 README 里正则抠 `## [x.y.z]` —— 界面会原样显示原作者的发布文案；`GET /api/update/progress` 还会把 `mirror_errors`（含镜像域名）和 `error_code="pypi_unreachable"` 吐给前端（`api/routers/update.py:190-231,362-379`）。
→ 选项：A 整块关掉 `/api/update/*`（前端只需不渲染 `CurrentVersionBadge`/`AppVersionBadge`）/ B 自建私有 PyPI index（PEP 503）并替换 `_PACKAGE_NAME`+`_PYPI_URL`+`_MIRRORS` 三处 / C 换成用户自己的内网制品库并只读版本号。
→ **已定（2026-10-15）：选 A 的轻量形态 —— 只摘挂载点（`api/app.py:205,286`）+ 隐藏前端入口，`self_update.py` 与相关测试代码留着**，将来接自有制品库时直接恢复挂载即可。执行细节见附录 B 的 P2。

**决策 5（新增，已定）：飞牛 NAS 分发链路整块删除。** 白标版不做 NAS 应用中心分发，`fnos/` 全目录及其 CI / 打包脚本 / `self_update.py` 的 FPK 升级分支一并移除（附录 A 第 13 项、附录 B 的 P1）。

---

## 3. 后端 / 出网地址清单（二档明细）

这些是真实发生的网络调用，白标时"改字符串"= 断功能，只有替换成自有服务或显式关闭两条路。

| 优先级 | 位置 | 地址 | 有无 env 覆盖 | 处置 |
|---|---|---|---|---|
| 🔴 B1 | `api/routers/skills.py:76-78` + `:296-316` | `skillhub-1388575217.cos.ap-guangzhou.myqcloud.com/install/install.sh` → `curl` 输出直接进 `bash` | **无** | 必须改代码：去掉自动安装，只提示；或换自有镜像 |
| 🔴 B2 | `experts/library/general-assistant/skills/octop-assistant/SKILL.md:130,135` | `finnie-1258344699.cos…/octop/install.sh`（随 wheel 分发给终端用户） | — | 整目录移走，或换成你的发布物 |
| 🔴 B3 | `infra/setup/self_update.py:31-47`（+ `api/routers/update.py:152,213,337`） | PyPI `octop` + 4 个国内镜像 | 部分（`OCTOP_GREEN_PACKAGES` 只影响安装目录，不影响 URL） | 见决策 4 |
| 🟠 B4 | `infra/skills/skillhub_common.py:10`；`skillhub_market.py:35-43,76-77`；`infra/agents/experts/skillhub_market.py:182-188,314,347,487-488` | `https://api.skillhub.cn`（技能市场 + 专家市场 + 热榜 + 远程头像 CDN） | **有**：`SKILLHUB_HOST`（注意这个变量名没有 `OCTOP_` 前缀） | 不改代码即可切自有 hub；无 hub 则需前端隐藏入口 |
| 🟠 B5 | `infra/agents/providers/onnx_download.py:25-35` | `COS_ENDPOINT_DEFAULT = "https://octop-1258344699.cos.ap-guangzhou.myqcloud.com"`（与 `finnie-1258344699` 同属一个账号 UID `1258344699`）、`huggingface.co`、`hf-mirror.com`、UA `octop-onnx-download` | **有**：`OCTOP_ONNX_COS_BASE` | 切自有桶或只走 HF |
| 🟡 B6 | `infra/skills/skills_hub.py:43-47,143-170,196,748-763,1141` | 默认 hub `clawhub.ai`；导入白名单前缀 `skills.sh`/`clawhub.ai`/`skillsmp.com`/`github.com`；`api.github.com/repos/…`、`raw.githubusercontent.com`、`github.com/…/archive/….zip`；读 `GITHUB_TOKEN`/`GH_TOKEN` | **有**：`OCTOP_SKILLS_HUB_BASE_URL`、`OCTOP_SKILLS_IMPORT_URL_PREFIXES` | 切自有 hub + 收窄白名单 |
| 🟡 B7 | `infra/setup/tls/preflight.py:25-33`；`infra/gateway/bot_creators/yuanbao_bot_creator.py:379,395` | `http://metadata.tencentyun.com/latest/meta-data/public-ipv4`、`100.100.100.200`（云厂商元数据）、`4.ipw.cn`/`api.ip.sb`/`ifconfig.me`/`icanhazip`/`ipify` 5 个"取我公网 IP"服务 | 无 | 非腾讯云环境会超时；换自有探测或禁用 |
| 🟡 B8 | `infra/agents/plugins/manager.py:38-59` | 插件安装只认 `github.com/<owner>/<repo>/blob|raw/…` → 重写为 `raw.githubusercontent.com` | 无 | 自建插件源时要改这里的 URL 解析 |
| 🟡 B9 | `infra/agents/plugins/bundled/github-trending/main.py:47`（`api.github.com/search/repositories`）；`movie-search/main.py:12` UA 里写 `https://github.com/octop`（**不存在的占位仓库，直接删**）；`arxiv-search:147`、`wiki-summary:12`、`infra/agents/experts/avatar.py:252`（UA `octop-avatar/1.0`） | — | — | UA 换自有标识 |
| ⚪ B10 | 第三方服务真实地址，**改了就是断功能**：`connectors/gateway/adapters/` 15 个（`ima.qq.com:473`、`openapi.inews.qq.com:11`、`i.weread.qq.com:10`、`a.y.qq.com:10`、`api.map.baidu.com:10`、`wendao-skill-prod.ctrip.com:10`、`flyai.open.fliggy.com:19`、`mcp-open-cater.meituan.com:11`、`open.chineselaw.com:11`、`agent.qcc.com:15`、`qyapi.weixin.qq.com:21`…）；`voice/adapters.py:100,132,191,236,342,400`（`asr/tts.tencentcloudapi.com`、openai、xiaomimimo）；`utils/search_probe.py:88-117`（tavily/brave/google/moonshot）；`settings/media_generation.py:26,84,104`（volces/dashscope/minimax）；`auth/captcha/providers.py:166-358`（geetest/tencentcloudapi/cloudflare/hcaptcha）；`utils/tencent_asr_sign.py:25-29`、`utils/tencent_sign.py:11-21`（TC3-HMAC-SHA256，region `ap-guangzhou`） | — | — | 按目标市场整条砍掉，**不要改地址** |
| ⚪ B11 | 协议里自报家门：`gateway/channels/qr_bind.py:26,70` `source=octop`、`bot_creators/feishu_bot_creator.py:235` `source="octop"`、`adapters/fliggy.py:81,115,120` `clientInfo.name="octop"`/`platform="Octop"`、`ctrip_wendao.py:49`、`connectors/oauth/discovery.py:122`、`oauth/mcp.py:89` `client_name="Octop Connector"`、`adapters/qq_mail.py:63`（`support@octop.local`） | — | — | `source=octop` 是腾讯侧渠道归因，**改了可能导致扫码被拒** → 保留并知情；`clientInfo`/`client_name` 改自有名安全 |

**更正（2026-10-16 实测，此前结论作废）**：原文"后端没有 COS/S3 作为用户存储后端的实现"**是错的**。COS 是**真实可用的存储后端**：`infra/backend/adapter.py:10` 把 `cos/s3/oss/obs/custom` 全列为对象存储 kind，`:49-63` 为 `kind='cos'` 组装 `{"type": "cos", bucket, region, secret_id, secret_key, endpoint, prefix}` 交给 harness 的 `resolve_backend`；`infra/backend/compat.py:31` 同样把 `cos` 计入远端 spec。所以 `BackendBuilder.tsx:103` 的 "Tencent Cloud COS" 不是空头 UI 选项，`:186,195-196` 的 `ap-shanghai` / `cos.<region>.myqcloud.com` 是真默认值 → 按"用户自带 key 接第三方服务"归 A2 **保留**，不改名（与 AWS S3 / 阿里 OSS 同级对待）。本仓库自身的只读下载桶（`finnie-*`、`octop-*`、`skillhub-*`，同属 UID `1258344699`）仍是纯来源痕迹。

---

## 4. 外围工程：发行物里会露馅的地方

| 必须改（否则装完就露） | 位置 |
|---|---|
| **bundle id 是 `com.tencent.octop`** | `desktop/src/build/config.yml:10`、`darwin/Info.plist:12`、`darwin/Info.dev.plist:12`、`windows/wails.exe.manifest:3`；**同时必须改** `build/stamp_version.py:15`（字面量正则）和 `:98`（报错文案），否则打包失败 |
| 桌面窗口/托盘/菜单栏/加载页/设置页 | `desktop/src/main.go:339,365,389,433`、`desktop/src/assets/index.html:6,494,509`（另有 `:558,571,581,591,598-601` 中英文案）、`Taskfile.yml:10` `APP_NAME`、`build/windows/info.json` 六键、`Info.plist:8,10,16,25`、`nsis/project.nsi:23-27,49,58-60,76-77` |
| 图标全套 | `build/appicon.png`、`appicon-macos.png`、`darwin/icons.icns`、`windows/icon.ico`、`darwin/dmg-background.jpeg`、`assets/tray-icon{,-template}.png`、`assets/octop-mascot-{peek,type}.webp`；`fnos/{docker,native}/ICON.PNG`、`ICON_256.PNG`、`fnos/*/app/ui/images/icon_{64,256}.png` |
| FPK 应用中心详情逐字显示"腾讯开源的…" + maintainer | `fnos/docker/manifest:4,7,8`、`fnos/native/manifest:7,8` |
| NAS 真实拉取上游镜像 | `fnos/docker/app/docker/docker-compose.yaml:3`（**先有自建 registry 才能改**） |
| OCI 元数据水印（且两处互相矛盾） | `docker/Dockerfile:66` `maintainer="OrcaKit Team"`、`:69` `…/TencentCloud/orca`；`fnos/docker/Dockerfile:40,43` `TencentCloud` + `…/TencentCloud/Octop` |
| Agent 会把上游安装命令念给用户 | §3 的 B2 |
| 内置专家/插件随包分发 | `pyproject.toml:112` 把 `experts/library/**/*` 打进 wheel；`plugins/bundled/__init__.py:1` 注释说明装进 `~/.octop/plugins` |
| 包元数据与版权 | `pyproject.toml:6` `name="octop"`、`:8` description（含 `built on octop-harness`）、`:10` license、`:12` `authors = [{name = "octop contributors"}]`；`LICENSE:3`；`fnos/{docker,native}/LICENSE:3` |
| 文档截图里的旧品牌 | `docs/assets/*.png` 15 张（`use-*.png`、`setup-*.png`、`overview.png`、`readme-chat*.png`）+ `octop-logo.svg`、`octop-banner.png`、`readme-banner{,-zh}.png`、`qrcode.png`（已过期）、`deploy-on-{cvm,lighthouse}.png` |
| 宣传页 | `docs/octop-introduction.html:467-489`（内联 SVG logo，渐变 `#FF0307→#FF5E60`）、`:516`（渠道清单文案）、`:905`（GitHub 大按钮）、`:916,925,934`（对比链接） |

**可以先不改**（只影响开发者，用户看不到）：`.github/` 整目录（脱离 GitHub 后 10 个 workflow 全部失效，含 `codeql.yml` 是 GitHub 专有；换 CI 时务必同步下线 `secrets.PYPI_API_TOKEN`、`DOCKERHUB_*`、`RELEASE_COS_{SECRET_ID,SECRET_KEY,BUCKET,REGION,ENDPOINT}` 这四组共用凭据，避免误发布到公共 PyPI）、`CONTRIBUTING.md`、`AGENTS.md:379,389-409`、`.cursor/skills/publish/`、`.githooks/`、`CHANGELOG.md` 里的裸 PR 号（`:531 (#160)`、`:610 (#89)`、`:740 (#14)` 等指向已消失的 tracker）、`desktop/src/go.mod:1`（`module octop.desktop` 已不含 host，干净）、`data-octop-no-drag` 等 CSS 契约类名、`legacy_imports.py` 兼容层、`uv.lock`（只有 pypi.org）。

---

## 5. 三档实施路线（按投入排序）

### 第一档 · 「一眼不可辨认」= 8 个改动面，2–4 人日，零功能风险

正好回答你最初的问题（去掉腾讯/GitHub 菜单与链接）：

1. `AvatarDropdown.tsx:58-59` + `:372-392` —— 删掉「项目地址」「帮助与反馈」两项（或改指自有域名）。**一行常量 + 两个 `<a>` 块。**
2. `UpdateConfig.tsx:30-31` —— 去掉上游 COS 安装命令（配合决策 4）。
3. `BrowserWorkspace/index.tsx:42`、`RemoteBrowser/index.tsx:124` —— 默认起始页换成 `about:blank` 或你自己的门户。
4. `SkillHubTab.tsx:381`、`Environments/PageHeader.tsx:23`、`assets/providers/index.ts:91-93` —— 三处外链按钮改指自有文档或隐藏。
5. `presetUtils.ts:10-19` + `providers/presets.py:214` + `providers.py:195` —— 按决策 1 补"预设可选"（隐藏/排序/分组名可配置）；`BackendBuilder.tsx:103,196` 的 COS 选项、`voice/presets.py:37-43` 的显示名按附录 A 逐条处置。
6. 品牌名替换：`dashboard/index.html:29,32`、`public/manifest.json:3-5`、`public/offline.html:9,71-73`、`App.tsx:63`；再批量过 `dashboard/src/locales/{en,zh}.json`（**各 134 行含品牌名**）与 `src/octop/i18n/{en,zh}.json`（大小写不敏感命中 en 28 行 / zh 26 行，两份行号完全对齐）。
7. 换图：`dashboard/public/` 全套 logo/favicon/PWA 图标/三个吉祥物 + `desktop/src/build/appicon*.png`、`icons.icns`、`icon.ico`、`tray-icon*.png`、`dmg-background.jpeg`。
8. 发行元数据：`pyproject.toml:8,12`、`LICENSE:3`、`api/app.py:110,309`、`openapi_meta.py:13,86,110,149`。

改完必须 `make build-frontend`（`dashboard/` → `src/octop/dashboard/`，构建产物不能手改），交付前跑 `make all`。

### 第二档 · 「装完也不像」+ 3–5 人日

L2 全部：桌面壳 bundle id / 显示名 / 窗口标题 / 安装目录 / 托盘；Docker OCI label；compose 镜像名与自建 registry；`fnos/*/manifest` 文案；`scripts/install.{sh,ps1}` 的 `OCTOP_REPO` 与默认镜像；`README{,_CN}.md` 首屏 badge / 快速开始 / 群二维码 / 腾讯云购买链接；`SECURITY.md` 联系人；15 张文档截图重截。
以及 §3 的 B1/B2/B3 三处远程执行与更新链路（**安全项，建议不要拖到第三档**）。

### 第三档 · 「源码里也认不出来」= 数周，建议不做

L3 的代号清洗（§6 统一口径下 HEAD 实测 `finnie` 35 行 / `lightclaw` 97 行 / `openclaw` 48 行；`workbuddy` 已移出范围，见附录 A3 #15。**「OpenClaw 迁移向导已孤儿」那条已随 P1-D 执行**，删死代码一次清掉 locale 两份各 10 行、共 20 行用户可见的 `OpenClaw` 文案（实测 10→2），比逐行改名便宜得多；`lightclaw` 的 90 行已随 P1-B 删三个腾讯云专家自动消失（`fnos/` 对代号数无贡献），剩下的真痕迹只有 `system_archive.py:61` 与 `presentation.py:12` 两处，且都是**行为契约**不是注释）+ 删 `.github/` 重写 CI + 深层改名（§2 决策 3 的后两层）。
建议顺序：先做完前两档，观察是否还有人认得出来；大概率不需要动第三档。

### 明确"不该白标化"的东西

`infra/connectors/catalog.json` 里腾讯文档/腾讯会议/微信读书等**第三方服务的真名和官方文档链**，属于"这个产品能连哪些服务"的事实描述，不是你的品牌。改掉只会让用户找不到申请 key 的入口。同样，`connectors/gateway/adapters/*` 的服务地址（§3 B10）改了就是断功能。

---

## 6. 交付前的自检命令（可重复跑）

```bash
# 本机（Windows/cp936）跑测试务必带 PYTHONUTF8=1，否则会多出 23 个假失败（详见附录 B「P1 减法」行）
# 且 onnxruntime 在本机 import 即段错误，需 --ignore 这 4 个文件：
#   tests/unit/agents/test_onnx_service.py tests/unit/api/test_knowledge_bases.py
#   tests/unit/knowledge/test_gate.py tests/unit/knowledge/test_params.py
PYTHONUTF8=1 uv run pytest tests/unit -q --tb=line -p no:cacheprovider \
  --ignore=tests/unit/agents/test_onnx_service.py --ignore=tests/unit/api/test_knowledge_bases.py \
  --ignore=tests/unit/knowledge/test_gate.py --ignore=tests/unit/knowledge/test_params.py
```

```bash
# L1 残留（应为 0；命中即仍需处理）
grep -rn "TencentCloud\|github.com/octop\|octop.cloud\|skillhub.tencent" dashboard/src --include="*.ts" --include="*.tsx"
grep -rn "cloud.tencent.com\|myqcloud.com\|qq.com\|tencentcloudapi" dashboard/src --include="*.ts" --include="*.tsx"   # 按决策 1/2 保留项逐条确认
# 代号泄漏：统一口径 = 固定后缀 + 排除依赖/构建目录 + 固定扫描范围（本报告的 48→34 等数字都用这条测得，可直接复跑）
INC="--include=*.py --include=*.ts --include=*.tsx --include=*.json --include=*.md --include=*.sh --include=*.yml --include=*.go"
EX="--exclude-dir=__pycache__ --exclude-dir=.venv --exclude-dir=node_modules"
S="src/octop dashboard/src desktop scripts docs tests plugins docker .github"
for k in finnie lightclaw openclaw workbuddy; do printf "%-10s %s\n" "$k" "$(grep -rn $INC $EX "$k" $S 2>/dev/null | wc -l)"; done
# 品牌词计数（固化口径，2026-10-16 起与本文数字一致；$INC/$EX/$S 用上面那三行，别改范围）
grep -rnP '(?<![A-Za-z0-9_])Octop(?![A-Za-z0-9_-])' $INC $EX $S | wc -l          # 命中行数
grep -rnPl '(?<![A-Za-z0-9_])Octop(?![A-Za-z0-9_-])' $INC $EX $S | wc -l         # 命中文件数
# 注意：`--include=*.py` 这类模式**必须加引号**。仓库根目录有 `conftest.py` 和一批 `*.md`，
# 不加引号时 bash 会把 `$INC` 展开成 `--include=conftest.py --include=AGENTS.md …`，
# src/octop 下的 .py 反而全被排除、品牌词直接 0 命中（2026-10-16 实测踩过）。
# 上面的代号循环同理：实测加引号得 finnie 24 / lightclaw 7 / openclaw 26 / workbuddy 18，与本文数字一致。
# P1 前(HEAD) → P1 后：finnie 35→33 / lightclaw 97→7 / openclaw 48→34 / workbuddy 26→18（大小写不敏感 -rni：workbuddy 39→29）
# 注：`fnos/` 内三个代号各 0 行，所以 P1-A 不减代号计数；`WHITELABEL.md`/`RESEARCH.md` 自身含代号，故不在扫描范围内
grep -rn $INC "com.tencent.octop" desktop                                                 # bundle id 与 stamp_version.py 正则需同时改
# 界面实测：头像菜单 / 设置→高级→更新 / 内置浏览器起始页 / 设置→模型 / 设置→语音 / 存储后端抽屉 / 渠道抽屉 / 技能市场 / 专家画廊 / 登录页验证码 / /api/docs
# 安装实测：docker inspect 看 OCI label、exe 属性页与版本号、fpk 详情页
```

---

## 7. 下一步判断

按已确立的取向（预设不砍、通用能力保留、只做品牌痕迹清理 + 补"可选"能力），收益最大的组合是：**第一档外观（§5）+ 附录 A 的 A1/A2 清理 + §3 的 B1/B2/B3 三处远程执行与更新链路 + 决策 1 的预设可配置化（1 人日）**，约 5–6 人日，覆盖实际会展示给别人看的一切。数据目录、环境变量、包名、渠道枚举留在第三档，产品形态稳定后再议——`OCTOP_HOME` 的 env 抽象已经把将来的迁移成本压到很低。

剩余只需你回答一项：**决策 4 的更新链路**（关闭 `/api/update/*` / 自建私有 PyPI index / 只读版本号），这是唯一带安全属性的未决项。附录 A 的 **A3「腾讯云专属能力」14 项**请逐条标注保留或移除，我按结果出具体改动方案并落代码。

---

## 附录 A · 腾讯云自带/专属项逐条清单

判据很简单：**去掉之后产品是否少了一个能力？** 少了 → 归 A3（要你决定）；只是少了一个指向腾讯页面的字符串 → 归 A1（必须清）；是"用户自带 key 接第三方服务"的通用能力 → 归 A2（建议留）。

### A1 · 挂着"腾讯云"名字，但其实是品牌/来源痕迹 → 必须清理，功能无损

| # | 位置（已核实） | 内容 | 处置 |
|---|---|---|---|
| 1 | `dashboard/src/components/BrowserWorkspace/index.tsx:42`<br>`dashboard/src/pages/RemoteBrowser/index.tsx:124` | 内置浏览器/远程浏览器的**默认起始页** `https://cloud.tencent.com` | 换成 `about:blank` 或你自己的门户 |
| 2 | `dashboard/src/pages/Agent/Channels/components/constants.ts:161` | `octopbot: "https://octop.cloud.tencent.com"` | 改指自有域名；这是原作者的控制台域名 |
| 3 | `同上 :156` | `qq: "https://q.qq.com/qqbot/openclaw/"` | 换成 QQ 机器人官方正常文档地址（含旧代号 `openclaw`） |
| 4 | `dashboard/src/pages/Settings/Environments/components/PageHeader.tsx:23` | 「需要腾讯云密钥？」→ `console.cloud.tencent.com/cam/capi` | 文案改成中性（"需要 API 密钥？"）+ 链接按所用服务动态给出 |
| 5 | `dashboard/src/pages/Agent/Skills/components/SkillHubTab.tsx:381` | `https://skillhub.tencent.com/` | 与 §3 B4 一并处理：换成自有市场或隐藏按钮 |
| 6 | `dashboard/src/components/BackendBuilder.tsx:103` | 存储后端选项 `label: "Tencent Cloud COS"`（`:196` 还有 `cos.<region>.myqcloud.com` placeholder） | ~~后端没有 COS 实现，改成中性 "S3 兼容对象存储"~~ → **更正：后端确实支持 `kind='cos'`（`infra/backend/adapter.py:10,49-63`）**，这是"用户自带密钥接第三方服务"，按 A2 **原样保留**，未改名 |
| 7 | `dashboard/src/assets/providers/index.ts:91-93` | 三个 `tencent-*` 预设的"获取 API Key"外链（`hunyuan.cloud.tencent.com/#/app/subscription`、`cloud.tencent.com/document/product/1721`） | 功能真链可留，但要先做 §5 第一档 #5 的可配置化 |
| 8 | `dashboard/src/pages/Settings/Models/presetUtils.ts:10-19` | `PRESET_GROUP_ORDER` 把 `tencent` **写死首位** | 改成后端下发顺序（决策 1） |
| 9 | `src/octop/infra/connectors/catalog.json:237,281,413,420` | `fliggy`、`ctrip-wendao`、`youdao-note` 三个**非腾讯**条目的 `doc_url`/`guide_url` 被挂在 `qclaw.qq.com/docs/…` | 明显是原作者文档站错放 → 换成各家自己的开放平台文档 |
| 10 | `src/octop/infra/agents/experts/library/general-assistant/skills/octop-assistant/SKILL.md:130,135` | `curl -fsSL https://finnie-1258344699.cos…` 写在**会分发给终端用户**的技能正文里 | §3 B2，安全项 |
| 11 | `README.md:310-312` + `docs/assets/deploy-on-{cvm,lighthouse}.png` | 腾讯云轻量/CVM 一键购买 deep link（含 `imageId=img-n3gxkolf`、`blueprintOfficialId=lhbp-nxq7695q`）、`zenith.hosting/host/octop` | 换成你自己的部署入口 |
| 12 | `README.md:573-585`、`docs/user-guide.md:454,456,480` | 企业微信客服群二维码 `docs/assets/qrcode.png`，文档自注**有效期至 2026-08-03（已过期）** | 删或换成你自己的支持渠道 |
| 13 | `docker/Dockerfile:13-16,22-25`、`docker/docker_build.sh:14-17`、`docker/README{,_CN}.md:49-52` | 注释/文档里 pip、npm、apt 示例镜像一律用腾讯云 | 换成中性示例 |

### A2 · 通用能力，只是对接的是腾讯服务 → 建议保留（可配置化即可）

| 能力 | 位置 | 说明 |
|---|---|---|
| 腾讯系模型预设（Coding Plan / Token Plan / 企业版 / 混元 Hy3 / HAI） | 上游 `octop_harness/providers/provider_template.json`（5 个 `vendor: tencent`，端点 `api.lkeap.cloud.tencent.com`、`tokenhub.tencentmaas.com`、`api.model.haihub.cn`） | 用户自带 key 即可用 → **保留**，靠决策 1 的隐藏/排序开关来"有得选"。配套判定逻辑 `providers/reasoning.py:49,99` 必须同步留 |
| 语音 ASR/TTS 腾讯云 | `infra/voice/presets.py:37-43`、`voice/adapters.py:191,236`、`utils/tencent_asr_sign.py:25-29`、`utils/tencent_sign.py:11-21`（TC3-HMAC-SHA256，region `ap-guangzhou`） | 真实云服务 → 保留；只调整显示名/描述文案口径 |
| 登录验证码「腾讯防水墙」 | `infra/auth/captcha/providers.py:262-325`（`slug="tencent"`、`captcha.tencentcloudapi.com`、需 CAM key）+ 前端 `pages/Login/captchaAdapters.ts:59-60`、`Settings/AdvancedSettings/CaptchaSettings.tsx:70,171` | 与 Cloudflare/hCaptcha/reCAPTCHA/极验并列的第 5 个验证码 provider → 保留能力，默认可不选 |
| 腾讯系连接器 14 条 | `infra/connectors/catalog.json`（`tencent-docs/ima/meeting/news/lexiang/weiyun/ardot`、`qq-mail`、`qq-music`、`wechat-reading`、`feishu-cli`、`wecom-cli`、`agently-cli`、`weknora`），实现在 `connectors/gateway/adapters/*.py` | 服务真名 + 官方申请 key 文档链（`qclaw.qq.com/docs/…` 8 处）→ 保留；删除要同时动 `catalog.json`、`gateway/registry.py:34-49` 的 `_ADAPTERS`、`api/routers/connectors.py:326,377,404,406,422` 的 if 分支、`builder.py` URL 常量、前端图标 slug，**不是删一条 JSON 就行** |
| IM 渠道 | `infra/gateway/channels/qr_bind.py`、`bot_creators/{feishu,yuanbao}_bot_creator.py`、`api/routers/channels.py`（枚举来自 `octop_gateway`） | 见决策 2 → 保留 |
| ONNX 模型下载的 COS 桶 | `infra/agents/providers/onnx_download.py:28` `octop-1258344699.cos.ap-guangzhou.myqcloud.com`（`:25-26` 另有 `huggingface.co`、`hf-mirror.com`） | 这是 HF 加速镜像，功能上有意义。但桶名带**原作者账号 UID** → 建议用已有的 `OCTOP_ONNX_COS_BASE`（`:81-83`）切到你自己的桶，而不是保留 |

### A3 · 腾讯云专属能力 → **已定处置**（2026-10-15）

判据：去掉是否少一个功能。结论已写入下面的「处置」列；执行顺序见 **附录 B**。

| # | 能力 | 位置 | 处置 |
|---|---|---|---|
| 1 | 专家「CVM AI Doctor」 | 原 `infra/agents/experts/library/cvm-ai-doctor/`（含 `AUDIT-REPORT-2026-05-09.md`、`.workbuddy` 路径、`sync_skill.sh:15` 指向 `~/vstation/finnie/src/lightclaw/…`） | **已删**（2026-10-15 P1-B，含 `dashboard/public/experts/avatars/cvm-ai-doctor.svg`） |
| 2 | 专家「CVM Cluster Doctor」 | 原 `infra/agents/experts/library/cvm-cluster-doctor/`（`skills/tencentcloud-infra/`、`scripts/tccli-oauth-helper.py:38-42`） | **已删**（同上，含 svg） |
| 3 | 专家「TencentCloud API」 | 原 `infra/agents/experts/library/tencentcloud-api/` | **已删**（同上，含 svg） |
| 4 | 专家「微信运营」 | `infra/agents/experts/library/wechat-ops/`（`wechat_publish.py:57-60` → `api.weixin.qq.com/cgi-bin/*`） | **留**（用户指定） |
| 5 | 元宝渠道 + 自动建 bot 子进程 | `infra/gateway/bot_creators/yuanbao_bot_creator.py:58-59,194,379,395,65` + 渠道/前端/CLI 触点 | **删**（`ChannelKind` 枚举在 `octop_gateway` 里，只能停用 Octop 侧；已入库的 `kind='yuanbao'` 行需数据清理） |
| 6 | TLS 预检取公网 IP | 原 `infra/setup/tls/preflight.py:25-26` 云厂商元数据（腾讯云 + 阿里云 `100.100.100.200`）；`:28-33` 5 个公共 echo | **已只删云元数据**（2026-10-15 P1-C）：`_METADATA_PUBLIC_IP_URLS` 与 `_fetch_public_ip` 里的元数据分支已移除，公共 echo 全保留；配套 `tests/unit/infra/setup/tls/test_preflight.py` 的 2 个元数据用例删除、4 处 patch 清理。⚠️ `infra/gateway/bot_creators/yuanbao_bot_creator.py:379,395` 仍用腾讯云元数据，属 P5（元宝渠道停用）范围 |
| 7 | SkillHub 技能/专家市场 | `infra/skills/skillhub_common.py:10`、`skillhub_market.py:35-43`、`experts/skillhub_market.py`（已有 `SKILLHUB_HOST`） | **留**（当作"接入腾讯 SkillHub"的第三方能力） |
| 8 | 一键安装 SkillHub CLI（`curl \| bash`） | `api/routers/skills.py:76-78,296-316`，无 env 覆盖 | **原样留**（用户判定：这就是 SkillHub 官方提供的技能指南脚本）。⚠️ 残留风险已知情：等于让 agent 执行第三方 COS 桶里的脚本，且界面/报错会打印 `skillhub-1388575217.cos.ap-guangzhou.myqcloud.com` |
| 9 | 一键升级拉公共 PyPI + 国内镜像 | `infra/setup/self_update.py:31-47` + `api/app.py:205,286` 挂载 + `octop update` CLI + 4 个测试文件 | **摘挂载点，代码留着**（决策 4：暂不提供自动更新，随时可恢复） |
| 10 | 安装器默认克隆上游 + 腾讯云 pip 镜像 | `scripts/install.sh:18-22,144,224,233`、`scripts/install-octop.sh`（重复实现）、`scripts/install.ps1:23` | **改**：克隆地址指向你自己的仓库；镜像示例改中性 |
| 11 | Docker CE 镜像候选含腾讯云 | 原 `infra/mobile/docker_install.py:35` | **已删该行**（2026-10-15 P1-C；`:34,36,37` 的阿里/网易/教科网保留，配套 `tests/unit/mobile/test_docker_install.py` 三处延迟字典同步去掉该键）。⚠️ 同文件 `:39-40` 的 `mirror.ccs.tencentyun.com` **registry mirror 探测未删**：它只在腾讯云内网可达、外网探测失败即跳过，是装完 Docker 后拉镜像的加速项，删了只少一个功能不多一个痕迹 —— 若要一并去掉需你点头 |
| 12 | 移动端 Redroid 手机自动化 | `docker/docker-compose.mobile.yml`、`infra/mobile/` | **留**（非腾讯专属）。顺手清 `:16` 写死的宿主路径 `/workspace/Octop` |
| 13 | 飞牛 NAS 分发链路 | `fnos/` 全目录、`.github/workflows/fnos-build-fpk.yml`、`scripts/build-fpk.sh`、`scripts/fnos/`、`self_update.py:148,864-991` 的 FPK 升级分支、`tests/unit/test_fnos_docker_persist.py` | **整块删**（用户明确不需要）。删后 `OCTOP_FPK_SITE_PACKAGES` 相关代码成为死代码，可一并移除 |
| 14 | 插件 `github-trending` | `infra/agents/plugins/bundled/github-trending/main.py:12,47` | **留**（与其余 29 个内置插件同等对待，仅 UA 里的 `https://github.com/octop` 死链要清） |
| 15 | 专家「美团生活助手」 | `infra/agents/experts/library/meituan-living-assistant/skills/meituan-deals/**`（`catalog.py:52` 注册）。`~/.workbuddy/credentials/…` 默认凭证目录（`scripts/auth.py:45`、`run.js:42`）、`WORKBUDDY_AUTH_FILE`/`WORKBUDDY_CLIENT_TYPE`/`WORKBUDDY_CONFIG_DIR`（`run.js:130,269,1084`）、探测 `/Applications/WorkBuddy.app`、`C:\Program Files\WorkBuddy`（`plugin_version_lite.py:97,116`）、请求体带 `clientSource: 'coupon-fusion-workbuddy'`（`run.js:547,946,1114,1198`） | **留**（用户 2026-10-15 指定）。<br>⚠️ 更正：`~/.workbuddy` 与新品名撞名的风险**实测不成立** —— `infra/agents/workspace/execute_env.py:87` 会注入 `OCTOP_AUTH_DIR`，`run.js:41-42` 只在未注入时才回退到 `~/.workbuddy`，因此 Octop 运行时不会生成该目录。剩余 `workbuddy` 字样属该技能与美团服务端之间的契约（改要 `auth.py`/`run.js`/`diag_auth_log.py`/`diag_issue_log.py`/`plugin_version_lite.py` 五处同步，且 `clientSource` 是上报字段），**建议不动** |
| 16 | 网关代码注释里的第三方产品名 | `src/octop/infra/gateway/media/tool_media.py:137` docstring "Convert **WorkBuddy-style** generation envelopes into standard media blocks."；同名出现在 `tests/unit/gateway/test_tool_media.py`、`dashboard/src/utils/toolMediaBlocks.test.ts:114` 用例名 | **留**（与 #15 一致，是对信封格式来源的事实描述）。若要去掉，纯注释/用例名改动、无行为影响，可单独做 |
| 17 | 上游新增 4 个知识工作专家（`f79015b0`，来自 Claude plugins 转换） | `experts/library/{cowork-plugin-management,design,engineering,productivity}`。实测命中：`productivity/skills/dashboard.html`（`cursor` 30 处 + `claude` 18/6 处）、`productivity/skills/memory-management/SKILL.md`（`CLAUDE` 23 处，指令要求读 `CLAUDE.md`）、`cowork-plugin-management/**`（`Claude`/`Cowork` 50+ 处）；`design`/`engineering` 零命中 | **留**（用户 2026-10-15 指定）。唯一**用户可见**的是 `cowork-plugin-management/manifest.json` 中文描述里那句「部分上游技能假设 Cowork 桌面环境」→ 会渲染在专家卡片上，待确认是否单独改写这一句 |

---

## 附录 B · 实施顺序（step → verify）

**执行前必须先拿到的设计参数**

已收到（2026-10-15）：产品名 `wkbuddy`、定位「政务办公伙伴」、自有域名主域 `daoshengtech.com`、桌面 bundle id `com.daoshengtech.wkbuddy`。
**品牌名更新（2026-10-20）：英文名 `wkbuddy` → `agentbuddy`（全小写连体，Q 大小写口径已裁决：不用 `Agent Buddy` 空格式、不用驼峰）；中文名不变仍为「政务伙伴」。** 全仓 `wkbuddy` 字面量约 911 处 / 734 行需统一替换为 `agentbuddy`，含契约点：桌面 bundle id `com.daoshengtech.agentbuddy`（须同步 `stamp_version.py` 正则）、镜像名 `agentbuddy:latest` / `agentbuddy-sandbox:*`、产物名 `agentbuddy-desktop-*`、compose 服务键、OpenAPI `title="agentbuddy API"`。zh 界面文案不受影响。

仍缺（P6/P8 的阻塞项，均已向用户提问）：

1. **中文名与大小写口径** —— `zh` 界面用「政务办公伙伴」还是 `wkbuddy`；`en` 用全小写 `wkbuddy` 还是 `WKBuddy`/`WkBuddy`（现在两种规则会同界面打架）。
2. **三个具体 URL** —— `HELP_FEEDBACK_URL`（`AvatarDropdown.tsx:59`，原 `https://octop.cloud`）、文档站（原 `docs.octop.cloud`）、内置浏览器起始页（`BrowserWorkspace/index.tsx:42`、`RemoteBrowser/index.tsx:124`，原 `cloud.tencent.com`）。内网部署的话三者是否都不指向公网。
3. **版权主体法定全称** —— `LICENSE:3`、`pyproject.toml:12` authors、`desktop/src/build/config.yml:8,12`。
4. **logo/图标素材** —— `dashboard/public/` 全套 + `desktop/src/build/` 的 icns/ico/tray/dmg 背景；先占位图还是等设计稿。
5. **版本号与制品宿主** —— `pyproject.toml:7` 续跟 `1.0.2b8` 还是重置；私有仓地址（当前 origin 实测 `github.com/kolehank/Octop`、upstream `TencentCloud/Octop`）；`scripts/install.{sh,ps1}` 的 COS 桶换成什么（MinIO/Nexus/内网 HTTP，或删脚本只留离线 wheel）；git 历史里的上游提交信息/PR 编号是否清除 —— 这决定第三档值不值得做。
6. **深水区"确认不动"签字** —— `octop` CLI 名（或加 `wkbuddy` 别名）、`~/.octop`、`octop.db`、90 个 `OCTOP_*`、`X-Octop-*`、systemd `octop.service`。
7. **桌面端本轮是否真发版** —— 决定 `com.daoshengtech.wkbuddy` 何时改（须同步 `stamp_version.py:15` 正则）。
8. ~~附录 A3 第 15、17 项的处置~~ → **已定：`meituan-living-assistant` 与 4 个新专家全部保留**（2026-10-15），P1 删除清单不变。仅剩一个小问题等回答：`cowork-plugin-management/manifest.json` 中文描述里「部分上游技能假设 Cowork 桌面环境」这句会渲染在专家卡片上，要不要改写（专家本体不动）。

以下按"不依赖上述参数 → 依赖"排序，每步可独立交付、独立验证。

> **2026-10-16 状态：P2–P8 全部落地，实际落点与验证以 §8 为准。** 下表保留作原始计划，其中的行号是盘点时（改动前）的位置，已随改动漂移。

| 阶段 | 内容 | 验证 |
|---|---|---|
| **P1 减法**（不需品牌参数，先做） | ✅ **已全部落地（2026-10-15）**。<br>**飞牛链路**：删 `fnos/` 全目录、`.github/workflows/fnos-build-fpk.yml`、`scripts/build-fpk.sh`、`scripts/fnos/`、`tests/unit/test_fnos_docker_persist.py`、`tests/unit/test_fnos_native_stop.py`；改 `release.yml`/`docker-publish.yml`/`auto-tag-on-release.yml`/`upload-release-cos.yml`、`scripts/release_download_links.py` + 配套测试（改为负向断言）、`.gitignore`、`mise.toml`、`README.md`/`README_CN.md`、`.cursor/skills/publish/SKILL.md`；`self_update.py` 的 FPK 分支 + `tests/unit/infra/setup/test_self_update.py` + i18n `update.fpk_*`。<br>**专家**：删 `experts/library/{cvm-ai-doctor,cvm-cluster-doctor,tencentcloud-api}` 与三个 svg、`catalog.py` 三条 fallback、i18n `skills.{cvm-ai-doctor,tencentcloud-infra}`（前后端 4 份）、两个测试 fixture 换成 `ops-engineer`/`general-assistant`。<br>**其他**：`docker_install.py` 删 `mirrors.tencent.com` 候选 + 3 处测试字典；`preflight.py` 删云元数据 + 测试同步；OpenClaw 孤儿（locale `setupWizard.{stepMigrate,migrate}`、`workspace.ts syncFromOpenClaw`、`types/workspace.ts` 两个接口） | 本机验证：**`ruff check` / `ruff format --check`（1195 files）/ `mypy src/octop`（581 files）全绿**；`PYTHONUTF8=1 uv run pytest tests/unit --ignore=tests/unit/agents/test_onnx_service.py --ignore=tests/unit/api/test_knowledge_bases.py --ignore=tests/unit/knowledge/test_gate.py --ignore=tests/unit/knowledge/test_params.py` → **3870 passed, 158 skipped, 0 failed**（10 分 04 秒）；`cd dashboard && ./node_modules/.bin/tsc -b` 通过，改动的 2 个前端测试文件 **35 passed**。前端全量 `vitest` 为 **10 failed / 245 passed**，逐条查因均与白标改动无关（chatStore mock 缺 `onSteerRestore`、jsdom `getComputedStyle`、react-pdf/pdfjs 收集期错误等既有问题）。<br>**本机两个坑（写下来免得下次重查）**：① 没有 `make`，`make all` 要手动拆成上面四条命令；② **默认 cp936 码页会造出 23 个假失败**（19 个 `db/*`+`backup/*` 的 `UnicodeDecodeError: 'gbk' … 0x92`，4 个 `test_vendor_wheels_argv.py` 的 `result.stderr is None`）——加 `PYTHONUTF8=1` 后这 9 个文件 **90 passed / 1 skipped** 全绿，别误判成回归。唯一真实阻碍是 `onnxruntime` 1.30.0 在本机 **`import` 即段错误**（exit 139，CPU 是 E5-2678 v3、有 AVX2，不是指令集问题；`OMP_NUM_THREADS=1` 无效），所以上述 4 个文件必须 `--ignore`；CI 跑 Linux + Windows，不受此限。 |
| **P2 更新链路摘除** | `api/app.py:205,286` 取消挂载；dashboard 隐藏 `CurrentVersionBadge`/`AppVersionBadge` 与 `UpdateConfig.tsx` 入口（`UpdateConfig.tsx:30-31` 的 COS 命令随之消失）；`/api/docs` 里 `summary="Upgrade Octop"`（`update.py:324`）随摘除自然不见 | `uv run pytest tests/unit/api tests/integration -q`（`test_update_router.py`/`test_update_api.py`/`test_update_cmd.py` 需按"路由未注册"调整）+ 界面点开设置→高级→更新确认入口已隐藏 |
| **P3 腾讯痕迹链接清理**（A1 13 条，不需品牌参数） | 浏览器起始页（`BrowserWorkspace/index.tsx:42`、`RemoteBrowser/index.tsx:124`）、`channels/constants.ts:156,161`、`Environments/PageHeader.tsx:23`、`BackendBuilder.tsx:103` 改中性 label、`catalog.json:237,281,413,420` 错放的 `qclaw` 链接、`movie-search/main.py:12` 死链 UA、`README`/`docs` 的 badge + 一键购买 + 过期二维码（`SECURITY.md:14-15` 换成你自己的联系人） | `cd dashboard && npx tsc -b` + `make build-frontend` + 界面逐条复查（自检命令见 §6） |
| **P4 预设可选**（决策 1） | `providers/presets.py:214` 支持隐藏/排序/分组名覆盖（建议 `~/.octop/provider_presets.json`，与既有 `OCTOP_*` 风格一致）；`providers.py:195` 透传；`presetUtils.ts:10-19` 改用后端下发顺序 | `uv run pytest tests/unit -k "provider or preset" -q` + 界面模型页确认顺序与隐藏生效 |
| **P5 元宝渠道停用** | Octop 侧停用 `yuanbao`：`channels/constants.ts:26,43,86,101,119`、`api/routers/channels.py` 校验、`bot_creators/yuanbao_bot_creator.py` 调用面、i18n `channel.*`；注意 `ChannelKind` 在 `octop_gateway`，DB 里已存在的 `kind='yuanbao'` 行要一次性清理 | `uv run pytest tests/unit/gateway -q`（`test_channels_qr.py`）+ 渠道抽屉确认不再出现 |
| **P6 品牌外观**（需上面第 1–4 项参数） | `dashboard/index.html:29,32`、`public/manifest.json:3-5`、`offline.html`、`App.tsx:63`、locales 各 134 行、`src/octop/i18n/{en,zh}.json` 25 处、全套 logo/吉祥物/PWA 图标、`api/app.py:110,309` 与 `openapi_meta.py:13,86,110,149`、`pyproject.toml:8,12`、`LICENSE:3` | `uv run pytest tests/unit/i18n -q`（键对齐 + 前后端 apiErrors 对齐）+ `make all` |
| **P7 代号清洗**（L3，可选） | ✅ **第 0 步已完成（2026-10-15，随 P1）**：OpenClaw 孤儿死代码已删（locale `setupWizard.stepMigrate` + `setupWizard.migrate` 整块、`api/modules/workspace.ts` 的 `syncFromOpenClaw` 与 import、`api/types/workspace.ts` 的 `SyncFromOpenClaw{Request,Response}`）；`MigrateMemory.tsx` / `api/routers/memory_portable.py` 未碰（活的互操作）。<br>余下（§6 口径实测 33/7/34 行）：`finnie`（`update.py:1`、`skills.py:4,114`、`cli/support/qr.py:1`、`experts/catalog.py:1`、`codex_oauth.py:3`、`scripts/install.sh:823` + `scripts/install-octop.sh:788`、`docs/user-guide.md` 3 行、`scripts/README.md` 2 行、dashboard 8 个文件 13 行、`tests/unit/cli/test_run_cmd.py`）、`lightclaw`（`system_archive.py:61,439`、`presentation.py:12`、`codex_oauth.py:3` —— **均为行为契约，改前想清楚兼容**；`cli/commands/service.py` 实测 0 行，先前那条引用有误，已删）。**`.workbuddy` 已移出范围**（A3 #15）；`SKILL.md:130,135` 的 `finnie-…myqcloud.com` 属 P3 | `grep -rn "finnie\|lightclaw" src/octop dashboard/src desktop scripts` 归零 + `make all`（含 i18n 键对齐测试 `uv run pytest tests/unit/i18n -q`） |
| **P8 发行物**（需 bundle id） | 桌面壳 `config.yml:10` + `Info.plist:12`/`Info.dev.plist:12`/`wails.exe.manifest:3` **与 `stamp_version.py:15,98` 的正则同步改**、`main.go:339,365,389,433`、`assets/index.html`、`info.json`、`NSIS`、图标全套；`docker/Dockerfile:66,69`（连仓库名都写错）、compose 镜像名与自建 registry | 重装后看 Dock/托盘/窗口标题/exe 属性页；`docker inspect` 看 OCI label；不打桌面包可推迟 |

**建议节奏**：P1 先落地（纯减法、可回滚、立刻让「专家」画廊和飞牛链路干净），P2–P4 一批，P6/P8 等你给品牌参数。全程不碰 §2 决策 3 的深水区（`octop` 包名、`OCTOP_*`、`~/.octop`、`X-Octop-*`、`ChannelKind` 枚举）。

---

## 8. 本轮落地情况（2026-10-15 → 10-16）

**口径确认**（本轮按这些参数执行）：中文名 **政务伙伴**（`zh` 界面）/ 英文名 **`wkbuddy`**（全小写，`en` 界面与发行物字面量；**2026-10-20 起更新为 `agentbuddy`，见附录 B 开头的品牌名更新**）；版权主体 **汇智道晟（舟山）科技有限公司**；**所有对外品牌 URL 暂填空白页 `about:blank`**（功能性第三方端点不动，只清来源痕迹）；**logo/图标素材沿用原样**，§8.2 是将来要替换的文件清单。工作树改动**未 commit、未 push**。

### 8.1 各阶段实际落点（step → 怎么验证）

| 阶段 | 实际改了什么 | 你现在怎么验 |
|---|---|---|
| **P2 更新链路摘除** | 挂载点从 `update.router` 换成新建的 `src/octop/api/routers/service_ops.py`（`api/app.py:284`）：只留 `GET /api/update/status`（本机版本 + service/desktop 判定，**不出网**）与 `POST /api/update/restart`。`api/routers/update.py`（`/check`、`/upgrade`、`/progress`）与 `infra/setup/self_update.py` **原样留在树里但不注册**；`cli/registry.py` 删掉 `"update"` 条目（`cli/commands/update.py` 保留、已不可达）；dashboard 侧是**删除**而非隐藏：`components/CurrentVersionBadge/`、`components/AppVersionBadge/`、`pages/Settings/AdvancedSettings/UpdateConfig.tsx` 及 `.module.less`、`hooks/useUpdateStatus.ts`(+test)、`utils/updateStatusCache.ts`(+test) 共 9 个文件，`api/modules/update.ts` 改指向 service_ops 的两个端点。`api/routers/memory_portable.py`（OpenClaw/Hermes 记忆互操作）同批删除并摘挂载 | `uv run pytest tests/unit/api/test_service_ops_router.py -q`；`GET /api/update/status` 只回 `current_version`/`service_mode`/`desktop`；界面：头像菜单与「设置→高级」不再有更新项 |
| **P3 外链空白页** | 61 处 `about:blank`，分布见 §8.3。附带清掉 README 的 Trendshift/stars/forks/PyPI 徽章、`contrib.rocks` 贡献者墙、`cdn.zenith.hosting` 部署按钮、正文里的 Discord 真实邀请码 | 逐条按 §8.3 回填；`grep -c "about:blank" README.md README_CN.md SECURITY.md` 计数应归零 |
| **P4 预设可选** | 后端收口在 `src/octop/infra/agents/providers/presets.py`：`DEFAULT_GROUP_ORDER`（`:17`，等价于原前端写死顺序）、`preset_overrides_path()`（`:29` → `~/.octop/provider_presets.json`，走 `PathLayout.from_env()`，即 `OCTOP_HOME`）、`load_preset_overrides()`（`:34`，缺文件＝无覆盖，坏文件抛 `CONFIG_FILE_CORRUPT`）、`apply_preset_overrides()`（`:42`：`hidden` 可按预设 id 或分组 key 命中、`order` 可列 id 和/或分组 key、`group_names` 改分组显示名；分组恒排在散项之前，组内保持模板序），`load_provider_presets()` 末尾统一应用（`:363`）→ `GET /api/providers/presets`、安装向导、`octop models presets` 三条链路同时生效，**响应结构未变**。前端 `dashboard/src/pages/Settings/Models/presetUtils.ts` 删掉 `PRESET_GROUP_ORDER`/`comparePresetGroups`，`groupPresets()` 改按后端数组首现顺序输出，单成员分组原位降级成散卡 | 新建 `~/.octop/provider_presets.json`，写 `{"hidden": ["opencode"], "order": ["kimi", "siliconflow"], "group_names": {"tencent": "TokenHub"}}` 后重启 → 模型页/向导/CLI 同步生效；`uv run pytest tests/unit/agents/test_provider_preset_overrides.py -q`（8 条）+ `cd dashboard && ./node_modules/.bin/vitest run src/pages/Settings/Models/presetUtils.test.ts`（6 条） |
| **P5 元宝渠道停用** | `infra/gateway/gateway.py:51` `DISABLED_CHANNEL_KINDS = frozenset({"yuanbao"})` → `_register_channel` 不注册（**已入库的 `kind='yuanbao'` 行保留在 DB 里，只是永远不加载**）；`api/routers/channels.py:71-77` 新增 `_reject_disabled_kind()`，在创建（`:146`）与更新（`:196`）时拒绝，错误码 `CHANNEL_KIND_UNSUPPORTED`（`infra/errors.py:52,191` → 400，i18n `errors.*` 前后端 4 份已加）；`channels/constants.ts:38-48` 的 `CHANNEL_KEYS` 去掉 `yuanbao`（label/icon/字段表暂留，删了会让历史行渲染报错）；`bot_creators/yuanbao_bot_creator.py` 的调用面摘除 | 渠道抽屉与「更多通道」都选不到元宝；`POST /api/channels` 带 `kind=yuanbao` → 400 `CHANNEL_KIND_UNSUPPORTED`；`uv run pytest tests/unit/gateway -q` |
| **P6 品牌词与版权** | 品牌字面量按「逐匹配 + 保护名单」替换：`api/app.py:110,309` `title="wkbuddy API"`、`api/openapi_meta.py` 标签与首页文案、`pyproject.toml` description/authors、`LICENSE:3` `Copyright (c) 2026 汇智道晟（舟山）科技有限公司`、`dashboard/index.html` + `public/manifest.json`（`name`/`short_name` = 政务伙伴）+ `offline.html`、前后端 i18n 4 份 JSON（`zh` 用「政务伙伴」、`en` 用 `wkbuddy`）、api/cli 26 文件 52 行、infra 其余 85 文件 138 行（含飞书机器人首条消息、首启口令横幅、`Description=wkbuddy AI Server`、bridge/隧道、memory slim 提示、浏览器 profile 目录名等） | `uv run pytest tests/unit/i18n -q`（键对齐 + 前后端 apiErrors 对齐，80 passed）；残留计数口径见 §8.5 |
| **P8 发行物引用点** | bundle id `com.daoshengtech.wkbuddy`：`desktop/src/build/config.yml:10`、`darwin/Info.plist:12`、`darwin/Info.dev.plist:12`、`windows/wails.exe.manifest:3`，**并同步改了 `desktop/src/build/stamp_version.py:14-15` 的正则与 `:96`**（不改则打 Windows 包时匹配不到 identity 直接失败）；`windows/info.json` 六键 + `LegalCopyright`、`nsis/project.nsi`、`nsis/wails_tools.nsh`、`Taskfile.yml` 的 `APP_NAME`、`main.go` 窗口/托盘文案、`assets/index.html` 加载页、`download.go` 产物名、`portable/*.sh`、`.github/workflows/octop-desktop.yml`、`scripts/release_download_links.py`；Docker 侧 `Dockerfile` LABEL（`maintainer`/`image.title` = wkbuddy、`image.source` = 空白页）、`docker-entrypoint.sh` 首启横幅、三个 compose 的**服务键与 container_name 全部同步改成 `wkbuddy`**（overlay 与 base 必须一致，否则 overlay 失效）、`docker-compose.cn.yml` 不再指向上游 GHCR 镜像、`docker_build.sh`、`docker/README*.md` | `uv run pytest tests/unit/desktop tests/unit/mobile tests/unit/test_release_download_links.py -q`；**桌面包本轮无法本机验证**（没有 Go/Wails 工具链），需在能打包的机器上跑一次 `task build` 看 exe 属性页与托盘 |
| **T1 三项裁决** | ① `infra/mobile/docker_install.py` 的 `mirror.ccs.tencentyun.com` registry mirror 探测**去掉**；② openclaw/hermes 记忆导出互操作**不留**（`api/routers/memory_portable.py` + 前端入口删除）；③ `cowork-plugin-management` 专家卡片「部分上游技能假设 Cowork 桌面环境」那句**改写** | 见 §8.6 全量测试；`grep -rn "ccs.tencentyun" src/octop` 归零 |

**刻意没动的深水区**（与 §2 决策 3 一致）：Python 包名 `octop`、CLI 程序名 `octop`、`~/.octop` 与 `octop.db`、90 个 `OCTOP_*` 环境变量、`X-Octop-*` 请求头、`ChannelKind` 枚举（在第三方包 `octop_gateway` 里）、DB 列名，以及组件真名 `Octop Harness|Gateway|Memory|Browser`（那是四个上游 PyPI 包的名字，改了会和依赖对不上）、代码符号 `OctopError`/`OctopServer`/`OctopSpinner`/`OctopHint`/`copyErrorForOctop`。

### 8.2 素材待替换清单（你说先沿用原样，将来换这些）

**A. 覆盖同名文件即可，不用改代码**（路径写死在引用处，只换内容最省事）：

| 用途 | 文件 |
|---|---|
| Web/PWA | `dashboard/public/favico.svg`、`apple-touch-icon.png`、`pwa-192.png`、`pwa-512.png`、`logo_horizontal_dark.png`、`logo_horizontal_white.png`、`logo_vertical_dark.svg`、`logo_vertical_white.svg` |
| 吉祥物 | `dashboard/public/octop-mascot-empty.png`、`-peek.webp/.webm`、`-type.webp/.webm`、`-tasks.png`（引用点：`dashboard/src/assets/mascot.ts:5`、`components/StreamConnectingIndicator/index.tsx:4`、`pages/Chat/components/ThinkingBubble.tsx:15`、`pages/Chat/components/WelcomeScreen.tsx:8-9`） |
| 渠道图标 | `dashboard/src/assets/channels/octop.svg`（import 在 `pages/Agent/Channels/components/constants.ts:9` —— **改名要同步这一行**） |
| 仓库头图/文档 | `docs/assets/readme-banner.png`、`readme-banner-zh.png`、`octop-logo.svg`、`octop-banner.png`、`qrcode.png`（原作者支持群码，已过期）、`deploy-on-lighthouse.png`、`deploy-on-cvm.png`；头图引用在 `README.md:2` / `README_CN.md:2`。`docs/assets/` 另有 16 张界面截图（`use-01…08`、`setup-01…03`、`model-01/02`、`overview`、`readme-chat`、`readme-chat-zh`）里是旧品牌 UI，要重截 |
| 桌面壳 | `desktop/src/build/appicon.png`、`appicon-macos.png`（wails 由它们生成 `icons.icns`/`icon.ico`，仓库里不存产物）、`desktop/src/build/darwin/dmg-background.jpeg`、`desktop/src/assets/tray-icon.png`、`tray-icon-template.png`、`octop-mascot-peek.webp`、`octop-mascot-type.webp` |
| 专家头像 | `dashboard/public/experts/avatars/*.svg`（现存 30 个，含 `default.svg`）；画廊里已安装的专家还会走 SkillHub 远程头像 CDN（§3 B4） |

**B. 还没处理的宣传物**：`docs/octop-introduction.html`（文件名本身带 `octop`，内含内联 SVG logo、渠道清单、GitHub 按钮）、`docs/assets/` 截图未重截。

### 8.3 URL 回填清单（现在写的是 `about:blank`，**待回填实测 56 处**）

> ⚠️ 别照着 `grep -rn about:blank` 的总数回填：全仓 71 处命中里，**15 处是代码原本就在的功能性用法**（弹窗 `window.open("about:blank", …)`：`desktop/src/ssoPopup.ts:34`、`pages/Agent/Connectors/index.tsx:466`；地址比较：`components/BrowserWorkspace/index.tsx:146`、`hooks/useBrowserViewController.ts:23`、`hooks/useRemoteBrowserBookmarks.ts:17`；测试：`utils/desktopExternalLinks.test.ts:24,28,73`、`desktop/src/openurl_test.go` 2 处；`api/routers/browser/stream.py` 1 处），把它们改成真地址会直接弄坏功能。剩下 56 处才是本表要回填的：`README.md`/`README_CN.md` 各 17、`connectors/catalog.json` 8、`octop-assistant/SKILL.md` 5、`Channels/components/constants.ts` 3、`AvatarDropdown.tsx` 2、`Dockerfile`/`SECURITY.md`/`PageHeader.tsx`/`RemoteBrowser/index.tsx`/`SkillHubTab.tsx`/`BrowserWorkspace/index.tsx:42` 各 1。

> 原值一并列出，方便你决定"换成自有地址"还是"这个入口干脆不要了"。

| 位置 | 现在的值 | 原值（HEAD） | 建议 |
|---|---|---|---|
| `dashboard/src/components/AvatarDropdown.tsx:56` | `GITHUB_URL` | `https://github.com/TencentCloud/Octop` | 你自己的仓库地址；不外传就把这个菜单项去掉 |
| `同上 :57` | `HELP_FEEDBACK_URL` | `https://octop.cloud` | 自有官网/帮助中心（内网部署给内网门户） |
| `dashboard/src/components/BrowserWorkspace/index.tsx:42` | 内置浏览器起始页 | `https://cloud.tencent.com` | 政务门户首页，或就保持 `about:blank` |
| `dashboard/src/pages/Control/RemoteBrowser/index.tsx:124` | 远程浏览器起始页 | `https://cloud.tencent.com` | 同上 |
| `dashboard/src/pages/Agent/Channels/components/constants.ts:155,157,160` | `qq` / `yuanbao` / `octopbot` 三个申请指引 | `q.qq.com/qqbot/openclaw/`、`yuanbao.tencent.com/bot`、`octop.cloud.tencent.com` | `qq`/`yuanbao` 可换回各平台**官方**文档；`octopbot` 是原作者控制台，不自建就该整条移除 |
| `dashboard/src/pages/Agent/Skills/components/SkillHubTab.tsx:381` | 技能市场外链 | `https://skillhub.tencent.com/` | SkillHub 官方站（该能力按裁决保留）或你自己的市场 |
| `dashboard/src/pages/Settings/Environments/components/PageHeader.tsx:23` | 「需要 API 密钥？」 | `https://console.cloud.tencent.com/cam/capi` | 按所用服务动态给出，或改中性文案 |
| `src/octop/infra/connectors/catalog.json:46,96,131,138,237,281,413,420` | 8 个 `doc_url`/`guide_url` | 全是 `https://qclaw.qq.com/docs/…`（原作者文档站，且 `fliggy`、`ctrip-wendao`、`youdao-note`、`tencent-ima`、`tencent-news`、`tencent-lexiang` 挂错） | 换成各家开放平台自己的文档：`flyai.open.fliggy.com`、携程问豆、有道云笔记、腾讯文档/会议官方站 |
| `…/general-assistant/skills/octop-assistant/SKILL.md:84,87,614,661` + `:85-86,97-124` 的 `/guide/…` 相对路径表 | 官网 / 源码 / 整套文档路径 | `https://octop.cloud`、`github.com/TencentCloud/Octop`、`https://docs.octop.cloud/**` | ⚠️ **这是 agent 会念给用户的内容**：`:80` 已明令「在填入正式地址前不要把链接发给用户」。要么补你自己的文档站，要么把这几节整块删掉 |
| `docker/Dockerfile:69` | `org.opencontainers.image.source` | `github.com/TencentCloud/Octop`（原值连仓库名大小写都和实际不符） | `docker inspect` 可见，填自有仓库或删掉该 LABEL |
| `SECURITY.md:14` | 提交安全通告入口 | `…/security/advisories/new` | 换成你自己的漏洞上报邮箱/表单 |
| `README.md` 11 处 / `README_CN.md` 10 处 | License 与 Version 徽章、4 个组件仓库（Harness/Gateway/Memory/Browser）、桌面下载、2 个腾讯云一键购买 | `github.com/TencentCloud/*`、`…/releases/latest`、`buy.cloud.tencent.com/{lighthouse,cvm}?…` | 徽章链接填自有仓库；`deploy-on-{lighthouse,cvm}.png` 两张按钮图 + 整个「云端部署」小节建议换成你的部署入口 |
| 已直接删除（无需回填） | — | Trendshift 徽章、GitHub stars/forks 徽章、`img.shields.io/pypi/v/octop`、`contrib.rocks` 贡献者墙、`cdn.zenith.hosting` 部署按钮、`discord.gg/QnWdhJxq9h` 真实邀请码 | 这些都指向上游项目自身，白标后无意义；`README.md` 的 Community 小节现在是「待填」占位 |

### 8.4 本轮造成的行为损失（知道才不会被当成 bug）

1. **没有检查更新 / 一键升级**：界面无入口、`octop update` 不可用、`/api/update/{check,upgrade,progress}` 未挂载。恢复 = `api/app.py:284` 换回 `update.router` + `cli/registry.py` 加回一行 + `git checkout HEAD -- <那 9 个前端文件>`。
2. **元宝渠道停用**：不能新建；历史 `kind='yuanbao'` 行仍在 DB 但永不加载（渠道列表里不可用）。要彻底清数据需 `DELETE FROM channels WHERE kind='yuanbao'` —— **我没执行**，等你确认。
3. **记忆互操作入口消失**：`api/routers/memory_portable.py` 与前端 `syncFromOpenClaw` 已删，无法再从 OpenClaw/Hermes 格式导入记忆。
4. **Docker 少一个内网加速候选**：`mirror.ccs.tencentyun.com` registry mirror 探测按你的裁决去掉；在腾讯云内网部署时不再自动加速拉镜像（阿里 / 网易 / 教科网三个候选仍在）。
5. **TLS 预检少一条取 IP 路径**：云厂商元数据（`metadata.tencentyun.com`、`100.100.100.200`）已删，5 个公共 echo 仍在；纯内网无出口时预检会失败，需手工指定公网 IP。
6. **三个腾讯云运维专家不可用**：`cvm-ai-doctor`、`cvm-cluster-doctor`、`tencentcloud-api` 及头像已删；装过它们的用户会留孤儿目录。
7. **飞牛 NAS 分发整链没了**：`fnos/` 全目录与 FPK 升级分支删除，`.fpk` 产物不再可能。
8. **README / SECURITY 十余个链接失效**（空白页）；`docs/**` 正文仍是上游版（本轮只改品牌词，没重写内容）。
9. **桌面端未经实机验证**：bundle id / NSIS / 图标链只有静态检查（本机无 Go 工具链，`go build`/`task build` 跑不了）。

### 8.5 残留计数与待你决策清单

**残留计数（2026-10-17 第四轮复核，命令已固化进 §6，数字以本轮为准）**：品牌词 `Octop`（排除保护名单后）**66 处 / 49 文件**——比 2026-10-16 记的 38/28 多出部分来自合并上游 1.0.2b9 带回的新代码/新文档，且都落在非用户可见面（`scripts/**` 那 3 处均为 `kolehank/Octop` 仓库地址）。分布：`tests/**` 35 行（fixture 与注释）、`src/octop` 21 行（逐条核实**全是** docstring/注释/专家技能说明：`laya_runtime.py` 4、`agent_mcp/` 与 `routers/agent_mcp.py` 5、`routers/decision.py` 2、`backend/grep_safety.py` 1、`business-operations/**` 7、`octop-assistant/SKILL.md` 2 处组件真名，均属保护名单/内部注释）、`docs` 5 行（`api.md` 3 + `plugin-channels.md` 1 属「doc 先不动」范围；`octop-ui-payload-offload.md:3` 1 行上游 issue 链接）、`scripts/**` 3 行（`kolehank/Octop.git` ×2 + `release_download_links.py` 的 `GITHUB_REPO`）、`.github` 2 行（`ISSUE_TEMPLATE/config.yml` 的 link 因 URL 带仓库名命中）。代号行数：`finnie` 24、`lightclaw` 6（§10.2 删 SKILL.md 一行后）、`openclaw` 26、`workbuddy` 18（A3 #15/#16 判定保留）。`desktop/` 里的 `com.tencent.octop` 已归零。

**§6 扫描口径之外还有一批（2026-10-16 补测，19 行 / 3 个文件，都要你定去留）**：`AGENTS.md` 8 处（`:37` 开篇 "**Octop** — self-hosted AI assistant platform"、`:60` 包布局、`:166/183/210/312/326` 等 —— 这是**给协作者和 coding agent 看的门面**，最终用户看不到，但"看起来是我的产品"这条它最显眼）；`.cursor/skills/publish/SKILL.md` 2 处（`:4` front-matter "Publish the Octop Python package"、`:13` 同义中文）；`CHANGELOG.md` 9 处（历史条目里的 "项目重命名为 Octop"、"Octop↔Octop 云端桥接" 等 —— **属既成事实的记录，改了等于伪造历史，我建议不动**）。

**需要你点头 / 给参数的（2026-10-16 已逐条给答复，**回执见 §8.5.1，下表保留作问题原文**）**：

| # | 事项 | 位置 | 说明 |
|---|---|---|---|
| 1 | **安装脚本克隆地址** | `scripts/install.sh:18`、`scripts/install-octop.sh:18`、`scripts/install.ps1`、`scripts/install.bat:11` | 四处默认 `OCTOP_REPO=https://github.com/TencentCloud/Octop.git`。填你的仓库？还是内网离线装 wheel、脚本只留 `pip install` 一条路？ |
| 2 | **发布物抓取源** | `scripts/release_download_links.py:15` `GITHUB_REPO = "TencentCloud/Octop"` | 桌面/便携版下载链接生成器仍指向上游 releases |
| 3 | **SkillHub 一键脚本** | `api/routers/skills.py:76-78,296-316`（`curl` 管道进 `bash`，源是 `skillhub-1388575217.cos…`） | 你已裁决"留"。但它等于让 agent 执行第三方桶里的脚本，报错还会打印该域名 —— 要不要顺手把打印的 URL 藏掉 |
| 4 | **ONNX 模型下载桶** | `infra/agents/providers/onnx_download.py:28` `octop-1258344699.cos…`（已有 `OCTOP_ONNX_COS_BASE` 可覆盖） | 换成你自己的桶，还是只走 HuggingFace / `hf-mirror` |
| 5 | **自动更新恢复时机** | §8.4 第 1 条 | 等你有自有制品库（私有 PyPI / Nexus / 内网 HTTP）时告诉我，我把挂载恢复并把 `_PACKAGE_NAME`/`_PYPI_URL`/`_MIRRORS` 换成自有的 |
| 6 | **PyPI/npm/apt 镜像示例** | `docker/Dockerfile`、`docker/docker_build.sh`、`docker/README*.md` | 文案已中性化；若你有内网镜像地址，我可以再统一一轮 |
| 7 | **GitHub Actions 与凭据** | `.github/workflows/docker-publish.yml`（GHCR org）、`scripts/ci/upload_release_cos.sh`（`octop/release/` 前缀）、`PYPI_API_TOKEN`、`DOCKERHUB_*`、`RELEASE_COS_*` | 这些 workflow 只有回到 GitHub 才生效。要不要整块下线，避免误发布到公共 PyPI |
| 8 | **元宝历史渠道行** | DB `channels.kind='yuanbao'` | 现在只停用不删（§8.4 第 2 条），要不要给你一条清理 SQL |
| 9 | **`docs/**` 正文** | `docs/octop-introduction.html`、`user-guide.md`、`connectors.md`、`api.md`（含 `TencentCloud/octop-harness` 链接） | 文档是"装完就会给人看"的东西，本轮只改了品牌词。要不要下一轮整批重写 |
| 10 | **git 历史与 origin** | 实测 origin `github.com/kolehank/Octop`、upstream `TencentCloud/Octop` | 第三档（改包名 / 清历史）值不值得做，取决于你是否公开源码 |
| 11 | **`provider_presets.json` 要不要给界面** | §8.1 的 P4 行 | 现在是发布方手写文件（改完重启生效）。要不要在「设置→模型」做可视勾选 |
| 12 | **`windows/info.json` 的 `CompanyName`** | 现填 `wkbuddy` | 语义上应是公司名（汇智道晟），要不要改 |

### 8.5.1 决策回执（2026-10-16，你逐条答复后的落点）

| # | 你的决策 | 实际落点 |
|---|---|---|
| 1 | 填我仓库地址 | ✅ 四处默认改为 `https://github.com/kolehank/Octop.git`：`scripts/install.sh:18`、`scripts/install-octop.sh:18`、`scripts/install.ps1:23`、`scripts/install.bat:11`；`CONTRIBUTING.md:10,93` 两条 clone 命令一并改。<br>⚠️ **顺带修了一个会被这一步引爆的坑**：原先 `install.sh:19-22` 用 `${OCTOP_REPO%/*}` 派生 `octop-harness/-gateway/-browser` 三个 clone 地址，改完之后 `--from-source` 会去 clone 并不存在的 `github.com/kolehank/octop-harness.git`。现在这三个默认**钉住上游 org**（`https://github.com/TencentCloud/octop-harness.git` 等），不再跟着 `OCTOP_REPO` 走，帮助文本同步改成 "default: upstream org, not OCTOP_REPO"。想覆盖仍然用 `HARNESS_*_REPO` 环境变量。`bash -n` 两个脚本通过 |
| 2 | 填我地址 | ✅ `scripts/release_download_links.py:15` → `GITHUB_REPO = "kolehank/Octop"`。配套测试 `tests/unit/test_release_download_links.py:28` 原本把 URL 写死，改成从模块读 `mod.GITHUB_REPO`，以后换仓库不用再动测试；2 passed |
| 3 | 不用 | ⏭ SkillHub 的 `curl \| bash` 与报错里打印的桶域名**保持原样**，不动 |
| 4 | 就按现在的来，白嫖腾讯的桶 | ⏭ `infra/agents/providers/onnx_download.py:28` 的 COS 桶不改（`OCTOP_ONNX_COS_BASE` 覆盖能力仍在） |
| 5 | 等迁到 Gitea 后用 Gitea 制品库 | 📌 **待办已记 §8.7**，本轮不恢复自动更新 |
| 6 | 同 5，记录下来后续改 | 📌 **待办已记 §8.7** |
| 7 | 发布到 GHCR 就行，其他暂时都去掉 | ✅ **三条通道剥掉，只留 GHCR + GitHub Release**：<br>· `release.yml` 删 `Publish to PyPI` job（`PYPI_API_TOKEN` 不再被任何工作流引用），`github-release` 的 `needs` 改指 `build`；生成 release notes 里的 `## Install / pip install octop==$version` 段一并删 —— 不发公共 PyPI 了还写着这条，等于教人装上游那个同名包<br>· `docker-publish.yml` 删两个 job 里的 `Log in to Docker Hub` 步骤与 `DOCKERHUB_USERNAME/TOKEN`，metadata 只出 GHCR 一个 image，merge 脚本由「遍历 GHCR+Hub」改成只处理 GHCR（多架构缺失仍告警、平台镜像全缺仍 exit 1 的语义保留）；头注里的示例改成 `ghcr.io/kolehank/octop:…`（镜像名本来就是 `github.repository` 小写得来）<br>· `upload-release-cos.yml` 与 `scripts/ci/upload_release_cos.sh` **已删**，`octop-desktop.yml` 末尾的 `upload-cos` job 摘掉（`RELEASE_COS_*` 五个 secret 全部不再被引用）<br>· `.cursor/skills/publish/SKILL.md` 三处口径同步（front-matter 的 "PyPI / Docker Hub + GHCR"、红线规则里的「直接上传 PyPI」、`VERSION_FILE` 的 "wheel / PyPI 唯一版本源"）<br>· 顺手修正 `README.md:281` / `README_CN.md:283` 的 `docker run … octop:latest` → `wkbuddy:latest`（`docker_build.sh:25` 打的标签就是 `wkbuddy:latest`，原写法必然 no such image），并把 `docker-compose.cn.yml` 的 `image:` 落实为 `ghcr.io/kolehank/octop:latest`<br>· 剩下的工作流只用 `GITHUB_TOKEN`：`ci.yml`、`codeql.yml`、`anti-spam-issues.yml`、`auto-tag-on-release.yml`、`sync-main-to-develop.yml`、`octop-desktop.yml`。四个改动过的 yml 已用 `yaml.safe_load` 校验通过 |
| 8 | 不用 | ⏭ DB 里 `kind='yuanbao'` 的历史行不清理，保持「停用不删」 |
| 9 | doc 暂时不动，后续我调整完再重写 | ⏭ `docs/**` 保持本轮品牌词替换后的状态。<br>📝 重写时记得这条已确认的过期项：`docs/user-guide.md:124` 仍是 `octop:latest` |
| 10 | 先不处理 | ⏭ 不动 git 历史、不改 `origin/upstream`、不动包名与 `OCTOP_*` |
| 11 | 不要，保持手写 | ⏭ 不加 UI，`~/.octop/provider_presets.json` 手写 + 重启生效即为最终形态 |
| 12 | 改成道晟科技 | ✅ `desktop/src/build/windows/info.json:8` `CompanyName` = 「道晟科技」。<br>**同时把 `desktop/src/build/config.yml:8` 的 `companyName` 也改成「道晟科技」**——那是 wails 的权威字段，`info.json` 只是它的生成产物，只改产物会在下次重生成时被覆盖回去。<br>⚠️ **两个后果要知道**：① 改 `config.yml` 的 `info:` 段后必须跑 `wails3 task common:update:build-assets` 才会刷新 `info.json` 等生成资产（文件顶部注释自己写的规则），本轮我直接手改了两处；② `Info.plist` 里没有 `NSHumanReadableCopyright` 这类字段承接 company，所以 macOS 侧不受影响；Windows exe 属性页的「公司」会变成中文，UTF-8 进 JSON 是安全的（同文件 `LegalCopyright` 早就放着中文全称），但**本机没有 Go/Wails 工具链，没能实机打包确认** |

### 8.6 验证证据（本轮实跑，本机 Windows）

| 命令 | 结果 |
|---|---|
| `PYTHONUTF8=1 uv run pytest tests/unit -q --tb=line -p no:cacheprovider --ignore=<4 个 onnx 文件>` | **3869 passed, 158 skipped, 0 failed**（9 分 10 秒；含新增 8 条预设覆盖测试） |
| `uv run ruff check src/octop tests` | All checks passed |
| `uv run ruff format src/octop tests` | 2 files reformatted，1194 files unchanged |
| `uv run mypy --strict src/octop` | Success: no issues found in 580 source files |
| `cd dashboard && ./node_modules/.bin/tsc -b` | exit 0 |
| `vitest run src/pages/Settings/Models/presetUtils.test.ts` | **6 passed**（新增 2 条：尊重后端顺序 / 单成员分组原位降级） |
| `cd dashboard && npm run build` | ✓ built in 1m37s，产物已写回 `src/octop/dashboard/`（PWA 102 entries）——**必须重构建，浏览器端才会显示新品牌** |
| 残留扫描 | 品牌词 **38 处 / 28 文件**（上一轮 43/32，差值来自本轮删除的 COS 工作流与 PyPI job）；`dashboard/src` 用户可见面 0；`desktop/` 的 `com.tencent.octop` 0；代号 24 / 7 / 26 / 18 |
| **第二轮（2026-10-16 决策落地）复跑** | `bash -n scripts/install.sh scripts/install-octop.sh` 通过；`powershell` 用 `Parser::ParseFile` 解析 `scripts/install.ps1` → `errors=0`；`yaml.safe_load` 校验 4 个改动/相关 yml（`release.yml`、`docker-publish.yml`、`octop-desktop.yml`、`auto-tag-on-release.yml`）+ 4 个 compose 全 OK；`desktop/src/build/windows/info.json` 用 `json.load` 解析并读出「道晟科技」；`ruff check` + `ruff format --check`（`scripts/release_download_links.py`、`tests/unit/test_release_download_links.py`）全绿；`PYTHONUTF8=1 uv run pytest tests/unit/desktop tests/unit/test_release_download_links.py -q` → **64 passed** |
| `PYTHONUTF8=1 uv run pytest tests/integration -q --ignore=<2 个 onnx 文件>` | **592 passed, 29 skipped, 2 failed → 修断言后这两个文件 11 passed**（44 分 23 秒 + 复跑 1 分 12 秒）。两个红都是**我写的断言错**，不是产品问题：`api/app.py:315` 有 `@app.get("/{full_path:path}")` SPA 兜底，未挂载路径 **GET → 404、非 GET → 405**，而 `test_update_api.py::test_update_chain_routes_are_not_mounted` 与 `test_channels_api.py::test_disabled_channel_kind_is_rejected` 一律断言 404；已改为 GET 断 404、POST/PATCH 断 405 并写明原因。另：`tests/integration/test_onnx_models_api.py` 单独跑实测 **exit 139**（本机 onnxruntime 段错误，与本轮改动无关），且崩溃时 faulthandler 会把 `-q` 的统计行挤掉、看着像"跑完没输出"，务必一并 `--ignore` 掉它和 `test_knowledge_bases_api.py` |

### 8.7 待办：等自建 Gitea + 制品库就绪之后再做（你 2026-10-16 明确「后面再说」）

**A. 恢复自动更新，并把源换成 Gitea 制品库**（当前状态是 §8.4 第 1 条：入口全摘、代码留着）

1. `src/octop/api/app.py:284` 的 `_RouterMount(service_ops.router, "/api", ["update"])` 换回 `update.router`（`/check`、`/upgrade`、`/progress` 随之复活；`service_ops.py` 的 `status`/`restart` 可保留或合并回去）。
2. `src/octop/cli/registry.py` 加回 `"update"` 条目（`cli/commands/update.py` 一直留着，没删）。
3. 前端 9 个文件用 `git checkout <P2 前的提交> -- <路径>` 取回：`components/CurrentVersionBadge/`、`components/AppVersionBadge/`、`pages/Settings/AdvancedSettings/UpdateConfig.tsx`(+`.module.less`)、`hooks/useUpdateStatus.ts`(+test)、`utils/updateStatusCache.ts`(+test)，并把 `api/modules/update.ts` 指回原端点。
4. `infra/setup/self_update.py` 的 `_PACKAGE_NAME` / `_PYPI_URL` / `_MIRRORS` 换成 Gitea 制品库地址 —— **这一步是安全前提**：现在这套默认值是去公共 PyPI 抓名为 `octop` 的包，白标之后继续开着等于把升级链路交给陌生上传者。
5. 复跑 `tests/unit/api/test_update_router.py`、`tests/unit/api/test_update_api.py`、`tests/unit/cli/test_update_cmd.py`、`tests/unit/infra/setup/test_self_update.py`（P2 时按「路由未注册」调整过，恢复时要调回去）。

**B. 统一 pip / npm / apt 镜像地址**（§8.5 第 6 条）：`docker/Dockerfile`、`docker/docker_build.sh`、`docker/README*.md`，以及 `scripts/install.sh:144,233` 的 pip 镜像候选首位、`install.sh` 的 `PLAYWRIGHT_DOWNLOAD_HOST` 默认（npmmirror → 官方）。文案本轮已中性化，等有内网地址再统一替换。

**C. 换仓库地址时会漏掉的引用点**（从 GitHub 迁到 Gitea 时逐条改，别只改 install.sh）：`scripts/install.{sh,ps1,bat}` 与 `scripts/install-octop.sh` 四处默认、`CONTRIBUTING.md:10,93`、`scripts/release_download_links.py:15`、`docker/docker-compose.cn.yml` 的 `image:`、`.github/workflows/docker-publish.yml:4,18,19` 注释、`README.md`/`README_CN.md` 里 §8.3 那 21 处待回填的 `about:blank`（正好一起填）。注意 `install.sh:20-22` 的三个 `HARNESS_*_REPO` 现在**钉的是上游 org**，与 `OCTOP_REPO` 脱钩，迁移时不会跟着变 —— 若 Gitea 上也要自建 harness 镜像，需显式设这三个环境变量。


---

## 9. 第三轮：合并上游 1.0.2b9（2026-10-17）

你要求「先提交，再同步远端，注意保留我的修改」，最后追加「全部都提交，然后推送」。落地成三个提交，且已推到 `origin/main`（`4f443bab..14a77d0c`，快进，无 force）：

| 提交 | 内容 |
|---|---|
| `ff1c3420` | 本轮全部白标改动（648 文件，+2025 / −51697）。作者与提交者 `daosheng <daosheng@hz.com>`（用 `git -c user.name=… -c user.email=…` 内联传入，**没有改你的 git config**） |
| `6d5adc51` | `Merge origin/main (1.0.2b9)`，吸收远端 39 个提交（上游已到 `4f443bab Release/1.0.2b9`） |
| `14a77d0c` | 本报告 + `RESEARCH.md` + `LOCAL-DEBUG-GUIDE.md` 入库 |

`kolehank/Octop` 是 **PUBLIC** 仓库，你已明确知情并选择把这三份内部文档一并提交推送 —— 也就是说「这是 TencentCloud/Octop 的白标底座」以及本表的决策记录，从 2026-10-17 起对外可见。推送前扫过凭据与内网 IP（无命中，唯一像是 `10.` 的命中是「Windows 10.0.19045」）。仓库外仍留了一份保险：`C:\Users\Administrator\Octop-backups\whitelabel-tracked.patch`（3.5 MB）+ `whitelabel-untracked.tgz`。

### 9.1 冲突处置（11 处，规则是「保留我们的删除，采纳他们的行为」）

| 冲突 | 处置 |
|---|---|
| `fnos/docker/Dockerfile`、`fnos/docker/app/docker/docker-compose.yaml`、`fnos/docker/manifest`、`fnos/native/manifest`、`scripts/build-fpk.sh`、`scripts/fnos/slim-site-packages.sh`、`tests/unit/test_fnos_docker_persist.py`（7 处 modify/delete，上游刚修了 fnos 两个 bug #2131 #2129） | **全部保持删除**，飞牛链路不复活 |
| 上游新增 `scripts/fnos/store_version.sh` | 一并删除（全仓只有它自己引用 `fnos_store_version`，无 workflow 引用） |
| `docker/docker-entrypoint.sh:162` | 取上游的 `[ ! -f "$INIT_MARKER" ]` 引导守卫（#1868），保留我们的「政务伙伴」文案 |
| `README.md:11` / `README_CN.md:11` 徽标 | `about:blank` 链接照旧、PyPI 徽标照旧不要，版本号跟到 `1.0.2b9` |
| `.cursor/skills/publish/SKILL.md:202` | 删掉上游新增的两条飞牛版本号步骤（原 4/5），`uv.lock` 那条恢复为第 4 步 |
| `src/octop/api/routers/channels.py:93` | `_reject_disabled_kind` 形参放宽成 `str \| ChannelKind \| None` —— 上游 #1823 把渠道 kind 改成可被插件扩展的 `Annotated[str, …]`（`channels.py:55`），元宝停用逻辑必须跟着放宽，否则 mypy 红 |

上游改动还让 3 个测试去读已删除的 `fnos/` 文件，同步改掉：`tests/unit/backend/test_grep_safety.py:98`（去掉 fnos Dockerfile）、`tests/unit/test_docker_nofile.py`（去掉 fnos compose 参数，并把服务名索引改成 `wkbuddy`，因为 compose 服务键已随品牌改名）、`tests/unit/test_docker_knowledge_dependencies.py`（整段 `test_fnos_source_dockerfile_installs_knowledge_extras` 删除）。

### 9.2 上游新代码带回来的品牌文案（已补白标）

`git diff f79015b0 origin/main` 的**新增行**里没有任何代号（finnie/lightclaw/openclaw/workbuddy 均 0）、没有 `cloud.tencent.com` / PyPI / DockerHub / `api/update` / `self_update`，`TencentCloud` 只出现在 README 徽标（已处理）与 `ghcr.io/tencentcloud`（在被删的 fnos 文件里）。需要补的只有新功能的用户可见文案：

| 位置 | 改动 |
|---|---|
| `dashboard/src/locales/en.json:3358,3361`、`zh.json:3358,3361` | Laya 本地安装说明与失败提示：`Octop` → `wkbuddy` / 政务伙伴 |
| `src/octop/i18n/en.json:975`、`zh.json:975` | `decision.*.error_health` 同上 |
| `src/octop/api/openapi_meta.py:98` | MCP 网关标签描述 → `wkbuddy experts` |
| `src/octop/api/routers/agent_mcp.py:33,68,89` | 三条路由 `summary` → `wkbuddy`（与既有 `bridge.py:66`、`update.py:315` 的写法一致） |
| `src/octop/infra/agent_mcp/protocol.py:31,37` | 两个 MCP 工具 `description` → `wkbuddy`。**工具名 `list_octop_experts` / `call_octop_expert` 不动**（对外协议标识符，等同 `ChannelKind` 那一类深水区） |

按「符号不动、文案才动」保留的：`hasOctopUi`、`BuiltinOctopUiFallback`、`OctopAgent`、`common.copyErrorForOctop`（键名保留，值早已白标）、`OctopError` / `OctopServer` / `_OctopLogFormatter`。

### 9.3 本轮**没**动的三件（第 1 件你 2026-10-17 已裁定保留）

1. **决策模型默认打外网**：`dashboard/src/pages/Settings/Models/components/DecisionSettingsPanel.tsx:35` 把 `https://openrouter.ai/api/alpha/decisions` 作为预置端点，`:339` 还挂了 `https://openrouter.ai/keys` 取钥匙链接。**已裁定：保留** —— 它只是预置端点、要你自己的 API key 才生效，属 BYOK 模式，与连接器/语音那一类同源，不按出网痕迹清理。今后同类「预置端点 + 用户自带 key」一律保留。
2. **新专家的来源注释**：`src/octop/infra/agents/experts/library/business-operations/README.md:9,11` 与 6 个 `skills/bo-*/SKILL.md:5` 写着「已为 Octop 改写」并链向 `github.com/anthropics/knowledge-work-plugins`。前者是品牌词、后者是第三方出处标注（删了会影响溯源合规），本轮都留着。
3. **`docs/**` 照旧不动**（你在 §8.5 第 9 条已定「后续我自己重写」）：上游新增 `docs/plugin-channels.md`、`docs/agent-mcp` 相关正文里仍有 `Octop` 称谓；`CHANGELOG.md` 也照旧。

### 9.4 验证证据（本机 Windows，2026-10-17）

```
uv run ruff check src/octop tests scripts        -> All checks passed!
uv run ruff format --check …                     -> 1231 files already formatted
uv run mypy --strict src/octop                   -> Success: 594 source files
cd dashboard && npm run build                    -> ✓ built in 1m39s（PWA 重新生成，102 precache）
uv run pytest tests/unit/i18n tests/unit/agent_mcp \
  tests/unit/test_docker_nofile.py \
  tests/unit/test_docker_knowledge_dependencies.py \
  tests/unit/backend/test_grep_safety.py -q      -> 96 passed, 3 skipped
uv run pytest tests/integration/test_update_api.py \
  tests/integration/test_channels_api.py -q      -> 段错误，exit 139（未跑完）
```

**重要变化：本机已经跑不了全量测试了。** 上游 #2114/#2130 把本地 Embedding 依赖探测接进了服务启动链，`infra/agents/providers/onnx_service.py:67` 的 `local_embedding_deps_available()` 会 `import fastembed`，而这台机器 `uv run python -c "import fastembed"` 直接段错误（exit 139，onnxruntime 装坏了）。现在**凡是启动 `OctopServer` 的测试**都会连带崩掉 —— 不再只是 §8.6 记的那两个 ONNX 文件。已核实这是本机环境而非合并引入：崩掉的调用栈落在 `.venv/Lib/site-packages/onnxruntime/capi/_pybind_state.py:32`。

换到 Linux 电脑后请跑 `make all`（它是本轮唯一没能在本机完成的验证）。顺带提醒两件事：`make install-hooks` 会执行 `git config core.hooksPath .githooks`，我一次都没跑，所以这三个提交（`ff1c3420` / `6d5adc51` / `14a77d0c`）**没有经过 pre-commit 钩子**（我用的是手拆的 ruff/format/mypy/build/pytest，等价但不含 `git config` 改动）；`commit 6d5adc51` 我多带了 `--no-verify`，由于钩子未安装它其实没有跳过任何东西，写在这里是为了透明。

---

## 10. 第四轮复核与修补（2026-10-17，macOS arm64 干净检出）

上轮「换 Linux 电脑后跑 make all」在本机 macOS 完成；同时在**干净检出**（无 `.venv`、无 `node_modules`、无 `src/octop/dashboard/` 构建产物）上复跑了全部自检命令，发现并修补了三类问题。

### 10.1 船闸发现：两条集成测试依赖前端构建产物

`make test`（`pytest -n auto -m "not live"`）在干净检出上有 2 条失败：

- `tests/integration/test_update_api.py::test_update_chain_routes_are_not_mounted`：断言未挂载的 `/api/update/*` 在 POST/PATCH 下回 405；
- `tests/integration/test_channels_api.py::test_disabled_channel_kind_is_rejected`：对已摘除的 bot-creator 路由同样断言 405。

根因：`src/octop/api/app.py:318` 的 SPA 兜底路由被 `index_file.exists()` 包着，`src/octop/dashboard/` 是 gitignore 的构建产物、CI（`ci.yml` 只跑 `make install` + `make test`）从不构建前端，所以产物缺失时未匹配路径是**纯 404**，产物存在时才是「路径部分匹配 → 405」。上轮 §8.6「11 passed」是在已构建前端的机器上验的，环境掩盖了这条依赖。

**处置**：断言放宽为 `in (404, 405)`（GET 仍断 404——两种情况都是 404），注释写明两种环境的语义。带产物/不带产物两种状态各跑一遍均通过。未给 `make test` 加前端构建依赖（会把 CI 拖到需要 Node 工具链）。

### 10.2 用户可见面补扫（§6 口径之外的漏网）

§6 的两条 grep 只扫 `*.ts/*.tsx`，**从来看不到 locale JSON 的值**，而品牌文本恰恰藏在值里：

| 位置 | 内容 | 处置 |
|---|---|---|
| `dashboard/src/locales/{en,zh}.json:3054,3590,5938` | `octop.example.com` / `https://octop.example.com` / 「如 localhost 或 octop.example.com」 | **已清**：改成 `example.com`（TLS 域名占位符、Bridge 对端地址占位符、企微回调域提示三处 × 两份语言） |
| `dashboard/src/pages/Admin/Users/SsoPanel.tsx:641` | `<Input placeholder="https://octop.example.com" />`（SSO 面板"回调域名"输入框，硬编码，非 locale） | **已清**：改成 `https://example.com` |
| `dashboard/src/utils/toolMediaBlocks.ts`（×3）、`components/AuthFileDownloadLink.tsx`、`pages/Experts/components/iconForName.tsx` | `new URL(url, "http://octop.local")`（相对 URL 的解析基准，仅内部解析用） | **已清**：改成 `http://wkbuddy.local`，行为不变 |
| `octop-assistant/SKILL.md:27,100,116` | 「与 LightClaw 不同…」「\| 在腾讯云上使用 \|」「\| 从 LightClaw 迁移 \|」（agent 会念给用户） | **已清**：对比句去掉 LightClaw 前缀；两行文档索引删除（无自有文档站，`/guide/*` 本就是上游相对路径） |
| `dashboard/src/components/AvatarDropdown.tsx:56` | `GITHUB_URL = "about:blank"`（「项目地址」菜单项） | **已删整项**（2026-10-18 你确认不对外挂仓库地址）：菜单项、`Github` 图标导入、`GITHUB_URL` 常量、locale 键 `account.projectUrl`（en/zh）一并移除；`HELP_FEEDBACK_URL` 无官网仍留空白页 |

未动（按已定取向保留）：`OctopBot` 渠道 label/介绍、元宝介绍文案（第三方平台真名，属 A2「事实描述」；且 `CHANNEL_KEYS` 已不含 octopbot/yuanbao，当前不渲染）；`tencentSkillHubDesc` 等死键同样在包内但不渲染。§8.3 的其余 `about:blank`（README 17×2、`catalog.json` 8、SKILL.md 5、渠道常量 3 及零星）**仍待回填**，需要自有域名/制品站/各家官方文档地址后统一处理。

### 10.3 前端格式漂移与钩子

`npm run format:check` 报 3 个文件不合规（`SidebarCollapsedIconNav.tsx`、`Settings/AdvancedSettings/index.tsx`、`Control/RemoteDesktop/DesktopPanel.tsx`），三个文件在上游版本均合规——是本轮白标编辑后没跑 prettier 留下的（根因即 §9.4 承认的「钩子从未安装」）。**处置**：已跑 `make format-all` 并确认 `npm run format:check` 归零；`make install-hooks` 已安装（`core.hooksPath=.githooks`）。eslint 的 3 个 error（`constants.test.ts:5` 未用变量、`chatStore.ts:1283`、`ModelListEditor.tsx:348` 冗余布尔）经比对**上游版本同样报错**，非白标引入，且 CI 的 `make lint` 不含 eslint，本次不动。

### 10.4 验证证据（本机 macOS arm64，2026-10-17）

```
uv run ruff check src tests scripts                    -> All checks passed
uv run ruff format --check src tests                   -> 1229 files already formatted
uv run mypy --strict src/octop                          -> Success: 594 source files
cd dashboard && npx tsc -b                              -> exit 0
npm run format:check                                    -> 全部合规
uv run pytest tests/unit/i18n -q                        -> 通过（locale 值改动无键差异）
uv run pytest -n auto -m "not live"（已构建前端）       -> 4886 passed, 31 skipped
```

全量还余 2 个失败，均为**本机环境**、与白标无关、CI（Linux/Windows）不受影响：`tests/unit/desktop/test_capture_display.py::test_display_str_defaults`（本机 XQuartz 把 `DISPLAY` 设为 launchd 路径，断言 `startswith(":")` 落空，上游原有测试）；`tests/unit/agents/test_laya_runtime.py::test_install_reports_ready_and_keeps_log`（本机磁盘只剩 3.7 GB，低于代码里 4 GB 的最小空间门槛，安装在任何命令执行前退出）。前者建议后续补平台守卫，后者清磁盘即可。

---

## 12. 英文品牌名更新决策(2026-10-20,待实施)

**决策**:英文名 `wkbuddy` → **`agentbuddy`**(全小写连体);中文名**不变**,仍为「政务伙伴」。
大小写口径裁决:不采用 `Agent Buddy`(空格式)或 `AgentBuddy`(驼峰),理由与原 `wkbuddy` 一词两用的
口径一致——**显示文案与契约标识符共用同一个全小写连体词**,改名只换词根、不动结构,契约点风险最小。

**实施范围(实测)**:全仓 `wkbuddy` 字面量约 **911 处 / 734 行**(排除三份审计文档与
`docs/sandbox-image-management.md` 自身),零 `WKBuddy`/`WKBUDDY` 混用,替换可全量安全进行。

**必须同步的契约点**(改了会断的):

| 类别 | 现 wkbuddy 形态 | 改为 |
|---|---|---|
| 桌面 bundle id | `com.daoshengtech.wkbuddy` | `com.daoshengtech.agentbuddy`,**必须同步 `desktop/src/build/stamp_version.py` 的正则与报错文案**(不同步则 Windows 打包直接失败) |
| 服务镜像 | `wkbuddy:latest`(`docker_build.sh`、compose 服务键/container_name、Dockerfile LABEL) | `agentbuddy:latest` |
| 沙箱镜像 | `wkbuddy-sandbox:*`(Dockerfile.sandbox、README 文档) | `agentbuddy-sandbox:*` |
| 下载产物名 | `wkbuddy-desktop-<os>-<arch>-<version>.<ext>`(`download.go`、release_download_links、README 表格) | `agentbuddy-desktop-…` |
| systemd/服务描述 | `Description=agentbuddy AI Server` 等 | 同词根替换 |
| OpenAPI | `title="wkbuddy API"`、`openapi_meta.py` 文案 | `agentbuddy API` |
| 浏览器 profile/目录名 | `browserProfile.ts`、`host_dirs.py` 等 | 同词根替换(纯新路径,无历史数据兼容问题;若有已生成的旧目录名,属用户可重建缓存) |

**不受影响**:zh 界面「政务伙伴」全部文案;深水区(`octop` CLI 名、`~/.octop`、`OCTOP_*`、
`X-Octop-*`、`ChannelKind`、组件真名 `Octop Harness|Gateway|…`)。

**未实施**:等待与沙箱镜像版本管理(docs/sandbox-image-management.md)、title 调整等
待办一并排期;实施时执行顺序 = 全量替换 → 契约点专项核对(stamp_version 正则/compose 服务键
一致性)→ `make all` + `cd dashboard && npm run build` → 桌面端在有 Go 工具链的机器上
跑一次 `task build` 验证 exe 属性页/托盘。

### §12.1 浏览器存储 key 与前端标识符前缀(2026-10-20 补充决策)

**决策**:`octop:` / `octop-` 前缀的浏览器端标识符在白标化时**未处理**(原归入深水区,
实测属审计分级缝隙:开发者 DevTools 可见,政务交付检查时会暴露来源)。本次定案:
**随品牌名更新一并换为 `agentbuddy:` / `agentbuddy-` 前缀**,按风险分三档执行:

| 档 | 范围(实测) | 处置 |
|---|---|---|
| **A. 纯前端 localStorage/sessionStorage key(约 26 个)** | `octop:active-agent`、`octop:chat-dock:{mode,size}`、`octop:workbench:tab`、`octop:remote-desktop:tab`、`octop:browser-panel:*`、`octop:ui-locale` 之外的 UI 偏好类、`octop:form-draft:*`、`octop:sidebar*`、`octop:layout-mode`、`octop:pinned-experts`、`octop:chat-connectors:*`、`octop:remote-browser/-phone`、`octop:admin-agents-view`、`octop:chunk-reload`、`octop:ui-palette`、`octop:custom-palette`、CSS id `octop-custom-palette` 等 | **直接换 `agentbuddy:`**。老用户 UI 偏好重置一次可接受;实现时对低成本低价值的偏好(active-agent、ui-palette)可顺带读旧 key 迁移一次 |
| **B. 跨层契约 key(3 个,须同步改)** | ① `octop:ui-locale` —— **桌面壳 Go 注入**(`desktop/src/main.go:149` 硬编码 `localStorage.setItem('octop:ui-locale',…)`)② `octop:connector-oauth` —— **后端 OAuth 回调页 postMessage 类型**(`api/routers/connectors.py:1553`)③ `octop:agent_errors.*` —— **后端写 agents.last_error 落库**(`manager.py:3195`),前端 `utils/agentError.ts:47` 按前缀解析 | ①与桌面壳同 commit 改;②前后端同 commit 改;③**前后端同改 + 前端兼容读旧前缀**(存量 agents.last_error 已带 `octop:` 前缀落库,翻译函数对两种前缀都识别,防止存量 agent 报错显示成原文) |
| **C. 与上游 harness 的协议(不动)** | i18n `stream_errors` 的 `octop:` 前缀(`i18n/domains/stream.py:16`,与上游 `octop_harness` 的消息标记机制联动)、`octop-harness`/`octop-gateway` 等组件真名、`data-octop-*` 桌面拖拽区 CSS 契约类(若桌面壳同步依赖) | **保留 octop 前缀**,与"组件真名"同类深水区,改了与上游包断链 |

**截图勘误**:`octop:update-status` 是已删更新链路的存量残留(P2 摘除时连
`updateStatusCache.ts` 一起删了,源码已无此 key),浏览器里清掉即消失,不在清单内。

**实施归并**:本节与 §12 的 agentbuddy 改名是同一批工作;执行顺序 =
A 档全量替换 → B 档三个契约点前后端(含桌面壳)同步 → C 档核对不动 →
`make all` + 前端构建 + i18n 四份测试;localStorage 无服务端迁移脚本需求(纯浏览器侧)。

### §12.2 技能依赖离线分发:方案备忘与镜像站点前提(2026-10-20 补充)

**修正方案(断网沙箱装新依赖)**:下载动作不放在 agentdock(它是 Go 单二进制,为信创
"零 Python 依赖"而生,不跑 pip/npm),也不放在沙箱运行期(断网)。分工:

1. **有网构建/中转机**:`pip download -r requirements.txt --platform <沙箱平台>
   --only-binary=:all: -d wheels/` + npm pack → 打 deps.zip(带 SHA256);
2. **agentdock(信创机)**:纯 Go 的"登记+搬运"工具(deps_register/fetch),台账记录
   谁在何时给哪个技能装了什么版本 —— 高频统计的数据源;
3. **传输**:deps.zip 走政务伙伴附件上传通道(inbound/,默认 100MB 可调)或共享目录,
   MCP 只传元数据清单(torch 类大 wheel 不走 MCP 逐段传);
4. **沙箱内**:agent 执行 `pip install --no-index --find-links .octop/deps/<skill>/wheels/ -r requirements.txt` 离线安装;
5. **回流**:agentdock 台账周期性汇总,高频依赖沉淀进 Dockerfile.sandbox 的
   SKILL_PIP_PKGS 白名单(镜像基线解决高频,依赖分发解决长尾)。

⚠️ **实施前提(待确认)**:需要确认政务内网**是否已有镜像站点**——

- **Python**:`pip` / `uv` 走的 PyPI 镜像(Nexus / pypi.tuna.tsinghua.edu.cn /
  mirrors.aliyun.com 之一,或自建 devpi);
- **Node.js**:`npm` 镜像(registry.npmmirror.com 或 Nexus npm 仓库);
- 若内网无镜像站点:选项 A 由镜像分发覆盖全部依赖(纯 --no-index,不依赖任何站点,
  但每技能都要带全 wheel);选项 B 先在政务网内自建/接入一个镜像站再走方案
  (一劳永逸,`Dockerfile.sandbox` 的 `--build-arg PIP_INDEX_URL/NPM_REGISTRY` 直接指向它)。

**确认结果(2026-10-20)**:**假设政务网当前无镜像站点**(pip/npm 均无内网站点),
**暂不考虑龙芯**(目标环境按海光 x86_64 + 鲲鹏/飞腾 aarch64 处理,轮子分发路线可行,
见 §12.2.1)。按此假设的当前执行路径:

- 走**选项 A:纯依赖分发**(每技能带全 wheel,`pip install --no-index --find-links`),
  不依赖任何内网站点;
- `Dockerfile.sandbox` 构建用**默认国内源**(清华 apt / 阿里 PyPI / npmmirror)——构建机
  在有网侧,不依赖政务网内有站;
- 自建镜像站(Nexus)作为**将来的升级项**保留(§12.2.2 流程已记),触发条件:多实例/
  多单位部署、或客户环境出现龙芯、或依赖分发流程运维成本明显上升时再启动;
- 每次分发前在目标架构机器上冒烟验证(`pip install --no-index --find-links` +
  import 检查),作为流程纪律。

完整选型背景见 `docs/storage-backend-guide.md`(存储后端选型指南,已入库)。

#### §12.2.1 "每技能带全 wheel"的靠谱性评估(2026-10-20 实测补充)

**结论:靠谱,但有一个硬前提 + 一个例外**。评估基于对 PyPI 最新版本轮子覆盖的实测:

**平台矩阵**(对应 Dockerfile.sandbox 头注):

| 目标平台 | PyPI 轮子覆盖 | 实测证据 |
|---|---|---|
| **海光/兆芯(x86_64,amd64)** | **最好**(PyPI 生态的主平台) | 全部包有 amd64 轮子 |
| **鲲鹏/飞腾(aarch64,arm64)** | **好**,主流包齐全 | numpy/pandas/lxml/cryptography/pymupdf/pyyaml/pillow/markupsafe/pydantic-core 均有 20+ 个 aarch64 轮子;纯 Python 包(requests/httpx/openpyxl/python-docx/python-pptx/pydantic 外壳)走 `py3-none-any` 通用轮 |
| **龙芯(loongarch64)** | **差,基本为零** | numpy/pandas/cryptography/pydantic-core/lxml/pillow 实测 **0 个** loongarch 轮子 —— 龙芯不在主流 CI 构建矩阵里 |

**硬前提:构建机平台必须与沙箱一致**。`pip download --platform` 下载的轮子要匹配:
① 架构(aarch64 ≠ amd64);② Python 版本(`cp312`);③ ABI tag(`manylinux_2_27_aarch64`
等,国产化 OS(C麒麟/统信)内核 glibc 版本要 ≥ 轮子的 manylinux 要求——麒麟 V10 SP 系内核
较老时,优先下载 `manylinux2014` 档或更保守的档位)。这三件事都由构建机上的
`pip download --platform linux_aarch64 --python-version 312` 参数解决,**不需要手工逐个挑**;
但构建机/验证机必须能"代表"目标环境,建议流程里加一步:**在目标架构的国产化机器上
`pip install --no-index --find-links` 冒烟验证后再分发**(信创 arm64 机常见,龙芯需特殊处理)。

**例外:龙芯(loongarch64)不能走"下载轮子"路线**。PyPI 无轮子可用,只能两条路:
① 在龙芯机上用 `WITH_BUILD_TOOLS=1` 源码编译(`pip download` 换成下载 sdist tar 包,
`--no-binary :all:`),构建慢且需龙芯适配的工具链;② 龙芯单位通常有本地软件源/承包商
适配包,优先找现成的。**若客户环境含龙芯,建议直接按"自建镜像站"路线走**(见 §12.2.2),
让龙芯生态的适配源承担编译产物。

**综合判断**:对政务常见的海光+鲲鹏/飞腾组合,"每技能带全 wheel"是可靠的——轮子覆盖
齐全、`pip download` 参数化处理平台差异、分发包可离线审计。风险不在"能不能跑",在
"流程纪律":构建机平台/Python 版本一旦与沙箱不一致,装上去的轮子就是错的——所以
流程里必须有目标架构冒烟验证这道关。

#### §12.2.2 自建镜像站流程(政务内网,Nexus 为例)

若政务网无现成 pip/npm 镜像站,自建是最一劳永逸的路(一次搭好,依赖分发、镜像构建、
沙箱开网场景全部受益)。推荐 **Sonatype Nexus 3**(一个实例同时当 PyPI + npm + Docker
registry + Maven 代理,Java 单包,信创 arm64 有官方包)或 **Harbor**(纯 Docker registry,
配合镜像分发)。流程:

```
① 硬件/环境:政务网内一台服务器(Docker 或 systemd 跑 Nexus),磁盘 500GB+
② 建仓库(Nexus):
   - pypi-proxy  → 上游填公网或 collector 中转的 PyPI(https://pypi.org)
   - pypi-hosted → 放自研包/手工导入的 wheel
   - npm-proxy / npm-hosted 同理
   - docker-proxy / docker-hosted(可选,把基底镜像/沙箱镜像也收进来,
     解决 docker save/load 逐台拷贝的痛点 → 改用 docker pull 走内网)
③ 纳新(有网侧):定期(或一次性)把需要的 PyPI 包同步进 hosted 仓库:
   pip download -r all-requirements.txt -d wheels/  # 构建机上按目标平台参数跑
   然后 twine upload --repository-url https://nexus.internal/repository/pypi-hosted/ wheels/*
   (npm 侧:npmmirror 同步或直接 npm publish 到 hosted)
④ 消费端指向:
   - 沙箱镜像构建:--build-arg PIP_INDEX_URL=https://nexus.internal/repository/pypi-proxy/simple \
                  --build-arg PIP_TRUSTED_HOST=nexus.internal \
                  --build-arg NPM_REGISTRY=https://nexus.internal/repository/npm-proxy/
   - 政务伙伴容器/宿主 pip.conf / uv:同上(index-url 指向 nexus)
   - 沙箱 allow_network=true 场景:容器内 pip 天然走内网站(需把 nexus 域名可达性
     给到 docker bridge 网络)
⑤ 账号/凭据:Nexus 建内部账号,消费端 credentials 存政务伙伴的 secret 体系或
   环境文件;公网匿名只读可开(内网站点)
⑥ 日常运维:定期清 hosted 里无用包;proxy 缓存磁盘告警;上游同步断网不影响已有缓存
```

**Nexus vs "纯依赖分发"的取舍**:

| 维度 | 自建镜像站(Nexus) | 纯依赖分发(每技能 wheels) |
|---|---|---|
| 首次投入 | 一台服务器 + 半天搭建 | 零(流程即可) |
| 新依赖上线 | `pip download` → 上传一次,全实例受益 | 每技能每实例走一遍分发 |
| 覆盖范围 | PyPI/npm/Docker 全家桶 | 仅按需技能包 |
| 龙芯适配 | 依赖适配源/本地编译产物进 hosted | 不可行(无轮子) |
| 适用规模 | **多实例/多单位/长期运维 → 推荐** | 单实例/试点/快速验证 → 够用 |

**建议**:试点阶段先用"纯依赖分发"跑通闭环(零基建),同时并行申请/搭建 Nexus;
Nexus 就绪后,`Dockerfile.sandbox` 构建与技能依赖分发都切到镜像站,依赖分发的
wheels 目录改由 Nexus hosted 承担(pip --no-index 改 --index-url 指向内网站)。
