# 存储后端选型指南(政务伙伴)

面向部署/运维决策:六类存储后端分别在什么场景使用、能力与数据形态差异、怎么选。
技术细节(字段、API、文件 I/O 语义)见 [agent-backend-file-io.md](./agent-backend-file-io.md);
本文只回答"选哪个、为什么"。

---

## 1. 一个核心概念

存储后端承载两样东西:

1. **agent 工作区文件** —— SOUL.md、技能文件、agent 生成/下载的文档,`read/write/ls/grep` 工具操作的对象;
2. **命令执行场所** —— `execute` 工具(bash)跑在哪里。

`filesystem` 与对象存储类**只管 ①**;`shell` / `docker` / `opensandbox` 既管 ① 又管 ②
(文件与命令在同一个隔离边界里)。所有类型实现同一套 harness 协议,对 agent 而言接口一致,
差的是"**文件躺哪、命令在哪跑、隔离多强**"。

## 2. 六类后端速查

| 类型 | 文件在哪 | 命令在哪跑 | 隔离强度 | 典型场景 |
|---|---|---|---|---|
| **本地文件系统** `filesystem` | 宿主机指定目录 | 宿主机(无隔离) | 无 | 单机自用;想直接用编辑器/`find` 看文件 |
| **本地 Shell** `shell` | 宿主机指定目录 | 宿主机 shell | 无 | 需要命令执行且信任 agent 的单机场景 |
| **Docker 沙箱** `docker` | 容器内同名绝对路径 | 容器内 | 强(可限网络/CPU/内存/pids) | **多用户生产主力**:政务部署、不可信技能、一人一容器 |
| **OpenSandbox** `opensandbox` | 远程沙箱服务内 | 远程沙箱内 | 强(托管) | 宿主机无 Docker daemon;K8s/云上把沙箱当独立服务托管 |
| **对象存储** `cos`/`s3`/`oss`/`obs`/`custom` | 对象存储桶 | **不能执行命令** | — | 文件持久化/共享/备份;大文件、二进制多 |
| **PostgreSQL** `postgres` | 一张 `(path, content JSONB)` 表 | **不能执行命令** | — | 已有 PG 基础设施;要 SQL 可查询、可审计的文件存储 |

## 3. 各类型要点与"存什么"

### 3.1 filesystem vs shell

两者文件都在宿主机。区别:`shell`(harness `local_shell`)让 agent 的命令**直接跑在宿主机
shell 里**——能 `pip install`、能 `git clone`,也能误删宿主文件;`root_dir` 只是虚拟根,
不是硬隔离。`filesystem` 类型本身不提供命令执行。**给命令执行选 shell,只给文件选 filesystem。**

### 3.2 Docker 沙箱(多用户主力)

- 容器以 `sleep infinity` 常驻;`close`/删除专家**不**删容器,显式 destroy(或存储管理面的
  沙箱重建功能)才连容器内文件一起删;
- 宿主 `workspace_dir` **不** bind-mount —— 文件经 Docker API(`put_archive`)写进容器内
  同名绝对路径,容器删了容器内文件就没;宿主侧仍保留 sessions/memory/checkpoints 等
  持久数据(两处落盘的边界见 `agent-backend-file-io.md` §13);
- 运行期默认 `allow_network=false`(断网是安全特性):技能只能用**烤进镜像**的依赖,
  依赖预装与镜像构建见 `docker/README_CN.md` 的 Agent 沙箱镜像章节与
  `docker/Dockerfile.sandbox`;
- 沙箱命名:`agent` scope 每专家一容器、`user` scope 同用户共用、`fixed` 显式指定;
  镜像升级与容器换代流程见 `docs/sandbox-image-management.md`(设计稿)。

### 3.3 OpenSandbox

能力与 Docker 沙箱等价(同一套沙箱原语),差别在**控制面**:Docker 是本机 daemon + 本地镜像,
OpenSandbox 是带 API 的远程沙箱服务(`endpoint` + `api_key`),沙箱随 agent 启动创建、
停止销毁,默认不可浏览。适合宿主机是 K8s 节点、或想把沙箱负载挪到专门机器的部署。

