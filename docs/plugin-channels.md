# 第三方通道插件

通道插件依赖配套的 harness `kind: channel` 与 gateway 动态注册接口。部署前应先安装包含这些能力的正式版本；本变更不预先填写尚未发布的版本号。

插件通过 `ctx.channel(kind, ChannelClass, label=..., fields=...)` 注册，类必须继承 gateway BaseChannel，并遵循 gateway 的构造与 Config 约定。安装和启用后，Octop 在网关恢复数据库通道之前注册实现。没有表单 schema 时可使用 JSON 配置。

插件 ID 拥有通道 kind；不同插件的冲突会报告错误，同一插件更新可以替换实现。后台插件安装、开关、卸载和重载先比较 kind、plugin_id 与实现类，仅停止并重建变化的通道类型；内容未变的通道插件复用原类，无关 tool 插件操作不会重启通道。该过程可能中断插件通道中的活动消息；内置通道不重启。数据库通道配置与历史不会删除；缺失插件的记录保留并显示运行失败。恢复插件后可重载或重启。

通道页面刷新按钮会重新读取插件目录，移除已禁用 kind 并更新名称和字段；当前界面尚不提供跨页面实时推送通知。

此功能仅为通道扩展机制，不包含 Octo 协议实现，也不保证第三方插件自身的消息幂等或权限策略。不需要改写 Dashboard 构建产物或修改 ChannelKind 枚举。

通道注册失败会写入插件列表的 registration_error，安装、启用和重载调用返回失败明细；启动时仍隔离坏插件以便其他通道继续工作。

## 为已有 QQ 群聊策略提供开关

此机制面向任意已加载的入站插件，不要求固定插件 ID。需要 Harness 的入站注册接口与 Gateway 的 `set_inbound_handler()`、`plugin_group_settings` 支持；仅安装插件不会为旧 SDK 添加接口。宿主在旧 SDK 上保留原有通道运行方式。

入站 hook 的处理器可以在 `channel_settings` 属性声明 QQ 群聊策略开关。Octop 只展示已加载处理器的声明，停用、卸载或加载失败后隐藏；隐藏不会删除已保存的通道配置。当前只支持 `channel_kind="qq"`、`section="group_context"`、`type="switch"`。每个声明需要 `name`（小写字母、数字和下划线，且不能占用宿主字段）、布尔值 `default`、含 `zh`/`en` 字符串的 `label` 和 `help`。同名字段只展示第一个声明。

开关写入通道配置 `group_context.<name>`，处理器可从 QQ 通道的 `plugin_group_settings` 副本读取已保存的布尔值，缺失时应使用声明的默认值。保存开关不会自动启用插件；插件自己的启用和试运行策略仍由插件负责。需要包含该接口的 Octop 和 Gateway 版本，旧宿主不会消费这些声明。

入站处理器的 `handle(channel, message, dispatch)` 在消息合并和 Agent 调用前执行，返回 `True` 表示接管。卸载时 `close()` 必须同步取消其任务；可选的 `wait_closed()` 用于等待清理完成。通过 `dispatch` 延迟派发仍经过会话锁、群可见范围及工具权限检查。普通群消息在处理器异常时停止派发，私聊、命令和 @ 保留原处理流程。

实现 `bind_decision_scorer(provider)` 的处理器会获得可选评分服务。异步 `provider()` 返回读取当前全局设置的评分函数或 `None`；插件自行限制上下文与调用时间并实现失败回退。关闭全局决策服务对后续调用生效，凭据不写入插件设置或管理 API。公共类型及生命周期约定见 [Harness 文档](https://github.com/TencentCloud/octop-harness/blob/develop/docs/inbound-plugins.md)。
