# cvm-ai-doctor × tencentcloud-infra 协作协议

> 本文件定义两个技能如何协同完成集群诊断和管理任务。
> **核心原则：技能通过 Markdown 散文指令协作，Agent 作为编排者，不存在代码级 API 调用。**

---

## 职责分工表

| 职责 | cvm-ai-doctor | tencentcloud-infra |
|------|:---:|:---:|
| 节点发现（DescribeInstances） | ❌ | ✅ |
| 云端监控指标（GetMonitorData） | ❌ | ✅ |
| TAT 批量命令执行（RunCommand） | ❌ | ✅ |
| TAT 结果轮询（DescribeInvocationTasks） | ❌ | ✅ |
| 实例生命周期（Reboot/Stop/Start） | ❌ | ✅ |
| OS 数据解析与诊断分析 | ✅ | ❌ |
| 跨节点关联分析 | ✅ | ❌ |
| 集群健康评分 | ✅ | ❌ |
| 诊断报告生成 | ✅ | ❌ |
| MEMORY.md 集群配置维护 | ✅ | ❌ |
| OAuth 凭据管理 | ❌ | ✅ |

---

## 核心协议：TAT 远程命令执行（集群 OS 快照）

### ⚡ 脚本优先路径（Script-First Path）

**优先**使用 `cvm-ai-doctor` 技能 `scripts/` 目录中的对应脚本，在本地 base64 编码后通过 TAT 发送到远端 CVM 执行。这样可以避免 LLM 每次重新组装命令，减少 token 消耗，也不容易遗漏或改写命令细节。

**Step A — Agent 在本地编码（根据 LightClaw 所在操作系统选择）：**

```bash
# Linux / macOS（-w 0 强制单行输出，无需 tr 管道）
SKILL_DIR="<cvm-ai-doctor 技能绝对路径>"

# Layer 2B 快速快照
CONTENT=$(base64 -w 0 < "$SKILL_DIR/scripts/cluster_os_snapshot.sh")

# 深度分析（根据异常类型选择对应脚本）
# CONTENT=$(base64 -w 0 < "$SKILL_DIR/scripts/cluster_deep_cpu.sh")
# CONTENT=$(base64 -w 0 < "$SKILL_DIR/scripts/cluster_deep_memory.sh")
# CONTENT=$(base64 -w 0 < "$SKILL_DIR/scripts/cluster_deep_disk.sh")
# CONTENT=$(base64 -w 0 < "$SKILL_DIR/scripts/cluster_deep_ssh.sh")
# CONTENT=$(base64 -w 0 < "$SKILL_DIR/scripts/cluster_deep_network.sh")
```

```powershell
# Windows PowerShell（ReadAllBytes 不产生换行，无需额外处理）
$SKILL_DIR = "<cvm-ai-doctor 技能绝对路径>"

# Layer 2B 快速快照
$CONTENT = [Convert]::ToBase64String([IO.File]::ReadAllBytes("$SKILL_DIR\scripts\cluster_os_snapshot.sh"))

# 深度分析（根据异常类型选择对应脚本）
# $CONTENT = [Convert]::ToBase64String([IO.File]::ReadAllBytes("$SKILL_DIR\scripts\cluster_deep_cpu.sh"))
# $CONTENT = [Convert]::ToBase64String([IO.File]::ReadAllBytes("$SKILL_DIR\scripts\cluster_deep_memory.sh"))
# $CONTENT = [Convert]::ToBase64String([IO.File]::ReadAllBytes("$SKILL_DIR\scripts\cluster_deep_disk.sh"))
# $CONTENT = [Convert]::ToBase64String([IO.File]::ReadAllBytes("$SKILL_DIR\scripts\cluster_deep_ssh.sh"))
# $CONTENT = [Convert]::ToBase64String([IO.File]::ReadAllBytes("$SKILL_DIR\scripts\cluster_deep_network.sh"))
```

**Step B — 让 tencentcloud-infra 执行（将 Step A 的输出填入 --Content）：**

