# Octop 新一代跨平台桌面客户端架构方案 (Electron + Local Python Runtime)

本文档制定了 Octop 新一代跨平台桌面客户端（支持 Windows、macOS、Linux）的系统架构、进程模型、Python 独立运行时集成、生命周期守护与安全代理方案。

Octop Desktop 每次随壳启动自己的 Python 进程，监听回环地址上由操作系统分配的随机端口。版本更新只走壳，桌面托管的 Web 应用不能单独升级后端或前端。

---

## 1. 架构总览与设计目标

### 1.1 核心目标

1. **原生跨平台**：一套代码支持 **macOS（Apple Silicon 与 Intel）**、**Windows（x64 与 arm64）** 以及 **Linux（x64 与 arm64）**。
2. **零系统环境依赖**：内置独立的绿色 Python 运行环境（CPython Green Portable），用户无需预装 Python、uv、Git 或 C++ 编译器。
3. **快速冷启动体验**：引入 Early Window 与持久化主题背景机制，消除冷启动白屏，渐进式展示后端加载状态。
4. **伴随进程随壳启动**：每次启动都拉起自己的 Python 进程，只监听 `127.0.0.1` 上的随机端口；用健康检查确认本次进程就绪，退出时回收本次进程树。
5. **凭据隔离**：特权自定义协议（`octop://`）代理转发 API 请求，渲染层完全沙箱化运行，后端凭据由主进程统一注入。
6. **与壳一起更新**：壳、Dashboard 静态资源和绿色 Python 运行时是同一个签名发布。客户端设置作为新增项放进原有 Web 设置，不另开壳设置页。桌面进程拒绝 Web 设置里的应用内升级和 `octop update`。用户手动覆盖安装旧版时，壳在启动前发现更高的本地运行时版本，于是停止启动，并在错误提示里写出检测到的本地版本（见 [§2.3](#23-手动覆盖安装旧版)）。

### 1.2 系统进程拓扑图

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              Electron Main Process (Shell)                             │
│                                                                                        │
│  ┌────────────────────────┐  ┌─────────────────────────┐  ┌─────────────────────────┐  │
│  │ Single Instance Lock   │  │ Login Shell Env         │  │ Early Window & Tray     │  │
│  └────────────────────────┘  └─────────────────────────┘  └─────────────────────────┘  │
│  ┌────────────────────────┐  ┌─────────────────────────┐  ┌─────────────────────────┐  │
│  │ Sidecar Supervisor     │  │ Custom Protocol Proxy   │  │ Clean Teardown Manager  │  │
│  │ (Spawn / Health Check) │  │ (octop:// Forward)      │  │ (Process Tree Kill)     │  │
│  └────────────────────────┘  └─────────────────────────┘  └─────────────────────────┘  │
└───────────────────────────┬─────────────────────────────────┬──────────────────────────┘
                            │ Spawn / Ready / Health Check    │ WebContents / Preload
                            ▼                                 ▼
┌───────────────────────────────────────────┐     ┌──────────────────────────────────────┐
│        Python Sidecar (Octop Server)      │     │      Renderer Process (Dashboard)    │
│                                           │     │                                      │
│  - Runtime: $OCTOP_HOME/portable/runtime  │     │  - Origin: octop://app/              │
│  - Packages: $OCTOP_HOME/portable/packages│     │  - React 18 + TypeScript + Vite      │
│  - Entry: launch.py run                   │     │  - sandbox: true                     │
│  - Loopback API: http://127.0.0.1:<port>  │     │  - contextIsolation: true            │
│  - FastAPI + Uvicorn + SQLite DB          │     │  - nodeIntegration: false            │
│  - LangGraph Harness & Gateway Channels   │     │  - Preload Bridge: window.octopDesktop│
└───────────────────────────────────────────┘     └──────────────────────────────────────┘
```

`$OCTOP_HOME` 是数据根目录。进程环境或 macOS / Linux 登录 Shell 里已经设置了非空 `OCTOP_HOME` 时使用该路径；都没有时为 `~/.octop`（Windows 为 `%USERPROFILE%\.octop`）。绿色运行时、数据库、工作区和 `config.json` 都在这个根目录下。

---

## 2. Python 独立便携运行时的分发与解压机制

为了摆脱对宿主系统 Python 环境的依赖，并规避 asar 虚拟文件系统对原生二进制（C-Extensions、DLL、`.so`）的限制，采用**随包携带外置绿色压缩包 + 本地原子解压**方案。

### 2.1 产物打包与放置

- 由 CI / Makefile 打包生成独立的绿色便携包：`Octop-portable-<plat>-<version>.zip`。
- 打包 Electron 时，将对应平台的 zip 文件放置在安装目录的 `process.resourcesPath` 下（**asar 压缩包外部**）。
- 内部标准解压结构：

```text
Octop-<platform>/
  runtime/       # 独立的 CPython 解释器及核心动态库
  packages/      # 完整的 site-packages 依赖库
  launch.py      # 服务启动引导脚本
  start.sh/bat   # 独立启动脚本
```

### 2.2 本地运行目录与解压逻辑

1. **存放路径**：数据根目录按 [§3.2](#32-环境变量注入与登录-shell-环境) 解析 `OCTOP_HOME`。绿色运行时解压到 `<OCTOP_HOME>/portable/`，与数据库、工作区放在同一根目录，目录需要可读写、可执行，并在应用升级后保留。
2. **校验与版本感知**：
   - 安装包附带 `portable-version.json`，记录与本次 Desktop 发布绑定的版本和 SHA-256 哈希。
   - 主进程在启动时比对 `<OCTOP_HOME>/portable/version.json`。
   - 两个文件都使用 `version` 与 `sha256`。`version` 与本次 Desktop 发布的版本号相同。壳在解压并校验成功之后才写入本地文件；写入之前失败不会留下一个更高的版本。
   - 若版本一致且解释器二进制存在，跳过解压。
   - 若随包版本更高或文件损坏，在保留 `OCTOP_HOME` 内用户数据的前提下替换运行时目录。
   - 若本地 `version` 高于随包版本，按 [§2.3](#23-手动覆盖安装旧版) 判定为手动覆盖安装了旧版：保留现有运行时，停止启动，错误提示写出检测到的本地版本。
   - 替换只发生在壳自己的发布切换之后。Web 里的「检查更新」「立即升级」和 `octop update` 不能替换这个目录。
3. **平台适配**：
   - **macOS**：解压完成并校验后，移除隔离属性，避免 Gatekeeper 拦截 `.dylib`：

```bash
xattr -dr com.apple.quarantine "$OCTOP_HOME/portable/"
```

- **Linux**：赋予解释器执行权限：

```bash
chmod +x "$OCTOP_HOME/portable/runtime/bin/python3"
```

- **Windows**：确保 `pywin32_system32` 下的 `pywintypes*.dll` 正确位于 `runtime\` 根目录，由 `launch.py` 引导以正确处理 `.pth` 文件。

### 2.3 手动覆盖安装旧版

安装器替换的是安装目录里的壳。`<OCTOP_HOME>/portable/` 不在安装目录里，所以用旧安装包覆盖之后，本地 `version.json` 仍是上一次成功解压的版本。壳的更新只会安装更高版本（见 [§6.1](#61-更新检测)）。启动时只要本地版本更高，就按手动覆盖安装旧版处理。典型来源是 Windows 把旧的 NSIS 包装进现有目录、macOS 用旧的 `.app` 覆盖，或 Linux 安装旧的 deb、rpm、改用旧的 AppImage。比较针对已经解析好的那一个 `OCTOP_HOME`。

比较规则与 [§6.1](#61-更新检测) 相同：去掉 `version` 开头的 `v` 后再比。`1.0.3` 高于 `1.0.3b1`，`1.0.3b1` 高于 `1.0.2`。随包版本缺失，或两个版本无法按这个顺序比较时，把本次安装包视为损坏：展示错误并停止启动，同时保留现有 `portable/`。这种情况不记成「本地版本更高」。

| 来源 | 路径 | 含义 |
|---|---|---|
| 随包 | 安装目录中的 `portable-version.json` | 本次启动的 Desktop 版本 |
| 本地 | `<OCTOP_HOME>/portable/version.json` | 本机已经成功解压过的运行时版本 |

启动 Python 之前按下面的顺序判定。提示里的本地版本只取本地文件的 `version` 字段：

1. 本地文件不存在：尚未解压。按随包版本解压，然后继续启动。
2. 本地文件无法解析，或没有 `version`：文件损坏。保留用户数据，替换运行时，然后继续启动。
3. 本地版本等于随包版本，且解释器二进制存在：跳过解压，继续启动。版本相同但二进制缺失时，按损坏替换后再继续启动。
4. 本地版本低于随包版本：按随包版本替换运行时，然后继续启动。
5. 本地版本高于随包版本：判定为手动覆盖安装了旧版，并同时做到下面几件事。

第 5 种情况：

- 停止在拉起 Python 之前。不申请端口，不请求 `/api/health`。
- 保留 `<OCTOP_HOME>/portable/`，也保留数据库、工作区、密钥和 `config.json`。
- 在同一次 Early Window 里展示错误。错误正文写出检测到的本地版本，并写出本次随包版本。版本原文原样展示，去掉开头的 `v` 只用于比较。
- 窗口里不提供继续启动或降级替换。用户安装不低于该本地版本的 Desktop 之后再打开。

文案要让用户直接读到检测到的版本，例如：「检测到本机运行时版本为 1.0.3，当前安装的是 1.0.2。这是手动覆盖安装的旧版，已停止启动，并保留了现有运行时。」数字以两个文件里的 `version` 为准。

主进程把这两个版本写入诊断日志。窗口里的错误仍然要包含检测到的本地版本。

---

## 3. 伴随进程生命周期管理器（Sidecar Supervisor）

主进程内置 `SidecarSupervisor` 模块，负责随壳启动 Python 后台、取得随机端口、就绪监听与退出回收。

### 3.1 随壳启动与随机端口

每次桌面启动都拉起自己的 Python 进程。壳不读取 `config.json` 的监听地址来寻找后台，也不读取 `desktop-port`，也不接管终端里已经运行的 `octop run`。

1. **回环地址**：本次进程固定监听 `127.0.0.1`。通过 `OCTOP_BIND_HOST=127.0.0.1` 覆盖本次进程，不写回 `config.json`。
2. **随机端口**：壳向操作系统申请一个临时端口（绑定 `127.0.0.1:0` 后立即关闭），再把得到的端口通过 `OCTOP_PORT` 传给子进程。端口只存在于本次进程。
3. **不写配置**：启动命令是 `launch.py run`，不传 `--host` 或 `--port`。这两个 CLI 参数会写回 `config.json`；环境变量只覆盖本次进程。
4. **绑定失败立即报告**：子进程无法绑定该端口时，壳展示诊断信息并停止本次启动。壳不改连其他端口，也不改为附着到已有服务。
5. **退出所有权**：退出时只回收本次启动的进程树。

### 3.2 环境变量注入与登录 Shell 环境

拉起 Python 进程时，主进程设置以下关键环境变量：

```ts
const octopHome = resolveOctopHome(process.env.OCTOP_HOME, loginShellEnv.OCTOP_HOME)
const portableDir = path.join(octopHome, "portable")
const env = {
  ...process.env,
  OCTOP_HOME: octopHome,
  PYTHONNOUSERSITE: "1",
  OCTOP_GREEN_PACKAGES: path.join(portableDir, "packages"),
  OCTOP_BIND_HOST: "127.0.0.1",
  OCTOP_PORT: String(assignedPort),
  OCTOP_REQUIRE_SETUP_PASSWORD: "0",
}

// 不设置 PYTHONPATH，由 launch.py 处理运行时和 .pth。
delete env.PYTHONPATH
```

`resolveOctopHome` 只在取值缺失时补默认路径，已有非空值保持不变：

1. 本次进程继承的 `OCTOP_HOME`（去掉首尾空白后非空）。
2. macOS / Linux 登录 Shell 读到的 `OCTOP_HOME`。Windows 没有这一步，使用用户或系统环境里已经传入的值。
3. 都没有时为 `path.join(os.homedir(), ".octop")`。

开头的 `~` 按当前用户主目录展开，展开后的路径同时用于解压目录和子进程环境，使壳与 Python 的 `PathLayout.from_env()` 指向同一位置。壳不把这个值写回 `config.json`。

`assignedPort` 是本次向操作系统申请到的端口。`OCTOP_BIND_HOST` 与 `OCTOP_PORT` 都不写回 `config.json`。

`OCTOP_REQUIRE_SETUP_PASSWORD` 是产品决定，不是界面开关：关掉初始化向导的 CLI 密码，安装完直接进主界面。前端从 `/api/setup/status` 的 `wizard_password_required` 读到同一个事实，据此隐藏密码步骤和 Admin 步骤的密码框；Web 部署不改前端代码，只是这个值仍为 `true`。壳运行期间这个键归壳所有，`~/.octop/env` 和 `/api/envs` 都不能把登录墙改回来。

令牌有效期保持服务端默认值，壳不去改它 —— 无密码的账户配一个长令牌只是把死局往后推，同时放大令牌泄漏的后果。真正解决"JWT 过期后登不进去"的是设备凭据：

- 壳首次使用时生成 32 字节设备密钥，用 `safeStorage`（Keychain / DPAPI / libsecret）加密后写到 `<OCTOP_HOME>/desktop-device.json`，权限 `0600`。
- **没有可用钥匙串的机器（headless Linux、WSL、CI）不落盘**：密钥只留在内存里，随进程结束消失。明文落盘会跟着家目录的每一次备份/同步走，而在这种机器上"密钥就放在密文旁边"只是障眼法；代价是这类机器每次启动要重新登录一次。服务端 `desktop_device` 只有一行且是覆盖写，所以反复注册不会堆设备。
- v1 遗留的明文文件会在启动时收敛：有钥匙串就重新加密，没有就删掉（当次启动仍沿用它的密钥）。`read()` 不把明文当凭据，只有 `migrate()` 有权收编它。
- 渲染进程看不到这个密钥。第一次拿到认证成功的响应后，`dashboard/src/api/desktopSession.ts` 让壳把凭据绑定到当前登录用户（`POST /api/auth/device/register`，重复注册会替换旧令牌，重装或换机器即接管）。
- 遇到 `401` 时 `request()` 通过壳续期一次（`POST /api/auth/device/token`）再重试。这个交换接口豁免 JWT，但要求壳标志位、对端是回环地址、SHA-256 摘要常量时间比对，并按来源做失败节流；服务端只存摘要（`secrets` 表 `desktop_device`）。
- `POST /api/auth/device/revoke` 用于忘记凭据，壳暴露为 `session.revoke`，留给后续的"重置本机登录"入口。

于是桌面端跨重启、跨 JWT 过期都不需要密码；使用期间的滑动续期照旧轮换令牌。唯一保留的死局是刻意保留的：凭据被删除、或用户行被移除时回到普通登录页，那属于服务端操作（`octop user passwd`），壳自己无力恢复。

**登录 Shell 环境**：

在 macOS 和 Linux 下，用户从桌面启动应用时，GUI 进程通常不会继承登录 Shell 中的环境变量。主进程在启动前异步执行：

```bash
$SHELL -ilc "env -0"
```

解析并合并 `OCTOP_HOME`、PATH、代理和模型提供商环境变量。进程环境里已经有非空 `OCTOP_HOME` 时，登录 Shell 里的同名变量不覆盖它。探测失败时回退到 Electron 继承的环境；此时 `OCTOP_HOME` 仍按上面的默认路径补齐。选择解压目录之前必须先得到最终的 `OCTOP_HOME`，并先完成 [§2.3](#23-手动覆盖安装旧版) 的版本比较。比较允许解压、且进程环境里已经有 `OCTOP_HOME` 时，解压可以和其余登录 Shell 变量的合并并行；否则先等这次探测结束。本地版本更高时停止启动，不再解压。

### 3.3 就绪检测（Ready Signal）

- 主进程只轮询自己刚启动的进程：`http://127.0.0.1:<assigned-port>/api/health`。
- 收到符合 Octop 健康响应结构的成功响应后，判定本次后台就绪。
- 就绪判断不依赖 stdout 文本。
- 健康检查有总超时。超时或子进程提前退出时，展示可操作的诊断信息。

### 3.4 任务感知退出与全进程树清理

Python 后端可能衍生工作进程或正在执行 Agent 任务，因此关机流程需要区分优雅退出和强制回收：

1. **退出拦截与任务检查**：
   - 监听窗口 `close` 和应用 `before-quit`。
   - 同时监听 `SIGINT` / `SIGTERM` / `SIGHUP`：终端 Ctrl+C、`kill`、IDE 停止按钮送的是信号而不是 quit 事件，默认处理会直接终止外壳，`before-quit` 不执行，独立进程组里的 Python 就成了孤儿。信号处理走同一条清理链路（停 Python → `app.exit`），第二次信号立即退出、不再等宽限期。
   - 调用后端拥有的任务检查接口；若存在正在进行的 Agent、代码执行或排队任务，弹出原生确认框。
2. **优雅关闭**：
   - 先请求后端正常停机并等待有限宽限期。
   - 仅在宽限期后仍未退出时升级为操作系统信号。
3. **进程树回收**：
   - **POSIX（macOS / Linux）**：启动子进程时设置独立进程组；退出时向进程组发送 `SIGTERM`，超时后发送 `SIGKILL`。
   - **Windows**：通过 Job Object 或 `taskkill /pid <pid> /T /F` 回收完整进程树。
4. **不保留端口文件**：随机端口只留在本次进程的内存中，退出时没有 `desktop-port` 需要清理。

#### 当前实现边界：任务检查尚未落地

清理链路本身已经完成：`before-quit` 与 `SIGINT` / `SIGTERM` / `SIGHUP` 走同一条路径
（先关 WebSocket 中继 → 请求 Python 停机并等待宽限期 → `app.exit`），信号路径第二次触发
立即退出。文档第 1 条里的**任务检查与原生确认框还没做**，原因是后端目前没有「在跑任务」
的注册表，壳拿不到可信的输入：

- `api/routers/terminal.py` 有进程内的 `_sessions`（存活的 PTY 会话），是唯一能直接统计的项。
- 浏览器流、对话 / Agent run、cron 等都没有进程内「在跑」集合，也没有现成的查询接口；
  `/api/health` 的 `agents_running` 是**已加载的 agent 数**，不是正在执行的任务数。

等到后端提供一个只读任务查询接口，再补两处：

1. 后端新增只读接口，返回在跑任务的数量与类型（不要顺手把「已加载」当「在跑」）。
2. `before-quit` 里查询它——仅在用户主动退出时查询，信号路径没有 UI 不弹框——有任务则弹
   原生确认框，用户取消即中止退出。

在那之前的行为是：退出即停机，不询问。这不会留下孤儿进程（§3.1 的独立进程组与上面的
信号路径已覆盖），但会中断正在执行的任务。

---

## 4. 快速启动体验（Early Window + Splash）

针对 Python 初始化带来的等待时间，采用**早期窗口占位 + 前端平滑就地挂载**策略：

```text
[用户启动 App]
       │
       ▼
Electron main 入口：执行轻量初始化并获取单实例锁
       │
       ▼
立即创建并展示 BrowserWindow（Early Window）：
  - 固定白色背景与深色文字，不跟随主题（此时页面还没拿到主题设置）
  - 加载轻量加载骨架屏
       │
       ├─────────────────────────────────┐
       ▼                                 ▼
主进程随壳拉起 Python Sidecar       前端等待 octopDesktopBoot.ready()
  - 运行时校验（§2.3；本地版本更高则停在本窗口）
  - 申请随机端口并启动进程
  - 轮询本次进程的 /api/health
       │                                 │
       ▼                                 ▼
收到 /api/health 成功响应 ─────────► 通知渲染层就地激活 React SPA
```

### 启动阶段要求

- Electron 入口模块保持轻量，窗口创建前不加载不必要的重型模块。
- 窗口位置、尺寸与背景色在创建窗口前读取。
- 解压目录依赖已经解析的 `OCTOP_HOME`（见 [§3.2](#32-环境变量注入与登录-shell-环境)）。解压和拉起 Python 之前先完成 [§2.3](#23-手动覆盖安装旧版) 的版本比较。本地版本更高时，同一窗口展示错误并停止；错误包含检测到的本地版本。
- 比较允许解压时，解压可以与登录 Shell 其余环境变量的合并并行。Python 进程在比较通过后随壳启动。
- 其他启动失败也保留同一窗口展示恢复操作，不通过多次导航制造白屏。

---

## 5. 安全体系与自定义特权协议代理

### 5.1 为什么不直接加载 `http://127.0.0.1:<port>`？

- 本地 HTTP 地址可能被普通浏览器或其他本机页面访问。
- 渲染层不应知道内部真实监听端口或长期认证凭据。
- 原生文件、外部链接与系统能力需要由主进程统一执行安全校验。

### 5.2 `octop://` 特权协议设计

主进程注册 `protocol.handle("octop")`：

| 请求路径 | 处理机制 | 安全保障 |
|---|---|---|
| `octop://app/`、`/assets/*`、`*.js`、`*.css` | 从客户端打包的 Dashboard 静态目录读取 | 只允许受支持的方法，路径必须位于静态资源根目录内 |
| `octop://app/api/*` | 主进程透明反向代理至 `http://127.0.0.1:<assigned-port>/api/*` | 校验来源和窗口身份，过滤伪造的 Host、Origin、Cookie 与连接级标头 |
| 外部 `http://` / `https://` 链接 | 拦截导航并调用 `shell.openExternal` | 防止外部页面进入应用受信上下文 |

流式响应需要保留背压与取消语义；SSE 不应先完整缓冲到主进程内存。

#### WebSocket：为什么必须走中继

自定义协议承载不了 WebSocket 握手：Chromium 的 upgrade 不会进入 `protocol.handle`，
而 `webRequest.onBeforeRequest` 虽然能看见 `webSocket` 类型的请求，却会丢弃
`redirectURL`（已实测：请求被记录，上游从未收到握手）。因此 `octop://app` 页面不能
像 fetch 一样"照原样"用 `ws://octop/app/...`。

方案是主进程起一个只监听 `127.0.0.1` 的中继（`protocol/ws-relay.ts`），页面从
`wsEndpoint()` 拿到它的临时端口与本次启动才生成的路径段，然后拨
`ws://127.0.0.1:<中继端口>/<随机路径段>/api/<path>?<query>`：

- **凭据隔离**：页面只见到中继，永远不知道 Sidecar 端口；中继每次连接都重新读端口，
  更新重启 Sidecar 后页面无需换地址。
- **路径即授权**：路径段不对一律 403，且用常量时间比较；`Origin` 必须等于
  `octop://app`，本机别的页面即使猜到路径也接不进来。
- **不新增信任**：JWT 仍由页面自己放进 query（和浏览器模式一致），中继不注入、不存储
  任何凭据；请求行按 `/api/...` 重写后原样转发握手头，101 之后只做双向 pipe，
  保留背压与取消语义。
- **失败可见**：Sidecar 没起来是 503，连不上是 504，后端拒绝（401/404）原样透传，
  绝不会把一次失败伪装成已建立的隧道。
- 路径段放在路径里而不是 query 里，是为了让调用方还能照常拼自己的 query。

### 5.3 严格沙箱与类型化 Preload 桥接

BrowserWindow 强制启用：

```ts
webPreferences: {
  preload: path.join(__dirname, "../preload/index.cjs"),
  nodeIntegration: false,
  contextIsolation: true,
  sandbox: true,
  webSecurity: true,
}
```

Preload 仅暴露最小类型化桥梁 `window.octopDesktop`：

- `getPlatformInfo()`：获取脱敏的平台与架构信息。
- `openDirectoryPicker()` / `openFilePicker()`：调用主进程原生选择器。
- `onBackendReady(callback)`：接收后端服务就绪事件。
- `windowControls`：最小化、最大化与关闭窗口。
- `clientSettings`：供 Web 设置页读写新增的客户端项（开机启动、关闭行为、主题背景、是否只跟随稳定版）。不能写 `config.json`，也不能指定更新检测地址或安装包地址。
- `openUpdateConfirmation()`：只能打开主进程的更新确认。渲染进程不能指定包地址，也不能授权安装。
- `wsEndpoint()`：返回 WebSocket 中继的地址（§5.2）。同步返回，因为 URL 拼装发生在渲染路径里没法 await；没有中继时返回 `null`，页面就回退到"从自身 origin 推导"。

不暴露原始 `ipcRenderer`、任意文件系统访问、任意命令执行或可指定目标 URL 的代理接口。所有 IPC handler 都校验 sender frame、origin 和参数 schema。

---

## 6. 更新：与壳同一发布

桌面更新由壳检测、下载并安装。一次发布仍然是同一个签名单位：壳、打包进安装包的 Dashboard 静态资源，以及对应平台的绿色 Python 运行时。没有单独的 Python 或 Dashboard 更新清单，也不能只更新其中一层。

### 6.1 更新检测

主进程用固定地址检测更新，渲染进程不能改这个地址，也不能提交另一个安装包 URL。

- 请求：`GET https://octop.cloud/api/downloads`
- 时机：启动后，以及用户在设置里点击「检查更新」时。请求不经过 Python 后端。
- 成功响应使用 `data.client`。`data.pet` 是另一个产品，桌面壳不读。

`data.client` 有两个通道：

| 通道 | 字段 | 含义 |
|---|---|---|
| 稳定版 | `data.client.stable` | 正式发布。`tag` 形如 `v1.0.2` |
| 测试版 | `data.client.beta` | 预发布。`tag` 形如 `v1.0.3b1` |

每个通道包含 `tag`、`releasesUrl` 和 `assets`。安装包只从 `assets` 里取。`releasesUrl` 只用于打开对应的发布说明。每个 asset 有 `name`、`ext` 和 `url`，当前包放在 `https://download.octop.cloud/`。壳只接受该主机上的 `https` URL。

按当前系统选择 asset 键：

| 系统 | 架构 | `assets` 键 |
|---|---|---|
| macOS | arm64 | `mac_arm` |
| macOS | x64 | `mac_intel` |
| Windows | x64 | `win_x64` |
| Windows | arm64 | `win_arm` |

清单里没有对应键时，这次检测不为该平台提供更新。Linux 目前不在上述键里。

**是否只跟随稳定版**是壳保存的客户端设置，默认开启。

1. 开启时，候选只有 `data.client.stable`。
2. 关闭时，候选是稳定版和测试版。
3. 去掉不高于当前已安装版本的候选，再去掉没有当前平台安装包的候选。剩下的里面取版本最高的一个。
4. 比较前去掉 `tag` 开头的 `v`。顺序与版本号一致：`1.0.3` 高于 `1.0.3b1`，`1.0.3b1` 高于 `1.0.2`。

因此，用户开着「只跟随稳定版」时，不会因为存在更高的测试版而提示更新。用户正在使用比当前稳定版更高的测试版时，也不会被提示降回稳定版。

请求失败、`success` 不为 `true`，或所选通道缺失时，展示检测失败。不把当前版本显示成已是最新。

### 6.2 客户端设置加在 Web 设置里

桌面不另开壳设置页。客户端设置作为新增项放进 Dashboard 已有的 Web 设置。

- 原有页面保留：模型、用户、安全、存储、语言、环境变量、备份等继续由 Python 后端保存，请求仍走 `octop://app/api/*`。
- 新增项也画在这些 Web 页面里。主进程通过 `clientSettings` 读写，不写入 `config.json`。项包括开机启动、关闭窗口时退出还是留在托盘、早期窗口使用的主题背景、壳自己的更新检查，以及「只跟随稳定版」。浏览器里打开的服务器版没有这些项。

服务器版和 CLI 仍然可以使用 Web 设置里的「检查更新」「立即升级」，以及 `octop update`。桌面托管的这次 Python 进程不行。

壳启动该进程时设置 `OCTOP_DESKTOP_SHELL=1`。后端据此：

- Web 设置里不提供应用内升级，也不展示 `octop update`、pip、安装脚本等手动升级入口。其余 Web 设置保留。
- `octop update` 和 self-update API 直接拒绝，不修改 `OCTOP_GREEN_PACKAGES` 指向的 `packages/`。
- 前端不能下载、替换或切换 Python 运行时。

壳的更新确认由主进程打开。Web 设置里新增的客户端更新项只能请求打开这个确认，不能指定包地址，也不能授权安装。确认界面不把更新文档转发给 Python 进程。

### 6.3 安装顺序

用户在壳的确认框里同意安装之后，主进程下载 §6.1 选出的安装包。确认框不能改这个地址。随后：

1. 锁住 API 准入。新请求返回 `503`，已接纳的请求排空。
2. 按第 3.4 节要求 Python 进程干净退出：宽限期内退出、退出码为 0。
3. 把退出交给安装器。安装器在用户上次选定的安装目录里替换壳、前端资源和随包运行时，不改回默认盘符。
4. 新版本启动后，由壳按 [§2.2](#22-本地运行目录与解压逻辑) 比较版本。随包版本更高时才替换 `<OCTOP_HOME>/portable/`。本地版本更高时按 [§2.3](#23-手动覆盖安装旧版) 停止，保留现有运行时。`OCTOP_HOME` 里的数据库、工作区、密钥和 `config.json` 保留。

干净退出没有完成时，安装被拒绝。安装失败且 Python 进程已经停过时，壳重新拉起本次进程，并重新加载 `octop://app/`，因为新进程的端口和注入都可能变了。

隐藏窗口上完成的下载把「安装并重启」推迟到窗口再次显示。强制更新仍要求任务栏或 Dock 的注意。

---

## 7. 跨平台原生体验设计

| 平台 | 优化点 |
|---|---|
| **macOS** | 使用沉浸式标题栏；同步系统深浅色；正确处理 Dock 重开、应用签名、公证与运行时 quarantine。 |
| **Windows** | 使用隐藏标题栏与 `titleBarOverlay` 保留 Snap Layouts；NSIS 向导安装，可选安装目录和盘符；确保更新和卸载时不遗留 Python 进程。 |
| **Linux** | x64 与 arm64 都同时发布 AppImage、deb 和 rpm，默认安装包是 deb。兼容 Wayland / X11；为文件选择器和托盘能力提供环境检测与回退。 |

### 7.1 Windows 安装位置与盘符

Windows 安装包使用带目录页的 NSIS 向导，对应 electron-builder 的 `oneClick: false` 与 `allowToChangeInstallationDirectory: true`。向导提供标准目录页，用户可以修改完整安装路径，包括盘符，例如从默认的 `C:\Program Files\Octop` 改到 `D:\Apps\Octop`。浏览对话框列出当前可用的盘符。

- 默认目录仍是本机安装范围下的常规位置：每机器安装为 `$PROGRAMFILES64\Octop`，每用户安装为 `$LOCALAPPDATA\Programs\Octop`。
- 用户确认的路径写入安装器的 `$INSTDIR`。开始菜单、桌面快捷方式和卸载登记都指向这个目录。
- 目标目录所在的盘必须已经就绪，并且安装进程对它有写权限。需要提权时由安装器申请，不因为用户选了非系统盘而失败。
- 后续壳更新沿用这次写入的安装目录，不把程序装回默认盘。
- 卸载只删除选定目录中的程序文件和壳登记的快捷方式。`OCTOP_HOME`（未设置时为 `%USERPROFILE%\.octop`）里的数据库、工作区、密钥、`config.json` 和已解压的 `portable/` 保留。
- 更换安装盘不搬家用户数据。Python 运行时仍解压到 `<OCTOP_HOME>\portable\`，监听端口逻辑与安装位置无关。

---

## 8. 工程结构与模块规划

Electron 桌面端包位于 `desktop/src/`：

```text
Octop/
  desktop/
    src/                        # Electron 包根目录（pnpm 包，Node 24）
      package.json
      pnpm-workspace.yaml
      electron-builder.config.ts
      electron.vite.config.ts
      tsconfig.json
      mise.toml
      scripts/
        run-dev.sh
        make-dev-runtime.sh
      resources/                # 打包资源：图标、随包 portable
        icon.icns
        icon.ico
        icon.png
        portable/
      main/
        index.ts
        app-version.ts
        supervisor/
          random-port.ts
          process-tree.ts
          runtime-extractor.ts
          shell-env.ts
          sidecar.ts
          health.ts
          version.ts
          sha256.ts
        update/
          update-coordinator.ts
          download.ts
          installer.ts
        protocol/
          stream-proxy.ts
          static-handler.ts
          ws-relay.ts
        windows/
          main-window.ts
          early-window.ts
        storage/
          client-settings.ts
      preload/
        index.ts
      renderer/                 # 壳页：独立轻量 React 应用（不依赖 Dashboard）
        splash.html
        error.html
        src/
          mount.tsx
          splash.tsx
          error.tsx
          base.css
          splash.css
          error.css
          assets/octop-mark.svg
      shared/
        ipc-contract.ts
        shell-error.ts
        global.d.ts
```

壳页（`renderer/`）是独立的小 React 应用：只依赖 `react` / `react-dom`，不引入
Dashboard 的 antd 或任何共享组件，因为它必须能在 Sidecar 和 Dashboard 都还不存在时
就渲染出第一帧。JSX 交给 esbuild 的自动运行时（tsconfig 的 `"jsx": "react-jsx"`），
没有引入 `@vitejs/plugin-react`——两个静态页面用不上 Fast Refresh。

启动失败时，主进程把 `error.html` 装进同一个 Early Window，并把载荷以 base64url 编进
query（页面是 `sandbox: true`、无 preload、无 IPC，这是两者唯一的通道）。载荷拆成两层：
`message` 是给用户读的一句话，`detail` 是路径 / errno 这类技术尾巴，默认收在「技术详情」
折叠区里——不会再出现把 `ENOENT: ...` 直接糊在标题下面的页面。

> 实现状态：`octop-desktop.yml` 已配置各平台 green zip + 原生 Electron 安装包；
> 签名、公证以及六平台实际 CI 产物仍需在仓库发布前逐项验证。
>
> 更新链路现状：[§6.3](#63-安装顺序) 的「确认框 → 下载 → 校验 → Python 干净退出 →
> 交给安装器」已在主进程实现（`main/update/{download,installer}.ts`），确认框只能由
> `openUpdateConfirmation()` 打开，渲染进程无法传入包地址。清单 asset 不带校验和，
> 所以当前只校验「下载链路绑定 `download.octop.cloud` 的 https」。
> 尚未实现：[§3.4](#34-任务感知退出与全进程树清理) 第 1 步的「退出前任务检查确认框」
> （后端还没有对应的任务查询接口），以及真机安装包端到端验证。
>
> 窗口控制按钮现状：窗口是 `frame: false`，按钮由 Dashboard 自绘
> （`components/DesktopWindowControls`）——macOS 在左上角画三个交通灯，
> Windows / Linux 在右上角画三个 46px 标题栏按钮，位置符合各自平台常规。
> 网页侧通过 `--window-controls-inset-start` / `--window-controls-inset-end`
> 做单边留白：macOS 侧边栏顶部预留 32px 可拖动条带给交通灯，Windows 的标题行、
> 抽屉、dock 工具栏在右侧让位。因为没用原生 `titleBarOverlay`，
> [§7](#7-跨平台原生体验设计) 里 Windows 的 Snap Layouts 悬停区暂不可用。

---

## 9. 构建发布流水线（CI/CD）

通过 CI 矩阵构建各平台安装包：

1. **构建 Dashboard**：执行仓库已有前端构建流程，生成最新静态产物。
2. **构建或下载对应平台的 Python 绿色包**：
   - `Octop-portable-<platform>-<version>.zip`
   - 放置在 `desktop/resources/portable/`。
3. **Electron 打包**：
   - macOS：DMG 与 Zip，配置 Developer ID 签名和公证。
   - Windows：带目录页的 NSIS 安装包，允许选择安装位置和盘符，并配置 Authenticode 签名。
   - Linux：electron-builder 的 `linux.target` 固定为 `["AppImage", "deb", "rpm"]`。x64 与 arm64 各发布这三种包；默认安装包是 deb，AppImage 和 rpm 同时发布。 |
4. **发布前验证**：
   - 在干净用户目录执行首次启动。
   - 验证运行时解压、setup wizard、健康检查和正常退出。
   - 验证每次启动都拉起自己的进程，并只监听 `127.0.0.1` 上的随机端口。
   - 验证终端里已有的 `octop run` 仍独立运行，桌面端不附着到它。
   - 验证 `config.json` 的 `bind_host` 与 `port` 不被本次启动改写。
   - 验证安装升级后用户数据库、工作区、密钥和 `config.json` 不被覆盖。
   - 验证手动覆盖安装旧版：本地 `version` 高于随包版本时启动失败；错误提示包含检测到的本地版本和当前随包版本；不启动 Python，保留 `portable/` 与用户数据。本地版本更低时仍按随包版本替换并继续启动。本地文件不存在时按首次解压处理。
   - 验证客户端设置作为新增项出现在 Web 设置里，浏览器版不出现这些项；Web 里的应用内升级和 `octop update` 被拒绝，壳、前端和 Python 运行时保持同一发布版本。
   - 验证更新检测由主进程 `GET https://octop.cloud/api/downloads` 完成。「只跟随稳定版」默认开启，此时忽略更高的 `data.client.beta`；关闭后才在稳定版和测试版中选择更高且带有当前平台安装包的版本。已安装测试版高于当前稳定版时不降级。
   - 验证已设置的 `OCTOP_HOME` 被用作数据根目录和解压目录；未设置时才使用 `~/.octop`。macOS / Linux 上，登录 Shell 中的值在 GUI 进程没有该变量时生效，进程环境里已有的值保持不变。
   - 验证 Windows 安装向导可以把程序装到另一个盘符，升级仍落在该目录，卸载不删除 `OCTOP_HOME`（默认 `%USERPROFILE%\.octop`）。
   - 验证 Windows 和 POSIX 平台均无遗留进程树。

---

## 10. 演进路线与实施计划

### 阶段一：运行时解压与进程监管核心

- 实现绿色便携包校验与原子替换逻辑。版本比较与 [§6.1](#61-更新检测) 使用同一顺序。
- 本地 `version` 高于随包版本时停止启动。错误提示包含检测到的本地版本，并覆盖这条路径的测试。
- 完成随壳启动、随机端口分配，以及针对本次进程的 HTTP 健康检测。
- 实现跨平台进程树优雅退出与强制回收。
- 为随机端口、配置不被改写、启动超时和子进程提前退出建立测试。

### 阶段二：特权协议与主窗口桥接

- 实现 `octop://` 静态资源映射与 API 代理。
- 保持 SSE 流式传输与请求取消能力。
- 搭建最小 Preload 安全桥并接入 Dashboard。
- 验证外部导航、路径遍历、伪造 Origin 和未授权 IPC 均被拒绝。

### 阶段三：启动体验与原生细节

- 落地 Early Window，减少白屏和启动布局跳动。
- 完成窗口状态持久化、macOS 标题栏、Windows Snap Layouts 和 Linux 回退。
- 增加启动阶段埋点，测量窗口显示、服务就绪与首个可交互页面时间。

### 阶段四：跨平台构建、签名与壳更新

- 完善 Electron 构建配置和 CI 矩阵，使一次发布同时钉住壳、Dashboard 和绿色 Python 包。
- 更新检测使用 `GET https://octop.cloud/api/downloads`，并提供「只跟随稳定版」。同时完成 macOS 公证、Windows 签名和 Linux 安装包验证。
- 客户端设置加在原有 Web 设置里；桌面进程拒绝应用内升级。更新确认、准入锁和干净退出后再交给安装器。
- Windows 安装向导提供目录页，用户可选安装位置和盘符；升级沿用该目录。
- 对每个平台执行干净安装、壳升级、卸载与残留进程检查。Windows 额外覆盖非系统盘安装。

---

## 11. 关键决策摘要

1. Electron 只拥有桌面能力，Octop Python 服务继续拥有业务逻辑。
2. Python 运行时位于 asar 外，并复用现有绿色便携包契约。数据根目录尊重已设置的 `OCTOP_HOME`；未设置时为 `~/.octop`。运行时、数据库、工作区和 `config.json` 都在这个根目录下。
3. Desktop 每次随壳启动自己的 Python 进程，退出时只回收这次启动的进程树。
4. 本次进程监听 `127.0.0.1` 和操作系统分配的随机端口；地址通过环境变量覆盖，不写回 `config.json`。
5. 就绪信号来自 `/api/health`，不解析日志文本。
6. 渲染进程不知道后台凭据，不获得 Node.js 或原始 IPC 能力。
7. 正常退出优先，强制进程树回收仅作为超时兜底。
8. 桌面更新由壳检测：`GET https://octop.cloud/api/downloads`，用 `data.client.stable` 与 `data.client.beta` 区分稳定版和测试版。用户默认只跟随稳定版，可以关闭该选项以接收测试版。壳、Dashboard 和绿色 Python 运行时同一发布版本。客户端设置加在原有 Web 设置里，不另开壳设置页；桌面进程拒绝 Web 应用内更新。
9. Windows 安装使用带目录页的 NSIS 向导，用户可以选择安装位置和盘符。升级沿用该目录；用户数据仍在 `OCTOP_HOME`（未设置时为 `%USERPROFILE%\.octop`）。
10. 手动覆盖安装旧版时，用随包 `portable-version.json` 与 `<OCTOP_HOME>/portable/version.json` 的 `version` 比较。本地版本更高则停止启动，错误提示写出检测到的本地版本，并保留现有运行时与用户数据。
