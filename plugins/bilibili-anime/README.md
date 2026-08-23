# 哔哩哔哩番剧播放器

在 Octop 聊天中搜索哔哩哔哩番剧，并用官方 iframe 播放器按集播放。

## 工具

| 名称 | 说明 |
|------|------|
| `bilibili_search_anime` | 按关键词搜索番剧，返回分集列表 + `octop_ui` 播放器 |

参数：`keyword`（必填）、`max_seasons`（可选，默认 5）。

## 聊天 UI

- 多部结果切换（季/版本）
- iframe 播放当前集
- 上一集 / 下一集 + 分集网格
- 全屏播放

## 安装

```bash
octop plugin install ./plugins/bilibili-anime --force
```

若服务已在运行：Dashboard **插件 → 重新加载**，或重启服务。

在智能体详情里启用 `bilibili_search_anime`，然后说例如：「搜索并播放葬送的芙莉莲」。

## 说明

- 服务端用 Bilibili 公开 API，避免浏览器 CORS。
- 播放走 `player.bilibili.com` 官方嵌入页；部分环境可能受登录/地区限制。
- 依赖：`httpx`（见 `plugin.yaml` `requires`）。
