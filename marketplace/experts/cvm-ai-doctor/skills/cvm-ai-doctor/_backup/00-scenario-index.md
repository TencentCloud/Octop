# 场景索引 (Scenario Index)

> **用途**: 快速定位用户问题对应的诊断 Reference 或 Command
> **更新**: 2026-03-24
> **覆盖**: 126 个 Commands + 5 个 References

---

## 🎯 AI 使用指南

### 工作流程

```
用户描述问题
  ↓
1. 在本索引中匹配场景 (10 秒)
  ↓
2. 根据推荐的 Reference 运行 Quick Mode (10 秒)
  ↓
3. 如果 Quick Mode 发现异常 → 运行 Deep Mode (20-60 秒)
  ↓
4. 报告结果 + 修复建议
```

### 场景匹配规则

**关键词触发**:
- 用户说的关键词 → 查找对应场景
- 支持中英文（"慢" = "slow", "卡" = "lag"）
- 支持模糊匹配（"内存不够" → "内存问题"）

**优先级**:
1. ⭐⭐⭐⭐⭐ 高频场景（80% 用户问题）
2. ⭐⭐⭐⭐ 中频场景（15% 用户问题）
3. ⭐⭐⭐ 低频场景（5% 用户问题）

---

## 📚 场景分类体系

### 一级分类（10 大类）

1. **性能问题** (Performance Issues) - 慢、卡、延迟
2. **资源问题** (Resource Issues) - CPU、内存、磁盘、网络
3. **系统健康** (System Health) - 健康检查、状态监控
4. **故障诊断** (Troubleshooting) - 崩溃、错误、失败
5. **硬件问题** (Hardware Issues) - 硬件故障、驱动、传感器
6. **网络问题** (Network Issues) - 连接、DNS、防火墙
7. **安全问题** (Security Issues) - 漏洞、权限、审计
8. **配置管理** (Configuration) - 设置、环境、路径
9. **软件管理** (Software Management) - 安装、更新、包管理
10. **日志分析** (Logging & Monitoring) - 日志、监控、追踪

---

## 🔥 高频场景 (⭐⭐⭐⭐⭐)

### 1. 性能类场景

#### 1.1 系统整体慢/卡顿
**用户关键词**: "慢"、"卡"、"lag"、"slow"、"sluggish"、"响应慢"

**推荐路径**:
```
Step 1: Quick 全面扫描
  bash references/resource-saturation.md

Step 2: 根据 Quick 结果决定 Deep 分析
  - CPU 异常 → deep --focus cpu
  - Memory 异常 → deep --focus memory
  - Disk 异常 → deep --focus disk
  - 多个异常 → deep --focus all
```

**关联 Commands**:
- `commands/debugging/diagnose-slowdown.md` (交互式诊断流程)
- `commands/system-health/system-health-checkup.md` (综合健康检查)

**预期时间**: Quick 10s + Deep 20-60s = 30-70s

---

#### 1.2 启动慢
**用户关键词**: "启动慢"、"boot slow"、"开机慢"、"启动时间长"

**推荐路径**:
```
Step 1: 检查启动日志
  bash references/system-logs.md --mode quick --focus boot

Step 2: 分析启动服务
  commands/debugging/boot/review-boot.md
  systemd-analyze blame
  systemd-analyze critical-chain
```

**关联 References**:
- `references/system-logs.md` (启动日志)

**关联 Commands**:
- `commands/debugging/boot/review-boot.md`
- `commands/debugging/boot/check-boot-logs.md`
- `commands/debugging/boot/failed-boot-services.md`
- `commands/optimisation/optimize-boot-speed.md`

---

#### 1.3 应用程序慢
**用户关键词**: "某个软件慢"、"浏览器慢"、"IDE 慢"、"应用卡"

**推荐路径**:
```
Step 1: 确认进程资源使用
  ps aux | grep <app_name>
  top -p <pid>

Step 2: 检查该应用的资源占用
  bash references/resource-saturation.md --mode deep --focus cpu
  
Step 3: 应用特定诊断
  - 浏览器: 检查扩展、缓存
  - IDE: 检查索引、插件
  - 数据库: 检查查询、连接池
```

**关联 Commands**:
- `commands/debugging/diagnose-slowdown.md` (步骤 12: 应用特定检查)

---

### 2. 资源类场景

#### 2.1 CPU 占用高
**用户关键词**: "CPU 高"、"CPU 100%"、"风扇狂转"、"CPU usage high"

