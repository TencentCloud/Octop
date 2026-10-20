---
name: docker-management
description: 管理 Docker 容器、镜像、卷、网络和 Compose 栈——生命周期操作、调试、清理和 Dockerfile 优化。
version: 1.0.0
author: sprmn24
license: MIT
compatibility: linux, macos, windows
metadata:
  octop:
    label:
      zh: "Docker 管理"
      en: "Docker Management"
    summary:
      zh: "管理容器、镜像、卷、网络与 Compose 栈。"
      en: "Manage containers, images, volumes, networks, and Compose."
  harness:
    emoji: "📦"
    tags: [docker, containers, devops, infrastructure, compose, images, volumes, networks, debugging]
    category: devops
    
---

# Docker 管理

## Harness-agent 工具

本技能从 Octop 移植。使用以下 harness/deepagents 工具：

| 概念 | 工具 |
|---------|------|
| Shell | `execute` |
| 读/写/编辑文件 | `read_file`, `write_file`, `edit_file` |
| 查找文件/搜索内容 | `glob`, `grep` |
| 获取 URL | `web_fetch` |
| 浏览器自动化 | `browser_use` |
| 子代理工作 | `task` |
| 记忆 | `memory_store`, `memory_recall`, `memory_search` |

内置技能文件位于 `/_builtin_skills/<name>/`。用户安装的技能位于 `/skills/<name>/`。

使用标准 Docker CLI 命令管理 Docker 容器、镜像、卷、网络和 Compose 栈。除了 Docker 本身外无需额外依赖。

## 何时使用

- 运行、停止、重启、移除或检查容器
- 构建、拉取、推送、标记或清理 Docker 镜像
- 使用 Docker Compose（多服务栈）
- 管理卷或网络
- 调试崩溃的容器或分析日志
- 检查 Docker 磁盘使用或释放空间
- 审查或优化 Dockerfile

## 先决条件

- Docker 引擎已安装并运行
- 用户已添加到 `docker` 组（或使用 `sudo`）
- Docker Compose v2（包含在现代 Docker 安装中）

快速检查：

```bash
docker --version && docker compose version
```

## 快速参考

| 任务 | 命令 |
|------|---------|
| 运行容器（后台） | `docker run -d --name NAME IMAGE` |
| 停止 + 移除 | `docker stop NAME && docker rm NAME` |
| 查看日志（跟随） | `docker logs --tail 50 -f NAME` |
| 进入容器 Shell | `docker exec -it NAME /bin/sh` |
| 列出所有容器 | `docker ps -a` |
| 构建镜像 | `docker build -t TAG .` |
| Compose 启动 | `docker compose up -d` |
| Compose 停止 | `docker compose down` |
| 磁盘使用 | `docker system df` |
| 清理悬空镜像 | `docker image prune && docker container prune` |

## 流程

### 1. 确定领域

弄清楚请求属于哪个领域：

- **容器生命周期** → run、stop、start、restart、rm、pause/unpause
- **容器交互** → exec、cp、logs、inspect、stats
- **镜像管理** → build、pull、push、tag、rmi、save/load
- **Docker Compose** → up、down、ps、logs、exec、build、config
- **卷和网络** → create、inspect、rm、prune、connect
- **故障排除** → 日志分析、退出码、资源问题

### 2. 容器操作

**运行新容器：**

```bash
# 后台服务，端口映射
docker run -d --name web -p 8080:80 nginx

# 带环境变量
docker run -d -e POSTGRES_PASSWORD=secret -e POSTGRES_DB=mydb --name db postgres:16

# 带持久化数据（命名卷）
docker run -d -v pgdata:/var/lib/postgresql/data --name db postgres:16

# 开发环境（绑定挂载源代码）
docker run -d -v $(pwd)/src:/app/src -p 3000:3000 --name dev my-app

# 交互式调试（退出时自动移除）
docker run -it --rm ubuntu:22.04 /bin/bash

# 带资源限制和重启策略
docker run -d --memory=512m --cpus=1.5 --restart=unless-stopped --name app my-app
```

关键标志：`-d` 分离模式、`-it` 交互+tty、`--rm` 自动移除、`-p` 端口（主机:容器）、`-e` 环境变量、`-v` 卷、`--name` 名称、`--restart` 重启策略。

**管理运行中的容器：**

```bash
docker ps                        # 运行中的容器
docker ps -a                     # 所有（包括已停止）
docker stop NAME                 # 优雅停止
docker start NAME                # 启动已停止的容器
docker restart NAME              # 停止 + 启动
docker rm NAME                   # 移除已停止的容器
docker rm -f NAME                # 强制移除运行中的容器
docker container prune           # 移除所有已停止的容器
```

**与容器交互：**

```bash
docker exec -it NAME /bin/sh          # Shell 访问（如果可用，使用 /bin/bash）
docker exec NAME env                   # 查看环境变量
docker exec -u root NAME apt update    # 以特定用户运行
docker logs --tail 100 -f NAME         # 跟随最后 100 行
docker logs --since 2h NAME            # 过去 2 小时的日志
docker cp NAME:/path/file ./local      # 从容器复制文件
docker cp ./file NAME:/path/           # 复制文件到容器
docker inspect NAME                    # 完整容器详情（JSON）
docker stats --no-stream               # 资源使用快照
docker top NAME                        # 运行中的进程
```

### 3. 镜像管理

