# KNOWN_RISKS.md

只记录仍影响维护的风险：触发条件、影响、应对与验证。修复后删除失效描述或保留简短 Resolved 条目和对应 PR。

- 手动文档语义对账依赖辅助模型；只接受原文引用、明确主体/范围和高置信结果，不确定/失败不强制停用。单次最多 100 条未核对 Atom、100,000 文档字符，宿主需呈现 partial/uncertain/unavailable 状态并支持续查。外部宿主未注册 provider 时，仅显式对账生效。外部文件并发写依赖宿主 freshness callback；采纳需传当前文档，底层 worker 至少校验最后对账版本。旧版本候选保留审计但不可直接采纳，需拒绝并核对新版。冲突 raw 整条从自动 fallback 排除，其中混合的其它事实仍可经有效 Atom/直接证据读取；不批量删除历史 Episode。见 ADR-042。

- PG 共享池预算仅覆盖同一进程、同一连接配置；多进程、不同配置和宿主控制面要额外预留服务端连接。长事务会占用业务池，饱和时有界等待后报错，不会无限扩容。CI/release 已使用专用 PG；本地未配置测试服务的 skip 仍不算 PG 验收。

- 未带结构化标记的合成报错无法可靠区别于正常对话，在线链路保留，不能声称已隔离所有旧报错。octop-harness / Octop 主路径已抛出异常；自定义宿主仍合成错误时必须传 `payload.octop_runtime_error=true`。旧版固定报错格式仅用于存量审核提示；缺失/混合来源的 review_*_ids 是只读清单，不是新增 UI 待办或自动停用，需人工核对。手工保存/批准/编辑不按措辞推断。见 ADR-041。

- `run_gc()` retention 当前仅 SQLite 实现，PG 返回空统计，是待修复的既有能力缺口。
  删除行、checkpoint retention 和物理空间回收是不同操作；不能据此推断宿主已自动调度。
- PostgreSQL 的 `btree_gin` 不可用时退回普通 GIN，namespace 过滤正确性保留，性能隔离减弱。
  共享 checkpoint 表维护需 database 级范围判断；普通 VACUUM 也不能承诺无锁等待。
- recall 墙钟预算可能受机器负载影响；超时失败需区分调度抖动与实际召回回归。
- dashboard 直接访问 SQLite 且不在 wheel 内。可选依赖版本、大库迁移耗时和真实 host hook 需要单独验证。
- 部分 SQLite 运行时的只读 FTS 检查可能报 `attempt to write a readonly database`；先验证引擎兼容性，不跳过完整性检查。
- Hermes 的安装解释器、`.pth` 位置和 standalone 与 installer 分发方式需要分别验收；OpenClaw hybrid 依赖真实 host 调用 prefetch。
- 合成 recall eval 的标签、时间与小样本限制见 TEST_MATRIX，尚不能作为正式质量门禁。
- 驱动、I/O 和 payload 错误会降级。其它异常会抛回调用方。未列入 `VECTOR_ERRORS` 的向量客户端错误不会被吞掉。见 ADR-038。
- `scripts/memory-slim --online` 依赖同级 Octop checkout，且脚本优先使用其虚拟环境。
  独立用户使用 `octop-memory db slim`。在线维护仍需宿主协调。
- `deploy-openclaw.sh` 会安装依赖、更新 checkout、替换插件目录。`--setup-dry-run` 只预览配置步骤。
  部署和真实宿主 E2E 需在专用环境另验。

## 已有安装的迁移

源码使用当前发行包、插件 ID、环境变量、默认目录和 PG schema。旧安装不会自动迁移。
步骤见 [集成指南](../integrations.md#更名与已有安装迁移)，存储协议取舍见 ADR-037。
