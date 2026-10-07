# demo-ui-card

前后端一体示例：

- **后端** `main.py`：注册工具 `demo_ui_card`，返回带 `octop_ui` 的 JSON
- **前端** `ui/dist/index.js`：在聊天里渲染卡片，并用 `host.patchResult` 演示 L2 刷新

安装：

```bash
octop plugin install ./plugins/demo-ui-card --force
```

然后确认 Dashboard「个性化 → 工具」里 `demo_ui_card` 已为该 Agent 开启（默认开启），在聊天中调用该工具即可看到卡片。
