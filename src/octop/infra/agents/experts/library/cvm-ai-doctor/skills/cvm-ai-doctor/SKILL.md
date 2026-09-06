---
name: cvm-ai-doctor
description: CVM 实例健康诊断,采用智能快速/深度检查模式。涵盖性能和使用问题专业检查、诊断、和修复。支持服务器、PC、虚拟机、容器场景，支持 Linux/macOS/Windows。
metadata:
  openclaw:
    requires:
      bins: ["bash", "ps"]
    os: ["linux", "darwin", "windows"]
  octop:
    emoji: "🩺"
    label:
      zh: "CVM AI 诊断"
      en: "CVM AI Doctor"
    summary:
      zh: "快速分诊后再深度检查 CPU、内存、磁盘与网络问题。"
      en: "Triage then deeply diagnose CPU, memory, disk, and network issues."
---

# CVM AI Doctor 技能

**用途**: 智能诊断系统各类性能问题和使用问题,采用快速检查(10秒分诊)→ 深度分析(20-60秒)工作流。

**支持系统**: 本地服务器、个人计算机(Mac/Windows/Linux)、虚拟机、容器。

---

## 🎯 何时使用此技能

**核心能力**:
- 系统性能诊断(CPU、内存、磁盘、网络)
- 健康检查(快速扫描、综合分析)
- 系统故障排查(崩溃、错误、慢、卡)
- 性能优化建议
- **集群管理**：多节点健康巡检、评分、关联分析、风险门控修复（需配合 `tencentcloud-infra` 技能）

**触发关键词**: 详见"Tier 1 核心场景"中的完整关键词列表

**注意**: 如果用户提到"LightClaw 自检"或"平台体检"或"安全检查",请使用 `health-check` 技能。

**注意**: 如果用户提到"集群"、"所有节点"、"所有CVM"，使用集群管理场景，需同时加载 `tencentcloud-infra` 技能。

### 🌐 远程服务器

- 用户提到 **IP 地址**或**远程主机** → 结合 `remote-connect` 技能使用(详见"远程诊断"章节)

---

## 🚀 快速/深度诊断工作流

两阶段诊断方法:

```yaml
快速模式 (3-10秒):
  - 快速扫描所有组件
  - 执行策略:
      优先: 执行快速扫描脚本 (如果存在) → ~3秒
        - Windows: pwsh scripts/quick_scan.ps1
        - Linux/macOS: bash scripts/quick_scan.sh
      回退: 读取 resource-saturation-quick.md → 运行单独命令 → ~10秒
  - 返回: 每个组件的 OK / WARNING / CRITICAL 状态
  
深度模式 (20-60秒, 按需触发):
  - 单组件: 只分析标记组件
  - 多组件: 使用组合关联分析
  - 根本原因分析 + 建议

决策规则:
  - 通用问题 ("慢", "卡") → 先快速扫描,再对标记组件深度分析
  - 特定组件 ("CPU高") → 跳过快速,直接深度分析
  - 多个异常 (2+ 个标记) → 使用深度组合分析
  - 健康检查 → 仅快速扫描,全部 OK 则停止
```

---

## 🔍 场景匹配

### Tier 1: 核心场景 (80% 覆盖率)

优先匹配以下场景:

