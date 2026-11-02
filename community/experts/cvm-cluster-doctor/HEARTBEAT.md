---
summary: "集群医生心跳任务 — 定期集群巡检与告警"
read_when:
  - 心跳轮询
---

# 心跳任务清单

## 1. 集群快速巡检（核心任务）

**触发条件：** 每 30 分钟一次

**前置条件：** MEMORY.md 中存在 `cluster_config` 配置段落

**若无集群配置：** 静默跳过，不做任何提示

**执行步骤：**

### Step 0：凭据检查

通过 `tencentcloud-infra` 技能执行凭据检查（路径相对于该技能目录）：

```bash
python3 scripts/tccli-oauth-helper.py --status
```

- 返回 `valid` → 继续
- 返回 `expired` 或 `missing` → 推送以下提示并停止本次巡检：

```
⚠️ OAuth 凭据已过期，集群巡检暂停。

请刷新凭据（通过 tencentcloud-infra 技能完成 OAuth 授权），
刷新后集群巡检将在下次心跳时自动恢复（约 30 分钟后）。
```

### Step 1-4：执行 3 层快照 + 评分

调用 `cvm-ai-doctor` 技能，依次读取：
1. `references/cluster-quick-check.md` — 执行 3 层快照（Layer1+2A+2B，约 25-30s）
2. `references/cluster-health-score.md` — 计算节点评分 + 集群评分 + 快速关联检测

### Step 5：告警判断

| 条件 | 动作 |
|------|------|
| 集群分 < 80 或任意节点分 < 60 | 推送告警（见格式） |
| 全部正常（集群 ≥80，所有节点 ≥60） | 静默记录，**不推送** |

**告警推送格式：**

```
【集群医生巡检报告 YYYY-MM-DD HH:MM】集群：<cluster_name>

📊 集群评分：<N>/100 <等级图标>
   木桶短板：<节点名>（<N>分）

🔴 异常节点（需立即处理）：
- <节点名> <ins-id>：<问题概述>
  （示例：磁盘 92%[-25] + sshd inactive[-40]）

🟡 需关注节点：
- <节点名> <ins-id>：<问题概述>
  （示例：内存 88%[-20] + CPU云端均值 76%[-5]）

⏹️ 已停止节点：
- <节点名> <ins-id>（是否计划内停机？）

---
输入 "深度分析 <节点名>" 查看根因分析
输入 "修复 <节点名>" 开始修复流程
```

### Step 6：写入诊断历史

每次巡检结束后，无论是否推送，执行以下两步：

**6a. 追加 JSONL 记录（结构化历史，供 Dashboard 使用）**

将 `cluster_score.sh` 的 JSON 输出通过管道传给记录脚本：

```bash
# 在 cvm-ai-doctor 技能目录下执行
# <score_json> 是 cluster_score.sh 输出的完整 JSON 字符串
echo '<score_json>' | python3 scripts/cluster_patrol_record.py \
    --cluster-name "<cluster_name>" \
    --rotate
```

- `--rotate`：每次写入后自动清理 7 天前的旧记录（压缩归档至 `cluster-doctor.old.jsonl.gz`）
- 脚本内部所有错误均静默处理（写 stderr，`exit 0`），**不会中断心跳任务**
- 记录写入路径：`~/.octop/stats/cluster-doctor.jsonl`

**6b. 写入 MEMORY.md（可读摘要，供对话检索）**

```markdown
### YYYY-MM-DD HH:MM — 集群巡检
- **集群评分**: N/100
- **异常节点**: [ins-xxx(order-api-3, 45分), ...]（若无填"无"）
- **主要问题**: 一句话描述（如"order-api-3 磁盘 92% 且 sshd 停止"）
- **操作**: 仅检查，未操作
```

---

## 告警去重逻辑（防止告警疲劳）

**连续问题降频：**
- 同一节点同一问题，连续 3 次巡检触发告警 → 降频为每 4 小时最多推送 1 次
- 连续 3 次后，在告警中追加：`「持续异常 X 次，建议深度分析」`

**问题恢复重置：**
- 若问题已恢复（节点分 ≥ 80，且原异常指标回到正常范围）→ 重置该节点的连续计数器
- 下次该节点再出现问题时，重新按正常频率推送