```bash
tccli tat RunCommand \
  --region <region> \
  --InstanceIds '["ins-xxx","ins-yyy","ins-zzz"]' \
  --CommandType SHELL \
  --Timeout 30 \
  --Content "<Step A 的输出>"
```

> **脚本路径说明**：`scripts/` 目录相对于 cvm-ai-doctor 技能目录。Agent 应在发出指令前将其展开为绝对路径。
> **回退规则**：若脚本文件不存在，回退到 cluster-quick-check.md / cluster-deep-analysis.md 中的内联命令。

---

### 回退：内联命令路径（脚本不存在时）

### cvm-ai-doctor 发出的指令（对 Agent 说）：

```
请调用 tencentcloud-infra 技能，执行以下 TAT 批量命令：

Region: ap-guangzhou
InstanceIds: ["ins-xxx", "ins-yyy", "ins-zzz"]
CommandType: SHELL
Timeout: 30
Content（base64 编码前）:
  h=$(hostname -s 2>/dev/null||echo unknown); \
  l=$(awk '{print $1}' /proc/loadavg 2>/dev/null||echo -1); \
  c=$(nproc 2>/dev/null||echo 1); \
  m=$(free -m 2>/dev/null|awk '/Mem:/{printf "%.0f/%d",$3,$2}'); \
  d=$(df / 2>/dev/null|awk 'NR==2{print $5}'|tr -d '%'); \
  s=$(systemctl is-active sshd 2>/dev/null||echo unknown); \
  echo "HOST=$h LOAD=$l NCPU=$c MEM_MB=$m DISK_ROOT_PCT=$d SSH=$s"

tccli 命令：
  tccli tat RunCommand \
    --region ap-guangzhou \
    --InstanceIds '["ins-xxx","ins-yyy","ins-zzz"]' \
    --CommandType SHELL \
    --Timeout 30 \
    --Content "$(printf '%s' '<上述命令>' | base64 -w 0)"
```

### tencentcloud-infra 执行后返回（示例）：

```json
{
  "InvocationId": "inv-abc123",
  "Response": {
    "RequestId": "...",
    "InvocationId": "inv-abc123"
  }
}
```

### cvm-ai-doctor 收到 InvocationId 后，发出轮询指令：

```
请调用 tencentcloud-infra 技能，轮询以下 TAT 执行结果：

tccli tat DescribeInvocationTasks \
  --InvocationId inv-abc123

轮询策略：
- 间隔：5 秒
- 最多轮询：12 次（总计 60 秒）
- 终止条件：所有任务 TaskStatus = SUCCESS 或 FAILED
```

### TAT 输出解码规则：

TAT 的 `TaskResult.Output` 字段为 base64 编码，解码方法：

```bash
echo "<base64_string>" | base64 -d
```

解码后得到单行文本，格式如下：
```
HOST=order-api-1 LOAD=0.85 NCPU=4 MEM_MB=2048/8192 DISK_ROOT_PCT=55 SSH=active
```

**由 cvm-ai-doctor 负责解析此输出**，tencentcloud-infra 只负责执行和返回原始结果。

---

## 核心协议：云端监控指标拉取

### cvm-ai-doctor 发出的指令：

```
请调用 tencentcloud-infra 技能，拉取以下实例的 CPU 和内存监控指标：

时间窗口：最近 15 分钟（EndTime = 当前时间，StartTime = 当前时间 - 15 分钟）
Period：300（5分钟聚合）

对每个实例执行：
  tccli monitor GetMonitorData \
    --Namespace QCE/CVM \
    --MetricName CpuUsage \
    --Instances '[{"Dimensions":[{"Name":"InstanceId","Value":"ins-xxx"}]}]' \
    --Period 300 \
    --StartTime "<StartTime>" \
    --EndTime "<EndTime>"

  tccli monitor GetMonitorData \
    --Namespace QCE/CVM \
    --MetricName MemUsage \
    --Instances '[{"Dimensions":[{"Name":"InstanceId","Value":"ins-xxx"}]}]' \
    --Period 300 \
    --StartTime "<StartTime>" \
    --EndTime "<EndTime>"
```