```yaml
系统慢/卡 (System Slow):
  keywords: [慢, 卡, slow, lag, 响应慢, sluggish, 性能问题, performance issue, 性能故障, performance problem]
  workflow: 快速扫描 → 对标记组件深度分析
  fixes: [commands/debugging/diagnose-slowdown.md, commands/system-health/review-startup-services.md]

CPU 高 (High CPU):
  keywords: [CPU, cpu高, cpu 100%, CPU满]
  workflow: 直接使用 resource-saturation-deep-cpu.md
  fixes: [commands/hardware/hardware-profilers/by-component/profile-cpu.md]

内存不足 (Low Memory):
  keywords: [内存, memory, OOM, swap, 内存不足]
  workflow: 直接使用 resource-saturation-deep-memory.md
  fixes: [commands/hardware/hardware-profilers/by-component/profile-ram.md]

磁盘问题 (Disk Issues):
  keywords: [磁盘, disk, I/O, io慢, 磁盘满, 磁盘空间, 盘满, C盘, D盘, disk full, space, 存储]
  workflow: 直接使用 resource-saturation-deep-disk.md
  fixes: [commands/optimisation/large-files.md, commands/storage/health-checks/check-drive-health.md]

网络问题 (Network Issues):
  keywords: [网络, network, 网卡, 丢包]
  workflow: 直接使用 resource-saturation-deep-network.md
  fixes: [commands/network/lan/diagnose-lan-connectivity.md]

健康检查 (Health Check):
  keywords: [检查, 健康, health, check, 诊断, 体检, 健康度, inspection, 专业检查, 专家检查, 快速检查, 深入检查, 深度检查, 全面检查]
  workflow: |
    一般健康检查 → 运行快速扫描脚本 (3秒):
      全部 OK 则停止。
    综合健康检查 (用户说"综合检查" / "全面体检" / "系统全检" / "深入检查" / "深度检查" / "专业检查" / "专家检查"):
      按顺序运行 3 个快速模块:
        1. resource-saturation-quick.md (CPU/内存/磁盘/网络)
        2. system-logs-quick.md (内核/OOM/文件系统/认证/服务错误)
        3. disk-smart-quick.md (磁盘 SMART 健康度)
      对发现的任何 WARNING/CRITICAL 组件进行深度分析。
  fixes: [commands/system-health/system-health-checkup.md]

系统崩溃/错误 (System Crash):
  keywords: [崩溃, crash, 错误, error, 重启, reboot, 系统救援, 系统急救, emergency, rescue, 紧急修复, 故障修复]
  workflow: system-logs-quick.md → 对错误类别深度分析
  fixes: [commands/debugging/diagnose-crash.md]

性能优化 (Performance Optimization):
  keywords: [性能优化, 性能提升, 提升性能, performance optimization, performance tuning, optimize, tuning, 调优, 优化建议]
  workflow: 快速扫描 → 识别瓶颈 → 深度分析 → 优化建议
  fixes: [commands/hardware/hardware-profilers/hardware-profile.md, commands/optimisation/large-files.md]

磁盘健康 (Disk Health):
  keywords: [磁盘健康, SMART, 坏道, 硬盘故障]
  workflow: disk-smart-quick.md → 如果 FAILED 则 disk-smart-deep.md
  fixes: [commands/storage/health-checks/check-drive-health.md]

硬件问题 (Hardware Issues):
  keywords: [硬件, hardware, 温度, RAID, ECC, 风扇]
  workflow: hardware-health-quick.md → hardware-health-deep.md
  fixes: [commands/hardware/hardware-profilers/hardware-profile.md]

时间问题 (Time Issues):
  keywords: [时间, NTP, 时钟, 时间不对, Kerberos]
  workflow: time-sync.md 快速 → 如未同步则深度分析
  fixes: []  # time-sync.md 本身包含修复步骤

SSH 登录问题 (SSH Login Issues):
  keywords: [SSH, ssh登录, 无法登录, 登录失败, can't login, login failed, connection refused, 连不上]
  workflow: |
    使用 cvm-self-diagnosis-repair.md → 诊断 SSH 服务、防火墙、磁盘、内存
    需用户确认后修复: 重启服务、修复配置、开放防火墙
  fixes: [references/cvm-self-diagnosis-repair.md]

诊断统计 (Diagnosis Stats):
  keywords: [统计, 诊断统计, stats, statistics, 诊断报告, 历史诊断, 诊断历史, 诊断趋势, diagnosis report, 问题率, 诊断次数]
  workflow: |
    执行: bash scripts/analyze_stats.sh
    支持的参数:
      --today     仅今天的数据
      --last Nd   最近 N 天 (如 --last 7d)
      --json      输出 JSON (供程序消费)
    如果用户问特定时间段 → 加对应参数
    如果用户问总览/概况 → 不加参数(全量)
  fixes: []

集群管理 (Cluster Management):
  keywords: [集群, cluster, 所有CVM, 所有节点, fleet, 批量检查, 多台服务器, 巡检, 节点, 健康巡检, 集群健康, cvm集群, 节点状态]
  workflow: |
    前置：本场景所有 tccli 命令通过 tencentcloud-infra 技能执行，
          必须确认该技能在当前会话已加载，且 OAuth 凭据有效。

    路由判断：

    1. 无集群配置（MEMORY.md 无 cluster_config 段落）→ 首次配置引导
       读 references/cluster-discovery.md，向用户展示以下引导词：
       ─────────────────────────────────────────────────────────
       我需要知道要管理哪些 CVM 实例。请选择配置方式：

       1. 标签过滤（推荐）：按服务标签批量选择，例如 Service=order-api
       2. 指定实例 ID：直接输入 ins-xxx,ins-yyy,ins-zzz
       3. 全量扫描：当前区域所有实例（⚠️ 大账户请谨慎）

       请告诉我：
       - 选哪种方式？
       - 实例所在区域（如 ap-guangzhou）？
       - 对应的标签键值 或 实例 ID 列表？
       ─────────────────────────────────────────────────────────
       收到回复后，通过 tencentcloud-infra 执行 DescribeInstances 并展示结果让用户确认，
       确认后写入 MEMORY.md cluster_config 段落。

    2. 有配置，用户要健康检查：
       → 读 references/cluster-quick-check.md（3 层快照，约 30 秒）
       → 读 references/cluster-health-score.md（生成评分报告）

    3. 发现异常，用户要深度分析：
       → 读 references/cluster-deep-analysis.md（按异常类型选 TAT 命令）

    4. 用户要修复：
       → 读 references/cluster-remediation.md（风险门控，串行执行）

    协作协议见 references/skill-collaboration-tencentcloud.md
  fixes: [references/cluster-remediation.md]
  risk_level: 🟡~🔴（依据具体操作，读 cluster-remediation.md 风险等级）

```