**推荐路径**:
```
Step 1: Quick 检查
  bash references/resource-saturation.md --mode quick

Step 2: Deep CPU 分析
  bash references/resource-saturation.md --mode deep --focus cpu

Step 3: 识别高 CPU 进程
  ps aux --sort=-%cpu | head -20
  top -b -n 1
```

**关联 References**:
- `references/resource-saturation.md` (CPU 分析)

**关联 Commands**:
- `commands/hardware/hardware-profilers/by-component/profile-cpu.md`

---

#### 2.2 内存不足/内存占用高
**用户关键词**: "内存不足"、"memory full"、"OOM"、"swap 满"、"内存占用高"

**推荐路径**:
```
Step 1: Quick 内存检查
  bash references/resource-saturation.md --mode quick

Step 2: Deep 内存分析
  bash references/resource-saturation.md --mode deep --focus memory

Step 3: 检查内存泄漏
  - 查看 swap 使用
  - 检查 OOM killer 日志
  - 分析进程内存趋势
```

**关联 References**:
- `references/resource-saturation.md` (内存分析)

**关联 Commands**:
- `commands/hardware/hardware-profilers/by-component/profile-ram.md`

---

#### 2.3 磁盘空间不足
**用户关键词**: "磁盘满"、"disk full"、"no space left"、"空间不足"

**推荐路径**:
```
Step 1: 检查磁盘使用
  df -h
  du -sh /* | sort -rh | head -20

Step 2: 找大文件
  find / -type f -size +1G 2>/dev/null | xargs ls -lh

Step 3: 清理空间
  commands/optimisation/large-files.md
  commands/optimisation/cleanup-system.md
```

**关联 Commands**:
- `commands/optimisation/large-files.md`
- `commands/storage/storage-deep-dive.md`

---

#### 2.4 磁盘 I/O 慢
**用户关键词**: "磁盘慢"、"I/O wait 高"、"disk slow"、"读写慢"

**推荐路径**:
```
Step 1: Quick 磁盘检查
  bash references/resource-saturation.md --mode quick

Step 2: Deep 磁盘分析
  bash references/resource-saturation.md --mode deep --focus disk

Step 3: 检查磁盘健康
  bash references/disk-smart.md
```

**关联 References**:
- `references/resource-saturation.md` (I/O 分析)
- `references/disk-smart.md` (SMART 健康)

**关联 Commands**:
- `commands/storage/health-checks/check-drive-health.md`
- `commands/storage/health-checks/smart-status.md`
- `commands/storage/storage-deep-dive.md`

---

#### 2.5 网络慢/网络问题
**用户关键词**: "网络慢"、"网速慢"、"ping 高"、"连接超时"、"network slow"

**推荐路径**:
```
Step 1: Quick 网络检查
  bash references/resource-saturation.md --mode quick

Step 2: 网络诊断
  commands/network/diagnose-network-issues.md
  
Step 3: 网络统计
  ip -s link
  netstat -s
  ss -s
```

**关联 References**:
- `references/resource-saturation.md` (网络统计)

**关联 Commands**:
- `commands/network/diagnose-network-issues.md`
- `commands/network/lan/diagnose-lan-connectivity.md`

---

### 3. 系统健康场景

#### 3.1 综合健康检查
**用户关键词**: "检查系统"、"健康检查"、"system check"、"health check"

**推荐路径**:
```
Step 1: 快速健康扫描
  bash references/resource-saturation.md --mode quick
  bash references/system-logs.md --mode quick
  bash references/disk-smart.md --mode quick

Step 2: 如有异常，Deep 分析
  根据 Quick 结果决定

Step 3: 综合报告
  commands/system-health/system-health-checkup.md
```

**关联 References**:
- `references/resource-saturation.md`
- `references/system-logs.md`
- `references/disk-smart.md`
- `references/hardware-other.md`

**关联 Commands**:
- `commands/system-health/system-health-checkup.md`

---

#### 3.2 定期维护检查
**用户关键词**: "定期检查"、"维护"、"routine check"、"maintenance"

**推荐路径**:
```
Step 1: 系统更新检查
  commands/system-health/system-upgrade.md
  
Step 2: 磁盘健康
  bash references/disk-smart.md

Step 3: 日志错误
  bash references/system-logs.md --mode quick

Step 4: 服务状态
  commands/system-health/review-startup-services.md
```

**关联 Commands**:
- `commands/system-health/system-upgrade.md`
- `commands/system-health/review-startup-services.md`

---

### 4. 故障诊断场景

