# 集群节点发现

> 本文件指导 Agent 如何发现、验证和持久化集群节点列表。
> 所有云 API 调用均通过 **tencentcloud-infra** 技能完成。

---

## 前置检查：OAuth 凭据有效性

每次集群操作前，**必须先验证凭据**（OAuth Token 2小时过期）。

执行方式见 **references/skill-collaboration-tencentcloud.md — "OAuth 凭据检查"协议**。

- 凭据有效 → 继续执行
- 凭据过期或缺失 → 引导用户刷新后再继续

---

## 发现方法（优先级从高到低）

### 方法 A：MEMORY.md 缓存（最快，优先使用）

1. 读取 MEMORY.md `cluster_config.last_discovery` 时间戳
2. 若距今 **< 1 小时**，直接使用 `cluster_config.known_nodes`，跳过 API 调用
3. 若距今 ≥ 1 小时，执行方法 B/C/D 重新发现并更新缓存

### 方法 B：标签过滤（推荐，适合长期稳定集群）

调用 tencentcloud-infra 技能，执行：

```bash
tccli cvm DescribeInstances \
  --region <region> \
  --Filters '[{"Name":"tag:<tag_key>","Values":["<tag_value>"]}]' \
  --Limit 100
```

从响应提取每个实例的：
- `InstanceId`：实例唯一标识（如 `ins-abc123`）
- `InstanceName`：实例名称
- `PrivateIpAddresses[0]`：内网 IP
- `PublicIpAddresses[0]`：外网 IP（可能为空）
- `InstanceState`：当前状态（RUNNING/STOPPED/SHUTDOWN 等）
- `Placement.Zone`：可用区

**多区域处理：**
若 MEMORY.md `cluster_config.additional_regions` 非空，对每个区域分别调用一次 DescribeInstances，合并结果。

### 方法 C：指定实例 ID 列表（精确控制）

```bash
tccli cvm DescribeInstances \
  --InstanceIds '["ins-xxx","ins-yyy","ins-zzz"]'
```

### 方法 D：全量发现（账户级，谨慎使用）

```bash
tccli cvm DescribeInstances --region <region> --Limit 100
```

⚠️ 大账户可能有大量实例，请确认用户意图后再使用全量模式。
超过 100 个实例时，需分页（递增 Offset）。

---

## TAT Agent 可用性确认

发现节点后，验证 TAT 自动化助手是否可用（仅限 CVM 实例，Lighthouse 无 TAT）：

```bash
tccli tat DescribeAutomationAgentStatus \
  --InstanceIds '["ins-xxx","ins-yyy"]'
```

- 状态 `Online` → TAT 可用，执行完整 3 层诊断
- 状态 `Offline` 或 `Installing` → **降级模式**：仅使用云端指标（Layer 1 + Layer 2A），
  在报告中标注 `⚠️ OS 快照不可用（TAT Agent 离线）`

---

## 用户引导流程（首次配置集群）

若 MEMORY.md 无集群配置，引导用户配置：

```
我需要了解要管理哪些 CVM 实例。请选择配置方式：

1. 标签过滤（推荐）：按服务标签批量选择
   示例："Service=order-api" 的所有实例

2. 指定实例 ID：直接输入 ins-xxx,ins-yyy

3. 全量（当前区域所有实例）

请告诉我选哪种方式，以及相关信息（标签键值 或 实例 ID 列表）？
```

收到回复后，执行对应发现方法，然后**展示发现结果让用户确认**：

```
发现以下节点（共 N 台）：
- ins-abc123 (order-api-1) | 10.0.0.1 | RUNNING
- ins-def456 (order-api-2) | 10.0.0.2 | RUNNING
- ins-ghi789 (order-api-3) | 10.0.0.3 | STOPPED ⚠️

确认保存此集群配置？（后续检查将使用此列表，1小时内免重新发现）
```

---

## 写入 MEMORY.md

用户确认后，将以下内容写入 MEMORY.md：

```markdown
## 集群配置 (cluster_config)

cluster:
  name: "<用户提供的集群名称，或默认 prod-<region>>"
  region: <region>
  additional_regions: []
  instance_filter:
    method: tag                    # tag | id_list | all
    tag_key: <标签键>
    tag_value: <标签值>
  instance_ids: []                 # method=id_list 时填写
  last_discovery: "<ISO 8601 时间戳>"
  known_nodes:
    - id: ins-abc123
      name: order-api-1
      private_ip: 10.0.0.1
      state: RUNNING
      tat_available: true
    - id: ins-def456
      name: order-api-2
      private_ip: 10.0.0.2
      state: RUNNING
      tat_available: true
    - id: ins-ghi789
      name: order-api-3
      private_ip: 10.0.0.3
      state: STOPPED
      tat_available: false
```

---

## Lighthouse 实例特殊处理

若发现实例是 Lighthouse（轻量应用服务器），需使用不同命令：

```bash
# Lighthouse 用 tccli lighthouse，不是 tccli cvm
tccli lighthouse DescribeInstances --region <region>
```

Lighthouse 实例**无 TAT 支持**，只能使用云端监控指标（Layer 2A 降级模式）。

---

## 错误处理

| 错误情况 | 处理方式 |
|---------|---------|
| DescribeInstances 返回空列表 | 提示"该区域/标签未找到实例，请确认标签是否正确" |
| API 调用失败（权限不足） | 提示"请确认 tccli 凭据有 QcloudCVMReadOnlyAccess 权限" |
| OAuth 过期 | 中断当前流程，引导用户刷新 OAuth Token |
| 实例超过 100 台 | 分页拉取，每次 Offset += 100，直到全部获取 |
