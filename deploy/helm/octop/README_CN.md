# Octop Helm chart

[English](README.md)

一次安装会部署 Octop，并默认带上含 pgvector 的 PostgreSQL。副本共用这套控制面。定时任务和 IM 通道通过数据库租约保证只有一个副本在执行。这个 chart 不安装 HorizontalPodAutoscaler。

每个 Pod 仍是一个进程。每个副本启动时都会加载已启用的专家。Dashboard 的 WebSocket 和轨迹推送留在该进程内存里。Ingress cookie `OCTOP_AFFINITY` 把同一个浏览器粘在同一个 Pod 上。该 Pod 消失后，下一次请求会落到存活副本。Service 不要设置 `sessionAffinity`。

集群里的专家工作区使用 PostgreSQL、OpenSandbox 或其他可迁移 backend。每个 Pod 的 `OCTOP_HOME` 是 emptyDir，不是共享工作区。用用户策略 `allowed_backend_types` 限制新建专家不要走本机文件系统。飞书去重库也在本机。持有该通道的 Pod 被换掉后，短时间可能重复处理飞书补发的消息。这个空档可以接受。

更完整的多副本说明见 [docs/cluster_CN.md](../../../docs/cluster_CN.md)。

## 从哪里安装

安装用 GHCR 上的 chart，不必克隆仓库。地址和镜像在同一个仓库，没有单独的 HTTP Helm 仓库。打 `v*` 标签时流水线推包。`appVersion` 是镜像 tag，例如 `1.0.3b5`。Helm 的 chart `version` 必须是 SemVer，所以 `1.0.3b5` 会发成 `1.0.3-b5`，`1.0.3` 保持 `1.0.3`。发布包里的 `appVersion` 已经是镜像 tag，安装时不用再写 `image.tag`。

```bash
helm upgrade --install octop oci://ghcr.io/tencentcloud/octop/charts/octop \
  --version 1.0.3-b5 \
  -n octop \
  --set ingress.host=octop.example.com
```

改 chart 源码时仍编辑仓库里的 `deploy/helm/octop`，在仓库根目录对这个目录执行 `helm upgrade --install`。后面的升级沿用第一次的来源：线上包装的继续带上 `--version`，目录装的继续用 `deploy/helm/octop`。

## 要准备什么

Chart 不保存口令，也不会在 values 里生成 Secret。线上包的默认值用 `helm show values oci://ghcr.io/tencentcloud/octop/charts/octop --version 1.0.3-b5` 查看。仓库里的 `values.example.yaml` 把同一批参数写成带注释的样例，`secrets.example.yaml` 是口令样例。复制后改域名和镜像，占位符换成真实口令，不要把填好的口令文件提交进仓库。

```bash
helm upgrade --install octop oci://ghcr.io/tencentcloud/octop/charts/octop \
  --version 1.0.3-b5 \
  -n octop \
  -f my-values.yaml
```

| 配置 | 是否必须 | 作用 |
|------|----------|------|
| Secret `octop-admin` 的 `username`、`password` | 必须 | 控制台登录账号。只在第一次初始化时用来创建管理员 |
| Secret `octop-pg` 的 `user`、`password`、`database` | 必须 | PostgreSQL 的库名、用户和口令。不是控制台密码 |
| `ingress.host` | 开启 Ingress 时必须 | 对外域名。`config.corsOrigins` 留空时会用 `https://<ingress.host>` |
| Secret `octop-tls` | `ingress.tls.enabled` 为 true 时必须 | 这张域名的 TLS 证书，默认名字是 `octop-tls` |
| `image.tag` | 建议填写 | 留空则用 chart 的 `appVersion`。请写成仓库里真实存在的版本 |
| `replicaCount` | 可选 | 默认 2。没有 HPA，要改副本数就改这个值再 upgrade |
| `config.timezone` | 可选 | 默认 `Asia/Shanghai` |
| `postgresql.enabled` | 可选 | 默认 true，由 chart 部署 pgvector。托管库设为 false，并填写 `database.host` |
| `shm.enabled` | 完整版镜像时打开 | 精简版保持 false。虚拟桌面、本地向量、OCR 需要 `<版本>-full`，并打开这项 |

管理员口令至少 8 位，同时包含字母和数字，并且不要用常见弱密码。不合格时不会创建管理员，每个 Pod 各自进入设置向导。初始化完成后，再改 `octop-admin` 不会改掉已经建好的控制台密码；再改 `octop-pg` 也不会改掉数据卷里已经建好的数据库账号。数据库账号要先在库里 `ALTER USER`，再更新 Secret。控制台密码在登录后自行修改。

改源码时，同一份默认值是 `helm show values deploy/helm/octop`。

## 发布 chart 要准备什么

打包推到 GHCR 不需要单独的 Helm 仓库密钥，也不给 chart 签名。流水线 `.github/workflows/helm-publish.yml` 使用 Actions 自带的 `GITHUB_TOKEN`，权限是 `contents: read` 和 `packages: write`。仓库设置里 Workflow permissions 要允许读写，这样 token 才能创建 GHCR 包。组织如果限制了套餐包的创建或公开，需要管理员允许这个仓库发布 packages。

触发是推送 `v*` 标签，或在 Actions 里手动运行并填写 `tag=v1.0.3b5` 这种标签。手动填写的标签必须指向已经包含这份 chart 的提交。已经发出的 `v1.0.3b5` 不含 chart，不会补发。镜像由另一条流水线推到 `ghcr.io/tencentcloud/octop`，chart 只引用这个 tag，不在打包时拉取镜像。包名是 `octop/charts/octop`，和容器镜像包 `octop` 分开。

