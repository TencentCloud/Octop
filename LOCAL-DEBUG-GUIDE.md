# 本地运行与调试指南（用于白标后的界面复查）

配套文档：[WHITELABEL.md](WHITELABEL.md)（改了什么见 §8.1，逐页复查清单见本文 §4）。

> **本机实测 vs 通用写法**：标 ✅ 的是在 `Windows 10.0.19045` + 本仓库当前工作树上真跑过的；
> 标 ⚠️ 的是命令来自 `Makefile`/`README`/`vite.config.ts` 但未在这台机器上执行。
> 三平台差异只在"装依赖 + make 是否可用 + 端口权限"，运行方式是同一套。

---

## 0. 先选对跑法（这一步决定你复查顺不顺手）

| 跑法 | 命令 | 改前端代码后 | 适合 |
|---|---|---|---|
| **A. 只跑后端**，浏览器开 `http://127.0.0.1:8088` | `uv run octop run` | **必须** `make build-frontend`（或 `cd dashboard && npm run build`）重新打包，且要清 Service Worker 缓存 | 只看后端行为、复现"用户实际看到的产物" |
| **B. Vite dev + 后端**（推荐做界面复查） | 两个终端：`uv run octop run` + `cd dashboard && npm run dev`，浏览器开 **`http://127.0.0.1:5173`** | 存盘即热更新，不用重构建 | 逐页看文案/菜单/顺序，边看边改 |

原理：`dashboard/vite.config.ts:315` 把 `/api` 代理到 `http://127.0.0.1:${VITE_API_PORT:-8088}`，dev server 监听 `0.0.0.0:${VITE_DEV_PORT:-5173}`。所以 **5173 是前端、8088 是后端**，别搞反。

入口对照：`pyproject.toml:98` → `octop = "octop.cli.main:cli"`；`Makefile:159` 的 `make dev` 就是上面 B 的两个进程合起来跑（Ctrl-C 一起停）。

**强烈建议用独立数据目录**，别碰你已经装好的那份：

```bash
export OCTOP_HOME="$HOME/.octop-review"   # Windows Git Bash 同样有效（OCTOP_HOME 是环境变量，不是路径常量）
```

---

## 1. Windows（本机，含真实坑）

**前提**：Git Bash（本仓库所有命令按 bash 写）、Python 3.12+、Node 18+、`uv`。
本机 `uv.exe` 在 `C:\Users\Administrator\python312\Scripts\uv.exe`；`node`/`npm` 在 `C:\nvm4w\nodejs\`。
**本机没有 `make`**，所以 `Makefile` 里每个 target 都得手动展开（下面已展开好）。

```bash
cd /c/Users/Administrator/Documents/code/Octop

# 1) 建/同步虚拟环境（等价 make install，Makefile:303）
uv sync                                  # ✅

# 2) 确认 CLI 起得来                                   # ✅ 已实测
uv run octop --version                   # → octop v1.0.2b8
uv run python -c "import octop.launch"   # → 无输出即成功（启动链路不碰 onnx）

# 3) 起后端（单独一个终端）
PYTHONUTF8=1 OCTOP_HOME="$HOME/.octop-review" uv run octop run
#    首次会进设置向导；也可以先 uv run octop init

# 4) 起前端（再开一个终端）                            # ⚠️ 未在本机跑过 npm run dev
cd /c/Users/Administrator/Documents/code/Octop/dashboard
npm ci          # 或 npm install（首次）
npm run dev     # → http://127.0.0.1:5173