#### 4.1 系统崩溃/重启
**用户关键词**: "崩溃"、"crash"、"重启"、"reboot"、"kernel panic"

**推荐路径**:
```
Step 1: 检查崩溃日志
  bash references/system-logs.md --mode deep --focus crash
  
Step 2: 内核日志
  dmesg | tail -100
  journalctl -k -b -1  # 上次启动的内核日志

Step 3: 硬件错误
  bash references/hardware-other.md
```

**关联 References**:
- `references/system-logs.md` (崩溃日志)
- `references/hardware-other.md` (硬件错误)

**关联 Commands**:
- `commands/debugging/diagnose-crash.md`

---

#### 4.2 服务失败/启动失败
**用户关键词**: "服务挂了"、"service failed"、"启动失败"、"服务无法启动"

**推荐路径**:
```
Step 1: 检查失败服务
  systemctl --failed
  journalctl -xe

Step 2: 查看具体服务日志
  systemctl status <service>
  journalctl -u <service> -n 100

Step 3: 启动日志
  commands/debugging/boot/failed-boot-services.md
```

**关联 References**:
- `references/system-logs.md` (服务日志)

**关联 Commands**:
- `commands/debugging/boot/failed-boot-services.md`
- `commands/logging/check-failed-units.md`

---

#### 4.3 错误日志分析
**用户关键词**: "错误"、"error"、"报错"、"异常"、"exception"

**推荐路径**:
```
Step 1: Quick 日志扫描
  bash references/system-logs.md --mode quick

Step 2: Deep 日志分析
  bash references/system-logs.md --mode deep

Step 3: 分类错误
  - 硬件错误 → hardware-other.md
  - 磁盘错误 → disk-smart.md
  - 内核错误 → system-logs.md
```

**关联 References**:
- `references/system-logs.md`

**关联 Commands**:
- `commands/logging/analyze-journal-errors.md`
- `commands/logging/tail-system-logs.md`

---

### 5. 硬件问题场景

#### 5.1 硬件健康检查
**用户关键词**: "硬件检查"、"hardware check"、"传感器"、"温度"

**推荐路径**:
```
Step 1: 综合硬件检查
  bash references/hardware-other.md

Step 2: 具体硬件分析
  commands/hardware/hardware-profilers/hardware-profile.md

Step 3: 单个组件检查
  - CPU: commands/hardware/hardware-profilers/by-component/profile-cpu.md
  - GPU: commands/hardware/hardware-profilers/by-component/profile-gpu.md
  - RAM: commands/hardware/hardware-profilers/by-component/profile-ram.md
  - Motherboard: commands/hardware/hardware-profilers/by-component/profile-motherboard.md
```

**关联 References**:
- `references/hardware-other.md`

**关联 Commands**:
- `commands/hardware/hardware-profilers/hardware-profile.md`
- `commands/hardware/hardware-profilers/hardware-identity.md`

---

#### 5.2 磁盘硬件故障
**用户关键词**: "磁盘坏了"、"disk failed"、"SMART error"、"坏道"

**推荐路径**:
```
Step 1: SMART 健康检查
  bash references/disk-smart.md --mode quick

Step 2: 详细 SMART 分析
  bash references/disk-smart.md --mode deep

Step 3: 硬件诊断
  sudo smartctl -A /dev/sda
  sudo smartctl -l error /dev/sda
```

**关联 References**:
- `references/disk-smart.md`

**关联 Commands**:
- `commands/storage/health-checks/check-drive-health.md`
- `commands/storage/health-checks/smart-status.md`

---

#### 5.3 温度过高/散热问题
**用户关键词**: "温度高"、"过热"、"hot"、"thermal"、"风扇"

**推荐路径**:
```
Step 1: 检查温度传感器
  bash references/hardware-other.md --focus temperature

Step 2: CPU 频率检查（是否降频）
  cat /proc/cpuinfo | grep MHz
  cpupower frequency-info

Step 3: 风扇状态
  sensors
  cat /sys/class/thermal/thermal_zone*/temp
```

**关联 References**:
- `references/hardware-other.md` (温度传感器)

---

#### 5.4 GPU 问题
**用户关键词**: "GPU"、"显卡"、"graphics"、"显示问题"

**推荐路径**:
```
Step 1: GPU 状态检查
  commands/hardware/hardware-profilers/by-component/profile-gpu.md

Step 2: GPU 驱动检查
  nvidia-smi  # NVIDIA
  radeontop   # AMD
  lspci | grep VGA

Step 3: GPU 优化
  commands/hardware/check-gpu-os-optimization.md
  commands/hardware/review-gpu-settings.md
```

