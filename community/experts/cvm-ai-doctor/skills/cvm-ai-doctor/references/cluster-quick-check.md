# 集群快速检查

> **目标：30 秒内完成对整个集群的 3 层快照，输出每个节点的健康状态。**
> 所有 API 操作通过 tencentcloud-infra 技能执行，
> 详见 references/skill-collaboration-tencentcloud.md。

---

## 执行前提

1. MEMORY.md 存在 `cluster_config.known_nodes`（已发现节点列表）
2. OAuth 凭据有效（执行方式见 references/skill-collaboration-tencentcloud.md — "OAuth 凭据检查"协议）
3. 若不满足，先执行 references/cluster-discovery.md

---

## 3 层快照执行顺序

```
Step 0 (~1s)  : OAuth 凭据检查
Step 1 (~2s)  : Layer 1 — 实例状态（DescribeInstances）
Step 2 (~3s)  : Layer 2A — 云端监控指标（GetMonitorData，并行拉所有节点）
Step 3 (~15s) : Layer 2B — TAT OS 快照（RunCommand，一次 API 覆盖所有节点）
Step 3b (~5s) : 轮询 TAT 结果（DescribeInvocationTasks）
Step 4 (~2s)  : 汇总 → 评分 → 生成报告
─────────────────────────────────────────────────
总耗时：约 25-30 秒
```

---

## Step 1：Layer 1 — 实例状态

**执行指令（让 tencentcloud-infra 执行）：**
```bash
tccli cvm DescribeInstances \
  --region <cluster_config.region> \
  --InstanceIds '<known_nodes InstanceId 数组>'
```

**收集字段：**
- `InstanceId`
- `InstanceName`
- `InstanceState`：RUNNING / STOPPED / SHUTDOWN / TERMINATING / REBOOTING

**立即标记：**
- `STOPPED` / `SHUTDOWN` / `TERMINATING` → 节点分 = **0**，不执行后续 Layer 2B
- `REBOOTING` → 等待，本次跳过（标注"重启中，跳过快照"）
- `RUNNING` → 继续 Layer 2A 和 2B

---

## Step 2：Layer 2A — 云端监控指标（5分钟均值）

**对所有 RUNNING 节点，并行执行（让 tencentcloud-infra 执行）：**

```bash
# 设置时间窗口（最近 15 分钟）
END_TIME=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
START_TIME=$(date -u -d "15 minutes ago" +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || \
             date -u -v-15M +"%Y-%m-%dT%H:%M:%SZ")   # macOS 兼容

# 对每个 RUNNING 节点拉取 CPU 使用率
tccli monitor GetMonitorData \
  --Namespace QCE/CVM \
  --MetricName CpuUsage \
  --Period 300 \
  --StartTime "$START_TIME" \
  --EndTime "$END_TIME" \
  --Instances '[{"Dimensions":[{"Name":"InstanceId","Value":"ins-xxx"}]}]'

# 对每个 RUNNING 节点拉取内存使用率
tccli monitor GetMonitorData \
  --Namespace QCE/CVM \
  --MetricName MemUsage \
  --Period 300 \
  --StartTime "$START_TIME" \
  --EndTime "$END_TIME" \
  --Instances '[{"Dimensions":[{"Name":"InstanceId","Value":"ins-xxx"}]}]'
```

**计算方法：**
取 `DataPoints[*].Values` 数组的均值（忽略 null）。
若无数据点，标记该节点 CPU/内存指标为 `N/A`。

---

## Step 3：Layer 2B — TAT OS 实时快照

## ⚡ 脚本优先路径：用 cluster_os_snapshot.sh 执行 TAT（Script-First Path）

若 `scripts/cluster_os_snapshot.sh` 存在，**直接 base64 编码脚本文件内容传给 TAT**，
无需展开内联命令。

**执行分工**：
- **Agent（本地）**：读取脚本文件并做 base64 编码（见下方命令）
- **tencentcloud-infra**：执行 `tccli tat RunCommand`，将编码内容发送到远端 CVM
- **远端 CVM**：TAT 自动解码并运行脚本，返回 KEY=VALUE 结果

**Step A — Agent 在本地编码（根据 LightClaw 所在操作系统选择）：**

```bash
# Linux / macOS（-w 0 强制单行输出，无需 tr 管道）
SKILL_DIR="<cvm-ai-doctor 技能目录>"
CONTENT=$(base64 -w 0 < "$SKILL_DIR/scripts/cluster_os_snapshot.sh")
echo "$CONTENT"   # 复制此输出作为 TAT --Content 的值
```

```powershell
# Windows PowerShell（LightClaw 运行在 Windows 时使用此版本）
$SKILL_DIR = "<cvm-ai-doctor 技能目录>"
$CONTENT = [Convert]::ToBase64String([IO.File]::ReadAllBytes("$SKILL_DIR\scripts\cluster_os_snapshot.sh"))
Write-Output $CONTENT   # 复制此输出作为 TAT --Content 的值
```

**Step B — 让 tencentcloud-infra 执行（一次 API 调用，覆盖所有节点）：**

```bash
tccli tat RunCommand \
  --region <region> \
  --InstanceIds '["ins-xxx","ins-yyy","ins-zzz"]' \
  --CommandType SHELL \
  --Timeout 30 \
  --Content "<Step A 输出的 base64 字符串>"
```

