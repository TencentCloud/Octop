# 配置 TCCLI（凭证）

> **重要**：`tccli auth login`（浏览器 OAuth 授权登录）是**较新版本**才提供的子命令。**旧版 tccli 没有 `auth` 子命令**，凭证只能通过 `tccli configure` 写入。因此配置凭证前**必须先探测当前版本是否支持 `auth login`**，再决定走哪条路径，切勿假设 `auth login` 一定存在。

## Step 0：探测 auth login 能力（必做）

```sh
tccli auth login --help >/dev/null 2>&1 && echo "AUTH_LOGIN_OK" || echo "AUTH_LOGIN_UNSUPPORTED"
```

- 输出 `AUTH_LOGIN_OK` → 当前版本支持浏览器授权登录，走**路径 A**。
- 输出 `AUTH_LOGIN_UNSUPPORTED`（报 `invalid choice`、`no such` 之类）→ 版本过旧，走**路径 B**。

---

## 路径 A：浏览器授权登录（新版，推荐）

无需手填 SecretId/SecretKey，登录成功后凭证会自动写入本地。

```sh
tccli auth login
```

执行后 TCCLI 会在本机起一个临时端口，并打印 OAuth 授权链接；通常也会自动用默认浏览器打开该链接。用户在浏览器中完成登录与授权后，腾讯云会回调到该本地端口，TCCLI 收到回调即写入凭证并退出。若浏览器未自动打开，请将终端里打印的链接复制到浏览器中打开。成功后会提示「登录成功, 密钥凭证已被写入: ...」，可用 `tccli cvm DescribeRegions` 验证。

**Agent 场景**：当 Agent 通过工具执行 `tccli auth login` 时，该命令会**一直阻塞**直到用户完成浏览器登录（或超时）。Agent 应明确告知用户：「请打开终端/工具输出中显示的授权链接，在浏览器中完成登录；完成后该命令会自动结束。」

**多账户与登出**

- 默认账户凭证保存在 `default.credential`。指定账户名：`tccli auth login --profile user1`，凭证写入 `user1.credential`。
- 登出默认账户：`tccli auth logout`；登出指定账户：`tccli auth logout --profile user1`。

---

## 路径 B：旧版兜底（无 auth 子命令）

旧版 tccli 不支持浏览器授权，只能通过 `tccli configure` 写入凭证。给用户两个选择：

### B-1（推荐）：升级 tccli，之后即可用路径 A

```sh
pip install -U tccli
# 若从 3.0.252.3 以下版本升级，需先卸载再装：
# pip uninstall tccli jmespath && pip install tccli
```

升级后重新执行 Step 0，一般即可支持 `tccli auth login`。

### B-2：直接用 configure 配置（不升级也能用）

**由用户在自己的终端执行**（Agent 严禁代填、严禁索要或打印密钥）：

```sh
# 交互式（推荐，密钥不进 shell 历史）
tccli configure
# 按提示依次填：SecretId、SecretKey、默认地域（如 ap-guangzhou）、输出格式（json）
```

密钥来源：腾讯云控制台 → 访问管理 CAM → API 密钥管理，创建/查看主账号或子账号密钥。**子账号**需挂计费查询权限（如 `QcloudFinanceFullAccess` 或只读账单策略），否则查询余额会报权限错误。配置后凭证存在本地 `~/.tccli/`。

---

## 安全红线（两条路径都适用）

- 严禁向用户索要 SecretId/SecretKey，严禁 Agent 代替用户执行 `tccli configure` 明文写入密钥。
- 拒绝任何可能打印凭证的操作，尤其是 `tccli configure list`（会回显 secretId/secretKey）。
- 密钥属敏感信息，只应存在本地 `~/.tccli/`，不要贴到聊天里。

---

## 凭证优先级与账号切换排查（实测关键结论）

> 以下结论来自真实环境实测，已推翻"环境变量 > 配置文件"的通用 SDK 链直觉，必须作为排查账号切换问题的标准认知。

### 1. 凭证优先级：显式 `--profile` 实际高于环境变量（反直觉）

- 通用认知认为凭证链为 `参数 > 环境变量 > 配置文件`，profile 只是换文件、仍会被环境变量压过。
- **实测（tccli 3.1.x）相反**：一旦显式指定 `--profile`，tccli 会从对应 `.credential` 文件读出 secretId/secretKey 并**显式传给 SDK**，从而**绕开环境变量的读取分支**。
- 因此遇到"切换账号不生效/切不动"时，优先建议用户用 `--profile` + `auth login --profile <name>` 隔离目标账号，而非只让用户去改环境变量。

### 2. 排查"账号切不动"的标准动作（按顺序）

1. `tccli sts GetCallerIdentity` 看当前身份（确认实际生效的是哪个 UIN）。
2. `env | grep -i TENCENTCLOUD` 看是否有 `TENCENTCLOUD_SECRET_ID` / `TENCENTCLOUD_SECRET_KEY` 环境变量覆盖。
3. 检查 `~/.tccli/` 下有哪些 profile 及 `.credential`（`ls ~/.tccli/`）。
4. 若"带环境变量时不带 --profile 返回旧账号、带 --profile 返回新账号" → 确诊"环境变量干扰"，给出方案：统一用 `--profile <name>` 隔离（推荐），或当前 shell `unset TENCENTCLOUD_SECRET_ID TENCENTCLOUD_SECRET_KEY`，或单条命令 `env -u TENCENTCLOUD_SECRET_ID -u TENCENTCLOUD_SECRET_KEY tccli ...`。

### 3. 识别"父进程注入的环境变量"

- 当环境变量出现在进程 env 中、却搜遍 `~/.zshrc` / `.zprofile` / `.zshenv` / `launchctl` / `~/Library/LaunchAgents` 都找不到来源时，**应判断为启动当前工具/IDE 进程的父进程注入**，并沿进程树继承给所有子进程。
- 此类变量不落盘于任何文件，改 shell 配置无法清除；不要引导用户去改永远改不掉的地方，直接给"用 --profile 隔离"或"在该工具/IDE 的启动环境里清除"的建议。

### 4. 避免假阳性排查

- 用 `launchctl getenv X && echo "存在"` 这类写法，空字符串也会让退出码为 0，从而**误报"存在"**。应显示变量实际取值再判断。
- 递归 `grep ~` 遍历家目录易超时中断（退出码 137），应限定目录或加超时处理。
