# 集群深度分析

> **当快速检查发现异常后，对问题节点或集群级关联模式进行深度诊断。**
> 快速检查（cluster-quick-check.md）完成后，用户要求深度分析时才执行本流程。

---

## 单节点深度诊断

当用户说"深度分析 <节点名>"或"为什么 <节点> CPU 这么高"时，
对该节点发送以下 TAT 命令（通过 tencentcloud-infra 技能执行）。

**命令按需选择，不需要全部执行——根据快速检查的异常类型选择：**

---

### CPU 高负载深度诊断

## ⚡ 脚本优先路径：cluster_deep_cpu.sh

若 `scripts/cluster_deep_cpu.sh` 存在，**Agent 先本地编码，再让 tencentcloud-infra 执行**：

```bash
# Step A — Agent 本地编码（Linux / macOS）
SKILL_DIR="<cvm-ai-doctor 技能目录>"
CONTENT=$(base64 -w 0 < "$SKILL_DIR/scripts/cluster_deep_cpu.sh")
```
```powershell
# Step A — Agent 本地编码（Windows PowerShell）
$SKILL_DIR = "<cvm-ai-doctor 技能目录>"
$CONTENT = [Convert]::ToBase64String([IO.File]::ReadAllBytes("$SKILL_DIR\scripts\cluster_deep_cpu.sh"))
```
```bash
# Step B — 让 tencentcloud-infra 执行
tccli tat RunCommand \
  --region <region> \
  --InstanceIds '["ins-xxx"]' \
  --CommandType SHELL \
  --Timeout 60 \
  --Content "<Step A 的输出>"
```

> 若脚本不存在，使用下方内联命令。

**回退：内联命令**

```bash
# 找出最耗 CPU 的进程
ps aux --sort=-%cpu | head -20

# 实时负载详情（非交互，bat 模式）
top -bn1 | head -30

# 检查是否有 CPU throttling（容器场景）
cat /sys/fs/cgroup/cpu/cpu.stat 2>/dev/null | head -5 || echo "no-cgroup"

# 检查 IO wait（是否是磁盘 IO 导致的 CPU 等待）
iostat -x 1 3 2>/dev/null | tail -20 || vmstat 1 3
```

---

### 内存高使用率深度诊断

## ⚡ 脚本优先路径：cluster_deep_memory.sh

若 `scripts/cluster_deep_memory.sh` 存在，**Agent 先本地编码，再让 tencentcloud-infra 执行**：

```bash
# Step A — Agent 本地编码（Linux / macOS）
SKILL_DIR="<cvm-ai-doctor 技能目录>"
CONTENT=$(base64 -w 0 < "$SKILL_DIR/scripts/cluster_deep_memory.sh")
```
```powershell
# Step A — Agent 本地编码（Windows PowerShell）
$SKILL_DIR = "<cvm-ai-doctor 技能目录>"
$CONTENT = [Convert]::ToBase64String([IO.File]::ReadAllBytes("$SKILL_DIR\scripts\cluster_deep_memory.sh"))
```
```bash
# Step B — 让 tencentcloud-infra 执行
tccli tat RunCommand \
  --region <region> \
  --InstanceIds '["ins-xxx"]' \
  --CommandType SHELL \
  --Timeout 60 \
  --Content "<Step A 的输出>"
```

> 若脚本不存在，使用下方内联命令。

**回退：内联命令**

```bash
# 找出最耗内存的进程
ps aux --sort=-%mem | head -20

# 内存详情（包含 Buffers/Cached/Swap）
free -m && cat /proc/meminfo | grep -E 'MemTotal|MemFree|Cached|SwapTotal|SwapFree|Shmem'

# 是否有 OOM kill 记录
dmesg 2>/dev/null | grep -i 'oom\|killed' | tail -10

# Swap 使用量
swapon --show 2>/dev/null || cat /proc/swaps
```

---

### 磁盘高使用率深度诊断

## ⚡ 脚本优先路径：cluster_deep_disk.sh

若 `scripts/cluster_deep_disk.sh` 存在，**Agent 先本地编码，再让 tencentcloud-infra 执行**：

