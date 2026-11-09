---
summary: "常见故障处置手册：内存/CPU 负载/磁盘/网络/服务/时间同步，每类含取证、判定、处置、验证"
read_when:
  - 诊断出具体症状需要处置方案
  - 用户要求"怎么修""能不能清理""要不要重启"
---

# RUNBOOK：常见故障处置

> 所有处置都遵循 `SOUL.md` 的门控规则：🟡 需确认，🔴 需明确说出实例 ID。
> 每节末尾的「验证」必须执行完才能报告完成。

## 1. 内存持续增长 / 接近打满

**取证**

```bash
free -m                                  # 看 available，不要只看 free
ps -eo pid,ppid,pmem,rss,comm --sort=-rss | head -10
cat /proc/meminfo | egrep 'MemAvailable|Cached|Slab|SReclaimable'
dmesg -T | grep -i 'killed process'      # 是否已发生 OOM
```

**判定**

| 现象 | 结论 | 走向 |
|---|---|---|
| `available` 仍 > 15% 且 `buff/cache` 占大头 | 不是真紧张，缓存可回收 | 不改，继续观察 |
| 单进程 RSS 单调增长、重启后归零 | 进程内存泄漏 | 1.1 |
| 无单进程异常但 `Slab/SReclaimable` 很大 | 内核对象堆积（dentry/inode） | 1.2 |
| 已出现 `killed process` | 已发生 OOM | 1.1 + 立即扩容评估 |

**处置**

- **1.1 泄漏进程**（🟡）：先重启该服务（不是整机），观察 RSS 是否回落；回落 → 泄漏确认，建议上报研发 + 临时加 `systemd` 内存上限或定时重载
- **1.2 Slab 堆积**（🟡）：`echo 2 > /proc/sys/vm/drop_caches` 只回收可回收部分；持续性堆积查 `slabtop -o | head`
- **1.3 容量不足**（🔴）：给出规格建议（当前 X GB / 峰值 Y GB / 建议 Z GB），改规格需停机

**验证**：`free -m` 的 `available` 回升；泄漏场景观察 10 分钟 RSS 曲线是否持平。

## 2. CPU 高 / 负载高（load > 核数）

**先分清 CPU 高还是 IO 等待高。**

```bash
cat /proc/loadavg
top -bn1 | head -15
vmstat 1 3          # 关键看 r（可运行队列）与 wa（IO 等待）
mpstat -P ALL 1 2   # 单核是否被单个进程占满
```

| 现象 | 结论 |
|---|---|
| `us+sy` 高、`r` 大 | CPU 真忙：找 top 进程 |
| `wa` 高、`r` 不大 | IO 慢：查磁盘/网络存储 |
| `sy` 异常高（>30%） | 系统调用/软中断：查 `ss -s`、网卡中断 |
| load 高但 CPU 空闲 | 大量 D 状态进程（`ps -eo stat,comm | grep '^D'`） |

**处置**

- 单进程打满（🟡）：先确认是否业务预期（压测/批量任务）；非预期 → 限流或（经确认）重启该进程
- 软中断高（🟢 只读定位）：`cat /proc/softirqs`、`ethtool -S eth0 | grep -i drop`，多队列/中断绑定建议交研发
- 实例规格不足（🔴）：给"当前峰值 / 建议规格"结论，改配需停机

**验证**：`vmstat 1 3` 的 `r` 回落、`top` 首进程 CPU 下降；load 有 5–15 分钟滞后，不能立刻判定。

## 3. 磁盘满 / 删了不释放

完整判定与处置见 `RUNBOOK-disk-full.md`（差值判定 → 文件多 / 删除未释放 / inode 满）。

速查：

```bash
df -h / ; df -i /
du -xhd1 / | sort -h | tail -6
lsof +L1 | grep -i deleted
```

**验证**：`df -h` 已用下降；若走了重开句柄，确认 `lsof +L1` 不再列出该文件。