### Tier 2: 扩展场景

**如果 Tier 1 未匹配**:
1. 读取 `references/00-scenario-index.md` (60+ 个专业场景)
2. 搜索用户关键词(精确匹配 → 子串匹配 → 相关词匹配)
3. 如果匹配 → 执行工作流 | 如果未匹配 → 运行快速扫描脚本(通用健康检查)

---

## 🔧 使用工作流

1. **解析用户请求** → 提取关键词和意图
2. **匹配场景** → 先尝试 Tier 1,未匹配则回退到 Tier 2
3. **执行快速检查** (如果是通用问题) → 获取每个组件的状态
4. **执行深度分析** (按需):
   - **1 个组件标记** → 使用单组件深度分析(cpu/memory/disk/network)
   - **2+ 个组件标记** → 使用组合深度分析(关联分析)
   - **全部 OK 但慢** → 审查组合决策树
5. **呈现结果** → 摘要 + 根本原因 + 建议
6. **提供修复方案** → 如果用户想修复:
   - 查阅匹配场景的 `fixes` (Tier 1) 或 `Commands` (Tier 2)
   - 读取相关的 `commands/*.md` 文件
   - **检查风险等级**(见下方"风险管理"章节)
   - 呈现带风险指示器的行动计划
   - **🟢 低风险**(只读): 直接执行
   - **🟡 中风险**(服务重启、清理): 询问用户确认
   - **🔴 高风险**(配置变更、包安装): 需明确确认并显示影响警告

---

## 🔒 风险管理

**风险等级**:

