# nong-gateway-plugin

> **不影响主体代码更新的「劫持元宝消息渠道」插件**
> 让 N 个 Octop 专家各带一个元宝 / Kimi 机器人进群，行为受控、prompt 极简、历史可检索。
> 不修改 Octop 与 harness_gateway 一行源码——官方升级随时可覆盖，插件照常工作。

[![平台](https://img.shields.io/badge/platform-Octop%20v1.0.0-blue)]()
[![类型](https://img.shields.io/badge/plugin%20kind-hook-green)]()
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)]()
[![License](https://img.shields.io/badge/license-MIT-lightgrey)]()

---

## 目录

- [一、这是什么](#一这是什么)
- [二、为什么需要它：一个真实事故](#二为什么需要它一个真实事故)
- [三、核心技术：劫持](#三核心技术劫持)
- [四、消息链条（完整分层）](#四消息链条完整分层)
- [五、功能清单](#五功能清单)
- [六、快速开始](#六快速开始)
- [七、配置参考](#七配置参考)
- [八、命令与工具](#八命令与工具)
- [九、故障排查](#九故障排查)
- [十、研发历程](#十研发历程)
- [十一、架构与边界](#十一架构与边界)
- [十二、研发投入](#十二研发投入)

---

## 一、这是什么

一个 **Octop 插件**（`kind: hook`），把 IM 群桥（元宝 / Kimi Claw）跑进 Octop 进程，
让群里每一个机器人绑定一个 Octop 专家 agent：

```
元宝群
 ├── @主理人   → 桥[main]      → Octop agent: main（总控，ask_agent 调度专家）
 ├── @分身助手 → 桥[assistant] → Octop agent: assistant
 └── @数据分析 → 桥[data-analysis] → Octop agent: data-analysis
```

**三个不变**：

1. **Octop 主体代码不变** —— 所有能力走插件，`pip install -U octop` 覆盖 venv 也不影响
2. **官方 UI 不变** —— 通道页扫码 / 启用 / 停用照常使用，插件在运行时接管业务
3. **模型上下文不变** —— 插件不注册 tool / skill / middleware，对模型而言它不存在

---

## 二、为什么需要它：一个真实事故

### 2.1 事故现场（2026-09-17）

用户在元宝群里发了一条消息，两个 AI 机器人开始**互相接话**，回复刷屏、停不下来。
面板停用前一直循环。

### 2.2 根因（日志实证）

```
1. Octop 内置通道页启用了两个元宝通道（分属 main / assistant 两个 agent）
2. 两个机器人被拉进同一个群
3. 内置通道把「机器人发的消息」也当新消息处理（Group.CallbackAfterSendMsg from=bot_xxx）
   → A 回 B → B 把 A 的回复当新消息 → A 再回 B → 无限循环
```

### 2.3 结论

官方内置通道是「**一个机器人接一个 agent**」的简单模型，缺少三样东西：

| 缺失 | 后果 |
|---|---|
| 不滤机器人消息 | 同群多机器人 → 互答死循环 |
| 无群策略（mention / 白名单） | 群里任何消息都触发，无法收敛 |
| 无多 agent 路由 | 无法「@谁谁答」，也无法让主控 agent 调度专家 |

**这个插件就是来补这三样的——但用不改主程序的方式。**

---

## 三、核心技术：劫持

### 3.1 问题

我们需要的管控（四道闸 / 群策略 / prompt 分层 / 本地账本）**只能在通道收到消息之后做**。
而官方通道的行为是：

```
WS 收帧 → parse → 无条件发 typing 气泡 → GroupContext → processor（起 agent 轮次）
```

只要通道被官方启用，消息就必然进入这条管道。**我们必须在管道内部换掉关键环节。**

### 3.2 解法：运行时劫持（runtime hijack）

不改文件、不打补丁、不 fork 官方代码，而是**在插件启动后对运行中的通道实例做运行时替换**：

```
插件 setup()（服务每次启动 / 重载自动执行）
   │
   ├─ 1. 等 octop gateway 注册该通道（gc 扫描定位 OctopServer → gateway.channel_manager）
   │
   ├─ 2. 运行时替换（全部是实例属性覆盖，进程内生效、落盘为零）
   │      ch._parse_yuanbao_message  ← 包一层：设 bot_mentioned 标记 + 本地账本落盘
   │      ch._group_context         ← 注入 GroupContextConfig（mention_only/mention/history=none）
   │      ch._send_typing_indicator ← 门控：没 @ 不发「正在输入」气泡
   │      ch._processor             ← 换成桥的业务处理器（四道闸 / 白名单 / 别名 / 群策略）
   │      ch._send_text             ← 换成出站编码版（@名字 → 平台结构化 at 元素）
   │
   └─ 3. 桥侧该 agent skip_ws=True —— 不抢订阅锁、不建第二条连接
          （单消费者 = 内置通道的单条 WS；双消费者从结构上消失）
```

**为什么叫「不影响主体代码更新的劫持」**：

| 传统做法 | 本方案 |
|---|---|
| 改 `harness_gateway` 源码 → pip 升级即丢 | 运行时替换运行中的实例，**升级后 setup 重跑自动重新接管** |
| fork 官方包 → 上游更新无法跟进 | 官方包原样，随时 `pip install -U` |
| 打包成独立服务 → 与官方抢同一个 bot | 不建第二条连接，**官方连接就是我们的连接** |

### 3.3 升级自愈

`setup()` 随服务启动自动执行，内含三段幂等自愈：

1. **kimi 通道回植**：pip 升级覆盖 venv 的 `harness_gateway` → 检测注册表缺 `kimi` → 从插件 vendor 目录拷回 + 补三处注册
2. **内置通道残留处置**：扫 `channels` 表，`enabled=1` 的 yuanbao/kimi 行 → 劫持模式下接管，非劫持模式自动停用（防双消费）
3. **官方备份在位检查**：venv-backup 缺失时自动 tar 一份，留回滚参照

---

## 四、消息链条（完整分层）

以一条群消息为例，**六层过滤，从外到内**：

```
┌─ 元宝平台云端 ─────────────────────────────────────────────┐
│  群消息推送（WS）                                           │
└────────────────────────┬───────────────────────────────────┘
                         ▼
  ① 劫持通道 parse 层
     ├─ 设 bot_mentioned 标记（结构化 at 的 user_id 与自己 bot_id 精确比对）
     └─ 本地账本落盘 ← 【渐进式披露】全部群消息进 md，agent 需要时 rg 查
                         ▼
  ② typing 门控
     └─ 没 @ → 不发「正在输入」气泡（官方原生是无条件发）
                         ▼
  ③ GroupContext（通道层）
     visibility=mention_only + activation=mention
     └─ 没 @ → return None，消息到此为止
        （不进 processor、不起 agent 轮次、零 token 消耗）
                         ▼
  ④ 桥四道闸（process）
     ├─ 自己发的 → 拒
     ├─ 重复推送 → 拒
     ├─ 白名单未命中 → 静默拒
     └─ 群消息未被 @ → 拒（monitor 模式例外，带节流）
                         ▼
  ⑤ prompt 组装（compose）
     【通道说明】
     【被引用的消息 · 谁】      ← 平台 quote + 本地回查
     【本轮请求 · 需要你回应】   ← 只有这条是「要答的」
                         ▼
  ⑥ Octop 宿主（官方 WS 会话 API）
     ws://127.0.0.1:8088/api/agents/<agent_id>/chat/ws
     └─ 每 agent 一个 thread，记忆 / 知识库 / 子代理全部保留
```

### 4.1 关键设计决策

| 决策 | 原因 |
|---|---|
| 群历史**不进 prompt** | 用户定调：渐进式披露——历史做本地存储，agent 要用时去查 |
| 账本落**专家工作区** | `<工作区>/群记录/<群>/<日期>.md`，agent 用 rg 直接检索 |
| `[机器人]` 标注 | 账本里人与 AI 分明，`rg '\[机器人\]'` 可单独查 AI 对话 |
| 本轮请求独立成块 | 模型不再有「这段是历史还是要答的」歧义 |
| 别名单播（aliasRoute） | `@元宝` 只由指定 agent 承接，避免多播刷屏 |

---

## 五、功能清单

| 能力 | 说明 |
|---|---|
| **多 agent 群聊** | 一机器人绑一专家；mention 默认拒绝；白名单；自消息滤除 |
| **@ 别名代理** | `@元宝`（平台助手）可路由到指定 agent；支持单播路由表 |
| **出站真 at** | 回复里的 `@名字` 编码成平台结构化 at 元素，被点对象真收到 |
| **出站媒体** | 回复末尾写 `MEDIA: <路径>`，文件发到群里（带工作区白名单与凭据名过滤） |
| **prompt 极简** | 只收：被 @ 的那条 + 引用 + 文件；群历史零占用 |
| **本地账本** | 群消息落 md 可 rg 检索，双通道去重；**per-agent 开关**：`groupLogMode`（off/md）× `groupLogScope`（human/all） |
| **群聊策略** | 照抄官方 QQ 渠道：visibility / activation / history / clear_after_reply |
| **面板开关三层** | 插件页总闸 / 专家页 per-agent 勾选 / config agents 段（默认拒绝） |
| **超时转后台** | 模型慢时转后台继续跑，完成后补发，不以「超时失败」收场 |
| **主动推送** | outbox 队列：`outbox/<agent>.json` → 专家可主动发群消息 |
| **升级自愈** | kimi 回植 / 内置通道残留处置 / 官方包备份，全程幂等 |
| **热重载** | 改配置 ≤30s 生效；重装插件新旧代干净交接，不丢锁 |

---

## 六、快速开始

### 6.1 前置

- Octop 已部署并运行（本机 8088）
- 元宝 / Kimi 机器人凭据（通道页扫码或已有 app_key/app_secret）

### 6.2 打包与安装

```bash
# 打包（自带校验：manifest 契约 / 密钥特征扫描 / 打包白名单）
python3 tools/打包.py --out dist/

# 安装
TOK=$(python3 取token.py --db /data/wwlst/octop/octop.db)   # 或从面板获取
curl -X POST "$OCTOP_API/api/plugins/upload" \
     -H "Authorization: Bearer $TOK" \
     -F "file=@dist/nong-gateway-0.1.0.zip" \
     -F "force=true"
```

### 6.3 迁移配置

```bash
# 从 octop.db channels 表 + 旧桥配置 → ~/.nong-gateway/config.json（0600）
python3 tools/迁移配置.py --write
```

### 6.4 启用劫持

```jsonc
// ~/.nong-gateway/config.json
{
  "hijackBuiltin": true,
  "hijackedAgents": ["main", "assistant"],
  "hijackedAgents 说明": "这些 agent 的通道启用后由插件接管，桥不建第二条连接"
}
```

### 6.5 验证

```bash
# 1. 通道页启用目标通道（UI 操作）
# 2. 看日志：劫持完成的四行
grep -E '劫持完成|群聊策略已应用' /data/wwlst/octop/logs/octop.log | tail -4

# 3. 群里 @机器人 说句话 —— 应只回一条
# 4. 群里不 @ 说句话 —— 应完全安静（气泡都没有），但账本多一行
tail -3 /data/wwlst/octop/agents/main/群记录/<群号>/$(date +%F).md
```

---

## 七、配置参考

### 7.1 顶层键

| 键 | 类型 | 说明 |
|---|---|---|
| `hijackBuiltin` | bool | 启用劫持模式（false = 自动停用内置通道，分发缺省） |
| `hijackedAgents` | list | 参与劫持的 agentId 列表 |
| `host` | str | 宿主机类型；本插件形态用 `octop` |
| `octopHome` / `octopPort` / `octopUserId` | - | octop 宿主连接参数 |
| `mentionTargets` | dict | 出站 at 编码：`{"名字": "user_id"}`（入站帧会动态学习覆盖） |
| `groupLogMode` | str | `md` = 群消息逐条落盘（可检索）；`off` = 不落盘。**全局兜底值**，可被 per-agent 覆盖 |
| `groupLogScope` | str | `human` = 只记人的发言（缺省）；`all` = 人 + 机器人（`[机器人]` 标注）。**全局兜底值**，可被 per-agent 覆盖 |
| `credentials` | list | 通道凭据（kind / agentId / appKey / appSecret / token ...） |
| `agents` | dict | 按 agent 的生效设置（见下） |
| `defaultPolicy` | str | `deny` = 默认拒绝（未点名的 agent 不服务） |

### 7.2 per-agent 键（`agents.<agentId>`）

| 键 | 说明 |
|---|---|
| `enabled` | 是否服务该 agent（默认拒绝，需显式点名） |
| `groupMode` | `mention`（只回被 @）/ `monitor`（全群回，带节流） |
| `allowFrom` | 发送人白名单（默认空 = 不接任何人） |
| `mentionAliases` | at 别名代理，如 `["元宝"]` |
| `aliasRoute` | 别名单播路由，如 `{"元宝": "main"}` |
| `groupLogMode` | 该 agent 的群记录落盘：`md` / `off` |
| `groupLogScope` | 该 agent 的落盘范围：`human`（只记人）/ `all`（人 + 机器人，带 `[机器人]` 标注） |
| `contextWindow` | 群近况条数（新架构下 prompt 不含历史，此键仅留兼容） |
| `outboundMedia` | 允许发文件到群 |
| `showThinking` / `forwardTools` | 是否展示思考 / 工具调用 |
| `role` | 角色名（映射工作区 / 工具 / 模型 / 沙箱） |

### 7.3 群记录（本地可检索账本）

**落点按 agent 自动隔离**（各自工作区内，沙箱互不可见）：

```
<octopHome>/agents/<agentId>/群记录/<群号>/<日期>.md
```

格式：`- HH:MM [机器人] 发送者: 内容（附媒体）`

- `rg` 直接可查：`rg -n "关键词" 群记录/`
- `[机器人]` 前缀只在该 agent 的 `groupLogScope=all` 时出现
- 双通道收到的同一条消息自动去重（跨代共享指纹表）

**per-agent 差异化示例**：

```jsonc
{
  "groupLogMode": "md",                      // 全局兜底
  "agents": {
    "main":      { "groupLogMode": "md",  "groupLogScope": "all"   },  // 总控：人+机器人全记（要看全局）
    "assistant": { "groupLogMode": "md",  "groupLogScope": "human" },  // 助手：只记人（去噪、省磁盘）
    "data-analysis": { "groupLogMode": "off" }                         // 不落盘（专干活的专家）
  }
}
```

两个键都在 `PER_AGENT_KEYS` 里，改完 **≤30s 热生效**，无需重启。

### 7.4 三种开关的语义

```
生效(agent) = config.agents 段点名（默认拒绝）
            ∩ 面板插件 per-agent 开关（agents.config_json.plugins["nong-gateway"].enabled，15s 读取）
            ∩ 面板插件全局开关（关 = 看门狗收线）
```

---

## 八、命令与工具

```bash
# 打包 + 校验
python3 tools/打包.py --check-only          # 只校验
python3 tools/打包.py --out dist/            # 校验 + 出 ZIP

# 配置迁移（octop.db channels → ~/.nong-gateway/config.json，0600）
python3 tools/迁移配置.py                    # dry-run
python3 tools/迁移配置.py --write            # 落盘

# 主动推送（专家 / 运维都可写）
cat > ~/.nong-gateway/outbox/main.json <<'EOF'
{"agent": "main", "subject": "<群号>", "text": "要发的内容"}
EOF
# 桥主循环 1s 轮询，发出后自动删除；失败重命名 .err 留痕
```

---

## 九、故障排查

| 症状 | 排查 |
|---|---|
| 通道启用后无反应 | `grep 劫持完成` 看是否接管；无则看 `劫持失败：通道 … 未注册` |
| 群里不 @ 也回话 | 检查 GroupContext 是否注入成功（`群聊策略已应用` 日志） |
| 看到「正在输入」气泡但不回 | typing 门控未生效（旧闭包），重载插件 |
| 双份回复 | `channels` 表同 bot 有两行 enabled=1，或内置通道复活 |
| 出站 @ 无效 | `mentionTargets` 里的 id 过期（bot 重建后 id 变），入站帧会自动学习 |
| 重载后行为没变 | 模块缓存 / 闭包未更新：看 `劫持完成` 时间戳是否为最近 |
| 账本不落盘 | `群消息落盘失败` 日志；确认该 agent 的 `groupLogMode=md`（per-agent 可覆盖全局） |
| 账本里看不到机器人发言 | `groupLogScope=human`（缺省）只记人；要记 AI 改 `all` |
| 账本重复行 | 跨代去重表未生效（应挂 builtins 共享），重载插件 |

---

## 十、研发历程

> 从「群里突然冒出 AI 回复」到「不影响主体更新的劫持插件」，全程 **2026-09-17 → 09-18**，
> 每一条结论都来自实测日志 / 抓帧 / 数据库，无一条推测。

### 第 0 阶段：事故（09-17 16:04）

用户群里发言 → 两个元宝机器人互答刷屏。
**定位**：内置通道不滤机器人消息 + 无群策略 → 互答死循环。
**处置**：通道页停用（`channels.enabled=0`）。

### 第 1 阶段：桥接原型（09-17 17:00-19:00）

决定用外部桥（nong_gateway）替换内置通道，产出插件骨架：

- 四道闸（自己发的 / 重复 / 白名单 / at 判定）
- 群策略（mention / monitor / 节流）
- octop 宿主适配器（官方 WS 会话 API，per-agent thread）

**踩坑**：热重载跨代状态不能挂模块属性（`unload_plugin` 会 pop `sys.modules`）→ 改挂 `builtins`；
收线必须调 `runner.stop()`（外层 Event 传不进阻塞循环）；WS 帧协议是 `token`/`done` 不是 `delta`。

### 第 2 阶段：出站真 at（09-17 20:00-20:30）

**发现**：agent 回复里的 `@名字` 是纯文本，被点对象收不到真 at。
**抓帧**得到平台结构：`TIMCustomElem.msg_content.data = {"elem_type":1002,"text":"名字","user_id":"…"}`。
**三变体实测**后定案：文本段保留全名 + at 元素 text 为纯名字 + 紧凑 JSON——缺一不可，
平台校验 TXT-AT 配对，不匹配就静默剥掉元素。

### 第 3 阶段：超时与死循环体感（09-17 20:31）

**现象**：慢任务 → 群里出现「[宿主报错] 等待回复超时」→ 后台跑完却不补发 → 用户再问 → 循环。
**两个真 bug**：defer 判定等一个永远不抛的异常（内部 deadline 是正常 return）；
模块缓存清理漏裸名（`octop_host` 本体没清，重载后跑旧类）。

### 第 4 阶段：UI 开关语义（09-17 深夜）

**发现**：面板 per-agent 插件勾选**不过滤 hook 线程**（官方只过滤 tool/skills）。
**补丁**：桥 15s 读 `agents.config_json.plugins`，与 UI 同源，关掉即沉默。

### 第 5 阶段：定位「主理人说话传到分身助手」（09-18 08:32）

**真相**：不是桥——是 `channels` 表被改回 `enabled=1`，内置通道复活，
用**内置通道时代的旧 session_key** 收发。
**处置**：重新停用 + 清理 5 条旧会话（API 级联 + SQL 清悬空 session）。

### 第 6 阶段：劫持诞生（09-18 09:30-10:00）

**用户诉求**：通道页要用来扫码/绑定，但启用就双消费。
**方案**：运行时劫持——通道页启用照常，插件在 gateway 注册后**替换实例的关键方法**。

**实现要点**（都踩过）：
- 通道实例在 **octop gateway 的 ChannelManager**（不是桥自己的空 manager）
- `OctopServer` 实例无单例 → **gc 扫描**定位，结果缓存 `builtins`
- 绑定函数必须 `async def`（普通函数被 await → `TypeError: NoneType`）

### 第 7 阶段：prompt 极简（09-18 12:00-13:00）

**用户定调**：「不是所有群聊消息都要塞进 prompt，做成可检索的。
只有我直接 @ 他的消息、连带的文件、引用的消息，才是 prompt。」

**落地**：compose 只输出【通道说明】+【引用】+【本轮请求】；
群消息改落本地账本（`群记录/<群>/<日期>.md`，`[机器人]` 标注）。

### 第 8 阶段：群聊策略照抄 QQ（09-18 12:58）

**发现**：官方 QQ 渠道有完整「群聊策略」UI，底层是 `GroupContextConfig`；
元宝适配器缺两块——parse 不设 `bot_mentioned`、Config 无 `group_context` 缺省。
**补丁**：劫持时包 parse 设标记 + 运行时注入策略（`mention_only` / `mention` / `history=none`）。
**效果**：非 @ 消息在**通道层**就被吞，连 processor 都不进。

### 第 9 阶段：气泡门控（09-18 14:56）

**用户观察**：没 @ 也看到「机器人在打字」。
**追查**：元宝通道 `_handle_text_frame` 对**每条**入站消息无条件发 `HEARTBEAT_RUNNING`，
且在 GroupContext 之前。
**补丁**：劫持 `_send_typing_indicator`，只在真正会被处理时亮气泡。

### 第 10 阶段：稳定性收敛（09-18 15:00）

**乱局**：多次热重载后，多代劫持线程互相覆盖绑定，导致「新 main.py + 旧 core」混搭报错、
账本漏记、行为回退。

**教训与修复**：
- 劫持线程必须**允许重复 spawn**（后绑覆盖先绑）——加防重锁反而把新闭包挡在外面
- 本地账本调用改**防御式**（`inspect.signature` 检查支持才传新参数）
- 打包必须**验证产物**（曾出现 `plugin/src` 未同步导致 dist 里是旧代码）

### 最终形态（09-18）

```
群消息 → ① parse（标记+落账本）→ ② typing 门控 → ③ GroupContext（非 @ 吞）
        → ④ 四道闸 → ⑤ prompt 极简 → ⑥ Octop 宿主（per-agent thread）
```

**不在主体里留一行改动，升级覆盖后自动重新接管。**

---

## 十一、架构与边界

### 11.1 目录

```
plugin/              可分发 ZIP 的内容（plugin.yaml + main.py）
  main.py            插件壳：启动门 / 看门狗 / 自愈 / 劫持线程
src/nong_gateway/    业务层（凭据、四道闸、compose、账本、宿主接缝）
src/nonggw_kimi/     vendor 的 kimi 通道（官方升级覆盖后依然可用）
src/octop_host/      Octop 宿主适配器（官方 WS 会话 API）
tools/               打包校验 / 配置迁移
dist/                产物 ZIP
```

### 11.2 边界（明确不做的）

- **不改 Octop / harness_gateway 源码**——所有改动都是运行时实例替换
- **不注册 tool / skill / middleware**——模型上下文零占用
- **不建第二条 WS 连接**——单消费者由「官方连接即我们的连接」保证
- **不碰面板 UI 代码**——用户看到的开关都是官方原生的

### 11.3 已知风险

| 风险 | 说明 |
|---|---|
| 官方改 WS 会话协议 | 宿主适配器会报错（日志留痕）→ 回滚 octop 版本 |
| 官方改通道内部方法名 | 劫持绑定失败（`劫持失败` 日志）→ 需同步适配 |
| 多代热重载 | 已加「允许重复 spawn + 后绑覆盖」；极端情况重启服务可清场 |

---

## 十二、研发投入

| 项 | 值 |
|---|---|
| 研发周期 | 2026-09-17 ~ 2026-09-18（两天，含深夜） |
| 主力模型 | **DeepSeek V4.1** |
| 模型成本 | **约 500 元** |
| 代码规模 | 插件壳 + 业务层 + vendor 通道约 8,000 行 |
| 提交数 | 42 commits（含 12 个实测修复） |
| 事故复盘 | 10 个研发阶段，全部有日志/抓帧/数据库实证 |

---

## 附：为什么是 hook 插件

| kind | 会进模型上下文的 | 本插件 |
|---|---|---|
| `tool` | 每个工具的定义（名称+描述+schema） | ✗ |
| `skill` | SKILL.md 正文注入工作区 | ✗ |
| `hook` | 仅注册的 middleware | ✗（一个都不注册） |

`setup()` 里只做三件事：启动门判定、起桥线程、起劫持线程。
对模型而言，这个插件**不存在**。

---

## License

MIT
