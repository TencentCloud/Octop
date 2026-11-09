---
name: cvm-ai-doctor
description: 腾讯云 CVM 的 OS 层诊断。快速分诊和单组件深度采集都经 TAT 下发到目标实例，不在 Octop 宿主机上执行。桌面环境、打印机、声卡、蓝牙、Conda、SMART 不在本技能范围。
metadata:
  octop:
    emoji: "🩺"
    label:
      zh: "CVM 诊断"
      en: "CVM diagnosis"
    summary:
      zh: "经 TAT 对目标 CVM 做分诊和 CPU、内存、磁盘、网络深度采集。"
      en: "Triage and deep CPU, memory, disk, and network collection on a target CVM via TAT."
---

# CVM 诊断

本技能只诊断**用户指定的腾讯云 CVM**。采集经 `tencentcloud-infra` 的 `tat-exec.sh --file` 下发。在 Octop 本机执行这些脚本，诊断的是 Octop 自己。

云监控能解释症状时停在云监控。需要进程、挂载点或日志时再下发脚本。

## 怎么采

| 目的 | 脚本 | 下发 |
|---|---|---|
| 3 秒分诊 | `scripts/quick_scan.sh`（Windows 用 `quick_scan.ps1`） | `tat-exec.sh --file` |
| 单组件细节 | `scripts/deep_scan.sh`，组件为 `cpu` `memory` `disk` `network` `all` | `--file` 不带参数，要用 SOUL 里的包装脚本 |
| 全貌巡检 | `tencentcloud-infra` 的 `cvm-patrol.sh` | 同上 |
| 多台共同根因 | `scripts/cluster_os_snapshot.sh`、`cluster_deep_*.sh`、`cluster_score.sh` | 同上，并发不超过 5 |

判读手册：

- 单机：`references/resource-saturation-quick.md`，以及 `resource-saturation-deep-cpu.md`、`memory`、`disk`、`network`、`combined`
- 日志：`references/system-logs-quick.md`，以及 `system-logs-deep-oom.md`、`kernel`、`fs`、`auth`、`service`
- 时间：`references/time-sync.md`
- 多台：`references/cluster-quick-check.md`、`cluster-deep-analysis.md`、`cluster-health-score.md`、`cluster-remediation.md`
- 和云 API 的配合：`references/skill-collaboration-tencentcloud.md`

范围以用户给出的实例或当前选中的实例为准。不要把节点列表写进 `MEMORY.md`，也不要先做一轮「集群配置引导」。

云硬盘没有物理盘 SMART。温度、RAID、风扇、电池这些物理机检查不用于 CVM。
