---
name: tcapi
display_name: 腾讯云 API 助手
description: Skill to call Cloud API for Tencent Cloud (腾讯云). Used for cloud automation or resource management. 当用户需要查询、创建、管理腾讯云资源，或执行云 API 自动化操作时触发。优先使用 Octop 自带 venv 中的 tccli，凭证支持全自动 OAuth 登录。
version: 1.0.0
tags: [tccli, cloud-api, tencent-cloud, automation]
keywords: [腾讯云, tccli, cloud api, 云资源, 云管理, 自动化运维]
prompt_template: 对 {service} 产品执行 {action} 操作
examples:
  - 查询广州地域的 CVM 实例
  - 创建一台按量计费的云服务器
  - 查看 COS 存储桶列表
---

# 腾讯云 API 助手

统一使用 **tccli** 命令行工具调用腾讯云 API，实现云资源的查询、创建、修改、删除等操作。

## 适用场景

- 云资源查询与管理（CVM / COS / CBS / VPC / TKE 等 200+ 产品）
- 自动化运维（批量操作、定时任务、脚本编排）
- 云 API 接口探索与文档检索

## 不适用场景

- 不支持 Terraform / Pulumi 等 IaC 编排工具
- 不做多云管理（仅限腾讯云）
- 不做费用充值、账号注册等非 API 操作

## 前置条件

- 已安装 tccli，未安装参考 [references/install.md](references/install.md)
- 已完成凭证配置（详见下方「Step 2 凭证配置」）

## 核心原则

> 1. **优先检索最佳实践 → 再查接口文档 → 最后调用 API**。不要跳过文档检索直接调用，避免用错接口或遗漏参数。
> 2. **在线文档是实时态，本地 tccli 是版本快照**。以在线文档（`cloudcache.tencentcs.com`）为准判断接口/参数是否存在；本地 tccli 因版本差异，可能缺少新接口、或残留已下线的旧接口。遇到本地报「无此接口」或服务端报「接口已下线」时，先查在线文档确认真实情况，再决定升级 tccli 或换用替代接口。

## 执行流程

### Step 0：环境自检（首次任务必做，一次探测串起所有分支）

**优先使用 Octop 自带的 Python 虚拟环境（venv）中的 tccli**：与 Octop 同环境、版本可控、不污染系统 Python。探测顺序：① Octop venv → ② 系统 PATH → ③ 临时安装进 venv。

```sh
# ① 定位 Octop venv（通过 octop 主进程的工作目录；找不到进程则退回常见路径）
OCTOP_PID=$(pgrep -f '\.venv/bin/octop run' | head -1)
OCTOP_ROOT=$([ -n "$OCTOP_PID" ] && readlink -f /proc/$OCTOP_PID/cwd || echo /workspace/octop)
TCCLI="$OCTOP_ROOT/.venv/bin/tccli"

# ② 逐级探测：venv 内 → PATH → 均无则装进 venv
if [ -x "$TCCLI" ]; then :
elif command -v tccli >/dev/null 2>&1; then TCCLI=tccli
else uv pip install --python "$OCTOP_ROOT/.venv/bin/python3" tccli; fi

# ③ 验证可运行且凭证有效
"$TCCLI" cvm DescribeRegions >/dev/null 2>&1 && echo "TCCLI_OK" || echo "TCCLI_NEED_CHECK"
```

> 若系统无 `uv`：`"$OCTOP_ROOT/.venv/bin/python3" -m ensurepip --upgrade` 后用同路径的 `python3 -m pip install tccli`。

判定分支：

| 探测结果 | 状态 | 处理 |
|:--------|:-----|:-----|
| 返回 `TCCLI_OK` | 已安装、可运行、凭证有效 | 直接进入 Step 1 |
| `command not found` / 安装失败 | **未安装** | 按 [references/install.md](references/install.md) 装进 Octop venv（推荐）或系统安装 |
| `bad interpreter` / `No module named tccli` | **装了但 shebang/环境坏** | 切换 Step 5 兼容模式（改用 venv 的 `python3 -c` 直接调 `tccli.main`），本会话后续统一使用 |
| 报 `secretId is invalid` / `AuthFailure.SecretIdNotFound` | **凭证缺失** | 进入 Step 2 配置凭证 |

