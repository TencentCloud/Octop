# 场景索引 (Scenario Index)

> **用途**: Tier 2 场景路由表。Tier 1（SKILL.md 内置 10 场景）匹配不到时，在此搜索关键词定位诊断流程。
> **平台**: Linux (完整) | macOS (完整) | Windows (基本)
> **使用方式**: 搜索用户关键词 → 找到匹配场景 → 执行推荐路径

---

## 跨平台规则

执行前必须先检测 OS：`OS_TYPE=$(uname -s)`

| 资源 | Linux | macOS | Windows |
|------|-------|-------|---------|
| 内存 | `free -h` | `vm_stat` + `sysctl hw.memsize` | `wmic OS get TotalVisibleMemorySize,FreePhysicalMemory` |
| CPU | `lscpu` / `top -b -n 1` | `sysctl -n machdep.cpu.brand_string` / `top -l 1 -n 20` | PowerShell `Get-Process \| Sort CPU -Desc` |
| 磁盘 | `df -h` / `lsblk` | `df -h` / `diskutil list` | `wmic logicaldisk get caption,size,freespace` |
| 网络 | `ip addr` / `ss` | `ifconfig` / `netstat` | `ipconfig /all` / `netstat -e` |
| 日志 | `journalctl -p err` | `log show --predicate 'messageType == "error"'` | PowerShell `Get-WinEvent -FilterHashtable @{LogName='System'; Level=2}` |
| 服务 | `systemctl --failed` | `launchctl list \| grep '^\\-'` | `Get-Service \| Where Status -ne Running` |
| 包管理 | `apt install` | `brew install` | `winget install` |

详细命令表见各 `commands/*.md` 文件。

**Linux-only 场景**（无需跨平台适配）：PipeWire、BTRFS/Snapper、systemctl 相关深度功能。

---

## 高频场景 (⭐⭐⭐⭐⭐)

### 1.1 系统整体慢/卡顿
**关键词**: 慢、卡、lag、slow、sluggish、响应慢

**路径**: Quick 全扫 `resource-saturation-quick.md` → Deep on flagged component

**Commands**: `commands/debugging/diagnose-slowdown.md`, `commands/system-health/system-health-checkup.md`

---

### 1.2 启动慢
**关键词**: 启动慢、boot slow、开机慢、启动时间长

**路径**: `system-logs-quick.md` → 启动服务分析

**Commands**: `commands/debugging/boot/review-boot.md`, `commands/debugging/boot/check-boot-logs.md`, `commands/debugging/boot/failed-boot-services.md`, `commands/optimisation/optimize-boot-speed.md`

---

### 1.3 应用程序慢
**关键词**: 某个软件慢、浏览器慢、IDE 慢、应用卡

**路径**: 确认进程资源 → Deep CPU 分析 → 应用特定诊断

**Commands**: `commands/debugging/diagnose-slowdown.md`

---

### 2.1 CPU 占用高
**关键词**: CPU 高、CPU 100%、风扇狂转、CPU usage high

**路径**: `resource-saturation-quick.md` → `resource-saturation-deep-cpu.md` → 识别高 CPU 进程

**Commands**: `commands/hardware/hardware-profilers/by-component/profile-cpu.md`

---

### 2.2 内存不足/内存占用高
**关键词**: 内存不足、memory full、OOM、swap 满、内存占用高

**路径**: `resource-saturation-quick.md` → `resource-saturation-deep-memory.md` → swap/OOM killer

**Commands**: `commands/hardware/hardware-profilers/by-component/profile-ram.md`

---

### 2.3 磁盘空间不足
**关键词**: 磁盘满、disk full、no space left、空间不足

**路径**: `df -h` → 找大文件 → 清理

**Commands**: `commands/optimisation/large-files.md`, `commands/storage/storage-deep-dive.md`

---

### 2.4 磁盘 I/O 慢
**关键词**: 磁盘慢、I/O wait 高、disk slow、读写慢

**路径**: `resource-saturation-quick.md` → `resource-saturation-deep-disk.md` → SMART 检查

**Commands**: `commands/storage/health-checks/check-drive-health.md`, `commands/storage/health-checks/smart-status.md`, `commands/storage/storage-deep-dive.md`

---

### 2.5 网络慢/网络问题
**关键词**: 网络慢、网速慢、ping 高、连接超时、network slow

**路径**: `resource-saturation-quick.md` → 网络诊断

**Commands**: `commands/network/diagnose-network-issues.md`, `commands/network/lan/diagnose-lan-connectivity.md`

---

### 3.1 综合健康检查
**关键词**: 检查系统、健康检查、system check、health check

**路径**: 3 个 Quick 扫描 → 有异常则 Deep → 综合报告

**References**: `resource-saturation-quick.md`, `system-logs-quick.md`, `disk-smart-quick.md`, `hardware-health-quick.md`

