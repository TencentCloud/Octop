# Discord 通道：本地验收与配置

支持私聊、服务器文字频道、已有线程、文本/图片/附件、正在输入提示、长回复自动分段。

## 1. 安装依赖并启动

Discord 适配器已随 `harness-gateway 0.9.9` 发布。Octop 要求 `harness-gateway>=0.9.9`，可直接使用发布包，无需克隆相邻网关仓库：

```sh
cd Octop
uv sync --locked --extra dev
uv run octop run
```

可在 `uv run octop run` 后追加原有启动参数。先停止占用同一服务端口的旧进程；不要同时启动两个使用同一 Bot Token 的实例。

仅在联调相邻 `harness-im-bridge` 源码时使用 `bash scripts/run-discord-local.sh`；该脚本会覆盖发布包为本地可编辑依赖。恢复发布包时重新运行 `uv sync --locked --extra dev`。

## 2. 填写位置

打开本地 Octop 网页，进入 **Agent → 通道 → 更多通道 → Discord**。

1. **Bot Token**：填写 Discord Developer Portal 的 Bot 页面生成的 Token，不需要 Public Key 或 Client Secret。
2. **允许所有可访问频道**：默认开启，无需填写频道 ID；机器人在所有有 Discord 访问权限的服务器文字频道和已有线程中可响应。关闭后，填写 **允许的频道 ID**，多个 ID 用逗号或换行分隔；留空则不接收服务器频道消息。已有线程继承父频道权限，也可单独填写线程 ID。旧配置缺少 `allow_all_channels` 时也默认开启；显式保存为 `false` 才限制到列表。
3. **允许私聊的用户 ID**：填写你的 Discord 用户 ID。私聊独立授权，空列表表示不接受任何私聊消息。
4. **HTTP Proxy / HTTP Proxy Auth**：网络需要代理时填写。认证格式为 `user:password`；代理应用到 Gateway、API 与附件下载。
5. 点击 **检查连接**，成功后 **保存**。连接检查验证机器人能够登录 Gateway，不证明某个频道具备发送权限；后者用下一节的真实消息验证。

在 Discord 用户设置开启开发者模式后，可右键频道/用户复制 ID。ID 必须保留完整数字，不是频道名，也不是 Application ID。

## 3. Discord 应用设置

在 Bot 页面开启 **Message Content Intent**。邀请机器人加入测试服务器，并给予 View Channels、Send Messages、Read Message History、Attach Files、Send Messages in Threads 权限。首版不需要 Server Members 或 Presence Intent。

服务器频道默认只在用户直接 `@机器人` 时启动 Agent；不把 `@everyone` 或角色提及当作直接触发。私聊允许列表中的用户无需 @。机器人与 webhook 消息被忽略。

## 4. 人工验收（约 10 分钟）

| 操作 | 预期 |
|---|---|
| 在允许频道发送 `@机器人 你好`，再发送一条不带 @ 的消息 | 前者回复，后者不单独触发 Agent |
| 在同一频道用两位用户提问，再去另一个允许频道/线程提问 | 同频道共享上下文，频道与线程分别隔离 |
| 用允许用户私聊，关闭允许所有频道后，再从未授权频道发消息 | 私聊有回复，未授权频道无回复 |
| 发图片/文件，要求生成长回复 | 附件进入现有媒体管线，长回复分段，代码块可读，无意外 @everyone |
| 停用/启用通道、重启服务，再次提问 | 正常恢复，没有重复回复；断线时重新获取通道状态可见重连提示 |

上传限制取决于 Discord 服务器和 Bot 权限；远程附件下载在适配器中限制为 25 MiB，超限/上传失败会走现有错误或附件降级处理。

暂不包含原生 Slash Command 注册、自动新建线程、语音房、编辑式流式回复。一个 Agent 建议先配置一个 Discord Bot；同一 Agent 多 Bot 共用同一频道的会话隔离不在首版范围。

本次自动化验收使用模拟 Gateway/REST，不需要真实 Token。真实网络、Discord 服务器权限与 LLM 回复由上述人工步骤验证。

## 5. 自动化验收结果（2026-09-21）

| 检查 | 结果 |
|---|---|
| harness-im-bridge `make all` | 格式、Lint、mypy 通过；458 项测试通过，13 项集成测试按默认命令排除 |
| Octop `make all` | 格式、Lint、mypy 通过；3587 项测试通过，17 项条件跳过 |
| Discord 最终相关后端复核 | 18 项通过，覆盖路由、实时状态、通道 CRUD 与配置探测 |
| 前端通道测试 | 12 项通过，包含 Discord 入口、Token 和长数字 ID 的完整保存流程 |
| `make build-frontend` / 启动脚本 | TypeScript 与 Vite 构建通过；`run-discord-local.sh --help` 通过；内置网页产物已生成 |

命令使用 `RUN='uv run --no-sync'` 保留未发布的本地网关；通道库复用 Octop 的开发环境（`UV_PROJECT_ENVIRONMENT=../Octop/.venv`）。Octop 完整测试需允许绑定本机随机端口，最初沙箱导致的 15 项端口权限失败已在允许本机端口后完整重跑通过。

没有使用真实 Bot Token，也没有发布包、提交或推送代码。人工测试请使用本文第一节的本地启动方式。

## 6. 全频道默认模式验收（2026-09-22）

新增「允许所有可访问频道」开关，前后端默认开启；缺少该字段的旧配置同样按开启处理。关闭并保存后保持指定频道模式；输入框保留原有 ID。私聊允许列表与直接 @触发规则不变。

- harness-im-bridge `make all`：460 passed，13 deselected；格式、Lint、mypy 通过。
- Octop `make all`：3591 passed，17 skipped；格式、Lint、mypy 通过。
- 前端通道测试：16 passed，覆盖默认开启、关闭后保存、旧配置默认值、重新编辑保留布尔值。
- 前端相关文件 ESLint 通过；TypeScript 和 Vite 构建通过，内置网页产物已更新。
- 重启本地 Octop 并刷新网页后生效；真实 Discord 联调仍由用户人工测试。
