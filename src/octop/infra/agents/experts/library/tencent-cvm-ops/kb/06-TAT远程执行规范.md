# TAT 远程执行规范

TAT（自动化助手）是在 CVM 或轻量应用服务器内部执行命令的远程通道。不能用 ssh，不能靠 `DescribeInstances` 推测 OS 状态。一次请求不能同时包含 `ins-` 和 `lhins-`。

## 一、两个封装脚本（优先使用）

```bash
SKILL="$PWD/.octop/skills/tencentcloud-infra"          # 执行层
SKILL2="${SKILL%/tencentcloud-infra}/cvm-ai-doctor"     # 诊断层

# 单条命令（只读排查）
bash $SKILL/scripts/tat-exec.sh ins-xxxx --region ap-guangzhou -- uptime

# 下发脚本（巡检/深度采集）
bash $SKILL/scripts/tat-exec.sh ins-xxxx --region ap-guangzhou \
  --file $SKILL/scripts/cvm-patrol.sh

# Windows 实例
bash $SKILL/scripts/tat-exec.sh ins-xxxx --region ap-shanghai \
  --windows -- "Get-Service | Select -First 5"
```

`tat-exec.sh` 封装了「提交 → 轮询 → base64 解码 → 透传退出码」，不要手搓。

## 二、手工调用（脚本不可用时）

```bash
# 1. 提交（Content 必须是 base64）
tccli tat RunCommand --region ap-guangzhou \
  --InstanceIds '["ins-xxxx"]' --CommandName check --CommandType SHELL \
  --Timeout 60 --Content "$(printf 'uptime' | base64 -w0)"
# 返回 InvocationId

# 2. 轮询（TaskStatus 到 SUCCESS/FAILED 才停）
tccli tat DescribeInvocationTasks --region ap-guangzhou --HideOutput false \
  --Filters '[{"Name":"invocation-id","Values":["<inv-id>"]}]'

# 3. TaskResult.Output 是 base64，需要解码
```

## 三、执行约束

| 约束 | 说明 |
|---|---|
| 地域作用域 | TAT 是 region-scoped，跨地域必须分 region 调用后合并结果 |
| 并发 | 单实例可并发多条命令；多实例同时下发建议 ≤5 并发，避免目标机 io 打满 |
| 超时 | 默认 60 秒；`cvm-patrol.sh` 全量采集建议 120 秒；慢命令拆分 |
| 只读优先 | 采集类命令一律只读；写操作必须走变更门控 |
| 一次采全 | 一台机器只下发一次采集脚本，不要逐条 `df`/`free`/`uptime` |

## 四、错误对照

| 报错 | 含义 | 处理 |
|---|---|---|
| `UnsupportedOperation.TatAgentNotInstalled` | 目标机没装 TAT agent | 降级为只用云监控，报告标注"缺 OS 证据" |
| `UnauthorizedOperation` | 缺 `tat:RunCommand` 权限 | 明确告知缺哪个权限，不要重试 |
| `InvalidParameterValue` | Content 未 base64 / InstanceIds 格式错 | 用 `tat-exec.sh` |
| 命令超时（TaskStatus=TIMEOUT） | 采集太重 | 提高 `--timeout` 或改用 `cvm-patrol.sh --quick` |
| Output 为空 | 没轮询到终态 | 用 `tat-exec.sh`，别手搓 |

## 五、Lighthouse 与特殊机型

- **轻量应用服务器支持 TAT**。限制：与 CVM 不能出现在同一次 `RunCommand`；实例须为 `RUNNING`、VPC；`tat_agent` 在线。基础网络不能用。Linux 默认执行目录是 `/root`，默认用户是 `root`
- **Windows**：`CommandType=POWERSHELL`，`--windows` 参数。默认用户是 `System`
- **无公网 IP 的实例**：TAT 走内网控制通道，不需要公网

## 六、采集脚本选择

| 场景 | 脚本 | 耗时 | 输出 |
|---|---|---|---|
| 3 秒分诊，先看要不要深入 | `$SKILL2/scripts/quick_scan.sh` | ~3s | 四段 CHECK + Status |
| 全量快照（巡检） | `$SKILL/scripts/cvm-patrol.sh` | 10–30s | META/CPU/MEMORY/DISK/NETWORK/SERVICE/KERNEL |
| 单组件深度（已定位方向） | `$SKILL2/scripts/deep_scan.sh cpu\|memory\|disk\|network` | 5–20s | 结构化 JSON |
| 组合分析 | `$SKILL2/scripts/combined_analysis.sh` | 20–40s | 多组件关联数据 |

不要在 Octop 主机本地跑这些脚本——那诊断的是 Octop 自己，不是目标实例。