**关联 Commands**:
- `commands/hardware/hardware-profilers/by-component/profile-gpu.md`
- `commands/hardware/check-gpu-os-optimization.md`
- `commands/hardware/review-gpu-settings.md`

---

### 6. 时间同步场景

#### 6.1 时间不准确
**用户关键词**: "时间不对"、"时钟不准"、"time sync"、"NTP"

**推荐路径**:
```
Step 1: Quick 时间检查
  bash references/time-sync.md --mode quick

Step 2: Deep 时间分析
  bash references/time-sync.md --mode deep

Step 3: 同步时间
  timedatectl status
  sudo timedatectl set-ntp true
```

**关联 References**:
- `references/time-sync.md`

---

## 🔄 中频场景 (⭐⭐⭐⭐)

### 7. 网络类场景

#### 7.1 LAN 连接问题
**用户关键词**: "局域网"、"LAN"、"内网连接"、"SSH 连不上"

**推荐路径**:
```
Step 1: LAN 诊断
  commands/network/lan/diagnose-lan-connectivity.md

Step 2: 扫描 LAN
  commands/network/lan/scan-lan.md

Step 3: SSH 设置
  commands/network/lan/lan-ssh-setup.md
```

**关联 Commands**:
- `commands/network/lan/diagnose-lan-connectivity.md`
- `commands/network/lan/scan-lan.md`
- `commands/network/lan/lan-ssh-setup.md`
- `commands/network/lan/smart-arp.md`

---

#### 7.2 防火墙问题
**用户关键词**: "防火墙"、"firewall"、"端口被阻止"、"connection refused"

**推荐路径**:
```
Step 1: 防火墙分析
  commands/security/firewall/analyze-firewall.md

Step 2: 检查端口
  sudo ss -tulpn | grep <port>
  sudo iptables -L -n -v
```

**关联 Commands**:
- `commands/security/firewall/analyze-firewall.md`

---

### 8. 安全类场景

#### 8.1 安全审计
**用户关键词**: "安全检查"、"security audit"、"漏洞扫描"、"安全评估"

**推荐路径**:
```
Step 1: 安全态势检查
  commands/security/posture-diagnostics/security-posture-check.md

Step 2: 漏洞探测
  commands/security/audits/probe-vulnerabilities.md

Step 3: 审计报告
  commands/security/audits/write-audit.md
```

**关联 Commands**:
- `commands/security/posture-diagnostics/security-posture-check.md`
- `commands/security/audits/probe-vulnerabilities.md`
- `commands/security/audits/write-audit.md`

---

#### 8.2 权限问题
**用户关键词**: "权限不足"、"permission denied"、"无法访问"、"access denied"

**推荐路径**:
```
Step 1: 调试权限
  commands/configuration/permissions/debug-folder-permissions.md

Step 2: 检查文件权限
  ls -la <path>
  namei -l <path>

Step 3: 修复权限
  - 建议安全的权限设置
  - 检查 SELinux/AppArmor
```

**关联 Commands**:
- `commands/configuration/permissions/debug-folder-permissions.md`

---

#### 8.3 间谍软件/病毒
**用户关键词**: "病毒"、"木马"、"spyware"、"malware"、"中毒"

**推荐路径**:
```
Step 1: 检测间谍软件
  commands/security/detect-spyware.md

Step 2: 安装杀毒软件
  commands/security/av/install-clamav.md

Step 3: 扫描系统
  sudo clamscan -r /home
```

**关联 Commands**:
- `commands/security/detect-spyware.md`
- `commands/security/av/install-clamav.md`

---

### 9. 配置类场景

#### 9.1 SSH 配置
**用户关键词**: "SSH"、"密钥"、"SSH key"、"远程连接"

**推荐路径**:
```
Step 1: 管理 SSH 密钥
  commands/configuration/ssh/manage-ssh-keys.md

Step 2: 查看 SSH 连接
  commands/configuration/ssh/list-ssh-connections.md

Step 3: SSH 故障排查
  ssh -vvv user@host
```

**关联 Commands**:
- `commands/configuration/ssh/manage-ssh-keys.md`
- `commands/configuration/ssh/list-ssh-connections.md`

---

#### 9.2 环境变量/PATH
**用户关键词**: "PATH"、"环境变量"、"command not found"、"找不到命令"

