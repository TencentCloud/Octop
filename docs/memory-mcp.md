# 共享记忆 MCP 接入

Octop 面板通过独立的 octop-memory 服务管理记忆空间和终端凭据。Claude Code、Codex、Cursor、Kiro 和 DSH 可以通过 Streamable HTTP 访问同一空间。

## 部署

1. 安装 `octop-memory[server]==1.0.7`，用 `octop-memory serve` 启动服务。
2. 在 Octop 上设置 `OCTOP_MEMORY_SERVICE_URL` 为 Octop 后端能够访问的服务地址。默认地址是 `http://127.0.0.1:8790`。
3. 共享入口时，将 `/mcp/` 转发到 Memory，面板和 `/api/memory-mcp/` 转发到 Octop。在 Octop 设置 `OCTOP_MEMORY_SAME_ORIGIN=1`，让面板生成该入口的终端地址。Memory 管理接口只供内部访问。远程终端使用 HTTPS 访问此入口。

## 空间和 Token

在「个性化 → 记忆 → 共享记忆」中使用空间管理码连接，选择空间，按终端创建只读或读写 Token。终端通过 `Authorization: Bearer <TOKEN>` 访问该空间。已有专家也可以绑定到空间。

创建或轮换后，面板只展示一次新 Token。安装命令在本机终端隐藏读取 Token，通过 `OCTOP_MEMORY_TOKEN` 交给安装器。复制给 AI 的提示可以直接粘贴，手动配置中的 `<TOKEN>` 在本机替换。

复制配置可以随时进行。需要替换凭据时，点击「轮换 Token」并确认，再更新使用这枚凭据的客户端。旧凭据随即失效。撤销可停用单个终端的访问。

## Codex 聊天与提取模型

1. 选择读写 Token，点击「配置本机 Codex」，按面板提示运行固定到 `v1.0.7` 的安装器。首次安装可使用 `OCTOP_CODEX_EXTRACTION=codex`。启用 `OCTOP_CODEX_PANEL_SYNC=1` 并设置面板的 `OCTOP_CODEX_REVIEW_URL`。升级时沿用本机原提取模式。
2. 在「Codex 提取模型」选择跟随当前 Codex 会话、Memory 服务模型，或有权限使用的 Octop 模型，例如 HY4。点击「应用到终端」发布到该 Token。
3. 开启同步的终端在下一轮聊天结束时拉取配置并回传版本。面板的「终端已确认」表示配置已抵达。当有可提取的用户消息时，后台复核会记录实际使用的模型。聊天本身继续使用 Codex 选择的模型。
4. 在记忆面板检查提取候选。每条事实附其来源原话，重复事实可累积证据，明确变更可以更新原记忆。

进一步了解[终端接入指南](https://github.com/TencentCloud/octop-memory/blob/v1.0.7/plugins/harness/AI-SETUP.md)和[面板发布、回执及复核接口](api.md)。
