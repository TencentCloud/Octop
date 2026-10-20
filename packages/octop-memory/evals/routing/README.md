# 写入路由黄金标注集(Routing Golden Dataset)

> 配套 `docs/plans/2026-07-17-memory-target-architecture.md` §3-4。
> 目标:extractor prompt / 路由规则每次改动后,跑一遍验证"该记的没丢、该丢的没记、记的去了对的地方"。

## 路由标签(expected_route)

| 标签 | 含义 | 对应机制 |
|------|------|----------|
| `xiaochao` | 小抄:常驻注入 | `__user__` / `__agent__` core block |
| `xiaochao_pinned` | 小抄置顶:锁定,不参与降级 | 禁忌/安全红线 |
| `xiaochao_ttl` | 小抄带有效期:到期降级或转正 | 近期状态 |
| `dict` | 字典:atom 入库,按需召回 | M4 管道 |
| `dict_fast` | 字典快车道:逐字秒级入库 | 显式"记住" |
| `dict_low_confidence` | 字典低置信:存但排序靠后 | 传闻/未确认 |
| `episode` / `episode_low` | 日记层,不进 atom | Episode 通道 |
| `lesson` | agent 教训 → SOUL.md 自进化区 | Phase 2 通道 |
| `inbox` | 收件箱便签:注入一次即清 | MEMORY.md |
| `manage` | 否认/纠错:两拍机制,非新增 | memory_manage |
| `manage+save` | supersede:旧条失效+新条入库 | 事实更新 |
| `split` | 一句多条,拆分后分别路由 | extractor 拆卡 |
| `needs_review` | 高危,入审核队列 | 自我指令类 rule |
| `discard` | 丢弃(L0 录像仍保留) | 不产 candidate |

## 覆盖的判定难点

- **R15 vs R16**:assistant 建议"考虑一下"(丢弃)vs"就这么办"(决策)——接受性判定
- **R08 / R23**:否定词与时序限定词的逐字保留(anti-dilution)
- **R17 / R18 / R30**:否认 ≠ 追加,纠错 = manage 两拍;更新 = supersede 链
- **R05 / R06**:检索捞不到的普适状态必须上小抄,且带 TTL
- **R12 / R26**:情绪进日记不进 atom;强度决定 intensity
- **R21**:自我指令类规则是 prompt 注入的持久化载体,必须 needs_review
- **R22 / R22b**:禁止清单是 **host 级配置**而非固定规则——默认只含 host 系统注入项(模型/部署配置),接了 OA 等外部源的部署自行扩充;同一句话("我工号是 88372")在不同部署下路由不同
- **R24**:一句话多条异质记忆必须拆卡
- **R31**:拆卡进阶——"和同事 Matt 吃麻辣烫"拆出三份命运:关系事实(dict)+ 一次性事件(episode)+ 偏好观察期(暂不存)。**注意:现有 extractor prompt 的 Example 0 与此冲突**(它教 LLM 把午餐抽成 low importance atom),落地时需改 prompt 把一次性事件让给 episode 通道
- **R32**:里程碑双写——"签下第一个合同"同时进 episode(情绪现场)和 atom(传记事实)。判据:**事件的发生本身,一年后还值得被引用吗?** 午餐不值得(R31),第一单值得(R32)。另含匿名实体陷阱:"百万网红"无稳定名,不建 Person 实体,匿名引用留在文本,得名后再建实体回挂
- **R25**:隐式偏好需要重复出现(≥2 次)才固化,防单次误判

## 建议指标

| 指标 | 定义 | 为什么重要 |
|------|------|-----------|
| 路由准确率 | expected_route 完全命中 / 总数 | 总体健康度 |
| **误存率**(最关键) | discard 类被存下来的比例 | 记忆污染不可逆,比漏记更伤 |
| 漏记率 | 非 discard 类被丢弃的比例 | 用户"说过的话它不记"的体感 |
| 否定保真率 | R08/R23 类 assertion 保留否定/限定词的比例 | anti-dilution 底线 |
| 主体归属正确率 | target 实体/页命中比例(R11/R29 类) | 张冠李戴检测 |
| 追加违规率 | R17/R18/R30 类走了 save 而非 manage 的比例 | 冲突治理底线 |

## 后续扩充方向

1. 每类扩到 10+ 例(现在每类 1-3 例,先跑通再扩量)
2. 多轮上下文依赖的 case(第 3 轮的"它"指代第 1 轮的项目)
3. 中英混排与纯英文对照组(FTS 中文分词的召回验证顺带做)
4. 从真实 L0 日志脱敏采样,替换手写例子