> `scripts/` 路径相对于 cvm-ai-doctor 技能目录。Agent 应将其展开为绝对路径。
> 若脚本文件不存在，回退到下方内联命令。

---

**回退：内联命令（脚本不存在时使用）**

**TAT 快照一行命令（向所有 RUNNING 且 TAT=Online 的节点批量执行）：**

```bash
h=$(hostname -s 2>/dev/null||echo unknown); \
l=$(awk '{print $1}' /proc/loadavg 2>/dev/null||echo -1); \
c=$(nproc 2>/dev/null||echo 1); \
m=$(free -m 2>/dev/null|awk '/Mem:/{printf "%.0f/%d",$3,$2}'); \
d=$(df / 2>/dev/null|awk 'NR==2{print $5}'|tr -d '%'); \
s=$(systemctl is-active sshd 2>/dev/null||echo unknown); \
echo "HOST=$h LOAD=$l NCPU=$c MEM_MB=$m DISK_ROOT_PCT=$d SSH=$s"
```

**让 tencentcloud-infra 执行（一次 API 调用）：**
```bash
COMMAND_CONTENT=$(cat <<'EOF'
h=$(hostname -s 2>/dev/null||echo unknown); l=$(awk '{print $1}' /proc/loadavg 2>/dev/null||echo -1); c=$(nproc 2>/dev/null||echo 1); m=$(free -m 2>/dev/null|awk '/Mem:/{printf "%.0f/%d",$3,$2}'); d=$(df / 2>/dev/null|awk 'NR==2{print $5}'|tr -d '%'); s=$(systemctl is-active sshd 2>/dev/null||echo unknown); echo "HOST=$h LOAD=$l NCPU=$c MEM_MB=$m DISK_ROOT_PCT=$d SSH=$s"
EOF
)

tccli tat RunCommand \
  --region <region> \
  --InstanceIds '["ins-xxx","ins-yyy","ins-zzz"]' \
  --CommandType SHELL \
  --Timeout 30 \
  --Content "$(printf '%s' "$COMMAND_CONTENT" | base64 -w 0)"
```

**轮询结果（最多 12 次，每次间隔 5 秒）：**
```bash
tccli tat DescribeInvocationTasks --InvocationId <inv-id>
```

终止条件：所有 `TaskStatus` = `SUCCESS` 或 `FAILED` 或 `TIMEOUT`

**解码 TAT 输出：**
```bash
echo "<base64_output>" | base64 -d
# 得到格式：HOST=xxx LOAD=0.85 NCPU=4 MEM_MB=2048/8192 DISK_ROOT_PCT=55 SSH=active
```

**解析内存百分比：**
```
MEM_MB=2048/8192  →  MEM_PCT = round(2048/8192 * 100) = 25%
```

---

## Step 4：汇总数据结构（传入评分模块）

对每个节点，整理以下字段后，交给 references/cluster-health-score.md 计算评分：

```
节点 ins-xxx 数据：
  instance_state: RUNNING
  cpu_cloud_avg_pct: 42.3          # Layer 2A，若 N/A 则留空
  mem_cloud_avg_pct: 68.1          # Layer 2A，若 N/A 则留空
  load: 0.85                       # Layer 2B TAT
  ncpu: 4                          # Layer 2B TAT
  load_ratio: 0.21                 # load / ncpu
  mem_used_mb: 2048                # Layer 2B TAT
  mem_total_mb: 8192               # Layer 2B TAT
  mem_pct: 25.0                    # Layer 2B TAT 计算
  disk_root_pct: 55                # Layer 2B TAT
  sshd_active: true                # Layer 2B TAT
  tat_available: true              # 是否有 OS 快照
  tat_status: SUCCESS              # SUCCESS / FAILED / TIMEOUT
```

## ⚡ 脚本优先路径：用 cluster_score.sh 替代手算（Script-First Path）

汇总完每个节点数据后，若 `scripts/cluster_score.sh` 存在，**直接调用脚本评分**，跳过手动计算：

```bash
# 每行代表一个节点，KV 格式：
{
  echo "node=ins-aaa name=api-1 instance_state=RUNNING load_ratio=0.21 mem_pct=25 disk_root_pct=55 sshd_active=true cpu_cloud_avg_pct=42 mem_cloud_avg_pct=68 tat_available=true"
  echo "node=ins-bbb name=api-2 instance_state=RUNNING load_ratio=1.8  mem_pct=82 disk_root_pct=79 sshd_active=true cpu_cloud_avg_pct=88 mem_cloud_avg_pct=84 tat_available=true"
  # ... 每个节点一行
} | bash scripts/cluster_score.sh
```

脚本输出包含每个节点的评分、扣分明细和集群最低分（木桶原则），交给 LLM 直接生成报告叙述。

若脚本不存在，按 `references/cluster-health-score.md` 手动计算。

---

## 特殊情况处理

| 情况 | 处理方式 |
|------|---------|
| TAT Timeout（实例 IO 过高） | 该节点标记 `tat_status: TIMEOUT`，仅用云端指标评分 |
| TAT FAILED（命令执行失败） | 记录错误信息，仅用云端指标评分 |
| 所有 TAT 均超时 | 报告"无法获取 OS 快照，仅云端指标" |
| 云端监控无数据 | 标注 `N/A`，跳过云端指标扣分 |
| 实例 REBOOTING | 跳过本次快照，下次巡检时重试 |
| 跨区域集群 | 对每个区域分别调用 TAT RunCommand，合并结果 |