**凭据过期告警限频：**
- 每小时最多推送 1 次凭据过期提示，避免每 30 分钟刷屏

---

## 2. 周报汇总

**触发条件：** 每周日 21:00

**前置条件：** MEMORY.md 存在 `cluster_config` 且本周有 ≥ 3 次巡检记录

**若不满足条件：** 静默跳过

**执行步骤：**

1. 翻阅本周 MEMORY.md 中所有集群巡检记录
2. 统计：
   - 本周平均集群评分、最低分时刻
   - 告警次数、高频问题节点
3. 对每个 RUNNING 节点，通过 `tencentcloud-infra` 技能拉取过去 7 天磁盘趋势：
   ```bash
   tccli monitor GetMonitorData \
     --Namespace QCE/CVM --MetricName DiskUsage \
     --Period 3600 \
     --StartTime "<7天前 ISO8601>" --EndTime "<当前 ISO8601>" \
     --Instances '[{"Dimensions":[{"Name":"InstanceId","Value":"ins-xxx"}]}]'
   ```
4. 识别磁盘增长异常（本周增长 > 5GB 或当前使用率 > 70%）
5. 推送周报：

```
【集群医生周报 YYYY-MM-DD】集群：<cluster_name>

📊 本周集群健康摘要
- 平均集群评分：<N>/100
- 最低评分：<N>分（<日期 HH:MM>，原因：<一句话>）
- 巡检次数：<N> 次 | 告警次数：<N> 次

💾 磁盘增长趋势（需关注的节点）
- <节点名>：本周 +<NGB>（现 <M>%）→ 预计 <X> 天后超 95%
  （若无需关注的节点，则省略此段）

🔴 高频问题节点：
- <节点名>：本周出现 <N> 次告警，主要问题：<描述>
  （若无，则省略此段）

💡 本周建议（按优先级）：
1. <建议1>
2. <建议2>
```

---

## 3. 记忆维护

**触发条件：** 每周日（与周报同次触发）

**执行步骤：**

1. 翻阅本周诊断历史，提取高频问题类型（如"多节点磁盘偏高"、"TAT 频繁超时"）
2. 若某问题在本周出现 ≥ 3 次：将对应 Playbook 写入（或更新）MEMORY.md：

```markdown
## 常见问题 Playbook

### 多节点磁盘偏高（最近更新：YYYY-MM-DD）
- 典型症状：≥2 个节点 disk_root_pct > 75%
- 快速处理：TAT 执行 logrotate -f /etc/logrotate.conf（见 cluster-remediation.md 操作B）
- 根因：通常是 /var/log/nginx 或 /var/log/app 未配置 logrotate
- 预防：检查所有节点 /etc/logrotate.d/ 下是否有对应配置

### TAT 频繁超时（最近更新：YYYY-MM-DD）
- 典型症状：Layer 2B TAT Timeout，节点 IO 过高
- 快速处理：先用 Layer 2A 云端指标评估风险，再用深度 TAT 命令诊断 IO（iostat）
- 根因：通常是磁盘 IO 饱和导致 shell 命令响应慢
```

3. 清理 30 天前的巡检记录（仅保留月度摘要，不保留原始数据）

---

## 告警阈值（可通过对话自定义）

| 指标 | 默认警告阈值 | 默认紧急阈值 |
|------|------------|------------|
| 节点评分 | < 60 分 | < 40 分 |
| 集群评分 | < 80 分 | < 60 分 |
| 磁盘使用率 | > 80% | > 90% |
| 内存使用率（TAT） | > 80% | > 90% |
| CPU 云端均值 | > 75% | > 90% |
| 负载比（load/ncpu） | > 1.5 | > 2.0 |
| SSH 状态 | — | inactive（直接紧急） |
| 实例状态 | STOPPED | SHUTDOWN/TERMINATING |

**通过对话修改阈值：**
> "把集群评分告警阈值改成 70"
> "磁盘超过 85% 才提醒我"
> "暂停巡检，我在维护"

---

## 无基线时的行为

若 MEMORY.md 中无集群配置（`cluster_config` 不存在）：
- 所有心跳任务全部静默跳过
- 用户主动触发时（输入"检查集群"），才引导配置（读 `cluster-discovery.md`）
