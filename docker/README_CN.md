# 政务伙伴 Docker 部署

---

本目录包含政务伙伴的 Docker 构建与部署相关文件。

### 文件说明

| 文件 | 说明 |
|------|------|
| `Dockerfile` | 多阶段镜像定义（构建上下文为仓库根目录） |
| `../.dockerignore` | 构建上下文忽略规则（Podman 与 BuildKit 均适用） |
| `docker_build.sh` | 从源码构建镜像（默认开启 BuildKit 缓存） |
| `docker-compose.yml` | 本地开发 / 自托管一键启动 |
| `docker-compose.cn.yml` | 同一套服务，不本地构建、直接拉取镜像（`image:` 需改成发布方自己的仓库地址） |
| `docker-compose.postgres.yml` | 仅 PostgreSQL（+ pgvector）开发/测试库；扩展在 `postgres/init-vector.sql` |
| `postgres/init-vector.sql` | 实例级 `CREATE EXTENSION vector`（initdb.d；**不**进政务伙伴迁移） |
| `docker-entrypoint.sh` | 容器入口：首次初始化数据库并启动服务 |
| `Dockerfile.sandbox` | **Agent 沙箱基础镜像**（Docker 沙箱后端用，非本服务镜像）：预装 git/curl/jq/node20/uv 与技能常用 Python 包，见[下节](#agent-沙箱镜像dockerfile-sandbox) |

### 快速开始

**方式一：Compose（推荐）**

在仓库根目录执行：

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

访问 `http://localhost:8088`。设置了合格的 `AGENTBUDDY_DEFAULT_PASSWORD`（≥8 位且同时包含字母和数字）时，首次启动会创建管理员，并把凭据写入 `/data/.agentbuddy/credential.txt`。未设置，或密码被策略拒绝（过短、缺字母/数字、常见弱密码）时，**不**自动建账号，打开页面走设置向导；向导口令在 `/data/.agentbuddy/agentbuddy-login.txt`（`credential.txt` 里也有说明）。在向导里自行设置管理员密码。

Compose 将多 agent 服务的文件描述符限制设为 65535。服务启动时也会在继承的 hard limit 内将 soft limit 提升至最多 65535，并记录实际限额。已有容器需重新创建才能应用 Compose 限额变化；仅重启不会改变容器的 hard limit。

**方式二：构建脚本**

```bash
bash docker/docker_build.sh
docker run -d \
  --name octop \
  --ulimit nofile=65535:65535 \
  -p 8088:8088 \
  -v octop-data:/data/.agentbuddy \
  -e HOME=/data \
  agentbuddy:latest
```

### 国内镜像加速

构建时可通过环境变量加速依赖下载：

```bash
PIP_INDEX_URL=https://mirrors.example.com/pypi/simple \
PIP_TRUSTED_HOST=mirrors.example.com \
NPM_REGISTRY=https://mirrors.example.com/npm/ \
APT_MIRROR=mirrors.example.com \
bash docker/docker_build.sh
```

### 常用环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `HOME` | `/data` | 必须为 `/data`，数据目录映射到 `~/.agentbuddy` |
| `AGENTBUDDY_PORT` | `8088` | HTTP 服务端口 |
| `AGENTBUDDY_DEFAULT_PASSWORD` | _(未设置)_ | 首次管理员密码（≥8 位，字母+数字）。合格则 `octop init` 建账号；未设置或不合格则走 Web 设置向导 |
| `AGENTBUDDY_ADMIN_USERNAME` | `admin` | 首次管理员用户名 |
| `AGENTBUDDY_DATABASE_URL` | — | PostgreSQL DSN（或其他 `AGENTBUDDY_DATABASE_*`，见 [configuration.md](../docs/configuration.md)） |
| `AGENTBUDDY_DATABASE_DRIVER` | — | 通过环境变量覆盖时：`sqlite` \| `postgresql` |
| `OPENAI_API_KEY` | — | OpenAI 兼容 API Key |
| `DASHSCOPE_API_KEY` | — | 阿里云通义千问 API Key |

Compose 可在 `docker/.env` 中配置上述变量。注意：`.env` 只参与 Compose 插值，变量必须出现在 `docker-compose.yml` 的 `environment:` 中才会进入容器。也可把相同键写入挂载数据目录下的 `~/.agentbuddy/env`。

### 知识库依赖

镜像除 `browser` 外，还包含 `local-embedding` 和 `knowledge-ocr` 可选依赖。
两次依赖安装均指定这些 extras，避免最后一次 `uv sync` 将其移除。构建时会检查
嵌入与 OCR 模块能否导入；不会下载模型权重，也不会自动开启知识库或 OCR。

通过控制台安装到运行中容器的依赖位于容器可写层，重建容器后会丢失。应重新构建或
拉取已包含这些 extras 的镜像，而不是依赖运行时安装。保留 `/data/.agentbuddy` 数据卷，
即可保留配置、知识库索引与本地嵌入模型缓存。已有部署需要重新构建或升级镜像才能
获得这些依赖，仅重启旧镜像无效。

### 数据持久化

- Compose 默认将宿主机 `~/.agentbuddy` 挂载到容器 `/data/.agentbuddy`
- `docker run` 示例使用命名卷 `octop-data`
- 首次启动：`AGENTBUDDY_DEFAULT_PASSWORD` 合格则执行 `octop init` 并写入 `credential.txt`；未设置或不合格则不建管理员，向导口令写入 `/data/.agentbuddy/agentbuddy-login.txt`，打开页面完成设置（容器不会因弱密码退出）。

### 健康检查

镜像内置 `HEALTHCHECK`，探测 `GET /api/health`：

```bash
curl http://localhost:8088/api/health
```

### 常用运维命令

```bash
docker logs -f octop
docker exec -it octop octop --version
docker compose -f docker/docker-compose.yml down
docker compose -f docker/docker-compose.yml up -d --build
```

### Agent 沙箱镜像（Dockerfile.sandbox）

把 agent 的文件工具与命令执行隔离进 Docker 容器时（存储后端 `type: "docker"`，
见 [agent-backend-file-io.md](../docs/agent-backend-file-io.md) §13），容器用的镜像默认是
`python:3.12-slim`——里面只有一个 Python 解释器。`Dockerfile.sandbox` 在此之上补齐
agent 干活需要的工具链：git / curl / wget / jq / rsync / ssh、Node 20 LTS、uv、ffmpeg、
中文字体（Noto CJK）、常用 Python 包白名单，并保留 harness 的运行前提
（bash、root、无 ENTRYPOINT——细节见文件头注释，改前必读）。

**构建**（默认已走国内源：清华 apt / 阿里 PyPI / npmmirror，国内构建机直接 build 即可）：

```bash
cd docker
docker build -f Dockerfile.sandbox -t agentbuddy-sandbox:1.0.0 .

# 海外构建机回官方源：
docker build -f Dockerfile.sandbox -t agentbuddy-sandbox:1.0.0 \
  --build-arg APT_MIRROR=deb.debian.org \
  --build-arg PIP_INDEX_URL=https://pypi.org/simple \
  --build-arg NPM_REGISTRY=https://registry.npmjs.org .

# 有内网 Nexus 源时（apt/pip/npm 全走内网）：
docker build -f Dockerfile.sandbox -t agentbuddy-sandbox:1.0.0 \
  --build-arg APT_MIRROR=nexus.internal.corp/debian \
  --build-arg PIP_INDEX_URL=https://nexus.internal.corp/repository/pypi/simple \
  --build-arg PIP_TRUSTED_HOST=nexus.internal.corp \
  --build-arg NPM_REGISTRY=https://nexus.internal.corp/repository/npm/ .
```

构建参数：

| 参数 | 默认 | 说明 |
|------|------|------|
| `BASE` | `python:3.12-slim` | 沙箱基底镜像 |
| `APT_MIRROR` / `PIP_INDEX_URL` / `PIP_TRUSTED_HOST` / `NPM_REGISTRY` | 国内源（清华/阿里/npmmirror） | 软件源；源配置只在构建期使用、**不写入镜像 ENV**，`docker load` 到内网后运行期不会带着不可达的死源 |
| `SKILL_PIP_PKGS` | 办公/文档/抓取类常用包 | 构建期烤进镜像的 Python 包（空格分隔）。沙箱运行期默认无网络（`allow_network=false`），技能只能用镜像里已有的包，按需增删 |
| `SKILL_NPM_PKGS` | 空 | 同上，Node 全局包 |
| `WITH_BUILD_TOOLS` | `1` | 编译工具链（gcc/python3-dev 等）。sdist-only 包（如内网 arm64 上的 pydantic-core）没它装不上；镜像可以小，但**鲲鹏/飞腾等 arm64 国产化环境建议保持 1** |

构建完成后镜像内 `/opt/sandbox-manifest-{pip,npm}.txt` 记录了实际装入的包清单，便于审计。

**离线导入（政务内网）**：

1. 在有网的构建机上构建（架构必须与内网服务器一致，见下）；
2. 导出：

   ```bash
   docker save agentbuddy-sandbox:1.0.0 | gzip > agentbuddy-sandbox-1.0.0.tar.gz
   ```

3. 用受控渠道（光盘/涉密 U 盘/内部文件系统）拷入内网，导入：

   ```bash
   docker load < agentbuddy-sandbox-1.0.0.tar.gz
   docker images | grep agentbuddy-sandbox   # 确认导入成功
   ```

4. 政务伙伴侧配置存储后端时把 `image` 填成 `agentbuddy-sandbox:1.0.0`（Admin「支持类型 →
   Docker」卡片或 storage_backends 配置）。镜像在本地已存在时不会触发 pull，
   配置即用；建议同时把主服务镜像按同样方式离线导入。

**不用 Docker 的政务机（wheel 离线安装）**：GitHub Actions 的 `Offline Wheel Bundle`
workflow（推 `v*` tag 自动跑，也可手动 Run workflow）会在 amd64/arm64 双平台产出
`offline-bundle-<platform>` artifact——内含主包与四上游 wheel、全部锁定依赖、
SHA256SUMS。下载后：解包 → `bash scripts/install-offline.sh <offline 目录>`
（需要政务机有 Python 3.12；零出网、零编译）。也可在本仓库检出后用
`bash scripts/offline_bundle.sh <平台标签…> cp312` 自行构建。

**架构（CPU 平台）必须匹配**：官方 `python`/`node` 基底是 multi-arch，构建机是什么
架构就出什么架构的镜像——x86_64 构建机（海光/兆芯/普通 x86 服务器）出 amd64 镜像，
鲲鹏/飞腾（arm64）构建机出 arm64 镜像，**amd64 镜像导入 arm64 服务器后要么跑不起来
要么走 qemu 模拟慢一个数量级**。跨架构构建用 buildx：

```bash
docker buildx build --platform linux/arm64 -f Dockerfile.sandbox \
  -t agentbuddy-sandbox:1.0.0 --load .
```

（arm64 机器较少时，也可在 x86 构建机上用 `--platform linux/arm64` 交叉构建，
但 pip 编译类包会慢很多；龙芯 loongarch64 无官方基底镜像，需自备基底后改造本文件。）

**验证**（导入后建议先起一个空沙箱自检，不必启动政务伙伴）：

```bash
docker run --rm --network none agentbuddy-sandbox:1.0.0 \
  bash -lc 'git --version && node -v && uv --version && python -V && pip list | head'
```

与 harness 的行为对齐：容器以 `sleep infinity` 常驻、命令经 `bash -lc` 执行、
工作区文件经 `put_archive` 写入（与宿主同名绝对路径）——这也是文件头三条硬约束的由来。