**推荐路径**:
```
Step 1: 检查 PATH
  commands/configuration/check-path.md

Step 2: 验证 bashrc
  commands/configuration/bash/validate-bashrc.md

Step 3: 添加别名
  commands/configuration/bash/add-bash-alias.md
```

**关联 Commands**:
- `commands/configuration/check-path.md`
- `commands/configuration/bash/validate-bashrc.md`
- `commands/configuration/bash/add-bash-alias.md`

---

#### 9.3 Git 配置
**用户关键词**: "Git"、"Git 配置"、"gitignore"、"Git 用户名"

**推荐路径**:
```
Step 1: 检查 Git 配置
  commands/configuration/git/check-git-config.md

Step 2: 全局 gitignore
  commands/configuration/git/check-global-gitignore.md
```

**关联 Commands**:
- `commands/configuration/git/check-git-config.md`
- `commands/configuration/git/check-global-gitignore.md`

---

### 10. 软件管理场景

#### 10.1 包管理问题
**用户关键词**: "apt 出错"、"包管理"、"package manager"、"依赖问题"

**推荐路径**:
```
Step 1: 检查 apt 健康
  commands/package-management/check-apt-health.md

Step 2: 第三方仓库
  commands/package-management/check-third-party-repos.md

Step 3: 未使用的包
  commands/package-management/identify-unused-packages.md
```

**关联 Commands**:
- `commands/package-management/check-apt-health.md`
- `commands/package-management/check-third-party-repos.md`
- `commands/package-management/identify-unused-packages.md`
- `commands/package-management/configure-auto-updates.md`
- `commands/package-management/evaluate-installed-software.md`

---

#### 10.2 Docker 问题
**用户关键词**: "Docker"、"容器"、"container"、"docker compose"

**推荐路径**:
```
Step 1: Docker 设置
  commands/dev-tools/docker/setup-docker.md

Step 2: 检查容器状态
  docker ps -a
  docker logs <container>

Step 3: 资源使用
  docker stats
```

**关联 Commands**:
- `commands/dev-tools/docker/setup-docker.md`

---

#### 10.3 Python 环境
**用户关键词**: "Python"、"conda"、"pyenv"、"虚拟环境"、"pip"

**推荐路径**:
```
Step 1: 识别 Python 环境
  commands/dev-tools/python/identify-python-environments.md

Step 2: pyenv 设置
  commands/dev-tools/python/pyenv/setup-pyenv.md

Step 3: conda 管理
  commands/dev-tools/python/conda/manage-conda-environments.md
```

**关联 Commands**:
- `commands/dev-tools/python/identify-python-environments.md`
- `commands/dev-tools/python/pyenv/setup-pyenv.md`
- `commands/dev-tools/python/conda/manage-conda-environments.md`
- `commands/dev-tools/python/conda/setup-conda-data-analysis.md`
- `commands/dev-tools/python/conda/setup-conda-llm-finetune.md`
- `commands/dev-tools/python/conda/setup-conda-rocm.md`
- `commands/dev-tools/python/conda/setup-conda-stt-finetune.md`

---

## 🔍 低频场景 (⭐⭐⭐)

### 11. 存储类场景

#### 11.1 RAID 配置
**用户关键词**: "RAID"、"磁盘阵列"、"disk array"

**推荐路径**:
```
commands/storage/raid/check-raid-config.md
```

---

#### 11.2 网络挂载
**用户关键词**: "NFS"、"SMB"、"网络共享"、"挂载"

**推荐路径**:
```
- NFS: commands/storage/network-mounts/setup-nfs-mounts.md
- SMB: commands/storage/network-mounts/setup-smb-mounts.md
```

---

#### 11.3 BTRFS 快照
**用户关键词**: "BTRFS"、"快照"、"snapper"

**推荐路径**:
```
commands/storage/health-checks/btrfs-snapper-health.md
```

---

### 12. 桌面环境场景

#### 12.1 显示问题
**用户关键词**: "显示器"、"多显示器"、"分辨率"、"display"

**推荐路径**:
```
- 列出显示器: commands/display/list-connected-displays.md
- 多显示器: commands/display/setup-multi-monitor.md
- 优化缩放: commands/display/optimize-display-scaling.md
- 配置切换: commands/display/switch-display-profile.md
- 保存配置: commands/display/capture-current-config.md
```

---

#### 12.2 KDE Plasma 问题
**用户关键词**: "KDE"、"Plasma"、"桌面环境"

