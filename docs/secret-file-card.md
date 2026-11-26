# 安全填写凭据文件卡片（request_secret_file）

Skill/CLI 需要 Token/Key 等凭据文件时，模型调用 `request_secret_file` 工具
（只传 `path`/`prompt`/可选 `title` 元数据），对话暂停并弹出专用秘密输入卡片；
用户在浏览器中填写后直接提交到后台专用 API，后台写入当前专家的私有 auth
目录，工具结果只包含 filled/cancelled 状态和路径——秘密正文不进入对话、
模型上下文、checkpoint、trajectory、SSE/WS、聊天历史或日志。

## 流程

```
Skill 文档指明所需文件（如 auth/hr.token）
  → 模型调用 request_secret_file(path="hr.token", prompt="…")
  → 独立凭据输入中间件 interrupt（allowed_decisions=["respond"]，会话旁路不可跳过）
  → 注册 pending 时后台标注 _secret_card 元数据（规范化路径、是否已存在）
  → 仪表盘渲染 SecretFileCard（密码输入、替换警告、取消）
  → 浏览器 POST /api/agents/{id}/chat/secret-file/submit（JWT 认证）
  → 后台校验 pending 归属（用户/专家/线程/状态，原子 claim 防重放）
  → 私有写入（见下）→ 以 respond 恢复回合，消息只含路径与状态
```

凭据输入不依赖安全设置中的工具审批开关。关闭审批、会话允许全部或安全策略
热更新都不会跳过卡片；普通工具审批和 `ask_user_question` 保留各自的流程。
每次只提交一个凭据请求；多请求或混合审批不能一次提交并误标全部已填写，
可以取消后让模型逐个发起。

## 安全边界（必须阅读）

- **本卡片不解决跨员工执行隔离。** 共用 HOME / root 且 `root_dir=/` 的本地
  专家之间仍可能互相读取凭据文件；这是宿主执行隔离问题，由独立任务处理。
- 同一专家已有的 shell/file 工具在后续回合仍能读取该文件——这是现实边界，
  卡片只保证秘密不经过对话与日志，不保证对模型后续动作不可见。
- 首版只允许当前用户**自己拥有的非共享专家**提交凭据；共享专家返回 403。
- 秘密永远不进入：工具参数、工具结果、HITL 恢复消息、LangGraph
  checkpoint、trajectory、聊天历史、API 响应、审计/错误日志。
  卡片上的 `password` 字段类型只是 UI 遮罩，不构成安全保证。
- 不提供 `read_secret` 工具，不回填/回显已存文件内容。

## 写入保证

| 后端 | 行为 |
|------|------|
| POSIX 宿主本地（root_dir=/ 或未设置） | auth 目录及其子目录 0700、文件 0600（进程用户所有）；临时文件 + `os.replace` 原子替换；拒绝工作区至 auth 的符号链接祖先及秘密路径中的符号链接；失败保留原文件 |
| Windows 等非 POSIX 宿主 | **明确拒绝**（`SECRET_BACKEND_UNSUPPORTED`）：尚无经过验证的私有 ACL 写入实现 |
| Docker / OpenSandbox（sandbox_fs） | **明确拒绝**（`SECRET_BACKEND_UNSUPPORTED`）：协议上传为 0644 tar 条目且无 stdin 执行通道，无法从创建起保证私有权限，也不做先上传后 chmod 的降级 |
| 云对象存储（COS/S3/OSS/OBS/Postgres）、scoped root_dir 本地 jail | **明确拒绝**（`SECRET_BACKEND_UNSUPPORTED`），不降级写入宿主 |

文件范围只允许专家平台管理的 auth 目录：新布局 `{workspace}/.octop/auth`，
旧布局 `{workspace}/.octop-auth`（复用 `agent_auth_dir` 规则）。模型不能给出
绝对路径、共享 HOME、其他专家目录或 `..` 越界路径。

## Skill / CLI 接入示例

Skill 文档中约定路径与验证方式：

```markdown
若缺少 HR Token，调用 request_secret_file(path="auth/hr.token",
prompt="HR 系统访问 Token，从 https://hr.example.com/keys 复制")。
填写完成后用返回的路径执行：`hr-cli --token-file <返回路径> whoami` 验证。
```

工具结果只告知 filled + 路径，例如：

```
凭据文件已由用户安全写入：/home/u/.octop/agents/<id>/.octop/auth/hr.token（status=filled）。
```

CLI 侧（在专家执行环境中）直接使用该路径，凭据不经过模型：

```bash
hr-cli --token-file /home/u/.octop/agents/<id>/.octop/auth/hr.token whoami
```

首版仅宿主本地后端可写入；沙箱/云存储专家的卡片会显示后端不支持并阻止提交。

### CLI 固定使用用户目录

默认本地完整环境额外提供非秘密路径变量：

```text
OCTOP_CLI_HOME=$OCTOP_AUTH_DIR/cli-home
```

CLI 要求 `~/.example/credentials` 时，卡片使用相对路径
`cli-home/.example/credentials`；要求 XDG 配置文件时，使用
`cli-home/.config/example/config.json`。内容仍由用户通过密码卡片提交，
目录和文件由同一私有写入流程创建。新专家的文件默认位于当前工作区
`.octop/auth/cli-home/`；已有旧凭据目录时继续复用，不搬迁或删除。

只为这一次 CLI 调用设置用户目录：

```bash
env HOME="$OCTOP_CLI_HOME" \
    XDG_CONFIG_HOME="$OCTOP_CLI_HOME/.config" \
    some-cli whoami
```

若该 CLI 还使用 XDG data/state/cache，将对应的 `XDG_DATA_HOME`、
`XDG_STATE_HOME`、`XDG_CACHE_HOME` 同时指向该私有 HOME 内的目录。
平台自身和普通命令的 `HOME`、`OCTOP_HOME` 不变；不要全局 export HOME，
也不要把秘密拼进命令。CLI 支持专用配置路径时，仍优先使用其参数或专用变量。

这依赖 CLI 遵守 HOME/XDG；硬编码系统路径、系统钥匙串、`sudo` 或登录 shell
重设环境等情况不能靠这个方案通用兼容。此调用示例适用于 POSIX shell，
未扩展到 Windows 或 scoped root / Docker 后端，也不构成跨专家执行隔离。

## IM 渠道

IM 中只显示只读提示卡（路径/用途），引导用户到网页端填写；`/approve`
不会批准秘密请求，IM 文本回复不会被当作凭据保存。