> 探测通过（`TCCLI_OK`）后，本会话无需再重复自检，直接调用即可。后续所有示例中的 `tccli` 均指探测到的 `$TCCLI`（venv 优先）。

### Step 1：检索 API 文档

调用前先通过 curl + grep 检索业务、接口、最佳实践、数据结构。参考 [references/refs.md](references/refs.md) 获取完整检索方式。

#### 1.1 发现业务

检索 tccli 服务名（如 cvm、cbs）：

```sh
curl -s https://cloudcache.tencentcs.com/capi/refs/services.md | grep 云服务器
```

参考输出：

```
[cvm](service/cvm/index.md) | 云服务器 | 2017-03-12 | ...
```

#### 1.2 发现最佳实践

优先检索是否有匹配当前场景的最佳实践：

```sh
curl -s https://cloudcache.tencentcs.com/capi/refs/service/cvm/practices.md | grep 重装
```

#### 1.3 检索接口

若最佳实践未覆盖，在业务接口列表中检索（接口名即 tccli 的 `<Action>`）：

```sh
curl -s https://cloudcache.tencentcs.com/capi/refs/service/cvm/actions.md | grep "扩容\|磁盘"
```

#### 1.4 阅读接口文档

获取参数说明和支持的地域信息：

```sh
curl -s https://cloudcache.tencentcs.com/capi/refs/service/cvm/action/ResizeInstanceDisks.md
```

#### 1.5 阅读数据结构

文档中涉及的数据结构可进一步查看：

```sh
curl -s https://cloudcache.tencentcs.com/capi/refs/service/cvm/model/SystemDisk.md
```

### Step 2：凭证配置（全自动 OAuth，无需用户手动敲命令）

**原则：Agent 全程自动驱动，用户只需在浏览器里点一次「授权」。** 检测到凭证缺失（`AuthFailure.SecretIdNotFound`）时不要让用户手动跑命令，按下面的自动化流程直接执行。

#### 2.1 先探测 `auth login` 能力（必做）

```sh
tccli auth login --help >/dev/null 2>&1 && echo "AUTH_LOGIN_OK" || echo "AUTH_LOGIN_UNSUPPORTED"
```

#### 2.2 自动 OAuth（`AUTH_LOGIN_OK` 时的标准动作）

`tccli auth login` 的行为：起本地回调服务（端口 9000–9100）→ 打印授权链接 → 阻塞等待浏览器完成授权回调。自动化的关键在三点：**`BROWSER=echo` 防止无头环境打不开浏览器而报错退出；后台运行不卡死会话；从日志提取链接推给用户**。

```sh
# ① 后台启动登录（BROWSER=echo 让 webbrowser 静默"成功"，仅打链接不真开浏览器）
BROWSER=echo nohup tccli auth login > /tmp/tccli_auth.log 2>&1 &
AUTH_PID=$!

# ② 轮询日志拿授权链接（拿到后立即以可点击形式发给用户）
for i in $(seq 1 10); do
  URL=$(grep -m1 -o 'https://cloud.tencent.com/open/authorize[^ ]*' /tmp/tccli_auth.log) && break
  sleep 1
done
echo "请在浏览器打开并完成授权（点一次「授权」即可，命令会自动继续）：$URL"

# ③ 轮询进程退出，等待用户完成授权（默认 5 分钟超时，可按需延长）
for i in $(seq 1 300); do
  kill -0 $AUTH_PID 2>/dev/null || break
  sleep 1
done

# ④ 验证凭证并回显身份
tccli cvm DescribeRegions >/dev/null 2>&1 && echo "AUTH_OK" || cat /tmp/tccli_auth.log
tccli sts GetCallerIdentity
```

> 环境能打开浏览器时（如桌面版 Octop），去掉 `BROWSER=echo`，第 ② 步直接提示「浏览器已弹出，请完成授权」即可。

