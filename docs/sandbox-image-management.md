# 沙箱镜像版本管理(设计稿)

状态:**设计已定稿,未实施**(2026-10-20)。等待明确指令后动代码。
2026-10-23 增补:allow_network 联网状态与联网漂移纳入台账(§5.7),recreate 同时作为联网开关的生效动作(§5.5)。
解决"沙箱镜像更新后,已有容器不换代"与"沙箱联网开关改了不生效"两个运维问题。
落点:后端 `src/octop/`,前端 `dashboard/src/`,文档 `docs/agent-backend-file-io.md` §13 增补。

---

## 0. 一句话结论

给 Admin 增加"沙箱容器台账 + 漂移检测 + 一键重建(CLI + API + 界面同步交付)":列出本机所有
`harness.agent.sandbox` 标签的容器、比对容器实际镜像与后端配置期望镜像,标出 **DRIFT**;
同时读取容器实际网络模式与配置期望的 `allow_network`,标出 **NETWORK-DRIFT**;
重建 = 自动备份容器内工作区到宿主 → 校验新镜像存在 → 删容器 → 下次对话自动用新镜像/新网络模式创建。
P2 增加"备份写回新沙箱"。

## 1. 背景与问题

Docker 沙箱的容器生命周期由 harness 决定,当前有三个"不会自动":

| 行为 | 现状(harness `docker_sandbox.py`) | 后果 |
|---|---|---|
| 镜像检查 | `ensure_docker_image` 只判断本地有没有该 tag(`:144`),不比较新旧 | 同名 tag 覆盖 `docker load` 后,已有容器感知不到 |
| 容器复用 | `_acquire_container` 按名字找到且在运行就复用(`:387`),不检查容器跑在哪个镜像上 | 后端配置改成新 tag 也一样复用旧容器 |
| 生命周期 | `close()` 永不删持久沙箱;只有 `destroy()` 删 | 没有任何管理面触发重建 |
| 网络模式 | `allow_network` 只在 `_create_container` 时固化为 `network_mode`(`:476-477`),复用容器不再看 | 配置改成 `allow_network: true/false` 对已存在的容器**不生效**;且联网状态无任何界面可见 |

与镜像换代同理,"改联网配置 → 想让它生效"也必须删容器重建,同样撞上"容器可写层
工作文件会丢"的问题。两个场景需要同一个原语:**安全的容器重建**。

于是"新镜像加了技能依赖 → 期望容器换代"这一步完全靠手工 `docker rm -f`,且容器内
工作区文件(沙箱无 bind-mount,文件在容器可写层)会随删除丢失,容易被当成 bug。

## 2. 数据分布边界:换代时"什么会动"

沙箱是"同名路径、两处落盘、不自动挂载"的设计。换代前必须清楚每类数据住哪:

| 数据 | 住哪 | 换容器时 |
|---|---|---|
| 会话记录 sessions / 记忆 memory / checkpoints | 宿主 `workspace_dir`(`~/.agentbuddy/agents/<id>/`) | **不受影响**(天然保留) |
| 对话历史 | 宿主(harness history) | 不受影响 |
| 专家工作区内容文件(SOUL.md、技能、agent 生成的文档) | **容器可写层**(容器内同名绝对路径) | **随删除丢失** → recreate 第 2 步备份兜住 |
| pip/npm 已装依赖 | 容器可写层(若有开网时装的) | 丢失;新镜像自带白名单,依赖升级正是换代的目的;**关闭联网重建时一并清掉,与"回收网络权限"的意图一致** |

结论:**换容器的唯一数据风险是工作区内容文件**,本设计的备份/写回机制专门覆盖它。
"换容器 = 丢对话"是误解,不存在。

## 3. 目标与非目标

**目标**

1. 台账:列出本机全部沙箱容器(scope/agent 归属/实际镜像/**实际网络模式**/状态/创建时间)。
2. 漂移检测:容器实际镜像 ≠ 期望镜像(来自 agent 配置或 storage_backends `kind=docker` 行)→ 标记 `drift`;
   容器实际网络模式 ≠ 期望 `allow_network` → 标记 `network_drift`(§5.7)。