**Commands**: `commands/system-health/system-health-checkup.md`

---

### 3.2 定期维护检查
**关键词**: 定期检查、维护、routine check、maintenance

**路径**: 系统更新 → 磁盘健康 → 日志错误 → 服务状态

**Commands**: `commands/system-health/system-upgrade.md`, `commands/system-health/review-startup-services.md`

---

### 4.1 系统崩溃/重启
**关键词**: 崩溃、crash、重启、reboot、kernel panic

**路径**: `system-logs-quick.md` → 内核日志 → 硬件错误

**References**: `system-logs-quick.md`, `hardware-health-quick.md`

**Commands**: `commands/debugging/diagnose-crash.md`

---

### 4.2 服务失败/启动失败
**关键词**: 服务挂了、service failed、启动失败、服务无法启动

**路径**: `systemctl --failed` → 服务日志 → 启动日志

**Commands**: `commands/debugging/boot/failed-boot-services.md`, `commands/logging/check-failed-units.md`

---

### 4.3 错误日志分析
**关键词**: 错误、error、报错、异常、exception

**路径**: `system-logs-quick.md` → `system-logs-deep` → 按类别分诊

**Commands**: `commands/logging/analyze-journal-errors.md`, `commands/logging/tail-system-logs.md`

---

### 5.1 硬件健康检查
**关键词**: 硬件检查、hardware check、传感器、温度

**路径**: `hardware-health-quick.md` → 具体组件

**Commands**: `commands/hardware/hardware-profilers/hardware-profile.md`, `commands/hardware/hardware-profilers/hardware-identity.md`

---

### 5.2 磁盘硬件故障
**关键词**: 磁盘坏了、disk failed、SMART error、坏道

**路径**: `disk-smart-quick.md` → `disk-smart-deep.md`

**Commands**: `commands/storage/health-checks/check-drive-health.md`, `commands/storage/health-checks/smart-status.md`

---

### 5.3 温度过高/散热问题
**关键词**: 温度高、过热、hot、thermal、风扇

**路径**: `hardware-health-quick.md` → CPU 频率 → 风扇状态

---

### 5.4 GPU 问题
**关键词**: GPU、显卡、graphics、显示问题

**路径**: GPU 状态 → 驱动检查 → GPU 优化

**Commands**: `commands/hardware/hardware-profilers/by-component/profile-gpu.md`, `commands/hardware/check-gpu-os-optimization.md`, `commands/hardware/review-gpu-settings.md`

---

### 6.1 时间不准确
**关键词**: 时间不对、时钟不准、time sync、NTP

**路径**: `time-sync.md` Quick → Deep

---

## 中频场景 (⭐⭐⭐⭐)

### 7.1 LAN 连接问题
**关键词**: 局域网、LAN、内网连接、SSH 连不上

**Commands**: `commands/network/lan/diagnose-lan-connectivity.md`, `commands/network/lan/scan-lan.md`, `commands/network/lan/lan-ssh-setup.md`, `commands/network/lan/smart-arp.md`

---

### 7.2 防火墙问题
**关键词**: 防火墙、firewall、端口被阻止、connection refused

**Commands**: `commands/security/firewall/analyze-firewall.md`

---

### 8.1 安全审计
**关键词**: 安全检查、security audit、漏洞扫描、安全评估

**Commands**: `commands/security/posture-diagnostics/security-posture-check.md`, `commands/security/audits/probe-vulnerabilities.md`, `commands/security/audits/write-audit.md`

---

### 8.2 权限问题
**关键词**: 权限不足、permission denied、无法访问、access denied

**Commands**: `commands/configuration/permissions/debug-folder-permissions.md`

---

### 8.3 间谍软件/病毒
**关键词**: 病毒、木马、spyware、malware、中毒

**Commands**: `commands/security/detect-spyware.md`, `commands/security/av/install-clamav.md`

---

### 9.1 SSH 配置
**关键词**: SSH、密钥、SSH key、远程连接

**Commands**: `commands/configuration/ssh/manage-ssh-keys.md`, `commands/configuration/ssh/list-ssh-connections.md`

---

### 9.2 环境变量/PATH
**关键词**: PATH、环境变量、command not found、找不到命令

**Commands**: `commands/configuration/check-path.md`, `commands/configuration/bash/validate-bashrc.md`, `commands/configuration/bash/add-bash-alias.md`

---

### 9.3 Git 配置
**关键词**: Git、Git 配置、gitignore、Git 用户名

**Commands**: `commands/configuration/git/check-git-config.md`, `commands/configuration/git/check-global-gitignore.md`

---

### 10.1 包管理问题
**关键词**: apt 出错、包管理、package manager、依赖问题

**Commands**: `commands/package-management/check-apt-health.md`, `commands/package-management/check-third-party-repos.md`, `commands/package-management/identify-unused-packages.md`, `commands/package-management/configure-auto-updates.md`, `commands/package-management/evaluate-installed-software.md`