```yaml
🟢 低风险 (自动执行):
  - 只读诊断: top, ps, df, free, netstat, journalctl
  - 不改变系统状态
  
🟡 中风险 (询问后执行):
  - 服务重启: systemctl restart, launchctl restart
  - 日志轮转、缓存清理
  - 临时文件删除 (来自 /tmp, /var/tmp)
  
🔴 高风险 (明确确认 + 显示影响):
  - 配置文件变更: /etc/sysctl.conf, sshd_config, 防火墙规则
  - 包安装/卸载: apt install, yum remove
  - 磁盘操作: 文件系统修复、分区变更
  - 进程终止: kill -9
```

**确认模板**(中/高风险):
```
⚠️ 风险等级: [🟡 中风险 / 🔴 高风险]
操作: [具体操作]
影响: [可能影响的服务/功能]
可逆: [是/否]

是否继续? (yes/no)
```

---

## 🚨 错误处理

**参考文件未找到**:
- 列出可用文件: `list_dir("references/")`
- 回退到基础检查(ps, top, free)
- 通知用户: "高级诊断不可用"

**命令执行失败**(工具不可用):
- 尝试替代命令(例如用 vmstat 替代 iostat)
- 跳过该检查并继续
- 在报告中注明: "工具 X 不可用,已跳过检查 Y"

**跨平台兼容性**: 详见"跨平台命令选择"章节中的操作系统检测和命令表

---

## 📋 快速参考

**决策逻辑**: 详见上方"快速/深度诊断工作流"章节

**快速模块** (commands/): `*-quick.md` 文件用于 10 秒分诊  
**深度模块** (commands/): `*-deep.md` 文件用于 20-60 秒分析  
**修复方案** (system-health/): 修复手册

---

## 🌐 跨平台命令选择

**执行命令前务必先检测操作系统**

**完整命令表**: 见 `references/00-scenario-index.md`

**快速参考**(最常用):
- 内存: Linux `free -h` | macOS `vm_stat` | Windows `wmic OS get TotalVisibleMemorySize`
- CPU: Linux `top -b -n 1` | macOS `top -l 1` | Windows `Get-Process | Sort CPU -Desc`
- 磁盘: Linux/macOS `df -h` | Windows `wmic logicaldisk get caption,size,freespace`

---

## 🔗 扩展资源

**当 Tier 1 未匹配时**:

```yaml
00-scenario-index.md:
  20 个类别中的 60+ 个专业场景
  搜索用户关键词,执行匹配的工作流
  
commands/ 目录:
  场景引用的 126 个命令
  每个命令文件包含 Linux/macOS/Windows 平台特定命令表
```

---

## 📚 参考文件

所有诊断参考文件位于 `references/` 目录:

### 快速模块(快速分诊)

```yaml
快速扫描脚本: 一体化健康检查 (3秒, Windows/Linux/macOS)
  - scripts/quick_scan.ps1: Windows PowerShell 版本
  - scripts/quick_scan.sh: Linux/macOS bash 版本
resource-saturation-quick.md: CPU/内存/磁盘/网络参考 (回退方案, 10秒)
system-logs-quick.md: 内核/OOM/文件系统/认证/服务错误 (10秒)
disk-smart-quick.md: 磁盘健康检查 (10秒)
hardware-health-quick.md: CPU 温度/内存/RAID/电池 (10秒)
time-sync.md: NTP 状态检查 (5秒)
```

### 集群诊断脚本（TAT 远端执行）

以下脚本**在远端 CVM 上运行**，由 Agent 在本地 base64 编码后通过 TAT `RunCommand --Content` 传入。
编码步骤参见 `references/skill-collaboration-tencentcloud.md`（⚡ 脚本优先路径）。

```yaml
scripts/cluster_os_snapshot.sh:
  用途: Layer 2B OS 快照，输出单行 KEY=VALUE，供 cluster_score.sh 评分
  超时: 30s

scripts/cluster_deep_cpu.sh:
  用途: CPU 深度分析（top 消费者、负载详情、cgroup throttling、IO wait）
  超时: 60s

scripts/cluster_deep_memory.sh:
  用途: 内存深度分析（top 消费者、meminfo、OOM 历史、swap 使用）
  超时: 60s

scripts/cluster_deep_disk.sh:
  用途: 磁盘深度分析（使用率、inode、大文件 ≥500MB、IO stats、logrotate 状态）
  超时: 90s

scripts/cluster_deep_ssh.sh:
  用途: SSH 深度分析（sshd 服务状态、监听端口、最近日志、配置关键行、失败记录）
  超时: 30s

scripts/cluster_deep_network.sh:
  用途: 网络深度分析（连接摘要、状态计数、接口统计、错误、DNS 解析测试）
  超时: 30s
```

