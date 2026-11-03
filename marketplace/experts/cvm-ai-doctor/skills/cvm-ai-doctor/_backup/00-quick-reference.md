# AI 快速场景匹配指南

> **用途**: AI 快速识别用户问题并选择正确的诊断路径
> **决策时间**: < 3 秒

---

## 🎯 一句话匹配规则

**看到用户关键词 → 立即匹配场景 → 运行 Quick Mode → 根据结果决定 Deep**

---

## 🔥 Top 10 高频场景（覆盖 80% 问题）

### 1. 系统慢/卡 ⭐⭐⭐⭐⭐
**关键词**: 慢、卡、lag、slow、sluggish、响应慢
```bash
bash references/resource-saturation.md
# Quick 10s → 如有异常 → Deep --focus <component>
```

### 2. CPU 高 ⭐⭐⭐⭐⭐
**关键词**: CPU、CPU 100%、风扇狂转、high CPU
```bash
bash references/resource-saturation.md --mode deep --focus cpu
```

### 3. 内存不足 ⭐⭐⭐⭐⭐
**关键词**: 内存、memory、OOM、swap、内存不足
```bash
bash references/resource-saturation.md --mode deep --focus memory
```

### 4. 磁盘空间满 ⭐⭐⭐⭐⭐
**关键词**: 磁盘满、disk full、no space、空间不足
```bash
df -h && du -sh /* | sort -rh | head -20
# 然后: commands/optimisation/large-files.md
```

### 5. 磁盘慢/I/O 高 ⭐⭐⭐⭐⭐
**关键词**: 磁盘慢、I/O wait、disk slow、读写慢
```bash
bash references/resource-saturation.md --mode deep --focus disk
bash references/disk-smart.md
```

### 6. 网络慢 ⭐⭐⭐⭐⭐
**关键词**: 网络慢、网速慢、ping 高、network slow
```bash
bash references/resource-saturation.md --mode quick
# 然后: commands/network/diagnose-network-issues.md
```

### 7. 健康检查 ⭐⭐⭐⭐⭐
**关键词**: 检查、健康、health、check、状态
```bash
# 全面 Quick 扫描
bash references/resource-saturation.md --mode quick
bash references/system-logs.md --mode quick
bash references/disk-smart.md --mode quick
# 如有异常 → 对应 Deep
```

### 8. 崩溃/重启 ⭐⭐⭐⭐⭐
**关键词**: 崩溃、crash、重启、reboot、panic
```bash
bash references/system-logs.md --mode deep --focus crash
# 然后: commands/debugging/diagnose-crash.md
```

### 9. 错误日志 ⭐⭐⭐⭐⭐
**关键词**: 错误、error、报错、异常、exception
```bash
bash references/system-logs.md --mode quick
# 如有大量错误 → Deep 分析
```

### 10. 硬件问题 ⭐⭐⭐⭐⭐
**关键词**: 硬件、温度、传感器、hardware、hot
```bash
bash references/hardware-other.md
# SMART 检查: bash references/disk-smart.md
```

---

## 🎯 AI 3 秒决策流程

```
Step 1: 提取关键词
  用户: "服务器很慢" → 关键词: ["慢"]

Step 2: 匹配场景
  "慢" → 场景 #1 (系统慢/卡)

Step 3: 运行 Quick
  bash resource-saturation.md (10 秒)

Step 4: 决策 Deep
  Quick 结果: Memory WARNING
  → 运行: bash resource-saturation.md --mode deep --focus memory (20 秒)

Step 5: 报告
  根因: Java 内存泄漏
  修复: 重启 Java + 增加内存
```

---

## 🔄 Quick/Deep 决策规则

### 何时运行 Deep？

| Quick 结果 | 用户意图 | 决策 |
|-----------|---------|------|
| **CRITICAL** | 任何 | ✅ 自动 Deep |
| **WARNING** | 包含"慢/卡/troubleshoot" | ✅ 自动 Deep |
| **WARNING** | 只是"检查" | ❓ 询问用户 |
| **OK** | 任何 | ❌ 无需 Deep |

### Deep 时 focus 选择

- 单一异常 → `--focus <component>`
- 多重异常 → 逐个 `--focus`，不要 `--focus all`
- 用户明确指定 → 直接 Deep 该组件

---

## 📊 完整场景索引位置

**详细索引**: `references/00-scenario-index.md`
- 60+ 场景分类
- 126 个 Commands 映射
- 5 个 References 映射
- 完整决策算法

---

## 🚀 使用示例

### 示例 1: "服务器慢"
```
1. 匹配 → 场景 #1
2. Quick: resource-saturation.md (10s)
3. 结果: CPU OK, Memory WARNING, Disk OK
4. Deep: --mode deep --focus memory (20s)
5. 报告: MySQL 占用 8GB，建议优化查询
```

### 示例 2: "磁盘坏了"
```
1. 匹配 → 场景 #10 (硬件) → #5.2 (磁盘故障)
2. Quick: disk-smart.md --mode quick (5s)
3. 结果: SMART CRITICAL
4. Deep: disk-smart.md --mode deep (15s)
5. 报告: Reallocated sectors 100+，立即备份
```

### 示例 3: "检查系统"
```
1. 匹配 → 场景 #7 (健康检查)
2. 批量 Quick:
   - resource-saturation.md (10s)
   - system-logs.md (5s)
   - disk-smart.md (5s)
3. 结果: 全部 OK
4. 报告: 系统健康，无需 Deep
```

---

## ⚡ 性能提示

- **Quick 优先**: 永远先运行 Quick
- **按需 Deep**: 只在 Quick 发现异常时 Deep
- **Token 优化**: Quick 200 tokens, Deep 500-700 tokens
- **时间控制**: Quick 10s, Deep 20-60s
- **批量 Quick**: 健康检查可并行运行多个 Quick

---

**快速参考版本**: 1.0
**完整索引**: references/00-scenario-index.md
**最后更新**: 2026-03-24