# 5) 只做 A 跑法时的重构建
cd /c/Users/Administrator/Documents/code/Octop/dashboard && npm run build
```

**Windows 独有的四个坑（都实测过）**

1. **`PYTHONUTF8=1` 必须带**。默认 cp936 码页会让 pytest 多出 **23 个假失败**（`UnicodeDecodeError: 'gbk' … 0x92`、`result.stderr is None`），也会让打印 emoji 的脚本 `UnicodeEncodeError`（另加 `PYTHONIOENCODING=utf-8`）。
2. **`onnxruntime` 1.30.0 在这台机器 `import` 就段错误**（exit 139，CPU 有 AVX2，不是指令集问题）。所以：**知识库 / 本地 Embedding / 语音相关界面在本机复查不了**，换 Linux 或 macOS 看；跑测试要 `--ignore` 4 个文件（见 §5）。
3. **端口**：`netstat -ano | grep :8088` 查占用（本机 8088/5173 当前空闲 ✅）。被占就 `uv run octop run --port 8090`，同时前端 `VITE_API_PORT=8090 npm run dev`。
4. **PowerShell 里环境变量写法不同**：`$env:PYTHONUTF8="1"; $env:OCTOP_HOME="$HOME\.octop-review"; uv run octop run`。

---

## 2. Linux（Debian/Ubuntu 与 RHEL/麒麟类）

```bash
# 依赖
curl -LsSf https://astral.sh/uv/install.sh | sh          # uv
sudo apt update && sudo apt install -y python3.12 python3.12-venv nodejs npm make git   # Debian 系
# RHEL/麒麟/统信：sudo dnf install python3.12 nodejs npm make git   （或 yum；Node 版本不足时走 NodeSource/dnf module）

git clone <你的仓库> octop && cd octop
uv sync                       # 若系统 Python 不是 3.12：uv python install 3.12 && uv sync
export OCTOP_HOME="$HOME/.octop-review"

make dev                      # 前端 + 后端一起起（Makefile:159）
# 或分开：
make dev-backend              # = uv run octop run
make dev-frontend             # = cd dashboard && npm run dev
```

**要点**

- Linux 上 `make` 可用，直接用 `make install` / `make dev` / `make build-frontend` / `make all`，不用像 Windows 那样手拆。
- **onnx 正常**，所以知识库/语音页面要在 Linux 上复查（这是本机做不了的那一块）。
- 想在局域网别台机器上看 dev 页面：Vite 已 `host: 0.0.0.0`（`vite.config.ts:295`）。若把端口设成 80 走同源，`sudo` 或 `setcap cap_net_bind_service=...`，并且 **`VITE_HMR_CLIENT_PORT` 要跟 `VITE_DEV_PORT` 一起设**，否则 HMR 的 WebSocket 连不上（`vite.config.ts:300` 注释专门写了这条，Safari 在特权端口上还会犯病）。
- 内网/离线环境：`uv sync` 与 `npm ci` 都需要源。离线做法是把 wheel 与 `node_modules` 预置过去，别指望脚本联网。
- 生产形态（不是复查用）：`octop service start` 注册 systemd；`docker compose -f docker/docker-compose.yml up -d` 本地构建。
- 开了防火墙/SELinux 时，先确认 5173/8088 在 `firewall-cmd --list-ports` 或 `ufw status` 里放行，否则"页面打不开"会被误判成代码问题。

---

## 3. macOS

```bash
brew install uv python@3.12 node make
git clone <你的仓库> octop && cd octop
uv sync
export OCTOP_HOME="$HOME/.octop-review"
make dev                      # 或 make dev-backend / make dev-frontend
open http://127.0.0.1:5173
```

- 与 Linux 同一套命令，`make` 装得到即可；Apple Silicon 上 onnx 也正常。
- **Safari 做界面复查时**：Service Worker + HMR 是老组合，出问题就换 Chrome/Edge 或开无痕窗口，再用 DevTools → Network → Disable cache。
- 桌面壳（`desktop/`）需要 **Go + Wails v3 + Task**，Web 复查不需要。本轮改过的 `bundle id` / `CompanyName` 只有打了桌面包才看得见，`desktop/README.md` 有打包步骤；本机没这套工具链，验证不了。

---

## 4. 界面复查清单（对着本轮白标改动逐条点）

登录 `http://127.0.0.1:5173`（B 跑法）或 `:8088`（A 跑法）。**先看语言**：切到中文应显示「**政务伙伴**」，切到英文应显示「**wkbuddy**」（全小写）。