### 返回数据处理：

tencentcloud-infra 返回 `DataPoints` 数组，**由 cvm-ai-doctor** 计算平均值：
- 取 `DataPoints[*].Values` 的均值作为该节点的 5 分钟平均 CPU/内存使用率
- 若 DataPoints 为空，标记该指标为"数据不可用"

---

## 核心协议：实例生命周期操作

### 🔴 高风险操作，必须在用户明确确认后才能发出

**重启实例：**
```
请调用 tencentcloud-infra 技能，重启以下实例：

tccli cvm RebootInstances \
  --region <region> \
  --InstanceIds '["ins-xxx"]' \
  --StopType SOFT

执行后，每 10 秒轮询一次 DescribeInstances 状态，直到实例回到 RUNNING。
超时：10 分钟
```

**停止实例：**
```
请调用 tencentcloud-infra 技能：

tccli cvm StopInstances \
  --region <region> \
  --InstanceIds '["ins-xxx"]' \
  --StopType SOFT
```

**启动实例：**
```
请调用 tencentcloud-infra 技能：

tccli cvm StartInstances \
  --region <region> \
  --InstanceIds '["ins-xxx"]'
```

---

## 降级模式：TAT 不可用时

当 TAT Agent 状态为 Offline 时，执行降级流程：

1. 跳过 TAT RunCommand（Layer 2B）
2. 仍执行 Layer 1（DescribeInstances）+ Layer 2A（GetMonitorData）
3. 在报告中每个无 OS 快照的节点旁标注：`⚠️ OS 快照不可用（TAT 离线）`
4. 评分时跳过 OS 相关指标（负载、SSH 状态），仅基于云端指标评分
5. 评分结果标注："仅云端指标，置信度较低"

---

## 协作场景对照表

| 用户说 | cvm-ai-doctor 动作 | tencentcloud-infra 动作 |
|--------|-------------------|------------------------|
| 检查集群健康状态 | 读 cluster-quick-check.md，指挥执行 | DescribeInstances + GetMonitorData + TAT RunCommand |
| 集群某节点负载高 | 读 cluster-deep-analysis.md，指挥深度 TAT | TAT RunCommand（ps aux, top 等） |
| 重启某台 CVM | 读 cluster-remediation.md，确认风险后指挥 | RebootInstances + 轮询 DescribeInstances |
| 发现新集群 | 读 cluster-discovery.md，指挥发现 | DescribeInstances + DescribeAutomationAgentStatus |
| 查询某节点内存趋势 | 读 cluster-deep-analysis.md，指挥拉取 | GetMonitorData（过去 24 小时） |

---

## 核心协议：OAuth 凭据检查

**每次调用任何 tccli 命令前，必须先执行此检查。**

```bash
python3 scripts/tccli-oauth-helper.py --status
```

> `scripts/` 是 tencentcloud-infra 技能目录下的相对路径，随技能部署位置自动解析，无需硬编码绝对路径。

**返回值处理：**
- 输出含 `valid` → 凭据有效，继续执行
- 输出含 `expired` 或 `missing` → 中断当前操作，提示用户刷新凭据：
  ```
  ⚠️ OAuth 凭据已过期，集群操作已暂停。
  请先完成 OAuth 授权，授权后重新发起本次操作。
  ```

---

## 重要约束

1. **凭据前置检查**：每次让 tencentcloud-infra 执行 API 前，先按上方"OAuth 凭据检查"协议确认凭据有效
2. **区域一致性**：TAT 是 Region-Scoped，跨区域集群需按区域分批调用
3. **Lighthouse 特殊处理**：Lighthouse 实例用 `tccli lighthouse`，无 TAT 支持
4. **批量优先**：TAT RunCommand 支持数组 InstanceIds，一次 API 覆盖所有节点，不要逐台调用
5. **结果等待**：TAT 异步执行，必须轮询 DescribeInvocationTasks 直到完成，不能假设已完成
