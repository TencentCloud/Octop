# 强记忆

<!-- 用户在「记忆 → 强记忆」中手动填写。每个会话开始时加载一次全文快照，修改对新会话生效。 -->
<!-- 适合记录始终需要参考的重要背景和约定。Agent 通过 memory_save 保存普通记忆，不修改本文件。 -->

## 本机环境基线

- Octop 运行在腾讯云 CVM 上，域名 `http://octop.devcloud.woa.com`，服务 `systemctl status octop`
- 云账号：单账号，授权范围约 300–550 台 CVM，主要地域 `ap-guangzhou`（另有 `ap-qingyuan`、`ap-nanjing` 等）
- 账号内有大量刚创建/已销毁的压测实例（名字形如 `inttest-*`、`it-*-1793xxxxx`）：**批量调用云 API 时它们会让整批请求失败**，必须做二分降级

## 凭据链路（两套，别搞混）

| 凭据 | 位置 | 谁在用 |
|---|---|---|
| 工作台 OAuth | `~/.octop/secrets/cloud/<uid>.enc` | 工作台页面（实例列表、监控图表） |
| tccli OAuth | `~/.tccli/<profile>.credential` | 对话里的我（走 tccli） |

工作台授权后会镜像一份到 tccli；`默认 profile=default`，若开启 `OCTOP_TCCLI_PROFILE_ISOLATION=1` 则为 `octop-<uid>`，真实值看 `~/.tccli/.octop-profile`。

工具路径和脚本用法在 `SOUL.md` 第二节。

## 知识库

已绑定《腾讯云CVM运维规范》（id `FY6KAS`），含：巡检 SOP 与分级标准、常见故障处置手册、变更门控与回滚规范、CVM 指标口径、诊断方法论与集群关联模式、TAT 执行规范。

**规范类问题先查 KB**（阈值、SOP、处置路径），**本环境的具体事实用 memory 工具**（哪台机器、上次结论、用户偏好）。

## 已知坑（踩过的）

1. `GetMonitorData` 批量请求中混入已销毁实例 → 整批 `InvalidParameterValue`，全部无数据；需二分拆分
2. 云监控数据延迟 1–2 分钟，查询窗口末端要回退 120 秒，否则末点常缺失
3. `CpuUsage`、内存、磁盘、`CpuLoadavg` 依赖云监控组件；未安装时为空 → 显示 `—`，**不是 0%**。内网带宽一般不依赖这个组件。云监控组件和 TAT 的 `tat_agent` 不是同一个
4. 轻量应用服务器可以用 TAT，但一次 `RunCommand` 不能和 CVM 混用；实例须为 RUNNING、VPC，且 tat_agent 在线。基础网络不能用 TAT
5. 批量 `DescribeInstances` 47 个地域串行要 4 秒以上，必须并发（16 并发约 2.5 秒）

## 用户偏好

- 要**证据**：结论后面挂数值或命令输出，不接受"疑似/可能"
- 不要反问"哪台机器"，默认指工作台当前选中的实例
- 诊断报告只用 `skills/tencentcloud-infra/references/diagnosis-report.md`。页面色带和诊断分级分列，不编造未采集的数字
- 变更前必须说清「动作 + 影响 + 回滚」，🔴 级要等用户说出实例 ID
