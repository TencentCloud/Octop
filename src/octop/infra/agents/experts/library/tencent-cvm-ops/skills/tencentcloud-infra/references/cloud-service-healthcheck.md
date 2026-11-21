# 多产品一起看

云服务器本身的诊断、巡检和报告用同目录的 `diagnosis-report.md`。不要在这里打 0–100 分，也不要拿分数解释云服务器页的颜色。

用户把 CVM 和数据库、缓存、负载均衡放在一起问时，只补充这些产品的监控，仍按诊断报告的结构输出。指标名以 `tccli <产品> <Action> help` 和知识库《CVM 指标口径》为准：

| 产品 | Namespace | 常用指标 |
|---|---|---|
| CDB | `QCE/CDB` | `CpuUseRate`、`ThreadsConnected`、`SlowQueries`。云盘架构指标带 `Cluster` 前缀 |
| Redis | `QCE/REDIS_MEM` | 维度名先用 `tccli monitor GetMonitorData help` 核对，常见为小写 `instanceid` |
| CLB | `QCE/LB_PUBLIC` 或 `QCE/LB_PRIVATE` | 维度 `vip`。没有 `QCE/LOADBALANCE` |
| COS | 对应 COS 命名空间 | 维度是 appid + bucket |

空序列写「未采集」。查不到指标名就先 `help`，不要套用 CVM 的 `CpuUsage`。