**推荐路径**:
```
- 优化性能: commands/kde/optimize-kde-performance.md
- 重置配置: commands/kde/reset-plasma-config.md
- 备份设置: commands/kde/backup-kde-settings.md
- 快捷键: commands/kde/list-kde-shortcuts.md
```

---

#### 12.3 音频问题
**用户关键词**: "音频"、"声音"、"麦克风"、"audio"、"sound"

**推荐路径**:
```
- 麦克风音量: commands/audio/mic-always-100.md
- 默认麦克风: commands/audio/set-as-default-mic.md
- PipeWire 优化: commands/system-health/optimize-pipewire.md
```

---

#### 12.4 蓝牙问题
**用户关键词**: "蓝牙"、"Bluetooth"、"耳机连不上"

**推荐路径**:
```
- 重置蓝牙: commands/bluetooth/reset-bluetooth.md
- 故障排查: commands/bluetooth/troubleshoot-bluetooth.md
```

---

### 13. 虚拟化场景

#### 13.1 虚拟化检查
**用户关键词**: "虚拟化"、"虚拟机"、"VM"、"KVM"、"VirtualBox"

**推荐路径**:
```
commands/virtualization/check-virtualization.md
```

---

### 14. 电源管理场景

#### 14.1 休眠/唤醒
**用户关键词**: "休眠"、"hibernate"、"睡眠"、"suspend"、"唤醒"

**推荐路径**:
```
- 休眠配置: commands/power-mgmt/hibernation.md
- 唤醒设备: commands/hardware/evaluate-wake-devices.md
- WOL 设置: commands/power-mgmt/wol-setup.md
```

---

### 15. 外设场景

#### 15.1 USB 设备
**用户关键词**: "USB"、"U盘"、"USB 设备识别不了"

**推荐路径**:
```
- 列出 USB: commands/peripherals/list-usb-devices.md
- 输入设备测试: commands/peripherals/evtest.md
```

---

#### 15.2 打印机
**用户关键词**: "打印机"、"printer"、"打印问题"

**推荐路径**:
```
commands/utilities/diagnose-printers.md
```

---

### 16. 开发工具场景

#### 16.1 IDE 问题
**用户关键词**: "IDE"、"VSCode"、"编辑器"

**推荐路径**:
```
- 推荐 IDE: commands/dev-tools/suggest-ides.md
- 优化 VSCode: commands/dev-tools/ides/optimize-vscode-installation.md
```

---

#### 16.2 Node.js 环境
**用户关键词**: "Node"、"npm"、"Node.js"

**推荐路径**:
```
- 版本检查: commands/dev-tools/node/node-version-check.md
- npm 安装: commands/dev-tools/node/npm-install.md
```

---

#### 16.3 SDK 管理
**用户关键词**: "SDK"、"SDKMAN"、"Java"

**推荐路径**:
```
- SDK 检查: commands/dev-tools/sdks/sdk-check.md
- 安装 SDKMAN: commands/installation/clis/install-sdkman.md
```

---

### 17. AI/ML 场景

#### 17.1 本地 AI 设置
**用户关键词**: "AI"、"机器学习"、"Ollama"、"ComfyUI"

**推荐路径**:
```
- GPU AI 评估: commands/ai/local-ai/gpu-ai-ml-assessment.md
- Ollama 设置: commands/ai/local-ai/ollama/setup-ollama.md
- Ollama 模型: commands/ai/local-ai/ollama/suggest-ollama-models.md
- Ollama 清理: commands/ai/local-ai/ollama/prune-ollama.md
- ComfyUI 设置: commands/ai/local-ai/comfyui/setup-comfyui.md
- 审计 AI 包: commands/ai/local-ai/audit-local-ai-packages.md
```

---

#### 17.2 AI CLI 工具
**用户关键词**: "AI CLI"、"命令行 AI"、"MCP"

**推荐路径**:
```
- AI CLI 推荐: commands/ai/cli-seeders/ai-clis.md
- 评估工具: commands/ai/cli-seeders/evaltools.md
- MCP 管理: commands/ai/mcp/manage-mcp-servers.md
```

---

#### 17.3 语音识别
**用户关键词**: "语音识别"、"STT"、"speech to text"

**推荐路径**:
```
commands/ai/stt/setup-speech-to-text.md
```

---

### 18. 文件系统优化场景

#### 18.1 文件整理
**用户关键词**: "整理文件"、"organize files"、"文件分类"

