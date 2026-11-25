---
summary: "磁盘使用率接近 100% 时的判定与处置手册：区分「文件太多」与「删除未释放」"
read_when:
  - 巡检发现磁盘 warning / critical
  - 用户反馈磁盘满、空间不足
---

# RUNBOOK：磁盘接近 100%

## 适用症状

- 巡检 `--- DISK CHECK ---` 段 Status 为 `warning` 或 `critical`
- 用户说"磁盘满了""空间不足""删了文件还是没释放"
- 监控显示磁盘使用率持续上涨

## 第一步：先分清是哪种满

不要看到 90% 就直接删文件。**先做差值判定**，这一步决定了后面完全不同的处置路径。

```bash
df -h /
du -sh /var/log/* 2>/dev/null | sort -h | tail -5
du -sh /var/lib/* 2>/dev/null | sort -h | tail -5
```

**判定规则**：

| 现象 | 结论 | 走向 |
|---|---|---|
| `df` 已用 ≈ `du` 合计（差值 < 5%） | 文件确实多 | 第二步 A |
| `df` 已用 − `du` 合计 > 10G | 有文件被删除但进程仍持有句柄 | 第二步 B |
| 两者都不高，但 inode 满 | 大量小文件 | `df -i`，走第二步 C |

> 这个差值就是"空间去哪了"的答案。差值越大，越可能是进程占用已删除文件。

## 第二步 A：文件确实多

```bash
du -h --max-depth=1 / 2>/dev/null | sort -h | tail -10
```

定位到具体目录后，再逐层下钻。处置优先级：

1. 日志归档（`/var/log`）—— 可清理，风险低
2. 缓存（`/var/cache`、`~/.cache`）—— 可清理，风险低
3. 业务数据 —— **不要直接删**，先确认归属与备份

## 第二步 B：删除未释放（最常见的"删了没用"）

```bash
lsof +L1 2>/dev/null | grep -i deleted
# 或
lsof -nP 2>/dev/null | grep deleted | awk '{print $1, $2, $7, $9}' | sort -k3 -h | tail -10
```

输出形如：

```
nginx  20431  root  5w  REG  254,1  29.4G  1234 /var/log/nginx/access.log (deleted)
                                ↑ 占用大小  ↑ 已删除但未释放
```

**关键点：文件已经 unlink，但 inode 还被进程持有，空间不会归还。** 删文件不等于释放空间。

处置动作（按风险从低到高）：

| 动作 | 命令 | 风险 | 说明 |
|---|---|---|---|
| 重开日志句柄 | `mv access.log access.log.bak && nginx -s reopen` | 🟡 中 | 不断连接，推荐 |
| 清空句柄 | `: > /proc/20431/fd/5` | 🟡 中 | 只清内容，进程不感知 |
| 重启进程 | `systemctl restart nginx` | 🔴 高 | 会中断连接，最后手段 |

执行前必须说明：**操作对象（哪个进程、哪个文件）、影响范围（是否断连）、回滚方式（mv 回来再 reopen）**。

## 第二步 C：inode 满

```bash
df -i
find / -xdev -type f 2>/dev/null | wc -l
```

常见成因：小文件堆积（session 文件、临时文件、mail spool）。处置前先确认目录归属。

## 第三步：验证（必须做）

```bash
df -h /
lsof +L1 2>/dev/null | grep -i deleted
tail -1 /var/log/nginx/access.log
```

三条同时满足才算修好：

1. 使用率明显回落
2. `lsof +L1` 不再有对应条目
3. 新日志有正常写入（证明句柄已重开）

## 第四步：防复发

单次清理不解决根因。检查是否缺少日志轮转：

```bash
cat /etc/logrotate.d/nginx 2>/dev/null
logrotate -d /etc/logrotate.conf 2>&1 | head -20
```

没有配置时，给出建议方案（不擅自写入）：

```conf
/var/log/nginx/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    sharedscripts
    postrotate
        [ -f /var/run/nginx.pid ] && kill -USR1 $(cat /var/run/nginx.pid)
    endscript
}
```

注意：`copytruncate` 与 `postrotate + reopen` 二选一。已有 `deleted` 文件问题时应优先 `reopen`，因为 `copytruncate` 在高写入场景会丢日志。

## 同类隐患排查

单台修好后，检查同批次机器：

```bash
# 对同分组/同镜像的实例执行同一条判定
df -h / | awk 'NR==2 {print $5}'
lsof +L1 2>/dev/null | grep -c deleted
```

汇总成"受影响实例列表"，而不是逐台贴输出。

## 输出要求

- 结论必须包含**判定依据**（df 与 du 的具体差值）
- 处置动作必须包含**影响与回滚**
- 修完必须给**验证结果**（前后对比）
- 最后给**防复发建议**，而不是"清理完成"
