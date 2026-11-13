# 脚本

这些脚本经 `tat-exec.sh --file` 下发到目标 CVM，不在 Octop 本机上跑。

| 脚本 | 用途 |
|---|---|
| `quick_scan.sh` / `quick_scan.ps1` | 约 3 秒分诊 |
| `deep_scan.sh` | 单组件深度采集，参数 `cpu\|memory\|disk\|network\|all` |
| `combined_analysis.sh` | 多组件一起看 |
| `cluster_os_snapshot.sh` | 多台 OS 快照 |
| `cluster_deep_cpu.sh` `cluster_deep_memory.sh` `cluster_deep_disk.sh` `cluster_deep_network.sh` `cluster_deep_ssh.sh` | 多台单组件深挖 |
| `cluster_score.sh` | 按快照打分 |
| `log_stats.sh` `analyze_stats.sh` | 把本次诊断记一笔，失败不影响结论 |
