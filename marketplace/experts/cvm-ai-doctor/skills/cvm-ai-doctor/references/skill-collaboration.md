# Skill Collaboration Guide

**Last Updated**: 2026-03-27

---

## Overview

This document defines how `cvm-doctor` collaborates with other skills, primarily `health-check`.

---

## 🩺 CVM Doctor ↔ Health Check

### Scope Division

| Aspect | **CVM Doctor** | **Health Check** |
|--------|----------------|------------------|
| **Target** | User's **CVM/VM/host** system | **LightClaw platform** itself |
| **Focus** | Performance bottlenecks | Security + configuration health |
| **Checks** | CPU/Memory/Disk/Network saturation | Process vitals, logs, auth, config, dependencies |
| **Trigger** | "慢/卡/CPU高/磁盘满/性能问题" | "自检/体检/安全检查/LightClaw状态" |
| **Output** | Performance analysis + optimization | Security score + health report |

---

## 🔀 Cross-reference Scenarios

### Scenario 1: User says "检查系统" (ambiguous)

**Decision tree**:

```yaml
if user_mentions("LightClaw" or "自检" or "体检" or "安全"):
  → Use health-check skill
  
elif user_mentions("慢" or "卡" or "CPU" or "性能"):
  → Use cvm-doctor skill
  
else:
  # Generic "check system" - prioritize performance
  → Execute cvm-doctor (Quick Mode)
  
  if all_components_ok:
    → Report: "✅ System performance is healthy."
    → Suggest: "Need LightClaw platform security audit? (say '自检' or '体检')"
  
  else:
    → Proceed to Deep Mode for flagged components
```

---

### Scenario 2: CVM Doctor detects LightClaw process anomaly

**Trigger condition**:
- Top CPU/Memory process name contains: `lightclaw` / `uvicorn` / `python.*lightclaw`

**Action in CVM Doctor report**:

```markdown
## 🔬 Deep CPU Analysis

**Top CPU Process**: lightclaw-server (PID 12345, 87.3% CPU)

⚠️  **Platform Component Detected**: The abnormal process is a LightClaw platform service.

💡 **Recommended Next Step**:
   Run platform health check for detailed diagnostics:
   
   User: "自检" or "LightClaw 体检"
   
   This will analyze:
   - Process vitals and thread count
   - Recent error logs
   - Configuration issues
   - Dependency conflicts
```

---

### Scenario 3: Health Check detects host environment issues

**Trigger condition**:
- Disk free space < 10%
- System uptime > 365 days
- Python version < 3.8

**Action in Health Check report**:

```markdown
## 💾 存储与数据安全 — 3/10 ⚠️

**问题**:
- 磁盘剩余空间仅 8% (24GB / 300GB)
- LightClaw 日志目录占用 15GB

💡 **建议使用 CVM Doctor 进行详细磁盘分析**:
   
   User: "检查磁盘" or "disk 慢"
   
   CVM Doctor 将提供:
   - 磁盘饱和度分析
   - 大文件扫描
   - I/O 性能诊断
   - 清理建议
```

---

### Scenario 4: Both skills needed (multi-layered issue)

**Example**: User says "系统最近很慢,还老是报错"

**Workflow**:

1. **First**: CVM Doctor (Quick Mode)
   ```
   Checks: CPU/Memory/Disk/Network saturation
   Result: Memory WARNING (Swap in use)
   ```

2. **Second**: If LightClaw process is involved
   ```
   Check top memory process → lightclaw-server (1.2GB)
   ```

3. **Third**: Cross-reference to Health Check
   ```
   Suggest: "LightClaw 进程内存占用异常,建议执行'体检'检查:
   - 日志错误(可能内存泄漏)
   - 配置问题(heartbeat 过于频繁)
   - 依赖冲突"
   ```

---

## 🎯 Implementation Checklist

### For CVM Doctor

- [x] Update SKILL.md trigger words to avoid "自检/体检/安全检查"
- [x] Add cross-reference logic in Quick Mode output format
- [x] Add collaboration section in SKILL.md
- [x] Create this skill-collaboration.md reference

### For Health Check (if editing)

- [ ] Add note: "For system performance issues (慢/卡/CPU高), use `cvm-doctor` skill"
- [ ] In host environment section, suggest CVM Doctor for disk/resource deep dive

---

## 📝 Cross-reference Templates

### CVM Doctor → Health Check

```markdown
💡 **LightClaw Platform Component Detected**

The issue involves a LightClaw service. For platform-specific diagnostics:

**Next Step**: Run health check
- User says: "自检" or "LightClaw 体检"
- Checks: Process vitals, logs, config, security
```

### Health Check → CVM Doctor

```markdown
💡 **宿主机资源问题**

检测到宿主机{磁盘/内存/CPU}资源异常。建议使用 CVM Doctor 进行详细分析:

**下一步**: 说 "检查{磁盘/内存/CPU}" 或 "系统性能诊断"
- 检查项: 资源饱和度、I/O 性能、进程分析
```

---

## 🌩️ CVM Doctor ↔ Tencent Cloud Infra

### 适用场景

用户说"检查集群"/"所有CVM"/"批量诊断"/"重启某台云服务器"时，
需要 cvm-doctor 与 tencentcloud-infra 协同完成任务。

### 职责划分

| 职责 | **CVM Doctor** | **tencentcloud-infra** |
|------|--------------|----------------------|
| 节点发现（API） | ❌ | ✅ DescribeInstances |
| 云端监控指标 | ❌ | ✅ GetMonitorData |
| 远程 OS 命令执行 | ❌ | ✅ TAT RunCommand |
| OS 数据诊断分析 | ✅ | ❌ |
| 跨节点关联分析 | ✅ | ❌ |
| 实例生命周期操作 | ❌ | ✅ Reboot/Stop/Start |
| 集群健康评分 | ✅ | ❌ |

### 快速决策规则

```yaml
if user_mentions("集群" or "cluster" or "所有CVM" or "所有节点" or "fleet" or "批量"):
  → 读取 references/cluster-quick-check.md
  → 通过 tencentcloud-infra 执行节点发现和 TAT 快照
  → 使用 references/cluster-health-score.md 生成评分报告

elif user_mentions("重启实例" or "重启云服务器" or "ins-" or "启动停止"):
  → 读取 references/cluster-remediation.md
  → 通过 tencentcloud-infra 执行实例生命周期操作（需风险确认）

else:
  → 继续使用现有单机诊断流程，不需要 tencentcloud-infra
```

### 完整协作协议

所有 API 调用细节（TAT 执行格式、数据结构、降级模式）详见：
`references/skill-collaboration-tencentcloud.md`

---

**Last Updated**: 2026-05-08
