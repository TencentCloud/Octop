# 服务器状态

在 Octop 聊天中展示当前服务器的基本信息与资源负载。

## 工具

| 名称 | 说明 |
|------|------|
| `get_server_status` | 采集 OS / 内核 / CPU / 内存 / 磁盘快照，返回 `octop_ui` 状态卡片 |

无需参数。需要最新数据时再次调用即可。

## 安装

```bash
octop plugin install ./plugins/server-status --force
```

若服务已在运行：Dashboard **插件 → 重新加载**，或重启 `octop run`。

在智能体详情中启用 `get_server_status`，然后说：「查看当前服务器状态」。

## 依赖

- `psutil>=5.9`（见 `plugin.yaml` `requires`）