---

### 10.2 Docker 问题
**关键词**: Docker、容器、container、docker compose

**Commands**: `commands/dev-tools/docker/setup-docker.md`

---

### 10.3 Python 环境
**关键词**: Python、conda、pyenv、虚拟环境、pip

**Commands**: `commands/dev-tools/python/identify-python-environments.md`, `commands/dev-tools/python/pyenv/setup-pyenv.md`, `commands/dev-tools/python/conda/manage-conda-environments.md`, `commands/dev-tools/python/conda/setup-conda-data-analysis.md`, `commands/dev-tools/python/conda/setup-conda-llm-finetune.md`, `commands/dev-tools/python/conda/setup-conda-rocm.md`, `commands/dev-tools/python/conda/setup-conda-stt-finetune.md`

---

## 低频场景 (⭐⭐⭐)

### 11.1 RAID 配置
**关键词**: RAID、磁盘阵列、disk array
**Commands**: `commands/storage/raid/check-raid-config.md`

### 11.2 网络挂载
**关键词**: NFS、SMB、网络共享、挂载
**Commands**: `commands/storage/network-mounts/setup-nfs-mounts.md`, `commands/storage/network-mounts/setup-smb-mounts.md`

### 11.3 BTRFS 快照 (Linux-only)
**关键词**: BTRFS、快照、snapper
**Commands**: `commands/storage/health-checks/btrfs-snapper-health.md`

---

### 12.1 显示问题
**关键词**: 显示器、多显示器、分辨率、display
**Commands**: `commands/display/list-connected-displays.md`, `commands/display/setup-multi-monitor.md`, `commands/display/optimize-display-scaling.md`, `commands/display/switch-display-profile.md`, `commands/display/capture-current-config.md`

### 12.2 KDE Plasma
**关键词**: KDE、Plasma、桌面环境
**Commands**: `commands/kde/optimize-kde-performance.md`, `commands/kde/reset-plasma-config.md`, `commands/kde/backup-kde-settings.md`, `commands/kde/list-kde-shortcuts.md`

### 12.3 音频问题
**关键词**: 音频、声音、麦克风、audio、sound
**Commands**: `commands/audio/mic-always-100.md`, `commands/audio/set-as-default-mic.md`, `commands/system-health/optimize-pipewire.md`

### 12.4 蓝牙问题
**关键词**: 蓝牙、Bluetooth、耳机连不上
**Commands**: `commands/bluetooth/reset-bluetooth.md`, `commands/bluetooth/troubleshoot-bluetooth.md`

---

### 13.1 虚拟化检查
**关键词**: 虚拟化、虚拟机、VM、KVM、VirtualBox
**Commands**: `commands/virtualization/check-virtualization.md`

---

### 14.1 休眠/唤醒
**关键词**: 休眠、hibernate、睡眠、suspend、唤醒
**Commands**: `commands/power-mgmt/hibernation.md`, `commands/hardware/evaluate-wake-devices.md`, `commands/power-mgmt/wol-setup.md`

---

### 15.1 USB 设备
**关键词**: USB、U盘、USB 设备识别不了
**Commands**: `commands/peripherals/list-usb-devices.md`, `commands/peripherals/evtest.md`

### 15.2 打印机
**关键词**: 打印机、printer、打印问题
**Commands**: `commands/utilities/diagnose-printers.md`

---

### 16.1 IDE 问题
**关键词**: IDE、VSCode、编辑器
**Commands**: `commands/dev-tools/suggest-ides.md`, `commands/dev-tools/ides/optimize-vscode-installation.md`

### 16.2 Node.js 环境
**关键词**: Node、npm、Node.js
**Commands**: `commands/dev-tools/node/node-version-check.md`, `commands/dev-tools/node/npm-install.md`

### 16.3 SDK 管理
**关键词**: SDK、SDKMAN、Java
**Commands**: `commands/dev-tools/sdks/sdk-check.md`, `commands/installation/clis/install-sdkman.md`

---

### 17.1 本地 AI 设置
**关键词**: AI、机器学习、Ollama、ComfyUI
**Commands**: `commands/ai/local-ai/gpu-ai-ml-assessment.md`, `commands/ai/local-ai/ollama/setup-ollama.md`, `commands/ai/local-ai/ollama/suggest-ollama-models.md`, `commands/ai/local-ai/ollama/prune-ollama.md`, `commands/ai/local-ai/comfyui/setup-comfyui.md`, `commands/ai/local-ai/audit-local-ai-packages.md`

### 17.2 AI CLI 工具
**关键词**: AI CLI、命令行 AI、MCP
**Commands**: `commands/ai/cli-seeders/ai-clis.md`, `commands/ai/cli-seeders/evaltools.md`, `commands/ai/mcp/manage-mcp-servers.md`