```bash
# Step A — Agent 本地编码（Linux / macOS）
SKILL_DIR="<cvm-ai-doctor 技能目录>"
CONTENT=$(base64 -w 0 < "$SKILL_DIR/scripts/cluster_deep_disk.sh")
```
```powershell
# Step A — Agent 本地编码（Windows PowerShell）
$SKILL_DIR = "<cvm-ai-doctor 技能目录>"
$CONTENT = [Convert]::ToBase64String([IO.File]::ReadAllBytes("$SKILL_DIR\scripts\cluster_deep_disk.sh"))
```
```bash
# Step B — 让 tencentcloud-infra 执行
tccli tat RunCommand \
  --region <region> \
  --InstanceIds '["ins-xxx"]' \
  --CommandType SHELL \
  --Timeout 90 \
  --Content "<Step A 的输出>"
```

> 若脚本不存在，使用下方内联命令。

**回退：内联命令**

```bash
# 找出最大的目录
du -sh /var/log/* /home/* /tmp/* /opt/* 2>/dev/null | sort -hr | head -20

# 根分区大文件
find / -maxdepth 5 -type f -size +500M 2>/dev/null | head -10

# 磁盘 IO 详情
df -h && iostat -x 1 3 2>/dev/null | tail -20

# 检查 inode 使用情况（inode 耗尽也会导致磁盘满报错）
df -i | head -10
```

---

### SSH 服务异常深度诊断

## ⚡ 脚本优先路径：cluster_deep_ssh.sh

若 `scripts/cluster_deep_ssh.sh` 存在，**Agent 先本地编码，再让 tencentcloud-infra 执行**：

```bash
# Step A — Agent 本地编码（Linux / macOS）
SKILL_DIR="<cvm-ai-doctor 技能目录>"
CONTENT=$(base64 -w 0 < "$SKILL_DIR/scripts/cluster_deep_ssh.sh")
```
```powershell
# Step A — Agent 本地编码（Windows PowerShell）
$SKILL_DIR = "<cvm-ai-doctor 技能目录>"
$CONTENT = [Convert]::ToBase64String([IO.File]::ReadAllBytes("$SKILL_DIR\scripts\cluster_deep_ssh.sh"))
```
```bash
# Step B — 让 tencentcloud-infra 执行
tccli tat RunCommand \
  --region <region> \
  --InstanceIds '["ins-xxx"]' \
  --CommandType SHELL \
  --Timeout 30 \
  --Content "<Step A 的输出>"
```

> 若脚本不存在，使用下方内联命令。

**回退：内联命令**

```bash
# sshd 服务详情
systemctl status sshd --no-pager -l 2>/dev/null || service ssh status

# 最近 sshd 日志
journalctl -u sshd -n 50 --no-pager 2>/dev/null || \
  tail -50 /var/log/auth.log 2>/dev/null || \
  tail -50 /var/log/secure 2>/dev/null

# sshd 是否监听端口
ss -tlnp | grep ':22\|:2222'
```

---

### 网络异常深度诊断

## ⚡ 脚本优先路径：cluster_deep_network.sh

若 `scripts/cluster_deep_network.sh` 存在，**Agent 先本地编码，再让 tencentcloud-infra 执行**：

```bash
# Step A — Agent 本地编码（Linux / macOS）
SKILL_DIR="<cvm-ai-doctor 技能目录>"
CONTENT=$(base64 -w 0 < "$SKILL_DIR/scripts/cluster_deep_network.sh")
```
```powershell
# Step A — Agent 本地编码（Windows PowerShell）
$SKILL_DIR = "<cvm-ai-doctor 技能目录>"
$CONTENT = [Convert]::ToBase64String([IO.File]::ReadAllBytes("$SKILL_DIR\scripts\cluster_deep_network.sh"))
```
```bash
# Step B — 让 tencentcloud-infra 执行
tccli tat RunCommand \
  --region <region> \
  --InstanceIds '["ins-xxx"]' \
  --CommandType SHELL \
  --Timeout 30 \
  --Content "<Step A 的输出>"
```

> 若脚本不存在，使用下方内联命令。

**回退：内联命令**

