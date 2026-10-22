# OpenDesign

Octop 的内置 OpenDesign 连接器通过持续 stdio MCP 调用独立 OpenDesign 实例。
在连接器目录选择 OpenDesign，创建实例，默认自动检测本机安装与启动配置，然后测试连接。
目录卡片与聊天选择器共用官方 Logo，本地资源来源：[OpenDesign 官网图标](https://open-design.ai/favicon.svg)。

## 本机

1. 安装并启动 [OpenDesign](https://github.com/nexu-io/open-design)。
2. 在 OpenDesign 配置支持外部 MCP 的生成 Agent / 模型，并确认 MCP 能生成设计。
   本机 0.24.1 实测：界面的 MiniMax BYOK 配置不会自动传给 MCP `start_run`，会报提供商配置不完整。可选择已配置的本机 CLI runtime；原生 OpenCode 使用自己的模型配置，须确保 OpenDesign 能找到 `opencode-cli` 或 `opencode`，并在生成时选择 `OpenCode` 而非 `BYOK OpenCode`。如需保持该 BYOK 路径，需要上游增加安全配置引用支持。不要将模型 Key 填入 MCP 工具参数。
3. 在 Octop 创建 OpenDesign 连接器，等待自动检测显示正在运行，探测后保存。未安装时按下载指引安装；已安装但未运行时打开应用并重新检测。
4. 保存后在聊天中选择该连接器。描述需求，确认设计方向，等待预览链接。

自动检测发生在 **Octop 主机**，通过已安装应用公开的 Sidecar SDK 查询 daemon，再读取 canonical MCP install-info；不扫描进程或端口，也不猜测固定端口。检测不会启动应用或安装软件。当前检测标准安装目录（macOS 的系统 / 用户 Applications，以及 Windows / Linux 的常见桌面安装目录）；自定义目录、源码运行和不包含发现 SDK 的版本请使用高级导入。

“高级：导入 MCP 配置”用于远程 SSH、非标准安装位置等场景。从 Settings → MCP server 复制完整 JSON，导入后会整体替换启动配置，无需逐项填写。`command` 是启动程序而非安装目录；`args` 是启动参数 JSON 数组；`env` 是 MCP 进程的环境变量 JSON 对象，三者由自动检测或导入统一提供。环境变量加密保存，浏览器状态接口不返回启动凭证。编辑已有实例时保留已保存配置，也可改用本机自动检测。模型配置仍在 OpenDesign 管理，不需要在此输入 API Key。

## 一键安装（新增 CLI 源码版本）

安装包含本次改动的 Octop CLI 和 OpenDesign CLI，并启动 OpenDesign。先固定所属 Octop 用户：

```bash
octop config set-user alice
od mcp install octop
```

也可通过 `OCTOP_USER` 环境变量指定用户。未指定或固定用户时会明确失败，不自动选择管理员。
重复安装更新同一用户、同一名称的 OpenDesign 实例并保持实例 ID；其他用户和其他名称不受影响。
`--name` 指定实例显示名称。新实例不共享，也不会在所有对话中自动启用。

```bash
od mcp install octop --name design-studio
od mcp install octop --print --json
od mcp install octop --uninstall --name design-studio
```

`--print` / `--dry-run` 只预览，不执行 Octop CLI。预览中的 launchSpec 包含完整启动环境，勿把输出当作脱敏日志。
普通安装通过 stdin 传递启动配置，由 Octop 加密保存，不把环境值放在命令参数或成功结果中。
卸载只移除 Octop 内该用户的指定连接器，重复卸载可成功，不删除 OpenDesign 项目，也不取消上游任务。
若 Octop 服务已经运行，需重启以刷新配置 / 释放旧会话；CLI 不会自行重启服务。

底层命令也可单独使用：

```bash
octop --user alice --json connector install open-design --config-file launch.json
octop --user alice --json connector get open-design
octop --user alice --json connector remove open-design
```

`--config-file -` 从 stdin 读取原始 `command` / `args` / `env` JSON。
当前已安装的 OpenDesign 0.24.1 不含新增的 `octop` 安装目标。源码开发时在 OpenDesign 仓库使用 Node 24：

```bash
pnpm --filter @open-design/daemon build
node apps/daemon/dist/cli.js mcp install octop
```

确保 Octop CLI 在该进程的 PATH 中。Harness 依赖使用 PyPI 正式版本。
OpenDesign 集成需要包含 `ManagedMCPClient` 的 Harness 发布版（上游 PR #65）；截至 2026-10-22，
PyPI 最新的 1.0.4 尚不包含该接口，需待新版发布后再完成集成验收和合入。
不要直接修改 Octop 数据库，也不要把 macOS `/usr/bin/od` 当作 OpenDesign CLI。

## 服务器 / Docker

每用户使用独立实例。管理员可配置 SSH 固定启动命令，将 stdio 连接到远端实例中的
MCP 进程；SSH 必须非交互且不分配 TTY。远端桥在实例内部调用 daemon，
不要把 daemon 的 HTTP URL 当作 Streamable HTTP MCP URL。

浏览器预览需要可访问、带认证的 HTTPS 入口。返回的内部地址无法直接交付给外部用户时，
应修正 OpenDesign 部署。不要向 Octop 容器挂载 Docker socket。

持久化 daemon 存储遵循上游 [AGENTS.md 的数据目录约定](https://github.com/nexu-io/open-design/blob/main/AGENTS.md)。

## 受管 MCP 接入

catalog 用 `mcp_mode: managed` 和 `runtime_handler` 声明由宿主管理会话。
注册处理器提供凭据校验、连接配置和运行时工厂；通用连接器运行时只按声明分发选中的工具，
并向已注册的运行时广播启动、关闭和持久化重绑定，不判断产品名称。
OpenDesign 的会话隔离、需求状态和工具包装仍由自身处理器负责。
普通 stdio 连接器继续由 Harness 加载，gateway 连接器保留启动后注入的既有路径。

## 行为与限制

- 需求草稿依赖 MCP 会话；空闲连接释放、服务重启或草稿过期后，需要重新确认需求。
- 生成任务由 OpenDesign 保存。停止 Octop 回复不会取消生成；可继续询问进度。
- 同一对话、同一连接器只跟踪一个当前任务。修改设计沿用原项目。
- 测试连接执行只读检查，不自动生成设计；真实生成需人工验收。
- 首期交付预览链接与按需源码，不自动同步文件或主动推送完成通知。
- 本次实现需要包含 `ManagedMCPClient` 的 octop-harness；当前 PyPI 1.0.4 尚不包含，等待新版发布后合入。

## English

Create an OpenDesign connector and use local auto-detection on the Octop host.
Install and open the application if prompted. The public Sidecar SDK discovers
the running daemon and retrieves its canonical launch configuration; no fixed port
is guessed. For custom paths, source builds, unsupported discovery versions or SSH
connections, use Advanced to import the full Settings → MCP server JSON. Arguments
and environment are populated together and encrypted at rest, without separate
fields. Configure the generation runtime in OpenDesign itself.

Local and server deployments use the same stdio protocol. A server may use a
dedicated SSH key and fixed remote launcher. Each user should have an independent
instance, and preview links must be accessible through an authenticated HTTPS
entry point. Connection tests are read-only; they do not prove generation works.

OpenDesign 0.24.1 does not forward the UI BYOK provider configuration through
external MCP `start_run`. Use a configured CLI runtime, or add upstream support
for a stored provider reference resolved inside the daemon. Do not pass raw API keys
through MCP tool arguments.

The updated OpenDesign CLI supports `od mcp install octop`: it invokes the Octop
CLI and passes the canonical launch spec over stdin. Select an owner with
`octop config set-user` or `OCTOP_USER`. Reinstallation preserves the instance ID;
`--uninstall` removes only that owned connector. Restart an already running Octop
server to refresh its runtime configuration. `--print` is a non-writing preview
and includes the full launch environment. Older packaged OpenDesign versions
need the updated CLI before they recognize the `octop` target.

The Harness dependency uses PyPI releases. As of 2026-10-22, the latest release
1.0.4 does not include `ManagedMCPClient` from upstream PR #65. Keep this integration
as a draft until a published release includes the API and passes the standard checks.