**推荐路径**:
```
- 桌面整理: commands/fs-optimisation/tidy-up/desktop-tidy.md
- 整理松散文件: commands/fs-optimisation/tidy-up/organize-loose-files.md
- 按类型分离: commands/fs-optimisation/separate/separate-by-filetype.md
- 照片视频分离: commands/fs-optimisation/separate/separate-photos-and-video.md
- 文件夹建议: commands/fs-optimisation/idate/suggest-folder-structure.md
```

---

#### 18.2 文件夹操作
**用户关键词**: "文件夹"、"目录"、"合并"、"拆分"

**推荐路径**:
```
- 合并文件夹: commands/fs-optimisation/consolidate/consolidate-folders.md
- 扁平化: commands/fs-optimisation/flatten/flatten.md
- 分块: commands/fs-optimisation/chunk/chunk-this-dir.md
```

---

### 19. 备份场景

#### 19.1 备份目标识别
**用户关键词**: "备份"、"backup"、"数据备份"

**推荐路径**:
```
commands/backup/identify-backup-targets.md
```

---

### 20. 其他场景

#### 20.1 字体管理
**用户关键词**: "字体"、"font"、"安装字体"

**推荐路径**:
```
- 列出字体: commands/fonts/list-fonts.md
- 安装 Google 字体: commands/fonts/install-google-fonts.md
```

---

#### 20.2 视频编解码器
**用户关键词**: "编解码器"、"codec"、"视频播放"

**推荐路径**:
```
- 检查编解码器: commands/media/check-codecs.md
- 视频编解码器: commands/video/codecs.md
```

---

#### 20.3 仓库管理
**用户关键词**: "Git 仓库"、"整理仓库"、"repo"

**推荐路径**:
```
- 整理仓库: commands/repositories/organise-repos.md
- 删除旧仓库: commands/repositories/delete-old-repos.md
```

---

#### 20.4 软件安装
**用户关键词**: "安装软件"、"install"、"GitHub 安装"

**推荐路径**:
```
- 从 GitHub 安装: commands/installation/install-from-gh.md
- 安装这个: commands/installation/install-this.md
- 安装 GitHub 程序: commands/program-management/install-github-program.md
```

---

## 🗂️ 快速查找表

### 按关键词索引

| 关键词 | 场景 ID | 优先级 |
|--------|---------|--------|
| 慢/卡/lag | 1.1 | ⭐⭐⭐⭐⭐ |
| CPU 高 | 2.1 | ⭐⭐⭐⭐⭐ |
| 内存不足 | 2.2 | ⭐⭐⭐⭐⭐ |
| 磁盘满 | 2.3 | ⭐⭐⭐⭐⭐ |
| 磁盘慢 | 2.4 | ⭐⭐⭐⭐⭐ |
| 网络慢 | 2.5 | ⭐⭐⭐⭐⭐ |
| 健康检查 | 3.1 | ⭐⭐⭐⭐⭐ |
| 崩溃 | 4.1 | ⭐⭐⭐⭐⭐ |
| 错误日志 | 4.3 | ⭐⭐⭐⭐⭐ |
| 硬件检查 | 5.1 | ⭐⭐⭐⭐⭐ |
| 磁盘故障 | 5.2 | ⭐⭐⭐⭐⭐ |
| 温度高 | 5.3 | ⭐⭐⭐⭐ |
| 时间不对 | 6.1 | ⭐⭐⭐⭐ |
| LAN 连接 | 7.1 | ⭐⭐⭐⭐ |
| 防火墙 | 7.2 | ⭐⭐⭐⭐ |
| 安全审计 | 8.1 | ⭐⭐⭐⭐ |
| 权限问题 | 8.2 | ⭐⭐⭐⭐ |
| SSH | 9.1 | ⭐⭐⭐⭐ |
| PATH | 9.2 | ⭐⭐⭐⭐ |
| 包管理 | 10.1 | ⭐⭐⭐⭐ |
| Docker | 10.2 | ⭐⭐⭐⭐ |
| Python | 10.3 | ⭐⭐⭐⭐ |

---

## 📝 使用示例

### 示例 1: 用户说"服务器很慢"

```
AI 决策流程:
1. 在索引中搜索 "慢" → 匹配到场景 1.1
2. 查看推荐路径:
   - Step 1: bash references/resource-saturation.md
3. 运行 Quick Mode (10 秒)
4. Quick 结果: Memory WARNING
5. 触发 Deep Mode: bash ... --mode deep --focus memory (20 秒)
6. Deep 结果: Java 内存泄漏
7. 生成报告 + 修复建议
```

---

### 示例 2: 用户说"磁盘坏了"