```bash
# 构建
docker build -t my-app:latest .
docker build -t my-app:prod -f Dockerfile.prod .
docker build --no-cache -t my-app .              # 干净重建
DOCKER_BUILDKIT=1 docker build -t my-app .       # 使用 BuildKit 更快

# 拉取和推送
docker pull node:20-alpine
docker login ghcr.io
docker tag my-app:latest registry/my-app:v1.0
docker push registry/my-app:v1.0

# 检查
docker images                          # 列出本地镜像
docker history IMAGE                   # 查看层
docker inspect IMAGE                   # 完整详情

# 清理
docker image prune                     # 移除悬空（无标签）镜像
docker image prune -a                  # 移除所有未使用的镜像（小心！）
docker image prune -a --filter "until=168h"   # 超过 7 天未使用的镜像
```

### 4. Docker Compose

```bash
# 启动/停止
docker compose up -d                   # 分离模式启动所有服务
docker compose up -d --build           # 启动前重建镜像
docker compose down                    # 停止并移除容器
docker compose down -v                 # 同时移除卷（会销毁数据）

# 监控
docker compose ps                      # 列出服务
docker compose logs -f api             # 跟随特定服务的日志
docker compose logs --tail 50          # 所有服务的最后 50 行

# 交互
docker compose exec api /bin/sh        # 进入运行中的服务 Shell
docker compose run --rm api npm test   # 一次性命令（新容器）
docker compose restart api             # 重启特定服务

# 验证
docker compose config                  # 验证并查看已解析的配置
```

**最小 compose.yml 示例：**

```yaml
services:
  api:
    build: .
    ports:
      - "3000:3000"
    environment:
      - DATABASE_URL=postgres://user:pass@db:5432/mydb
    depends_on:
      db:
        condition: service_healthy

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
      POSTGRES_DB: mydb
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U user"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  pgdata:
```

### 5. 卷和网络

```bash
# 卷
docker volume ls                       # 列出卷
docker volume create mydata            # 创建命名卷
docker volume inspect mydata           # 详情（挂载点等）
docker volume rm mydata                # 移除（如果在使用中则失败）
docker volume prune                    # 移除未使用的卷

# 网络
docker network ls                      # 列出网络
docker network create mynet            # 创建桥接网络
docker network inspect mynet           # 详情（已连接的容器）
docker network connect mynet NAME      # 将容器连接到网络
docker network disconnect mynet NAME   # 断开容器连接
docker network rm mynet                # 移除网络
docker network prune                   # 移除未使用的网络
```

### 6. 磁盘使用和清理

始终在清理前进行诊断：

```bash
# 检查什么在使用空间
docker system df                       # 摘要
docker system df -v                    # 详细分解

# 定向清理（安全）
docker container prune                 # 已停止的容器
docker image prune                     # 悬空镜像
docker volume prune                    # 未使用的卷
docker network prune                   # 未使用的网络

# 激进清理（先与用户确认！）
docker system prune                    # 容器 + 镜像 + 网络
docker system prune -a                 # 也包括未使用的镜像
docker system prune -a --volumes       # 一切——包括命名卷
```

**警告：** 绝不在未与用户确认的情况下运行 `docker system prune -a --volumes`。这会移除可能包含重要数据的命名卷。

## 陷阱

| 问题 | 原因 | 修复 |
|---------|-------|-----|
| 容器立即退出 | 主进程完成或崩溃 | 检查 `docker logs NAME`，尝试 `docker run -it --entrypoint /bin/sh IMAGE` |
| "端口已被分配" | 另一个进程正在使用该端口 | `docker ps` 或 `lsof -i :PORT` 查找它 |
| "设备上没有剩余空间" | Docker 磁盘已满 | `docker system df` 然后定向清理 |
| 无法连接到容器 | 应用在容器内绑定到 127.0.0.1 | 应用必须绑定到 `0.0.0.0`，检查 `-p` 映射 |
| 卷权限被拒绝 | 主机与容器的 UID/GID 不匹配 | 使用 `--user $(id -u):$(id -g)` 或修复权限 |
| Compose 服务无法相互访问 | 网络或服务名称错误 | 服务使用服务名称作为主机名，检查 `docker compose config` |
| 构建缓存不工作 | Dockerfile 中层顺序错误 | 将不常变化的层放在前面（依赖项在源代码之前） |
| 镜像太大 | 无多阶段构建，无 .dockerignore | 使用多阶段构建，添加 `.dockerignore` |

## 验证

任何 Docker 操作后，验证结果：

- **容器已启动？** → `docker ps`（检查状态是否为 "Up"）
- **日志干净？** → `docker logs --tail 20 NAME`（无错误）
- **端口可访问？** → `curl -s http://localhost:PORT` 或 `docker port NAME`
- **镜像已构建？** → `docker images | grep TAG`
- **Compose 栈健康？** → `docker compose ps`（所有服务 "running" 或 "healthy"）
- **磁盘已释放？** → `docker system df`（比较之前/之后）

## Dockerfile 优化技巧

审查或创建 Dockerfile 时，建议以下改进：

1. **多阶段构建**——分离构建环境和运行时以减小最终镜像大小
2. **层排序**——将依赖项放在源代码之前，以便更改不会使缓存层失效
3. **合并 RUN 命令**——更少的层，更小的镜像
4. **使用 .dockerignore**——排除 `node_modules`、`.git`、`__pycache__` 等
5. **固定基础镜像版本**——`node:20-alpine` 而不是 `node:latest`
6. **以非 root 运行**——添加 `USER` 指令以提高安全性
7. **使用 slim/alpine 基础镜像**——`python:3.12-slim` 而不是 `python:3.12`