### 17.3 语音识别
**关键词**: 语音识别、STT、speech to text
**Commands**: `commands/ai/stt/setup-speech-to-text.md`

---

### 18.1 文件整理
**关键词**: 整理文件、organize files、文件分类
**Commands**: `commands/fs-optimisation/tidy-up/desktop-tidy.md`, `commands/fs-optimisation/tidy-up/organize-loose-files.md`, `commands/fs-optimisation/separate/separate-by-filetype.md`, `commands/fs-optimisation/separate/separate-photos-and-video.md`, `commands/fs-optimisation/idate/suggest-folder-structure.md`

### 18.2 文件夹操作
**关键词**: 文件夹、目录、合并、拆分
**Commands**: `commands/fs-optimisation/consolidate/consolidate-folders.md`, `commands/fs-optimisation/flatten/flatten.md`, `commands/fs-optimisation/chunk/chunk-this-dir.md`

---

### 19.1 备份目标识别
**关键词**: 备份、backup、数据备份
**Commands**: `commands/backup/identify-backup-targets.md`

---

### 20.1 字体管理
**关键词**: 字体、font、安装字体
**Commands**: `commands/fonts/list-fonts.md`, `commands/fonts/install-google-fonts.md`

### 20.2 视频编解码器
**关键词**: 编解码器、codec、视频播放
**Commands**: `commands/media/check-codecs.md`, `commands/video/codecs.md`

### 20.3 仓库管理
**关键词**: Git 仓库、整理仓库、repo
**Commands**: `commands/repositories/organise-repos.md`, `commands/repositories/delete-old-repos.md`

### 20.4 软件安装
**关键词**: 安装软件、install、GitHub 安装
**Commands**: `commands/installation/install-from-gh.md`, `commands/installation/install-this.md`, `commands/program-management/install-github-program.md`

---

## C 类：集群管理场景（需 tencentcloud-infra 技能协作）

> **前提**: 用户提到"集群"/"所有CVM"/"多台服务器"等关键词时进入此类场景。
> 所有云 API 调用通过 tencentcloud-infra 技能执行。
> 完整协作协议见 `references/skill-collaboration-tencentcloud.md`。

---

### C1 集群健康快速检查
**关键词**: 集群健康、集群状态、所有CVM状态、所有节点、cluster health、fleet check、批量检查
**路径**: `references/cluster-quick-check.md` → `references/cluster-health-score.md`
**协作技能**: tencentcloud-infra (DescribeInstances + GetMonitorData + TAT RunCommand)
**耗时**: 约 30 秒

---

### C2 集群深度诊断
**关键词**: 集群深度诊断、集群慢、集群异常原因、某节点详细、节点深度分析
**路径**: `references/cluster-deep-analysis.md`（在 C1 快速检查基础上执行）
**协作技能**: tencentcloud-infra (TAT RunCommand)
**耗时**: 约 60-120 秒（视节点数量）

---

### C3 集群健康评分
**关键词**: 集群评分、集群报告、健康分数、节点评分
**路径**: `references/cluster-health-score.md`（需要 C1 数据作为输入）
**协作技能**: —（纯计算，输入来自 C1）

---

### C4 集群节点发现/配置
**关键词**: 发现集群节点、配置集群、添加集群、集群节点列表、注册节点
**路径**: `references/cluster-discovery.md`
**协作技能**: tencentcloud-infra (DescribeInstances + DescribeAutomationAgentStatus)

---

### C5 集群节点修复
**关键词**: 重启集群节点、恢复节点、启动停止的实例、重启服务、ins- 重启
**路径**: `references/cluster-remediation.md`
**协作技能**: tencentcloud-infra (TAT RunCommand / RebootInstances / StartInstances)
**风险等级**: 🟡~🔴（需确认）

---

### C6 集群内存级联告警
**关键词**: 所有节点内存高、集群内存问题、多台OOM、内存级联
**路径**: `references/cluster-deep-analysis.md` § 模式 1（Memory Cascade）
**协作技能**: tencentcloud-infra (TAT RunCommand)

---

### C7 集群负载不均衡
**关键词**: 某节点特别忙、集群负载不均、负载倾斜、脑裂、split-brain
**路径**: `references/cluster-deep-analysis.md` § 模式 2（Load Asymmetry）
**协作技能**: tencentcloud-infra (CLB DescribeTargetHealth + TAT)

---

### C8 集群磁盘告警
**关键词**: 所有节点磁盘满、集群磁盘使用率高、多台磁盘告警
**路径**: `references/cluster-deep-analysis.md` § 模式 3（Correlated Disk Growth）
**协作技能**: tencentcloud-infra (TAT RunCommand)

---

**版本**: 2.1 (新增 C 类集群场景) | **更新**: 2026-05-08