## 4. 网络异常（连不上 / 时通时不通 / 大量超时）

**分层排查，别一上来改安全组。**

```bash
ss -s                                   # TIME_WAIT / orphaned 是否异常
ss -tn state established | wc -l        # 连接数
ip -s link | grep -A1 errors            # 网卡 errors/dropped
cat /proc/sys/net/netfilter/nf_conntrack_count 2>/dev/null
getent hosts <目标域名>                  # DNS
```

| 层 | 检查 | 结论 |
|---|---|---|
| DNS | `getent hosts` / `cat /etc/resolv.conf` | 解析失败 → 改 resolv.conf 或内网 DNS |
| 本机监听 | `ss -tlnp` | 端口没监听 → 服务问题，不是网络 |
| 安全组/ACL | `tccli cvm DescribeSecurityGroups` + 实例绑定 | 规则缺失/方向反了 |
| 路由/NAT | `ip route`、`traceroute` | 出网不通 |
| 连接数 | `ss -s` TIME_WAIT 暴涨 | 短连接风暴，建议连接池/keepalive |

**处置**

- 安全组缺规则（🔴）：必须列出"端口/源 IP/方向"三要素让用户确认后再改
- conntrack 打满（🟡）：`dmesg | grep -i conntrack` 确认后调 `nf_conntrack_max`
- 服务没监听（🟡）：回到第 6 节处理服务

**验证**：从同 VPC 另一台机器 `telnet <ip> <port>` 或 `curl -sv`；再复采 `ss -s`。

## 5. DNS / 时间同步异常

```bash
timedatectl                      # NTPSynchronized
chronyc tracking 2>/dev/null || ntpq -p 2>/dev/null
cat /etc/resolv.conf
```

时间漂移 > 5 分钟会导致证书校验、鉴权、日志错乱（也是"监控时间对不上"的常见原因）。

**处置**（🟡）：`systemctl restart chronyd` / 重新指向内网 NTP；改完立即 `timedatectl` 验证 `NTPSynchronized: yes`。

## 6. 服务异常（failed / 反复重启）

```bash
systemctl --failed
systemctl status <unit> --no-pager -l
journalctl -u <unit> -n 80 --no-pager
systemctl show <unit> -p NRestarts
```

**判定**

| 现象 | 结论 |
|---|---|
| `NRestarts` 持续增长 | 启动即崩，看日志首行报错 |
| `status=203/EXEC` | 可执行文件/路径错误 |
| `status=226/NAMESPACE` | 权限/挂载命名空间问题 |
| OOM killed | 回到第 1 节 |

**处置**

- 配置错误导致起不来（🟡）：先备份当前配置，再回滚到上一个可用版本，`systemctl daemon-reload && restart`
- 端口被占（🟢 定位 + 🟡 处置）：`ss -tlnp | grep :<port>` 找到占用进程，经确认后再停

**验证**：`systemctl is-active` = active，且 `NRestarts` 不再增长；业务探针（curl/端口）通过。

## 7. 实例状态异常（控制台显示异常/无法登录）

| 状态 | 含义 | 处置 |
|---|---|---|
| `STOPPED` | 已关机 | 需用户确认后再 `StartInstances`（🔴） |
| `REBOOTING` / `PENDING` | 中间态 | 等待 3–5 分钟再查，不要连续下发操作 |
| `RUNNING` 但连不上 | 网络/服务/密钥问题 | 回到第 4 节；VNC 登录看是否系统层卡住 |

**验证**：`tccli cvm DescribeInstances` 状态回到 `RUNNING`，且 `tat-exec.sh ... -- uptime` 能拿到输出。

## 通用收尾

1. 任何变更后**重新采集同一组指标**，比对前后数值
2. 报告写明：改了什么 / 依据 / 当前状态 / 遗留风险
3. 同类隐患顺手排查（同标签/同镜像的其他实例是否有同样特征），给出列表而不是笼统建议