本机手工推送时，用一个带 `write:packages` 的 GitHub PAT 登录，不需要别的 key。直接 `helm package` 得到的 chart 版本是仓库里的 `0.1.0`。要发成和标签一致的 SemVer，先按流水线那样改写 `Chart.yaml` 的 `version` 和 `appVersion`，不要把这次改写提交回去：

```bash
echo "$GHCR_PAT" | helm registry login ghcr.io --username <GitHub 用户名> --password-stdin
helm package deploy/helm/octop
helm push octop-*.tgz oci://ghcr.io/tencentcloud/octop/charts
```

第一次推送后，到 GitHub 的 Packages 里确认这个 chart 包是公开的，否则别人 `helm pull` 会要求登录。

## 前置条件

- Kubernetes 1.25 或更新版本、Helm 3。启用自带数据库时需要默认 StorageClass（20Gi ReadWriteOnce）
- 能拉取 `pgvector/pgvector:pg16` 和 `ghcr.io/tencentcloud/octop:<tag>`。等待数据库的 init 容器也用 `postgresql.image`，托管库同样要能拉到这张镜像
- `ingress.className` 保持 `nginx` 时使用 Ingress NGINX。别的入口控制器要在 values 里改类名和注解
- 开启 TLS 时，准备一张 Ingress 域名的证书，Secret 名字是 `octop-tls`

`image.tag` 默认取 chart 的 `appVersion`。请设成仓库里真实存在的 tag。默认镜像是精简版。需要虚拟桌面、本地向量或 OCR 时，把 tag 设为 `<version>-full`，并设 `shm.enabled=true`。

## 安装

两个 Secret 的含义和口令要求见上一节。`--version` 写成已经发布的 chart 版本。镜像 tag 来自这个包的 `appVersion`。

```bash
kubectl create namespace octop

kubectl -n octop create secret generic octop-pg \
  --from-literal=user=octop \
  --from-literal=password="$(openssl rand -base64 24)" \
  --from-literal=database=octop

kubectl -n octop create secret generic octop-admin \
  --from-literal=username=admin \
  --from-literal=password='REPLACE_WITH_ADMIN_PASSWORD'

kubectl -n octop create secret tls octop-tls \
  --cert=fullchain.pem --key=privkey.pem

helm upgrade --install octop oci://ghcr.io/tencentcloud/octop/charts/octop \
  --version 1.0.3-b5 \
  -n octop \
  --set ingress.host=octop.example.com
```

没有对外域名、或者入口不是 Ingress NGINX 时，先关掉 Ingress，用端口转发检查：

```bash
helm upgrade --install octop oci://ghcr.io/tencentcloud/octop/charts/octop \
  --version 1.0.3-b5 \
  -n octop \
  --set ingress.enabled=false

kubectl -n octop port-forward svc/octop 8088:8088
```

入口控制器不是 NGINX 时，改 `ingress.className`，并换掉 `ingress.annotations` 里的 NGINX 注解。MicroK8s 自带的 Traefik 常见类名是 `public`。cookie 粘滞、长连接超时和关闭响应缓冲仍然要在那个控制器上配好。

第一次启动时，两个副本可能同时执行 `octop init`。后完成的那个看到管理员已存在会跳过创建并继续启动。若两台正好撞上唯一约束，后一台退出并再启动一次，第二次跳过创建。

库一旦初始化，再改 `octop-pg` 的用户名或密码不会改掉已有数据目录里的账号。要换口令，得进库执行 `ALTER USER`，再更新 Secret。

## 检查

```bash
kubectl -n octop rollout status statefulset/octop-pgvector
kubectl -n octop rollout status deploy/octop

kubectl -n octop exec octop-pgvector-0 -- \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\dx"'

kubectl -n octop port-forward svc/octop 8088:8088
curl -fsS http://127.0.0.1:8088/api/health
```

`\dx` 里应能看到 `vector`。`/api/health` 返回 JSON，其中 `ok` 为 `true`，`db` 为 `true`。

用 Ingress 域名和 `octop-admin` 里的用户名、密码登录。抢到租约的副本会执行对应的通道或定时任务，其他副本会记下跳过。

## 改域名

```bash
helm upgrade octop oci://ghcr.io/tencentcloud/octop/charts/octop \
  --version 1.0.3-b5 \
  -n octop \
  --reuse-values \
  --set ingress.host=octop.example.com
```

TLS Secret 里的域名要和这里一致。如果关掉 TLS，把注解 `nginx.ingress.kubernetes.io/session-cookie-secure` 改成 `"false"`。

## 副本和升级

```bash
helm upgrade octop oci://ghcr.io/tencentcloud/octop/charts/octop \
  --version 1.0.3-b5 \
  -n octop \
  --reuse-values \
  --set replicaCount=3
```

滚动更新时先起新 Pod 再停旧 Pod。旧 Pod 退出时释放通道和任务租约，新 Pod 在对账周期内接手。已经粘在旧 Pod 上的页面会断开，刷新后进入存活副本。

## 托管 PostgreSQL

扩展由数据库管理员预先执行（`CREATE EXTENSION vector`）。chart 不再部署自己的数据库：

```bash
helm upgrade --install octop oci://ghcr.io/tencentcloud/octop/charts/octop \
  --version 1.0.3-b5 \
  -n octop \
  --set postgresql.enabled=false \
  --set database.host=pg.example.com \
  --set ingress.host=octop.example.com
```

`octop-pg` 这个 Secret 仍然提供库名、用户和口令。控制面迁移由 Octop 启动时执行，不需要手工跑 `*.pg.sql`。
