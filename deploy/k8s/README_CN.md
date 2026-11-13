# Octop 集群部署（Kubernetes）

[English](README.md)

一套清单部署三样东西：带 pgvector 的 PostgreSQL、多个 Octop 副本、一个对外入口。副本共用同一套控制面配置。定时任务和 IM 通道用数据库租约保证只有一个副本在执行。

## 这套清单覆盖的范围

PostgreSQL 控制面里已经是全集群共享的：

- 用户、模型、连接器、通道、定时任务
- 技能包正文（`skill_package_files`）
- 知识库原文和 pgvector 向量（`knowledge_files`、`knowledge_chunks`）
- JWT 密钥（`secrets` 表，副本启动时读同一行）
- 专家记忆。控制面是 PostgreSQL 时，未单独指定的专家默认把记忆写到同一个库，按 `agent_<id>` schema 分开

定时任务和 IM 通道在抢到行级租约后才运行。租约约 90 秒，持有副本大约每 30 秒续期；副本退出时会主动释放。别的副本在对账周期里接手。

## 还依赖入口粘滞的部分

每个副本启动时都会加载已启用的专家。租约限制的是通道和定时任务，不是专家进程。

Dashboard 的 WebSocket 和轨迹推送都在进程内存里，不跨副本转发。聊天请求如果换了一个 Pod，实时事件就断了。

因此 Ingress 用 cookie 把同一浏览器粘在同一个 Pod 上。Pod 消失后，下一次请求会换到存活副本。Service 保持不设置 `sessionAffinity: ClientIP`：流量若先经过同一个 Ingress Pod，ClientIP 会把所有用户粘到一个 Octop 副本。

专家工作区文件仍看该专家自己的 backend。默认是本机文件系统，落在 Pod 的 emptyDir 上，Pod 重建后这些文件不在了。集群里要保留工作区文件时，把专家 backend 配成 S3、COS、OpenSandbox 或其他可迁移后端。飞书通道的去重库也在本机；持有该通道的 Pod 被换掉后，可能短时间重复处理飞书补发的消息。

## 前置条件

- Kubernetes，以及默认 StorageClass（PostgreSQL 要 20Gi 的 ReadWriteOnce 卷）
- 能拉取 `pgvector/pgvector:pg16` 和 `ghcr.io/tencentcloud/octop:latest`
- Ingress NGINX。`ingressClassName` 是 `nginx`。别的入口控制器需要改 `octop/ingress.yaml` 里的类名和亲和注解
- 一张给 `octop.example.com` 用的 TLS 证书，Secret 名字是 `octop-tls`

`:latest` 是精简版，没有虚拟桌面、本地向量和 OCR。需要这些能力时把 Deployment 的镜像换成 `ghcr.io/tencentcloud/octop:<version>-full`，并给容器加上大约 1Gi 的 `shm`。

## 文件

| 文件 | 作用 |
|------|------|
| `kustomization.yaml` | 命名空间 `octop`，汇总下面的资源 |
| `postgres/configmap.yaml` | `CREATE EXTENSION vector`，内容与 `deploy/docker/postgres/init-vector.sql` 一致 |
| `postgres/` | 单副本 pgvector。扩展只在数据卷第一次初始化时创建 |
| `octop/deployment.yaml` | 默认 2 个副本 |
| `octop/service.yaml` | 集群内 `octop:8088`，无会话亲和 |
| `octop/ingress.yaml` | TLS、cookie 粘滞、WebSocket 超时、100Mi 上传 |
| `octop/pdb.yaml` | 自愿中断时最多停 1 个副本 |
| `secrets.example.yaml` | Secret 样例，不在 kustomization 里 |

## 部署

在仓库根目录执行。数据库口令和管理员口令分开。管理员口令至少 8 位，并且同时包含字母和数字；不合格时入口脚本不会建管理员，每个 Pod 会各自进入设置向导。

```bash
kubectl apply -f deploy/k8s/namespace.yaml

kubectl -n octop create secret generic octop-pg \
  --from-literal=user=octop \
  --from-literal=password="$(openssl rand -base64 24)" \
  --from-literal=database=octop

kubectl -n octop create secret generic octop-admin \
  --from-literal=username=admin \
  --from-literal=password='REPLACE_WITH_ADMIN_PASSWORD'

kubectl -n octop create secret tls octop-tls \
  --cert=fullchain.pem --key=privkey.pem

kubectl apply -k deploy/k8s
kubectl -n octop rollout status statefulset/octop-pgvector
kubectl -n octop rollout status deploy/octop
```

第一次启动时，两个副本可能同时执行 `octop init`。后完成的那个看到管理员已存在会跳过创建并继续启动。若两台正好撞上唯一约束，后一台退出并再启动一次，第二次跳过创建。这是预期行为。

库一旦初始化，再改 `octop-pg` 的用户名或密码不会改掉已有数据目录里的账号。要换口令，得进库执行 `ALTER USER`，再更新 Secret。

## 改入口域名

三处要一起改：

1. `octop/ingress.yaml` 的 `host` 和 `tls.hosts`
2. `octop/deployment.yaml` 的 `OCTOP_CORS_ORIGINS`（带协议，例如 `https://octop.example.com`）
3. TLS Secret `octop-tls`

然后重新 `kubectl apply -k deploy/k8s`。

## 验证

```bash
kubectl -n octop exec octop-pgvector-0 -- \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\dx"'

kubectl -n octop port-forward svc/octop 8088:8088
curl -fsS http://127.0.0.1:8088/api/health
```

`\dx` 里应能看到 `vector`。`/api/health` 返回 JSON，其中 `ok` 为 `true`，`db` 为 `true`。

浏览器打开 Ingress 域名，用 `octop-admin` 里的用户名和密码登录。通道和定时任务的运行身份可以在日志里确认：抢到租约的副本会执行，其他副本会记下跳过。

## 扩容和更新

```bash
kubectl -n octop scale deploy/octop --replicas=3
kubectl -n octop rollout restart deploy/octop
```

滚动更新时先起新 Pod 再停旧 Pod。旧 Pod 退出时释放通道和任务租约，新 Pod 在对账周期内接手。已经粘在旧 Pod 上的页面会断开，刷新后进入存活副本。

## 换成托管 PostgreSQL

可以不部署 `postgres/`。托管库需要预先允许 `CREATE EXTENSION vector`（很多托管角色不能自己建扩展）。然后只保留 Octop 的 Deployment、Service、Ingress、PDB，并把 `OCTOP_DATABASE_HOST` 指到托管地址。控制面迁移仍由 Octop 启动时执行，不需要手工跑 `*.pg.sql`。
