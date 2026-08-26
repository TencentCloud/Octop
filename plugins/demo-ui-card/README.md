# demo-ui-card

前后端一体示例：

- **后端** `main.py`：注册工具 `demo_ui_card`，返回带 `octop_ui` 的 JSON
- **前端** `ui/dist/index.js`：在聊天里渲染卡片，并用 `host.patchResult` 演示 L2 刷新

安装：

```bash
octop plugin install ./plugins/demo-ui-card --force
```

然后在 Dashboard「工具管理」为 Agent 启用 `demo_ui_card`，在聊天中调用该工具即可看到卡片。
