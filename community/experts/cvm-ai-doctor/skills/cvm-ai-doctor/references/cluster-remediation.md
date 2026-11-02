# 集群修复操作

> **风险门控的集群级修复操作指南。**
> 所有操作通过 tencentcloud-infra 技能执行（TAT 或云 API）。
> **修复必须串行，每台节点操作后验证恢复再继续下一台。**

---

## 风险等级体系

### 🟢 自动执行（无需确认，只读或低风险）
- 拉取实例状态和监控指标
- TAT 执行只读诊断命令（ps、df、ss、journalctl、cat）
- 展示报告和建议

### 🟡 一次确认（可逆的服务级操作）
**执行前必须告知用户，等待确认后方可执行：**
- TAT 重启单个服务：`systemctl restart <service>`
- TAT 清理 /tmp 临时文件：`find /tmp -mtime +7 -delete`
- TAT 强制执行日志轮转：`logrotate -f /etc/logrotate.conf`
- TAT 清理旧日志文件（只清 7 天前）

**确认提示模板：**
```
⚠️ 即将在 <N> 个节点上执行：systemctl restart nginx
影响：nginx 服务将重启约 15-30 秒，期间该节点不对外提供服务
可逆：是（重启后自动恢复）
负载均衡器会在健康检查失败后自动摘除该节点

确认执行吗？（回复 "yes" 继续）
```

### 🔴 明确确认（云端实例生命周期，重大影响）
**必须让用户明确说出 "确认重启 ins-xxx" 才能执行：**
- 重启实例：`tccli cvm RebootInstances`
- 停止实例：`tccli cvm StopInstances`
- 启动实例：`tccli cvm StartInstances`

**确认提示模板：**
```
🔴 高风险操作：将重启实例 ins-xxx (order-api-3)
---
影响：
- 该实例约 1-3 分钟不可用（重启期间）
- 正在运行的连接将被中断
- 若已配置 CLB 健康检查，流量将自动转移到其他节点

注意事项：
- 当前集群 RUNNING 节点数：3/4
- 重启后仅剩 2/4 节点处理流量，请确认其余节点有足够容量

要继续请明确回复：确认重启 ins-xxx
```

### 💀 绝不执行（即使用户明确要求）
- **同时重启 ≥ 50% 的节点**（可能导致服务整体不可用）
- `rm -rf` 任何目录
- `DROP TABLE` / `DELETE FROM`
- 删除 /etc/ssh 或 sshd 配置
- 清空整个日志目录（允许清旧文件，不允许清当前日志）

遇到此类请求，回复：
```
❌ 此操作风险极高（影响整集群可用性），无法执行。

安全替代方案：
1. 逐台重启（每台间隔 2 分钟，最多同时操作 1 台）
2. 先在腾讯云控制台确认实例健康后再操作

如确需操作，请手动在腾讯云控制台操作，并提前通知相关团队。
```

---

## 串行修复执行原则

**核心规则：绝不并发操作多台节点**

```
正确流程：
  节点1 → 执行操作 → 等待 10 秒 → 验证恢复 →
  节点2 → 执行操作 → 等待 10 秒 → 验证恢复 →
  节点3 → ...

错误做法（禁止）：
  节点1、节点2、节点3 同时执行操作 ❌
```

最大并发：**1 台节点**（不管集群有多少台）

---

## 常见修复操作手册

### 操作 A：重启集群中某服务（🟡 中风险）

**场景：** 某服务（如 nginx/java/node）崩溃或响应异常

**执行流程：**

```
1. 确认操作范围（哪几个节点？）
2. 输出风险提示，等待用户确认

3. 对节点 1 执行 TAT（通过 tencentcloud-infra）：
   tccli tat RunCommand \
     --InstanceIds '["ins-xxx"]' \
     --CommandType SHELL --Timeout 30 \
     --Content "$(printf '%s' 'systemctl restart nginx' | base64 -w 0)"

4. 等待 TAT 完成（轮询 DescribeInvocationTasks）

5. 验证服务恢复（TAT 执行）：
   systemctl is-active nginx && echo "OK" || echo "FAILED"

6. 若验证通过，间隔 10 秒后对节点 2 执行相同操作
7. 若验证失败，暂停并报告
```

### 操作 B：清理磁盘（🟡 中风险）

**场景：** 磁盘使用率 > 80%

**执行流程（只清安全文件，不删业务数据）：**

```bash
# 清 7 天前的 /tmp 文件
find /tmp -mtime +7 -delete 2>/dev/null && echo "tmp cleaned"

# 强制日志轮转
logrotate -f /etc/logrotate.conf 2>/dev/null && echo "logrotate done"

# 清已压缩的旧日志（*.gz 保留最新 3 个）
find /var/log -name "*.gz" | sort | head -n -3 | xargs rm -f 2>/dev/null && echo "old gz cleaned"
```

**不执行：** 删除任何 .log 文件（正在写入），不清 /var/log/\* 当前日志

### 操作 C：重启实例（🔴 高风险）

**场景：** 节点无响应、内核死锁、TAT 连不通

**执行流程：**

```
1. 确认该节点状态：DescribeInstances
2. 确认 CLB 健康检查已经将该节点摘除（否则重启期间会有流量损失）
3. 输出 🔴 高风险提示，等待用户明确确认

4. 通过 tencentcloud-infra 执行重启：
   tccli cvm RebootInstances \
     --region <region> \
     --InstanceIds '["ins-xxx"]' \
     --StopType SOFT

5. 每 10 秒轮询 DescribeInstances，直到 InstanceState = RUNNING
   最长等待：10 分钟（600 秒）

6. 实例 RUNNING 后，再等 30 秒让系统服务完全启动

7. 通过 TAT 执行恢复验证：
   systemctl is-active sshd && \
   uptime && \
   free -m | awk '/Mem:/{print "MEM:", $3"/"$2, "MB"}' && \
   df / | awk 'NR==2{print "DISK:", $5}'

8. 更新 MEMORY.md 诊断历史
```

### 操作 D：启动已停止的实例（🔴 高风险）

**场景：** 发现集群中有 STOPPED 实例，且不是计划内停机

```
1. 先确认：询问用户该实例停止是否计划内
2. 若非计划内，输出 🔴 提示，等待确认

3. 通过 tencentcloud-infra 启动：
   tccli cvm StartInstances \
     --region <region> \
     --InstanceIds '["ins-xxx"]'

4. 轮询 DescribeInstances 直到 RUNNING
5. 等待 60 秒（服务启动）
6. TAT 验证（同操作 C 步骤 7）
```

---

## 修复后验证标准

操作完成后，使用以下标准判断是否修复成功：

| 指标 | 成功标准 |
|------|---------|
| sshd 状态 | `systemctl is-active sshd` = `active` |
| 目标服务 | `systemctl is-active <service>` = `active` |
| 磁盘 | `disk_root_pct < 80%`（清理后） |
| 实例状态 | `DescribeInstances InstanceState` = `RUNNING` |
| 系统负载 | `load/ncpu < 1.0`（重启后 5 分钟内） |

---

## 操作日志记录

每次修复操作结束后，写入 MEMORY.md 诊断历史：

```markdown
### <YYYY-MM-DD HH:MM> — 集群修复操作
- **症状**: <用户报告的问题>
- **受影响节点**: [ins-xxx, ins-yyy]
- **操作**: <执行了什么操作>
- **结果**: <成功/部分失败>
- **验证**: <验证命令和结果>
```
