# 第二轮浏览器验收操作

浏览器套件使用 Browser skill 的持久 Node 运行时和实际可见页面，不通过隐藏状态、令牌注入或接口请求替代 UI 操作。当前实现覆盖首页固定数据检查及隔离实例的跨页队列；其他完整 E2E 与无损原版截图基准仍待补齐。

## 两类环境

固定展示使用 `/dev/workbuddy.html`，复用生产主壳、输入和消息组件。仅开发入口装载固定数据/本地回调，禁止保存真实业务。用于可重复的尺寸、主题、语言和截图检查。

真实验收使用一个全新的临时 `OCTOP_HOME`，在真实初始化和登录界面完成配置。不要指向现有业务实例。后端与前端端口分别为 18089/5194，例如：

```sh
acceptance_home="$(mktemp -d)"
OCTOP_HOME="$acceptance_home" OCTOP_REQUIRE_SETUP_PASSWORD=false uv run octop run --host 127.0.0.1 --port 18089
```

另一个终端从 `dashboard/` 启动新展示：

```sh
VITE_UI_VARIANT=workbuddy VITE_API_PORT=18089 VITE_DEV_PORT=5194 npm run dev -- --host 127.0.0.1 --port 5194
```

从真实初始化页面创建验收管理员，选择 SQLite。仅该新建实例关闭初始化密码要求；正常登录的滑块和已有认证流程保持启用。

## 本地受控模型

从仓库根目录启动：

```sh
uv run python dashboard/scripts/workbuddy-test-model.py \
  --workspace-root /absolute/disposable/octop-home/agents/main \
  --port 18090
```

`--workspace-root` 必须指向上面临时实例的验收 Agent 工作区。服务仅监听 127.0.0.1，只响应 `/models`、`/v1/models`、聊天完成和 embeddings 端点，其他路径返回 404。可选 `--evidence-jsonl` 保存工具名称/流式标志，不保存提示、凭据或请求头。

在真实模型管理界面创建兼容 Provider，地址 `http://127.0.0.1:18090/v1`，模型 `octop-ui-acceptance`，填写仅供本地测试的字符串作为 API key，保存、测试连接并配置模型。这不调用外部模型，也不替换业务 API。

普通消息返回分段固定文本；默认每段 1.5 秒，可用 `--chunk-delay` 调整。提示含“验收审批”时请求真实 `write_file`，含“验收提问”时请求真实 `ask_user_question`，含“验收工具”时请求真实 `current_time`。工具执行、权限、审批、失败与文件保存全部由 Octop 决定，模型脚本不读写工作区文件。审批测试必须在该隔离实例的真实安全界面启用 HITL，并通过原确认流程。

## 首页 20 组检查

按 Browser skill 初始化 `tab`、`viewport`、`fs` 后，在 Node 运行时导入：

```js
var checks = await import(
  "/absolute/repository/dashboard/scripts/workbuddy-browser-checks.mjs"
);
var results = [];
for (var theme of ["light", "dark"]) {
  for (var language of ["zh", "en"]) {
    for (var size of [
      [1440, 900],
      [1280, 800],
      [1920, 1080],
      [390, 844],
      [768, 1024],
    ]) {
      results.push(
        await checks.checkHomeFixture({
          tab,
          viewport,
          fs,
          baseUrl: "http://127.0.0.1:5194",
          outputDir: "/absolute/evidence/output",
          width: size[0],
          height: size[1],
          theme,
          language,
        }),
      );
    }
  }
}
```

视口设置作用于选中的标签页；套件会检查尺寸确实应用到该页。建议按主题/语言分批执行，保留每组 JSON/JPEG。JPEG 仅为展示证据，不能作为 1% 无损原版像素差异验收。

## 真实跨页队列

在真实登录实例中，保持中文、标准外观、展开的桌面侧栏。使用独立 runId，先执行发送/排队阶段：

```js
var scenario = await checks.beginChatQueueAcrossPages({
  tab,
  baseUrl: "http://127.0.0.1:5194",
  runId: "unique-run-id",
});
```

返回状态 `streaming-in-background` 时页面已经进入自动化；此时不要重新装载聊天页。可继续独立检查其他界面，待受控模型的两轮输出完成后执行核对阶段：

```js
var result = await checks.checkStoredChatQueue({
  tab,
  fs,
  outputDir: "/absolute/evidence/output",
  scenario,
});
```

核对通过真实历史入口返回，等待两条回复完成并刷新，再校验两条消息与两条固定回复，保存 JSON/JPEG。提前调用或接口失败会报错，不能改写成功结果。分阶段避免浏览器工具单次等待限制中断长流式任务，并能验证聊天页卸载期间的发送。它仍不是覆盖所有功能、角色和浏览器的无人值守 CI 套件。

本轮执行证据见 [round2-verification.md](round2-verification.md)。

## 技能、连接器、插件与终端

在同一隔离实例创建工作区技能，编辑正文保存后刷新重读；390px 视口打开技能文件树，检查 350px 卡片及内部滚动。连接器配置仅使用本地无效地址、关闭共享/默认开启，验证保存重读和真实探测错误；此场景不计作外部服务连接成功。

插件验收使用仓库已有 `tests/fixtures/plugins/echo-tool` 两个文件打包成 ZIP，从临时目录的本地静态服务提供，通过真实安装表单安装。随后禁用并刷新重读，恢复启用后在 Agent 插件工具中修改 `prefix`，保存并刷新重开。仅在临时实例运行，不安装到已有业务目录；不运行外部插件或额外依赖。

终端只执行 `echo octop-round2-terminal-check`，离开控制台后返回并选择终端，确认同一会话与输出仍在。以上人工路径有第二轮截图及记录，尚未做成覆盖所有操作的无人值守套件。

## 知识、记忆、人格与渠道

知识验收可在同一本地 Provider 添加 `octop-ui-embedding` 并标记为嵌入模型，在知识功能设置中选择它、关闭 OCR。模型仅返回确定性的 32 维向量，用于走通真实索引生命周期；不能用于评价语义检索质量。创建私有知识库和 Markdown 文档，编辑、保存、等待索引就绪，刷新预览核对文件名与正文。

在人工记忆中创建验收条目，刷新查看、替换正文，再次刷新查看。人格文件通过专家编辑的 SOUL.md 编辑器修改、保存和刷新核对，测试后恢复原文；不要直接改写后端工作区文件。

渠道仅使用本地 MQTT 地址 `127.0.0.1:18899`、独立验收主题、保持停用，不配置实际外部收件人。刷新重读配置，探测应保留真实连接拒绝状态。检查端口以整数提交，390px 下表单和底部按钮可以滚动访问。这些用例只验证保存重读及失败反馈，不作为实际通道连接、绑定、消息收发成功。