### 3.4 对象存储(cos/s3/oss/obs/custom)——怎么存、存什么

每个 agent 文件 = **一个 JSON 对象**:

```json
{"content": "文件内容(文本)或 base64(二进制)", "encoding": "utf-8 | base64",
 "created_at": "…", "modified_at": "…"}
```

- 对象 key = `{prefix}/{虚拟路径}`(如 `agents/ZE6GR2/SOUL.md`);目录用零字节占位对象表示;
- 配置四件套:`access_key` + `secret_key` + `bucket` + `endpoint`(cos 另需 region);
  `custom` 走通用 S3 协议(MinIO 等);
- **不能执行命令** —— 对象存储当 agent 主后端时,命令执行要配 composite
  (文件走 OSS、命令走本地 shell/Docker);
- 阿里 OSS / 腾讯 COS / 华为 OBS / AWS S3 是"用户自带密钥接第三方服务"的通用能力,原样保留。

### 3.5 PostgreSQL —— 怎么存、存什么

首次使用自动建表(`CREATE SCHEMA` + `CREATE TABLE`):

```sql
CREATE TABLE {schema}.{table} (
    path TEXT PRIMARY KEY,      -- 虚拟路径,如 agents/ZE6GR2/SOUL.md
    content JSONB NOT NULL,     -- 同一个 FileData 信封(SQL 内可直接查)
    created_at TIMESTAMPTZ,
    modified_at TIMESTAMPTZ
)
```

- row 字段映射:`endpoint`→host:port、`access_key`→用户名、`secret_key`→密码、
  `bucket`→库名、`region`→schema(默认 public;表默认 `deepagents_files`);
- **同样不能执行命令**,需要与命令执行后端组合;
- 二进制以 base64 进 JSONB,效率不适合大文件量。

### 3.6 OSS vs PostgreSQL 怎么选

两者**存的内容一模一样**(同一个 FileData JSON 信封),差别在形态与运维:

| 维度 | OSS 类 | PostgreSQL |
|---|---|---|
| 大文件/二进制 | 友好(原生对象) | 差(base64 进 JSONB) |
| 查询/审计能力 | 只能按 key 取 | **SQL 可查**:存了什么、何时改的一条 SELECT |
| 运维依赖 | 外部对象存储(或内网 MinIO) | 复用现有 PG(备份/权限/HA 顺手) |
| 组合命令执行 | 需 composite | 需 composite |

## 4. 决策树

```
agent 需要执行命令(bash)吗?
├─ 需要
│   ├─ 多用户 / 跑不可信技能? ──────────────► Docker 沙箱(Dockerfile.sandbox 镜像)
│   ├─ 宿主机没有 Docker? ──────────────────► OpenSandbox
│   └─ 单机、完全信任 agent? ───────────────► shell(最省事,注意无隔离)
└─ 不需要(纯文件)
    ├─ 要 SQL 可查/审计? ───────────────────► PostgreSQL
    ├─ 大文件、二进制多? ────────────────────► OSS 类(内网可 MinIO=custom)
    └─ 就在本机、想直接看文件? ──────────────► filesystem
```

## 5. 政务部署建议

1. **多用户 + 跑技能 → Docker 沙箱为主**,镜像用 `docker/Dockerfile.sandbox`
   (预装 git/curl/node/uv 与技能依赖白名单;构建与离线导入见 `docker/README_CN.md`);
2. **文件要跨实例持久/审计 → 组合**:PG(表级清晰、易审计)或 OSS/MinIO(大文件友好),
   经 composite 与沙箱组合;
3. **单机内网小规模 → filesystem/shell 最省事**,但需告知使用方:agent 命令跑在宿主机上;
4. 技能依赖的离线分发(断网沙箱装新依赖)方案与镜像站点前提,见
   `WHITELABEL.md` §12.2(待办池)。

---

*依据:src/octop/infra/backend/{adapter,resolver,docker_spec,postgres_spec}.py、
harness `backends/{docker_sandbox,postgres,oss_backend,cloud_storage_base}.py`(2026-10-20 核实)。*