#### 2.3 兜底路径（`AUTH_LOGIN_UNSUPPORTED`，旧版 tccli）

旧版没有 `auth` 子命令。**先自动升级再走 2.2**（装进 Octop venv，不需要 sudo）：

```sh
uv pip install --python "$OCTOP_ROOT/.venv/bin/python3" -U tccli
# 无 uv 时："$OCTOP_ROOT/.venv/bin/python3" -m ensurepip --upgrade && ... -m pip install -U tccli
```

升级后重新探测（2.1），一般即可支持 `auth login`。若升级失败（如离线环境），才退化为半手动：引导用户在自己的终端执行 `tccli configure` 交互式填密钥——**Agent 仍不代填、不索要、不打印密钥**。

完整的多账户（--profile）、登出、凭证优先级排查细节见 [references/auth.md](references/auth.md)。

**安全红线**：严禁向用户索要 SecretId/SecretKey，也拒绝任何有可能打印凭证的操作（尤其是 `tccli configure list`）。OAuth 全自动流程中 Agent 接触不到密钥明文，天然满足此红线。

### Step 3：调用 API

基本形式：

```sh
tccli <service> <Action> [--param value ...] [--region <地域>]
```

输入参数：

| 参数 | 类型 | 必填 | 说明 |
|:-----|:-----|:-----|:-----|
| `service` | string | 是 | 产品标识，如 `cvm`、`cbs`、`vpc`。通过 Step 1.1 检索获取 |
| `Action` | string | 是 | 接口名，如 `DescribeInstances`、`RunInstances`。通过 Step 1.3 检索获取 |
| `--region` | string | 视接口 | 地域，如 `ap-guangzhou`。多数产品必传；全局接口（cam、account、dnspod、domain、ssl、ba、tag）可省略 |
| `--param value` | 各类型 | 视接口 | 接口参数，简单类型直接传值，复杂类型传 JSON 字符串 |

常用示例 —— 查询 CVM 地域：

```sh
tccli cvm DescribeRegions
```

查询实例（需指定地域）：

```sh
tccli cvm DescribeInstances --region ap-guangzhou
```

参数规则：

- 非简单类型参数必须为标准 JSON，例如：`--Placement '{"Zone":"ap-guangzhou-2"}'`。
- 创建类接口示例（按需替换参数）：
  ```sh
  tccli cvm RunInstances --InstanceChargeType POSTPAID_BY_HOUR \
    --Placement '{"Zone":"ap-guangzhou-2"}' --InstanceType S1.SMALL1 --ImageId img-xxx \
    --SystemDisk '{"DiskType":"CLOUD_BASIC","DiskSize":50}' --InstanceCount 1 ...
  ```

输出格式：tccli 返回标准 JSON，包含 `Response` 字段。示例：

```json
{
  "Response": {
    "TotalCount": 1,
    "InstanceSet": [{"InstanceId": "ins-xxx", "InstanceName": "test", ...}],
    "RequestId": "eac6b301-..."
  }
}
```

空结果输出：查询无匹配时，列表字段返回空数组，计数字段为 0：

```json
{
  "Response": {
    "TotalCount": 0,
    "InstanceSet": [],
    "RequestId": "eac6b301-..."
  }
}
```

效率约束：腾讯云 API 默认限频为 **10 次/秒**（部分接口更低），批量操作时需控制调用频率，避免触发 `RequestLimitExceeded`。建议串行调用或加间隔，不要并发轰炸。

避免并行调用：tccli 当前并行调用存在配置文件竞争问题，会导致响应失败。当前请逐个接口调用。

### 本地参数强转陷阱（type coercion）

部分 tccli 版本会按本地 schema 把某些参数强制类型转换后再发出，与云端期望不符，导致"永远 InvalidParameter"但用户参数其实填对了——这是**本地 tccli 的锅，不是用户的锅**：