### 深度模块(根本原因分析)

```yaml
资源饱和:
  - resource-saturation-deep-cpu.md
  - resource-saturation-deep-memory.md
  - resource-saturation-deep-disk.md
  - resource-saturation-deep-network.md
  - resource-saturation-deep-combined.md (多组件关联分析)
  
系统日志:
  - system-logs-deep-kernel.md
  - system-logs-deep-oom.md
  - system-logs-deep-fs.md
  - system-logs-deep-auth.md
  - system-logs-deep-service.md
  
硬件:
  - disk-smart-deep.md
  - hardware-health-deep.md
```

---

## 🤝 技能协作

### 与 `tencentcloud-infra` 技能的协作（集群管理）

本技能与 **tencentcloud-infra** 技能深度集成，支持腾讯云 CVM 集群级别的诊断与管理。

**触发词：** 集群、cluster、所有CVM、所有节点、fleet、批量检查、多台服务器

**集群管理工作流（约 35 秒）：**

```yaml
1. 检查 MEMORY.md 是否有 cluster_config
   → 无：读取 references/cluster-discovery.md，引导用户配置集群
   → 有（< 1小时）：直接使用缓存节点列表

2. 读取 references/cluster-quick-check.md，执行 3 层快照：
   - Layer 1：通过 tencentcloud-infra 调用 DescribeInstances
   - Layer 2A：通过 tencentcloud-infra 调用 GetMonitorData（云端指标）
   - Layer 2B（⚡ 脚本优先）：本地编码 scripts/cluster_os_snapshot.sh → 通过 tencentcloud-infra 调用 TAT RunCommand
     脚本不存在时回退到 cluster-quick-check.md 中的内联命令

3. 读取 references/cluster-health-score.md，计算评分和生成报告

4. 如有异常节点，询问是否深度分析
   → 是：读取 references/cluster-deep-analysis.md

5. 如有修复需求（重启节点/服务），读取 references/cluster-remediation.md
```

**所有云 API 操作由 tencentcloud-infra 技能执行，详见：**
`references/skill-collaboration-tencentcloud.md`

---

### 与 `health-check` 技能的协调

**范围划分**:
- **CVM Doctor** → 系统**性能**诊断(CPU/内存/磁盘/网络饱和)，以及集群节点诊断
- **Health Check** → LightClaw **平台**健康(安全审计、配置、日志、依赖)

**何时交叉引用**:

1. **CVM Doctor 检测到 LightClaw 进程异常**:
   ```
   如果异常进程名包含 "lightclaw" 或 "uvicorn":
     → 建议用户运行 health-check 进行平台专属诊断
   ```

2. **用户说通用的"检查系统"**:
   ```
   优先: CVM Doctor (快速模式)
   如果全部 OK → 可选建议: "性能健康。需要检查 LightClaw 平台吗?"
   ```

3. **发现宿主环境问题**:
   ```
   如果磁盘空间 < 10% 或系统运行时间 > 365 天:
     → CVM Doctor 提供详细的磁盘/资源分析
     → Health Check 报告为宿主环境风险因素
   ```

**交叉引用模板**:
```markdown
💡 检测到问题涉及 LightClaw 平台组件。
   建议运行平台健康检查:
   
   用户: "自检" 或 "体检" (触发 health-check 技能)
```

---

**最后更新**: 2026-04-22
**版本**: 3.3 (新增 Patrol 定期巡检 + Dashboard)
**兼容性**: Linux (完整), macOS (完整), Windows (基础)