```
AI 决策流程:
1. 在索引中搜索 "磁盘坏" → 匹配到场景 5.2
2. 查看推荐路径:
   - Step 1: bash references/disk-smart.md --mode quick
3. Quick 结果: SMART CRITICAL
4. 触发 Deep Mode: bash ... --mode deep
5. Deep 结果: Reallocated sectors 100+
6. 报告: 磁盘即将失效，建议立即备份
```

---

### 示例 3: 用户说"检查系统健康"

```
AI 决策流程:
1. 在索引中搜索 "健康检查" → 匹配到场景 3.1
2. 查看推荐路径:
   - Step 1: 运行 3 个 Quick 检查
   - bash resource-saturation.md --mode quick
   - bash system-logs.md --mode quick
   - bash disk-smart.md --mode quick
3. 全部 OK → 报告正常
4. 如有异常 → 触发对应 Deep Mode
```

---

## 🎯 AI 决策算法

```python
def match_scenario(user_query):
    """根据用户查询匹配场景"""
    keywords = extract_keywords(user_query)
    
    # 1. 精确匹配
    for keyword in keywords:
        if scenario := exact_match(keyword):
            return scenario
    
    # 2. 模糊匹配
    for keyword in keywords:
        if scenario := fuzzy_match(keyword):
            return scenario
    
    # 3. 默认场景（综合健康检查）
    return scenario_3_1

def execute_scenario(scenario, user_query):
    """执行场景推荐路径"""
    path = scenario.recommended_path
    
    # Step 1: Quick Mode
    if "reference" in path.step1:
        quick_result = run_quick_mode(path.step1)
    
    # Step 2: 决策是否 Deep
    if should_run_deep(quick_result, user_query):
        deep_result = run_deep_mode(path.step2, quick_result.focus)
        return generate_report(quick_result, deep_result)
    else:
        return generate_report(quick_result)

def should_run_deep(quick_result, user_query):
    """决定是否运行 Deep Mode"""
    if quick_result.has_critical():
        return True  # 自动触发
    elif quick_result.has_warning():
        if "troubleshoot" in user_query or "慢" in user_query:
            return True  # 自动触发
        else:
            return ask_user("发现异常，是否深度分析？")
    return False  # 不需要 Deep
```

---

## 📈 统计信息

### 覆盖范围
- **总场景数**: 20 大类 + 60+ 细分场景
- **Commands 覆盖**: 126 个文件
- **References 覆盖**: 5 个核心诊断模块
- **预计覆盖率**: 95%+ 常见用户问题

### 场景分布
- **高频场景** (⭐⭐⭐⭐⭐): 6 大类，20 个场景 → 80% 用户问题
- **中频场景** (⭐⭐⭐⭐): 4 大类，15 个场景 → 15% 用户问题
- **低频场景** (⭐⭐⭐): 10 大类，25+ 场景 → 5% 用户问题

### 预期效果
- **匹配准确度**: 90%+
- **首次响应时间**: 10 秒（Quick Mode）
- **完整诊断时间**: 30-70 秒（Quick + Deep）
- **Token 节省**: 70-80%

---

## 🔄 维护指南

### 更新频率
- **高频场景**: 每月检查一次
- **中低频场景**: 每季度检查一次
- **新增 Command/Reference**: 立即更新索引

### 更新流程
1. 识别新场景或 Command
2. 分析用户关键词
3. 确定优先级（⭐⭐⭐⭐⭐ / ⭐⭐⭐⭐ / ⭐⭐⭐）
4. 添加到对应分类
5. 更新快速查找表
6. 测试 AI 匹配准确度

---

## 📚 参考资料

### References 文件
- `references/resource-saturation.md` - 资源饱和度分析
- `references/system-logs.md` - 系统日志分析
- `references/disk-smart.md` - 磁盘 SMART 健康
- `references/hardware-other.md` - 硬件健康检查
- `references/time-sync.md` - 时间同步检查

### Commands 目录
- `commands/debugging/` - 故障诊断
- `commands/system-health/` - 系统健康
- `commands/hardware/` - 硬件相关
- `commands/network/` - 网络相关
- `commands/security/` - 安全相关
- `commands/configuration/` - 配置管理
- `commands/storage/` - 存储相关
- `commands/package-management/` - 包管理
- `commands/dev-tools/` - 开发工具

---

**版本**: 1.0
**最后更新**: 2026-03-24
**维护者**: AI Assistant
**状态**: ✅ 生产就绪