- **典型信号**：服务端返回 `InvalidParameter`，message 指向"参数 X 取值类型错误 / 应为 date"等，但你传入的值语义上是对的。例如 TRTC 某些日期参数被本地标成 `Timestamp` 强转整数时间戳，云端实际要 `YYYY-MM-DD` 纯日期。
- **识别**：先 `tccli <svc> <Action> --help` 看参数类型标注；若本地类型是 Timestamp/Integer 而在线文档写的是 Date/String，基本可确诊。
- **缓解（按优先级）**：
  1. 查在线文档确认参数真实类型与格式（必要时用纯日期而非时间戳）；
  2. 试 `--cli-unfold-arguments` 让 tccli 不再做本地合并/转换；
  3. 若仍被本地强转卡死，绕过 tccli 用 Python SDK（`tencentcloud-sdk-python`）直连，把原始值（如纯日期字符串）原样赋给请求参数发出，即可通过云端类型校验。
- **重要**：这类 `InvalidParameter` 是"假参数错"，不要甩锅给用户参数填错。

### Step 3.5：输出解析规范（stdout/stderr 分流与 JSON 健壮性）

tccli 的 stdout 与 stderr 是两条独立流，解析时必须严格区分，否则会把警告/错误文本当结果吞掉导致解析崩溃。

**① 分流捕获，禁止盲目 `2>&1`**
- 正常调用只解析 stdout；stderr 单独落盘便于诊断：
  ```sh
  tccli <service> <Action> [--region <地域>] 2>/tmp/tccli_err.log
  ```
- 不要把 `2>&1` 当作习惯写法——一旦 tccli 把 `WARNING` / `DeprecationWarning` / 版本提示吐到 stderr，合并流会让 stdout 前被塞入非 JSON 文本，导致 `json.loads` 直接崩溃。

**② 解析前"抠 JSON"**
- 即便做了分流，也先用正则提取首个 `{` 到末个 `}` 的闭区间（或 `[...]`）再 `json.loads`，避免前后缀文本（版本提示、空格、回车）导致失败：
  ```python
  import re, json
  m = re.search(r'\{.*\}|\[.*\]', raw, re.DOTALL)
  data = json.loads(m.group(0)) if m else None
  ```

**③ 解析失败兜底（不抛 Traceback）**
- 若 stdout 无法解析为 JSON：提示"输出非预期 JSON"，并回显原始 stdout 前 N 字符供诊断，而非抛出 Python 堆栈。
- 若 stdout 无 JSON 而 stderr 含异常信息，按以下规则解析：
  - **锚点优先**：以 `[TencentCloudSDKException]` 为唯一权威锚点提取 `code` / `message` / `requestId`，**忽略同行 stderr 里 `usage:` 帮助块等噪音**（它们常与异常挤在同一段，不能"出现 usage 就判参数错"而误伤）。
  - **区分本地错 vs 服务端错**：有 `requestId` → 服务端已受理并返回（如 `InvalidParameter` / `InternalError` / `UnauthorizedOperation`）；无 `requestId` 且只有 `usage:` → 本地 argparse 参数解析错，与云端无关。
  - 优雅翻译为可读错误（见 Step 4 异常表），不要退化为崩溃。
- 注意：服务端报错、权限拒绝、接口下线等异常大多落在 **stderr**，分离流是正确翻译错误码的前置条件。

### Step 4：异常处理

调用失败时，tccli 会返回包含 `Error` 字段的 JSON：

```json
{
  "Response": {
    "Error": { "Code": "AuthFailure.SecretIdNotFound", "Message": "secretId is invalid" },
    "RequestId": "xxx"
  }
}
```

常见错误及处理：

