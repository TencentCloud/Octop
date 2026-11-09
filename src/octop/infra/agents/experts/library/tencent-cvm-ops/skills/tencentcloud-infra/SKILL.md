---
name: Tencent Cloud Infra
description: '用 tccli 管理腾讯云 CVM：实例查询、云监控 GetMonitorData、TAT 远程执行、OAuth。工作台云服务器页只有 CVM（ins-）。轻量应用服务器（lhins-）走 lighthouse API，监控命名空间是 QCE/LIGHTHOUSE。TAT 对两种实例都可用，但一次 RunCommand 不能混用。实例必须 RUNNING、VPC、tat_agent 在线。当前实例只用 scripts/whoami.sh，地域用 whoami.sh --with-region。参数以 tccli <服务> <操作> help 为准。'
metadata:
  {
    "openclaw": {
      "emoji": "☁️",
      "os": ["darwin", "linux"],
      "requires": {},
      "install": [
        {
          "id": "pip",
          "kind": "pip",
          "package": "tccli",
          "bins": ["tccli"],
          "label": "Install TCCLI"
        }
      ]
    },
    "octop": {
      "emoji": "☁️",
      "label": { "zh": "腾讯云基础设施", "en": "Tencent Cloud Infra" },
      "summary": {
        "zh": "用 tccli 查询 CVM、云监控和 TAT。",
        "en": "Query CVM, Cloud Monitor, and TAT with tccli."
      }
    }
  }
---

# 腾讯云资源管理

工作台「云服务器」页只有 CVM。轻量应用服务器用 `tccli lighthouse` 和 `QCE/LIGHTHOUSE`，不要用 `cvm` 命令查 `lhins-`。参数以 `tccli <服务> <操作> help` 为准，不要凭记忆拼参数名。

写操作的分级、确认和回滚以 `SOUL.md` 为准。诊断报告用 `references/diagnosis-report.md`。

## 当前实例

只用 `bash scripts/whoami.sh`。加 `--with-region` 会多打出 `zone=` 和 `region=`。不要用 tccli 猜「当前机器」，也不要自己 curl 元数据。

## TAT

不要假设能 ssh。一次 `RunCommand` 只能是一种实例；目标必须是 `RUNNING`、VPC，且 `tat_agent` 在线。Linux 默认在 `/root` 以 `root` 执行。

```bash
bash $SKILL/scripts/tat-exec.sh <instance-id> --region <region> -- uptime
bash $SKILL/scripts/tat-exec.sh <instance-id> --region <region> --file $SKILL/scripts/cvm-patrol.sh
bash $SKILL/scripts/tat-exec.sh <instance-id> --region <region> --windows -- "Get-Service | Select -First 5"
```

`tat-exec.sh` 负责提交、轮询、base64 解码和退出码。手搓 `RunCommand` 容易拿到空输出。

| 报错 | 处理 |
|---|---|
| `UnsupportedOperation.TatAgentNotInstalled` | 只用云监控，写明缺少 OS 层证据 |
| `UnauthorizedOperation` | 说明缺 `tat:RunCommand`，不要重试 |
| 超时 | 加大 `--timeout`，或 `cvm-patrol.sh --quick` |

`cvm-patrol.sh` 只读，分段为 `META / CPU / MEMORY / DISK / NETWORK / SERVICE / RECENT-KERNEL / END`。阈值判定在 `SOUL.md`。

## 凭据

先 `python3 scripts/tccli-oauth-helper.py --status`。

- `✅ 凭证有效` 或 `♻️ 已用 refreshToken 自动续期`：继续，不要让用户重新登录。
- `❌ 凭证与 refreshToken 均已失效`：`python3 scripts/tccli-oauth-helper.py --get-url`，把输出里的链接原样给用户。用户发回 base64 验证码后执行 `--code "验证码"`。
- 授权链接只能来自 `--get-url` 的标准输出。不要拼接、不要改 `%5F`、不要自己打开浏览器。
- 验证用 `tccli cvm DescribeRegions`。`tccli sts GetCallerIdentity` 不支持 OAuth 临时凭证。
- 用户主动给出 SecretId / SecretKey 时才 `tccli configure set`。不要主动索要 AK/SK。

## 云监控

```bash
tccli monitor GetMonitorData --region <r> \
  --Namespace QCE/CVM \
  --MetricName CpuUsage \
  --Instances '[{"Dimensions":[{"Name":"InstanceId","Value":"<ins-xxx>"}]}]' \
  --Period 60 --StartTime "<now-1h ISO>" --EndTime "<now-120s ISO>"
```

`Period=60` 的 CPU 和内网带宽是平均值；`300` 和 `3600` 是区间最大值。`CvmDiskUsage` 是所有磁盘的最大值。空序列是未采集，不是 0。指标名和页面色带见 `HEARTBEAT.md` 与知识库《CVM 指标口径》。

## 速查

| 任务 | 命令 |
|---|---|
| CVM 实例 | `tccli cvm DescribeInstances --region <r>` |
| 轻量实例 | `tccli lighthouse DescribeInstances --region <r>` |
| 云硬盘 | `tccli cbs DescribeDisks --region <r>` |
| 安全组规则 | `tccli vpc DescribeSecurityGroupPolicies --region <r> --SecurityGroupId <sg-id>` |
| 地域 | `tccli cvm DescribeRegions` |
| 参数 | `tccli <服务> <操作> help` |

未安装 tccli 时：`pip install tccli`。

## 按场景打开的参考

| 场景 | 文件 |
|---|---|
| 诊断报告 | `references/diagnosis-report.md` |
| 安全组与登录加固 | `references/cvm-security-check.md` |
| 域名、证书到期 | `references/auto-check-resource.md` |
| 云硬盘购买、挂载、扩容 | `references/cbs-bindto-cvm.md` |
| CDB / Redis / CLB 等一起看 | `references/cloud-service-healthcheck.md` |

建站、应用部署、OpenClaw 安装不在本专家的工作里。