3. 重建:删除漂移(或任意)沙箱容器;**删除前自动备份容器内工作区到宿主**,新容器创建后自动写回(P2)。
4. 镜像清单:列出本地镜像、体积、被哪些后端配置引用,辅助"导出新镜像前确认引用关系"。
5. **镜像 tag 编辑路径**:专家编辑抽屉的存储后端区块当前整体禁用(见 §4),P1 打通"只改 image tag"的受控编辑,配合换代。
6. 两个入口:Admin API(`/api/admin/sandboxes`)+ CLI(`octop sandbox`);Dashboard「Admin → 存储」页增加"沙箱"面板。
7. i18n:API 错误码进 `ErrorCode` + 前后端四份 bundle;CLI 输出同现有命令风格(英文为主)。

**非目标**

- 不做镜像构建/导入自动化(`docker save/load` 与 `Dockerfile.sandbox` 的构建仍走文档流程);
- 不改 harness 的复用策略(同名容器即复用是合理默认,换代由本功能显式触发);
- 不做自动定时换代(升级永远是人触发的动作,政务环境需要窗口期);
- 不做远程 Docker 宿主机管理(部署形态确认:单机 daemon;见 §10 Q1 裁决);
- OpenSandbox 后端不纳入(它是远程托管、随 agent 启停,没有"换代"问题)。

## 4. 为什么专家编辑抽屉的存储后端是禁用的(考证)

现状:`EditAgentDrawer.tsx:862` 对 `AgentBackendFields` 无条件传 `disabled` +
`rootDirMode="edit"`;创建抽屉(`CreateFromExpertDrawer.tsx:799`)不传,可正常编辑。
即:**前端约定"后端只能在创建时选,编辑时锁死"**,后端数据层并无对应限制
(`PATCH /api/agents/{id}` 接受 `config.backend`,`agents.py:391-394` 有 root_dir 策略校验)。

历史考证(上游提交):