| 错误码 | 含义 | 处理方式 |
|:------|:-----|:---------|
| `AuthFailure.SecretIdNotFound` | 凭证缺失或无效 | 按 Step 2 全自动 OAuth 流程执行：`BROWSER=echo` 后台 `auth login` → 推送授权链接 → 轮询等待 → 验证回显；旧版则先自动升级（详见 Step 2 / references/auth.md） |
| `AuthFailure.UnauthorizedOperation` | 无权限 | 检查 CAM 策略，确认子账号有该接口权限 |
| `InvalidParameterValue` | 参数值不合法 | 查阅接口文档确认参数取值范围 |
| `ResourceNotFound` | 资源不存在 | 确认资源 ID 和地域是否正确 |
| `RequestLimitExceeded` | 请求频率超限 | 等待后重试，或减少并发调用频率 |
| `UnsupportedOperation` / `DeprecatedOperation` / `InvalidAction` | 接口已下线/更名，或本地版本认得但云端已淘汰 | 检索在线文档确认现行接口，改用替代接口；勿死磕旧接口 |
| 本地 `invalid choice: 'XxxAction'` / argparse 报错，非服务端返回 | **旧版 tccli 本地缺少该新接口**（发布快照落后于云端） | 引导 `pip install -U tccli` 升级；或先查在线文档确认接口存在后再操作 |
| `DryRunOperation` | DryRun 操作成功 | 非真实错误，表示参数校验通过 |
| `UnsupportedRegion` | 不支持的地域 | 查阅接口文档确认支持的地域列表 |
| `ResourceInsufficient` | 资源不足 | 换可用区或调整规格重试 |
| 网络超时 / 连接失败 | 网络不通 | 检查网络连通性，确认是否需要代理 |
| `InternalError`（message 含 `nil pointer` / `nil pointer dereference`） | 接口云端已废弃 / 后端服务已拆除 | **不是服务端随机故障，停止重试**；检索在线文档确认真实情况，改用替代接口 |
| `AuthFailure.TokenFailure` / `FailedOperation.RefreshTokenError` | OAuth token 已失效（浏览器授权过期或吊销） | 自动重新走 Step 2 全自动 OAuth（`tccli auth login --profile <name>`）；完成后按"身份确认"规范回显当前账号再继续 |

### Step 5：tccli 不可用时的兜底方案

当直接执行 `tccli` 报错 `bad interpreter`、`No module named tccli` 或 `command not found` 时，通常是 tccli 的 shebang 指向了已卸载的 Python 解释器（环境问题，并非每个用户都会遇到）。此时**优先改用 Octop venv 的 Python 直接调 `tccli.main`**（venv 里 tccli 与 Octop 同源，最可靠）；没有 Octop venv 时才**动态探测**系统 Python 及其 site-packages，**不要硬编码任何平台特定路径**：

```sh
# ① 优先：Octop venv 的 python（Step 0 已定位 $OCTOP_ROOT）
"$OCTOP_ROOT/.venv/bin/python3" -c "
import sys
sys.argv = ['tccli', 'cvm', 'DescribeInstances', '--region', 'ap-guangzhou']
from tccli.main import main
main()
"

# ② 兜底：动态探测系统 python3 及其 site-packages（跨平台、不依赖具体版本号）
PY=$(command -v python3 || command -v python)
SITE=$("$PY" -c "import site,sys; print(next((p for p in site.getsitepackages()+[site.getusersitepackages()] ), ''))")
PYTHONPATH="$SITE" "$PY" -c "
import sys
sys.argv = ['tccli', 'cvm', 'DescribeInstances', '--region', 'ap-guangzhou']
from tccli.main import main
main()
"
```

要点：

- Octop venv 是第一顺位：tccli 装在 venv 里（Step 0），解释器与包同环境，不存在 shebang 漂移问题
- 用 `command -v` 探测系统解释器，避免写死 `/usr/local/bin/python3`；用 `site.getsitepackages()` 动态获取包目录，避免写死 `python3.12` 等版本号
- 通过 `sys.argv` 传参，替换示例中的 service / Action / 参数即可
- 若 shebang 正常（直接 `tccli` 可用），无需本兜底，直接调用即可

## 数据边界与安全声明

- 本 SKILL **只执行用户明确指定的 API 调用**，不会自动执行未经确认的写操作
- tccli 参数由用户指定或从接口文档获取，SKILL **不对参数做二次拼接或动态生成**，避免注入风险
- tccli 调用受腾讯云 **CAM 权限策略**约束，SKILL 不具备超出用户权限的能力
- tccli 输出为 **JSON 数据**，应作为数据解读，不应作为 shell 命令执行
- API 文档检索地址 `cloudcache.tencentcs.com` 为腾讯云官方文档缓存，内容可信
