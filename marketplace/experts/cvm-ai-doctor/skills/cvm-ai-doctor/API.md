# CVM Doctor Public API

> **版本**: 1.1 | **更新**: 2026-03-27
>
> 本文件声明可被外部 Skill（如 remote-doctor, health-check）稳定引用的文件路径与格式。
> 未列出的文件视为内部实现，可能随时变更。

---

## References

诊断知识模块。外部消费者通过文件路径引用，从中提取诊断命令和判断逻辑。

### Quick（快速扫描，10s 级）

| 路径 | 用途 |
|------|------|
| `references/resource-saturation-quick.md` | CPU / 内存 / 磁盘 / 网络快扫，返回每组件 OK / WARNING / CRITICAL |
| `references/system-logs-quick.md` | 内核 / OOM / 文件系统 / 认证 / 服务日志错误扫描 |
| `references/disk-smart-quick.md` | 磁盘 SMART 健康检查 |
| `references/hardware-health-quick.md` | CPU 温度 / 内存 / RAID / 电池状态 |
| `references/time-sync.md` | NTP 时间同步状态（Quick + Deep 合一） |

### Deep（根因分析，20-60s 级）

| 路径 | 用途 | 何时触发 |
|------|------|---------|
| `references/resource-saturation-deep-cpu.md` | CPU 根因分析 | Quick 报 CPU WARNING+ |
| `references/resource-saturation-deep-memory.md` | 内存根因分析 | Quick 报 Memory WARNING+ |
| `references/resource-saturation-deep-disk.md` | 磁盘 I/O 根因分析 | Quick 报 Disk WARNING+ |
| `references/resource-saturation-deep-network.md` | 网络根因分析 | Quick 报 Network WARNING+ |
| `references/resource-saturation-deep-combined.md` | 多组件关联分析 | Quick 报 2+ 组件异常 |
| `references/system-logs-deep-kernel.md` | 内核日志深度分析 | Quick 报内核错误 |
| `references/system-logs-deep-oom.md` | OOM 事件分析 | Quick 报 OOM |
| `references/system-logs-deep-fs.md` | 文件系统错误分析 | Quick 报 FS 错误 |
| `references/system-logs-deep-auth.md` | 认证失败分析 | Quick 报认证错误 |
| `references/system-logs-deep-service.md` | 服务故障分析 | Quick 报服务错误 |
| `references/disk-smart-deep.md` | SMART 详细分析 | Quick 报 SMART FAIL |
| `references/hardware-health-deep.md` | 硬件深度检查 | Quick 报硬件异常 |

### 索引

| 路径 | 用途 |
|------|------|
| `references/00-scenario-index.md` | 60+ 场景路由表（关键词 → 诊断流程 → command 路径） |
| `references/skill-collaboration.md` | Skill 协作指南（与 health-check 等 Skill 的分工与交叉引用） |

---

## Skill Collaboration

### Integration with other Skills

| Skill | 协作关系 | 参考文档 |
|-------|---------|---------|
| `health-check` | 分工协作:CVM Doctor 负责**性能诊断**,Health Check 负责**平台自检** | `references/skill-collaboration.md` |
| `remote-connect` | 远程诊断:CVM Doctor 提供命令,remote-connect 负责执行 | `SKILL.md` Remote Diagnostics 章节 |

**Cross-reference points**:
- CVM Doctor detects LightClaw process anomaly → Suggest health-check
- Health Check detects host resource issue → Suggest CVM Doctor
- User says ambiguous "检查系统" → CVM Doctor prioritizes, then suggests health-check if all OK

---

## Commands

`commands/` 目录包含 126 个命令文件，由场景索引按路径引用。

外部消费者**不需要**维护完整的 command 路径清单——通过 `00-scenario-index.md` 动态查找即可。这里只约定格式。

### 文件格式契约

每个 command `.md` 文件遵循以下结构：

```
# 标题

## Platform Detection
OS_TYPE=$(uname -s) 检测段

## 诊断/操作步骤
Markdown 表格，列固定为：

| 检查项 | Linux | macOS | Windows |
```

**可依赖的约定：**

1. 表格单元格内是**可直接执行的 shell 命令**
2. 所有诊断类命令是**只读的**（不改变系统状态）
3. 会修改系统的命令，文件内有 `⚠️` 标记并要求用户确认

---

## 诊断流程契约

```
Quick → Triage → Deep 三级流程:

1. Quick: 读 *-quick.md，执行其中命令，收集各组件状态
2. Triage: 根据 Quick 结果决定走哪个 Deep 模块
   - 1 个组件异常 → 对应的 *-deep-{component}.md
   - 2+ 个组件异常 → *-deep-combined.md
   - 全部正常 → 结束
3. Deep: 读对应 *-deep-*.md，执行其中命令，输出根因分析
```

外部编排器只需实现这个三步流程，具体命令从 reference 文件中提取。

---

## 诊断统计

每次诊断完成后,Agent 自动追加一条 JSONL 记录。

### 统计文件

| 路径 | 格式 | 用途 |
|------|------|------|
| `~/.lightclaw/stats/cvm-doctor.jsonl` | JSONL (每行一条 JSON) | 本地诊断统计,可用于聚合分析 |

### 记录 Schema

```json
{
  "ts": "ISO8601",
  "mode": "quick | deep | quick+deep",
  "scenario": "Tier 1 场景名或 general",
  "os": "linux | darwin | windows",
  "duration_s": "int (秒)",
  "components": {
    "cpu": "ok | warning | critical | skipped",
    "memory": "ok | warning | critical | skipped",
    "disk": "ok | warning | critical | skipped",
    "network": "ok | warning | critical | skipped"
  },
  "issues_found": "int (WARNING + CRITICAL 组件数)",
  "severity": "ok | warning | critical",
  "trigger": "user | cron"
}
```

### 消费方式

外部工具可以读取此文件进行聚合分析:

```bash
# 统计总诊断次数
wc -l ~/.lightclaw/stats/cvm-doctor.jsonl

# 统计问题发现率
jq -s '[.[] | select(.issues_found > 0)] | length as $issues | length as $total | {total: $total, issues: $issues, rate: ($issues/$total*100)}' ~/.lightclaw/stats/cvm-doctor.jsonl

# 统计各组件异常分布
jq -s '[.[] | .components | to_entries[] | select(.value != "ok" and .value != "skipped")] | group_by(.key) | map({component: .[0].key, count: length})' ~/.lightclaw/stats/cvm-doctor.jsonl
```

---

## 变更日志

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-04-08 | 1.2 | 新增诊断统计章节,声明 `cvm-doctor-stats.jsonl` 格式和消费方式 |
| 2026-03-27 | 1.1 | 新增 Skill 协作章节,声明与 health-check 的分工;新增 `references/skill-collaboration.md` |
| 2026-03-26 | 1.0 | 初始版本 |