| # | 位置 | 期望 | 关联改动 |
|---|---|---|---|
| 1 | 浏览器标签标题 / 新标签图标 | `政务伙伴`（zh）/ `wkbuddy`（en） | `dashboard/index.html` |
| 2 | 安装为应用（PWA）后的名称 | `name`/`short_name` = 政务伙伴 | `dashboard/public/manifest.json`、`offline.html` |
| 3 | 登录页、首启口令横幅、初始化向导 | 全文无 `Octop`；向导能建管理员（密码 ≥8 位且含字母数字） | `src/octop/infra/setup/*`、i18n `zh/en` 4 份 |
| 4 | **头像下拉菜单** | 「GitHub」「帮助与反馈」链接是 `about:blank`；**没有"检查更新"入口、没有版本徽标** | P2/P3：`components/AvatarDropdown.tsx:56,57` |
| 5 | **设置 → 高级** | **不出现「更新」卡片**（原来在那儿） | P2：`UpdateConfig.tsx` 已删 |
| 6 | **设置 → 模型（预设卡片）** | 分组顺序按后端数组首现顺序；写 `~/.octop-review/provider_presets.json` 后重启，隐藏/改名/置顶立刻生效 | P4：`providers/presets.py:42`、`presetUtils.ts` |
| 7 | **渠道抽屉 → 新建渠道** | **列表里没有"元宝"**；其余渠道（企微/钉钉/飞书/QQ…）仍在 | P5：`channels/constants.ts`、`DISABLED_CHANNEL_KINDS` |
| 8 | 内置浏览器起始页 / 远程浏览器起始页 | 空白页（原为 `cloud.tencent.com`） | `BrowserWorkspace/index.tsx:42`、`RemoteBrowser/index.tsx:124` |
| 9 | 技能页 → SkillHub 标签 | 外链是 `about:blank`；技能列表与安装仍可用（这是功能，不该坏） | `SkillHubTab.tsx:381` |
| 10 | 环境/密钥页「需要 API 密钥？」 | 中性文案，不指腾讯云控制台 | `Settings/Environments/components/PageHeader.tsx:23` |
| 11 | 连接器卡片的使用说明链接 | 8 条 `doc_url`/`guide_url` 均为空白页 | `infra/connectors/catalog.json:46,96,131,138,237,281,413,420` |
| 12 | 专家画廊 | **没有** `cvm-ai-doctor`/`cvm-cluster-doctor`/`tencentcloud-api`；`wechat-ops`、`meituan-living-assistant`、4 个新专家在；`cowork-plugin-management` 卡片是新改写的那句文案 | P1-B / T1 |
| 13 | `/api/docs`（Scalar） | 标题 `wkbuddy API`，tag 描述无上游品牌，**看不到 update/upgrade 那组路由** | `api/app.py:110,309`、`openapi_meta.py`、P2 摘挂载 |
| 14 | 知识库、语音、本地 Embedding | Linux/macOS 上应正常；**本机 Windows 会段错误，属环境不属改动** | onnx extra |
| 15 | 任何"下载桌面端/便携版"入口 | 不应出现飞牛 `.fpk` 相关字样 | P1-A |

预设覆盖文件样例（写完重启后端生效；坏 JSON 会报 `CONFIG_FILE_CORRUPT`，缺文件＝无覆盖）：

```json
{ "hidden": ["opencode"], "order": ["kimi", "siliconflow"], "group_names": { "tencent": "TokenHub" } }
```

CLI 侧一起验（很快）：

```bash
uv run octop models presets --json | head -40      # 顺序/隐藏应与界面一致（同一条后端代码）
uv run octop update --help                          # 期望：没有这个命令（P2 从 cli/registry 摘掉）
curl -s -X POST "http://127.0.0.1:8088/api/update/check" -H "Authorization: Bearer <token>"  # 期望 405
```

⚠️ 最后那条 405 是**正确**结果：`api/app.py:315` 有个 `@app.get("/{full_path:path}")` SPA 兜底路由，未挂载的 API 路径 **GET → 404、非 GET → 405**。别把它当成"路由还在"。

---

## 5. 调试与验证命令