- `7e74b1e0`(#481)"polish expert root-dir UX":编辑模式禁用 `RootDirSelect` 并替换提示文案——
  禁用的起点是 **root_dir 越狱语义**(编辑 root_dir 会改变既有路径映射/执行 jail,风险高),
  属于谨慎防呆,不是数据不可改;
- `5e7a8ba9`(容器 FS 默认值/专家头像轮):编辑抽屉对整个 `AgentBackendFields` 传
  `disabled`,**没有附带提示文案、没有迁移机制**——是"编辑后端 = 没有配套的迁移/重建故事,
  先整体锁死"的防呆,而非数据层不可改。

结论:上游禁用的真实原因与讨论一致——**没有容器换代/数据迁移机制之前,开放编辑的
风险不可控,干脆锁死**。本功能(台账+备份+重建)正是补上这块缺失的机制;P1 打开
**受控的镜像 tag 编辑**(只允许改 image,root_dir/路径映射继续锁),编辑入口与
"换代三步"联动(见 §5.1),其余字段维持禁用。

## 5. 核心设计

### 5.1 配置变更生效标准流程(本功能支撑的完整闭环)

镜像换代与联网开关共用同一流程,recreate(③)是两者共同的生效动作:

```
① 准备新配置
   · 镜像换代:构建新镜像(有网机,新 tag!禁止同名覆盖/禁止 latest)
     docker build -f Dockerfile.sandbox -t agentbuddy-sandbox:1.1.0 .
     docker save | gzip → 内网 → docker load
   · 联网开关:改 agent config.backend.allow_network(API)或
     storage_backends config_json(存储管理界面高级配置)——无构建步骤
② 改配置指向新值
   · 镜像:storage_backends 管理的:PATCH 后端行 bucket/config_json.image(现有能力)
     agent 内联 backend:专家编辑抽屉"P1 新增的只改 image 编辑"或 API
   · 网络:同上两条路径,键为 allow_network
③ 换容器(本功能一键,镜像 + 网络同时生效)
   Admin 沙箱面板/CLI:recreate → 备份→校验→删容器
   → 该用户/专家下次对话自动用新镜像/新网络模式创建 → P2 备份写回
```

### 5.2 升级纪律(定死)

- **永远用新 tag**(`1.0.0 → 1.1.0`),**禁止同名 tag 覆盖导入**,**禁止 `latest`**。
  理由:同名覆盖让"实际跑的是哪个版本"不可审计,漂移检测失去基准。
- 兜底:P3 增加 **STALE-TAG 防呆**——比对"容器镜像 ID vs 该 tag 当前本地 ID",
  不一致(说明有人覆盖过)时标 `STALE-TAG` 并提示 recreate。

### 5.3 容器发现

不维护自建注册表,以 **Docker label 为事实来源** 实时查询:

- harness 建容器时打的标签(`docker_sandbox.py:66-68`;实际键名以 harness 源码为准):
  - `harness.agent.sandbox = "1"`
  - `harness.agent.sandbox_scope = agent|user|fixed`
  - `harness.agent.id = <agent_id>`(agent scope)
- 发现逻辑:Octop 侧 lazy `import docker` → `docker.from_env()` →
  `client.containers.list(all=True, filters={"label": "harness.agent.sandbox=1"})`,
  对每个容器读 `attrs["Config"]["Image"]`(实际镜像)、`attrs["State"]["Status"]`、
  `attrs["Created"]`、`attrs["NetworkSettings"]["Networks"]`(实际网络模式,§5.7)。
- 探测失败(Docker 不可达)返回明确错误(`SANDBOX_DOCKER_UNAVAILABLE`),不静默空列表。

### 5.4 期望值(漂移比对基准:镜像 + 网络)

期望镜像按优先级取:

1. **agent 级**:`agents.config_json.backend.image`(agent scope 时容器名/label 反查
   agent_id,经 `AgentManager._backend_spec_for_row` 同一条解析路径取
   `enrich_docker_backend_spec` 之后的最终 image);
2. **用户级引用**:`storage_backends` 表 `kind='docker'` 行的 `config_json.image`
   (缺省回退 `bucket` 列,与 `row_to_backend_spec` 一致,`adapter.py:129-137`);
   scope=user 的容器按 `sandbox_prefix` 找到引用该后端的专家集合,任一专家的期望
   镜像即作为该容器期望值;多专家引用不同镜像时,期望值取"任一匹配",并在条目上
   列出全部被引用镜像(避免误报)。
3. 取不到期望值时 `expected_image = null`,`drift = null`(unknown,不误报)。

比对口径:v1 用 **tag 字符串比对**(§5.2 纪律下够用);ID 级防呆在 P3(§10 Q2 裁决)。

期望 `allow_network` 用**同一期望来源、同一条解析路径**:

- 期望来源解析出的 harness spec 即包含 `allow_network`(透传链路:
  agent `config.backend` / storage_backends `config_json` →
  `apply_docker_cfg_keys`,`docker_spec.py:10-36`);spec 未写该键时取 harness 构造
  默认 `False`(`docker_sandbox.py:305`)。
- 期望值无法解析(同 `expected_image = null` 的情形)时 `expected_allow_network = null`,
  不判 NETWORK-DRIFT。

### 5.5 重建(recreate)流程

```
POST /api/admin/sandboxes/{container_name}/recreate

1. 校验:容器存在、label 匹配(防止把无关容器传进来)
2. 活跃会话检查:关联专家有进行中对话 → 409 SANDBOX_IN_USE(硬拒绝,Q5 裁决)
3. 影响面确认:user scope 容器反查引用该后端的全部专家,响应/前端确认弹窗
   列出专家清单(Q3 裁决)
4. 备份:get_archive(tar 流)导出容器内工作区 →
        宿主 {AGENTBUDDY_HOME}/sandbox-backups/{container_name}/{YYYYMMDD-HHmmss}/
   - workspace_root 从容器 attrs WorkingDir / agent_id 推导
     (与 harness _in_container_workspace_root 同规则);推导失败时
     备份容器 label 标记的 .octop 全目录
   - meta.json 记录:容器名/scope/agent_id/旧镜像/时间/触发用户
5. 预拉校验:ensure_docker_image(期望镜像)——镜像缺失且 pull 失败 →
   409 SANDBOX_IMAGE_MISSING,**旧容器保留**(顺序刻意:先备份→校验→才删)。
   网络模式无需此步:不落镜像,由 harness 下次建容器时按期望 allow_network 写入。
6. 删除:docker rm -f {container_name}
7. 响应:{recreated: true, backup_path, old_image, expected_image,
   old_network_mode, expected_allow_network}
   新容器由 harness 在下次对话创建(新镜像 + 新网络模式随创建生效);
   P2 提供"备份写回新沙箱"
```

任何一步失败都终止且旧容器仍在。

**保留策略**:每个容器名保留最近 N 份备份(默认 3,`config.json` 可配
`sandbox_backup_keep`),过期清理在每次 recreate 时顺带执行。

### 5.6 镜像清单

`GET /api/admin/sandboxes/images`:

- 本地镜像(可按配置中出现的 sandbox 镜像名前缀过滤,或全量);
- 每项:tag、ID(截断)、体积、创建时间、**被引用次数**(期望镜像集合反查)、
  在跑容器数(台账反查)。
- 用途:升级前确认"哪些容器还在用旧 tag"、导入后确认"新 tag 已就位"。

### 5.7 联网状态与 NETWORK-DRIFT(2026-10-23 增补)

背景:`allow_network` 配置存在于 agent `config.backend` 或 storage_backends
`config_json`,但**没有任何界面能看到"某个沙箱现在到底通不通网"**,也没有任何机制让
配置改动作用于已存在的容器(见 §1 第四行)。本节把网络纳入台账与漂移体系:

**读取方式**:台账逐容器已读 `attrs`,顺手读 `attrs["NetworkSettings"]["Networks"]`
的 key 集合 —— 只有 `none`(或为空)即实际 `network_mode: none`(离线);含
`bridge`/自定义网络即联网。这是 Docker 的权威事实,无需读 harness 状态。

**比对口径**:

| 字段 | 实际值 | 期望值 | 不一致时 |
|---|---|---|---|
| 离线 | `Networks` 仅含 `none` | 期望 spec 的 `allow_network`(缺省 `False`) | `network_drift = true` |

- 期望 `allow_network = true` 而容器离线 → **NETWORK-DRIFT(配置了联网但未生效)**
- 期望 `false` 而容器联网 → **NETWORK-DRIFT(应关网但容器仍联网,需尽快 recreate 收回)**
  ——这一行对政务场景是**安全信号**,面板上与镜像 DRIFT 同级高亮。
- 期望值解析不到 → `network_drift = null`(unknown),不误报。

**语义与联动**:

1. NETWORK-DRIFT 的唯一修复动作就是 **recreate**(§5.5)——recreate 删除容器后,
   harness 下次建容器按当前配置写入 `network_mode`,镜像与网络两个维度同时换新。
   不为"只改网络"做单独的接口,避免两条重建路径。
2. **关闭联网 = 变相的资源回收**:重建会清掉容器可写层里 `pip install` 装的依赖
   (§2),这与"收回网络权限"的意图一致,写入面板确认弹窗文案,防止误以为"只是断网、
   环境还在"。
3. **审计视角**:台账的联网列本身就是政务场景的检查清单——哪些沙箱开着网、开了多久
   (容器 Created 时间)、是否与配置意图一致,一屏可见。
4. 网络粒度边界:本设计只覆盖 `none` ↔ 默认 bridge 的开/关。自定义网络、按域名出
   口白名单(防火墙/代理)不在 harness 与本功能能力内,运维可在宿主机层面自行配置,
   文档不展开。

**风险提示(写进面板文案)**:开启联网的沙箱,容器内进程可达宿主机所在的局域网与公网;
工作区文件存在被外传的可能。开关联网属于高风险配置变更,recreate 确认弹窗对
"离线 → 联网"方向要展示这条提示。

## 6. 接口设计

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/admin/sandboxes` | `storage_backends`(复用,Q4 裁决) | 容器台账(含 drift、network_drift/受影响专家) |
| POST | `/api/admin/sandboxes/{name}/recreate` | 同上 | 重建(备份→校验→删除) |
| GET | `/api/admin/sandboxes/images` | 同上 | 本地镜像清单+引用统计 |
| GET | `/api/admin/sandboxes/backups/{name}` | 同上 | 某容器的历史备份列表 |
| POST | `/api/admin/sandboxes/backups/{name}/restore` | 同上 | 备份写回(§8 P2) |

响应模型走 Pydantic;新错误码:

- `SANDBOX_CONTAINER_NOT_FOUND`(404)
- `SANDBOX_LABEL_MISMATCH`(400,目标不是 harness 沙箱)
- `SANDBOX_IMAGE_MISSING`(409,期望镜像本地不存在且 pull 失败;旧容器保留)
- `SANDBOX_IN_USE`(409,关联专家有进行中对话,硬拒绝)
- `SANDBOX_BACKUP_FAILED`(500,备份失败,旧容器保留)
- `SANDBOX_DOCKER_UNAVAILABLE`(503,Docker daemon 不可达)

CLI(`octop sandbox`,嵌入式 transport,模板 = `cli/commands/bridge.py` + `embedded_ops`):

```
octop sandbox list [--drift-only]      # 台账
octop sandbox recreate <container>     # 重建,--yes 跳过确认;不做批量(Q7 裁决)
octop sandbox images                   # 镜像清单
octop sandbox backups <container>      # 备份列表
```

注册:`cli/registry.py` 加 `"sandbox": (".commands.sandbox", "sandbox", "Manage sandbox containers")`。

## 7. 前端(Dashboard)

- **Admin → 存储** 页新增「沙箱容器」卡片(与现有 Docker 类型卡片同页,不新开导航项):
  容器表(名称/scope/受影响专家反查名/实际镜像/期望镜像/**联网状态 + 期望联网(§5.7)**/
  状态 `ok|DRIFT|NETWORK-DRIFT|unknown|STALE-TAG(P3)`/
  操作列重建按钮);DRIFT 与 NETWORK-DRIFT 行橙色高亮(后者状态列文案区分
  "配置未生效"与"应关网仍联网"两个方向);重建按钮二次确认弹窗,列受影响专家清单,
  文案写明"容器内文件将备份到宿主后清空,对话与记忆不受影响";
  **方向为"离线 → 联网"时追加联网风险提示**(§5.7 末),方向为"联网 → 离线"时追加
  "已安装的 pip/npm 依赖将随容器清空"提示。
- **专家编辑抽屉松绑(P1,只开 image)**:`AgentBackendFields` 增加受控模式——
  编辑时仅当 backend 为 docker/named 且属于"只改 image"场景时开放 tag 下拉/输入,
  其余字段维持禁用;提示文案说明"换镜像后需在沙箱面板执行换代,专家会话与记忆不受影响"。
- 镜像清单折叠在沙箱卡片下方("查看本地镜像")。
- i18n 键进 `dashboard/src/locales/{en,zh}.json` 的 `adminSandbox.*` 命名空间,
  与后端 `errors.*` 同步新增(四份 bundle 对齐,`tests/unit/i18n` 兜底)。

## 8. 分期

| 期 | 内容 |
|---|---|
| **P1(已实现,2026-10-23,待提交)** | 台账(含联网状态列)+ 漂移检测(镜像 tag 比对 + 网络 NETWORK-DRIFT,§5.7)+ recreate(备份/活跃会话硬拒绝/影响面清单/联网方向提示)+ 镜像清单 + 专家编辑抽屉"只改 image"受控编辑 + 编辑抽屉防冲掉(backend 区块禁用时保存不重建 backend,Q12);API + CLI + Dashboard 卡片;错误码六枚;i18n 四份 |
| P2 | 仅一项:备份"恢复到新沙箱"——**先演练再定**(Q13):真实升级 + 手工 docker cp 验证后决定;若做,恢复语义 = 全量覆盖,时序限"recreate 后首次对话前"或弹窗明确提示替换。~~保留策略配置化~~(Q13 划掉,固定 3 份为终态) |
| P3 | 仅 STALE-TAG 防呆(Q13 立项:容器镜像 ID vs tag 当前本地 ID,不一致标 STALE-TAG 提示 recreate);~~批量升级向导~~(Q7 维持,不做);fixed scope 精细化(等真实痛点,未定义) |

## 9. 模块落点(实现时)

| 文件 | 动作 |
|---|---|
| `src/octop/infra/backend/sandbox_admin.py`(新) | 核心:发现/比对/备份/删除/镜像清单;lazy `import docker`,风格对齐 `probe.py:134-155` |
| `src/octop/api/routers/sandbox_admin.py`(新) | 路由,模板 = `storage_backends.py` 的 admin_router + `service_ops.py` 的结构 |
| `src/octop/api/app.py` | `_RouterMount(sandbox_admin.admin_router, "/api/admin/sandboxes", ["admin"])` |
| `src/octop/cli/commands/sandbox.py`(新) | 命令组,模板 = `bridge.py` |
| `src/octop/cli/registry.py` | 注册 `sandbox` |
| `src/octop/infra/errors.py` | 6 个新 ErrorCode + status 映射 |
| `src/octop/i18n/{en,zh}.json` + `dashboard/src/locales/{en,zh}.json` | 错误码与面板文案,四份对齐 |
| `dashboard/src/pages/Admin/Storage/` | 沙箱卡片组件 + `api/modules/sandbox.ts` |
| `dashboard/src/pages/Experts/components/AgentBackendFields.tsx` + `EditAgentDrawer.tsx` + `agentBackendForm.ts` | 受控 image 编辑;防冲掉:编辑模式保存不重建 backend(Q12) |
| `tests/unit/backend/test_sandbox_admin.py`(新) | fake docker client 覆盖发现/比对(镜像+网络)/备份/删除/拒绝分支 |
| `tests/integration/test_sandbox_admin_api.py`(新) | 路由鉴权与错误映射 |
| `docs/agent-backend-file-io.md` §13 | 增补"镜像升级与容器换代"小节,引用本设计 |

边界:全部落在 `infra/backend/`(可 import `infra/utils`、harness 包)与 `api/`、`cli/`,
不新增跨层依赖;Docker SDK 调用集中在 `sandbox_admin.py` 一处,便于 fake。

## 10. 决策记录(2026-10-19/20 讨论裁决)

| # | 问题 | 裁决 |
|---|---|---|
| Q1 | 部署形态:是否需要远程 Docker 宿主机 | **只管本机 daemon**(部署形态确认单机;harness 无 remote host 概念) |
| Q2 | 漂移比对口径与升级纪律 | **永远新 tag、禁同名覆盖、禁 latest**;v1 tag 字符串比对;P3 加 STALE-TAG ID 防呆。配置支持改镜像(`PATCH storage-backends` 的 bucket/config_json 即镜像名),改配置后须 recreate 才换代 |
| Q3 | 重建影响面展示 | **P1 就做反查**:user scope 容器列出受影响专家清单(agent scope 一对一直接列) |
| Q4 | 权限点 | **复用 `require_permission("storage_backends")`**,不新增 sandbox_manage |
| Q5 | 重建期间活跃对话 | **P1 硬拒绝**:活跃会话 → 409 SANDBOX_IN_USE,提示先结束对话 |
| Q6 | 备份写回时机 | **留 P2**;v1 备份宿主可见可下载,跑一轮真实升级再决定是否需要一键写回 |
| Q7 | CLI 批量重建 | **P1 不做**;逐个确认,符合政务窗口期操作习惯 |
| Q8 | 编辑抽屉禁用原因考证 | 上游无迁移/重建机制前的**防呆锁死**(root_dir 越狱语义起点,后扩大到全区块);本功能补机制后 P1 开"只改 image"受控编辑 |
| Q9 | 入口形态 | **API + CLI + Dashboard 界面同步交付**(P1) |
| Q10 | 容器重建的工作区处理 | **默认备份工作区**(备份→校验镜像→才删),不做可选开关 |
| Q11 | 联网状态纳入(2026-10-23 增补) | 台账加联网列(实际网络模式 + 期望 allow_network);`network_drift` 与镜像 drift 并列;修复动作复用 recreate,**不做独立的"应用网络配置"接口**;关网方向提示依赖清空、开网方向提示外泄风险;粒度边界 = none ↔ bridge 开/关,出口白名单不在范围 |
| Q12 | allow_network 配置入口(2026-10-23 增补,同日细化) | **本功能不加新的配置编辑 UI**,入口 = 现有两条路径:①**推荐:named 后端**——存储管理界面该后端行"高级配置 JSON"写 `allow_network`(现有 UI);专家编辑抽屉对 named 引用是无损往返(`parseBackendSpec→buildBackendSpec` 只重建 `{type:"named",name}`),不会冲掉;作用域为整个后端行,按专家控制则建"联网/离线"两个后端行、创建时分配。②agent 内联 backend:创建时 `POST /api/agents` 的 `config.backend` 直写;创建后 `PATCH /api/agents/{agent_id}` 的 `config`(agents.py:378,**全量替换 config_json**,须先 GET 再整体提交)。**现存冲掉风险(已考证,2026-10-23)**:专家编辑抽屉保存时按表单重建整个 `config.backend`(`EditAgentDrawer.tsx:428-443`;`agentBackendForm.ts:50-64,297-310` 对 inline docker spec 返回 DEFAULT_BACKEND,只保留已知键)——inline docker 的专家在编辑抽屉点保存,backend 连同 `allow_network`/`image` 被静默替换为默认,属现存 bug(锁 UI 未锁保存路径)。**P1 增加防冲掉小改**:编辑抽屉 backend 区块禁用(编辑模式)时,保存路径不重建 backend、原样保留 `agentConfig.backend`,仅创建抽屉照旧构建。修复前运维纪律:inline 后端的联网开关改完后,避免再经编辑抽屉保存该专家 |
| Q13 | P2/P3 立项裁决(2026-10-23,用户确认) | **P2-1 备份写回:先演练再定**——提交 P1 后在真实环境跑一轮镜像升级,手工 `docker cp` 从备份目录恢复,验证是否需要一键写回,再决定实现形态;**恢复语义(将来若做)= 全量覆盖**(理由:`.octop` 内 auth token/系统树随镜像版本演进,升级即意味着启用新环境,旧内容无保留价值);实现时注意:恢复若发生在新容器已跑过对话之后会吃掉新文件,时序上应限制在"recreate 后首次对话前"或确认弹窗明确提示替换。**P2-2 保留策略:不做**,固定每容器 3 份为终态(无配置键、无界面)。**P3:仅立 STALE-TAG 防呆**(比对容器镜像 ID vs tag 当前本地 ID,不一致标 STALE-TAG 提示 recreate,便宜可随手做);批量升级向导不做(Q7 逐个确认裁决维持);fixed scope 精细化等真实痛点再议 |

## 11. 风险与实现前需实测的两件事

1. **备份实现方式**:docker py 没有 `docker cp` 等价物,要用 `get_archive`(tar 流)。
   大工作区(几百 MB+)的耗时与内存占用需在实现首日实测;必要时分目录流式导出。
2. **容器 WorkingDir 可靠性**:scope=user 容器的 workspace_root 是 harness exec mkdir
   建的,不是镜像 WORKDIR;从 attrs 推导失败时的 fallback(按 label agent_id 反查配置)
   要在实现时验证。

其余已知风险(实现时对齐):

- 备份体积大时 docker cp 慢:v1 不做大小预估,面板文案提示;
- 容器正跑任务:已由 Q5 硬拒绝覆盖;
- user scope 混布影响面:已由 Q3 反查清单覆盖。