```bash
# 连接状态摘要
ss -s

# TCP 连接详情（排除 ESTABLISHED，只看异常状态）
ss -nt state CLOSE-WAIT | wc -l
ss -nt state TIME-WAIT | wc -l
ss -nt state FIN-WAIT-1 | wc -l

# 网络错误统计
ip -s link show | grep -A2 'errors\|dropped'

# DNS 解析时延
time dig +short google.com 2>/dev/null || time nslookup google.com 2>/dev/null
```

### 系统日志快速扫描（综合）

```bash
# 最近 1 小时的 ERROR/CRITICAL 日志
journalctl --since "1 hour ago" -p err -n 50 --no-pager 2>/dev/null || \
  tail -200 /var/log/syslog 2>/dev/null | grep -iE 'error|critical|fatal' | tail -30

# 系统重启记录
last reboot 2>/dev/null | head -5
```

---

## 5 种跨节点关联分析模式

当快速检查发现多个节点同时异常时，根据模式选择性执行深度分析。

---

### 模式 1：内存级联压力（Memory Cascade）

**触发条件：** ≥ 3 个节点 `mem_pct > 80%`（同时）

**假设：** 共享后端资源（DB/Cache）压力传导至所有前端节点

**诊断步骤：**

1. 对高内存节点执行 TAT（通过 tencentcloud-infra）：
   ```bash
   ps aux --sort=-%mem | head -10 | awk '{print $1,$2,$4,$11}'
   ```

2. 对比各节点 top memory 进程：
   - **相同进程名**（如 `java`/`node`/`python`）→ 怀疑应用层内存泄漏
   - **不同进程名** → 怀疑共享后端资源饱和

3. 若怀疑共享 DB/Cache，通过 tencentcloud-infra 检查相关实例：
   ```bash
   # MySQL 实例监控（假设有单独的 CDB）
   tccli monitor GetMonitorData \
     --Namespace QCE/CDB \
     --MetricName Connections \
     --Instances '[{"Dimensions":[{"Name":"InstanceId","Value":"cdb-xxx"}]}]' \
     --Period 300 --StartTime "..." --EndTime "..."

   # Redis 监控
   tccli monitor GetMonitorData \
     --Namespace QCE/REDIS_MEM \
     --MetricName CpuUsage \
     --Instances '[{"Dimensions":[{"Name":"instanceid","Value":"crs-xxx"}]}]' \
     --Period 300 --StartTime "..." --EndTime "..."
   ```

**结论模板：**
```
🔍 模式 1：内存级联压力
- 受影响节点：[order-api-1, order-api-2, order-api-3]
- 各节点 top 内存进程均为：java (订单服务)
- 假设：应用存在内存泄漏，需查看最近部署记录
- 建议：① 检查近期代码变更 ② 滚动重启服务（见 cluster-remediation.md）
```

---

### 模式 2：负载不均衡（Load Asymmetry）

**触发条件：** `MAX(load_ratio) - MIN(load_ratio) > 0.5`（正常节点间）
且只有 1-2 个节点高负载

**假设：** 负载均衡配置失效，流量集中打到少数节点

**诊断步骤：**

1. 通过 tencentcloud-infra 检查负载均衡器后端状态：
   ```bash
   tccli clb DescribeTargetHealth \
     --LoadBalancerId lb-xxx \
     --ListenerIds '["lbl-xxx"]'
   ```

2. 在高负载节点执行 TAT，查看连接数：
   ```bash
   ss -nt state ESTABLISHED | wc -l
   netstat -n | grep ESTABLISHED | wc -l 2>/dev/null
   ```

3. 对比高负载节点和正常节点的连接数差异

**结论模板：**
```
🔍 模式 2：负载不均衡
- 高负载节点：[order-api-3]（load_ratio=1.8），其余节点均 < 0.3
- order-api-3 ESTABLISHED 连接：1240，其余节点均 < 50
- 假设：CLB 后端健康检查异常，order-api-3 承接了所有流量
- 建议：① 检查 CLB 后端健康状态 ② 确认 order-api-1/2 服务进程正常
```

---