```bash
# 前端：类型 / 单测 / lint / 只跑某个文件
cd dashboard && ./node_modules/.bin/tsc -b                       # ✅ exit 0（别用 npx tsc，本机 npx 会命中同名包且假成功）
cd dashboard && ./node_modules/.bin/vitest run src/pages/Settings/Models/presetUtils.test.ts

# 后端：全量（本机必须带这 4 个 --ignore，否则 import onnx 段错误）
PYTHONUTF8=1 uv run pytest tests/unit -q --tb=line -p no:cacheprovider \
  --ignore=tests/unit/agents/test_onnx_service.py \
  --ignore=tests/unit/api/test_knowledge_bases.py \
  --ignore=tests/unit/knowledge/test_gate.py \
  --ignore=tests/unit/knowledge/test_params.py
#  基线：3869 passed / 158 skipped / 0 failed
PYTHONUTF8=1 uv run pytest tests/integration -q --tb=line -p no:cacheprovider \
  --ignore=tests/integration/test_onnx_models_api.py --ignore=tests/integration/test_knowledge_bases_api.py
#  基线：592 passed / 29 skipped（约 45 分钟；崩溃时 faulthandler 会把统计行挤掉，别当成"跑完没输出"）
PYTHONUTF8=1 uv run pytest tests/unit/i18n -q          # 改品牌文案后必查：中英键对齐 + 前后端 apiErrors 对齐

# 静态门（Linux/mac 用 make all；Windows 手拆）
uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy --strict src/octop
```

调试开关：`OCTOP_LOG_LEVEL=debug`；只起后端不起前端时用 `make build-frontend` 后直连 8088；想看接口契约直接开 `/api/docs`。

---

## 6. 症状 → 原因 → 处置

| 症状 | 原因 | 处置 |
|---|---|---|
| 页面还是旧品牌 / 旧菜单 | ① 你在 8088 上看的是打包产物，改源码没重构建；② **Service Worker 缓存** | 改 `dashboard/src` 后 `npm run build`；浏览器 DevTools → Application → Service Workers → **Unregister** + "Update on reload"，或直接用无痕窗口 |
| 5173 页面能开但接口全 404/超时 | 后端没起，或后端端口≠代理目标 | 起 `uv run octop run`；端口不一致时 `VITE_API_PORT=8090 npm run dev` |
| 改代码页面不热更新 | HMR 端口不对（改了 `VITE_DEV_PORT` 却没改 `VITE_HMR_CLIENT_PORT`） | 两者一起设，见 `vite.config.ts:300` 注释 |
| 后端启动即 `Segmentation fault (core dumped)` / exit 139 | 本机 onnxruntime | 换 Linux/macOS；本机走 §5 的 `--ignore` |
| pytest 一堆 `UnicodeDecodeError` / `stderr is None` | Windows cp936 | 加 `PYTHONUTF8=1`，那批文件即转绿 |
| 8088 被占 | 本机已有实例或服务 | `uv run octop run --port 8090`；Windows `netstat -ano \| grep :8088` |
| 登录不进去 / 忘了管理员密码 | 管理员凭据落在数据目录 | 看 `$OCTOP_HOME/octop-login.txt`（向导解锁口令）与 `credential.txt`；复查环境直接换新 `OCTOP_HOME` 最省事 |
| 未挂载的 API 返回 405 而不是 404 | SPA GET 兜底路由（正常行为） | 按 §4 末的说明判断，别改代码 |
| `make: command not found` | Windows 无 make | 按 §1 手拆；或 `choco install make` 后用 `make dev` |

---

## 7. 提交前必须注意的三件事（本仓库约定）

1. **`make install-hooks` 会执行 `git config core.hooksPath .githooks`**（`Makefile:295-297`）——它改你的 git 配置，**本轮我一次都没运行过**。你要是自己决定运行，请知情。
2. 运行了 hooks 之后，每次 `git commit` 会自动跑 `make all` + dashboard 打包，很慢；本仓库允许 `SKIP_PRECOMMIT=1 git commit …` 应急，但那不是"验证过了"。
3. 当前工作树是 **303 个 staged 删除 + 342 个改动 + 5 个未跟踪文件，未 commit、未 push**；`WHITELABEL.md`/`RESEARCH.md`/本文都还是未跟踪状态。