### 模式 3：相关磁盘增长（Disk Growth Correlation）

**触发条件：** ≥ 2 个节点 `disk_root_pct > 75%`

**假设：** 统一的日志策略失效，所有节点日志未被清理

**诊断步骤：**

1. 对高磁盘节点执行 TAT（通过 tencentcloud-infra）：
   ```bash
   du -sh /var/log/* 2>/dev/null | sort -hr | head -10
   find /var/log -name "*.log" -mtime -1 2>/dev/null | xargs du -sh 2>/dev/null | sort -hr | head -5
   ```

2. 对比各节点的大文件目录
3. 检查 logrotate 配置是否正常：
   ```bash
   logrotate --debug /etc/logrotate.conf 2>&1 | tail -20
   ```

**结论模板：**
```
🔍 模式 3：相关磁盘增长
- 受影响节点：[order-api-2, order-api-3]（磁盘 78%, 82%）
- 两节点最大目录均为：/var/log/nginx（分别 15GB, 18GB）
- 最近修改时间：今天（access_log 持续增长）
- logrotate 最后运行：7 天前（异常）
- 建议：强制执行日志轮转（logrotate -f /etc/logrotate.conf），设置每日自动清理
```

---

### 模式 4：网络退化集群（Network Degradation）

**触发条件：** ≥ 2 个节点报告网络相关异常（ss 异常连接数高/DNS 超时）

**诊断步骤：**

1. 对多个节点执行 TAT，收集网络诊断：
   ```bash
   ss -s 2>/dev/null | grep -E 'TCP|UDP'; \
   ip -s link show 2>/dev/null | grep -A1 'errors:'; \
   echo "CLOSE_WAIT: $(ss -nt state CLOSE-WAIT 2>/dev/null | wc -l)"; \
   echo "TIME_WAIT: $(ss -nt state TIME-WAIT 2>/dev/null | wc -l)"
   ```

2. 检查是否所有节点属于同一可用区（若是，可能是 AZ 级问题）
3. 通过 tencentcloud-infra 检查安全组是否被误修改：
   ```bash
   tccli vpc DescribeSecurityGroups --SecurityGroupIds '["sg-xxx"]'
   ```

---

### 模式 5：服务失效级联（Service Failure Cascade）

**触发条件：** 相同 systemd 服务在 ≥ 2 个节点同时失效（TAT 快照中 SSH=inactive 或 deep 检查发现）

**诊断步骤：**

1. 对问题节点执行 TAT，收集服务状态：
   ```bash
   systemctl status <service_name> --no-pager -l 2>/dev/null | tail -30; \
   journalctl -u <service_name> --since "1 hour ago" -n 30 --no-pager 2>/dev/null
   ```

2. 检查最近部署时间：
   ```bash
   who /var/log/wtmp 2>/dev/null | tail -10
   ls -lt /etc/systemd/system/ | head -10
   ```

3. 检查依赖服务（如数据库连接失败导致应用 crash）

---

## 深度分析报告格式

```
## 深度分析报告 — <节点名/模式名>
时间：<YYYY-MM-DD HH:MM>

### 诊断结论
<根因假设：一句话>

### 证据
- <具体数据1>
- <具体数据2>

### 影响范围
- 受影响节点：[...]
- 影响时长估算：<X 分钟/小时>

### 修复建议
1. 🟡 [立即] <操作1>
2. 🟡 [今天内] <操作2>
3. 🟢 [本周] <操作3>

> 执行修复请参考 references/cluster-remediation.md
```

---

## 历史趋势分析（按需）

若用户要求查看趋势（"这台服务器 CPU 过去一天怎么样"），通过 tencentcloud-infra 拉取历史指标：

```bash
# 过去 24 小时，每 1 小时一个点
tccli monitor GetMonitorData \
  --Namespace QCE/CVM \
  --MetricName CpuUsage \
  --Period 3600 \
  --StartTime "<24小时前>" \
  --EndTime "<当前时间>" \
  --Instances '[{"Dimensions":[{"Name":"InstanceId","Value":"ins-xxx"}]}]'
```

将 DataPoints 数组格式化为简单表格，供用户判断趋势。
