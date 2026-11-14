# 把 Octop 跑成多台

一台 Octop 配 SQLite 就够用。多台一起跑时，用户、专家和模型放到同一台 PostgreSQL，入口用 cookie 把同一个浏览器固定到其中一台。已经有 Kubernetes 时，从 GHCR 安装 Helm chart，不必克隆仓库。还没有 Kubernetes 时，按下面的虚拟机步骤，在前面放一台反向代理。

## 目录

1. [一台和多台](#1-一台和多台)
2. [存在数据库里的内容](#2-存在数据库里的内容)
3. [什么时候用多台](#3-什么时候用多台)
   1. [专家的文件](#31-专家的文件)
   2. [已有的 SQLite](#32-已有的-sqlite)
4. [一次请求会到哪一台](#4-一次请求会到哪一台)
   1. [每台自己的数据目录](#41-每台自己的数据目录)
   2. [入口和管理员密码](#42-入口和管理员密码)
5. [在虚拟机上安装](#5-在虚拟机上安装)
   1. [准备 PostgreSQL](#51-准备-postgresql)
   2. [启动两台 Octop](#52-启动两台-octop)
   3. [前面的代理](#53-前面的代理)
   4. [检查两台是否共用一个库](#54-检查两台是否共用一个库)
6. [在 Kubernetes 上安装](#6-在-kubernetes-上安装)
   1. [要准备的配置](#61-要准备的配置)
   2. [安装](#62-安装)
   3. [更换域名](#63-更换域名)
   4. [检查是否装好](#64-检查是否装好)
   5. [托管数据库](#65-托管数据库)
   6. [调整副本数](#66-调整副本数)
7. [故障和备份](#7-故障和备份)
   1. [一台停止之后](#71-一台停止之后)
   2. [备份](#72-备份)
   3. [当前限制](#73-当前限制)

## 1. 一台和多台

一台 Octop 配一个 SQLite，个人或者一个小组用着很合适。用户、专家、模型、通道和知识库都在这台机器的 `~/.octop` 里。再加一台机器时，这个目录不能直接拷过去用。两台会各有一份配置，在这边改了模型，另一边看不到。原来那台停了，服务也跟着停。

多台一起跑时，这些配置改存到同一台 PostgreSQL。每台 Octop 启动后都从这个库读取用户、模型和专家。前面放一个入口，用 cookie 把同一个浏览器固定到其中一台，这样一次对话的后续请求还会回到这台机器。定时任务和即时通讯通道在数据库里各占一行租约，同一时刻只有拿到租约的那台在执行。再增加一台 Octop，让它连上这个库即可。

PostgreSQL 在这里仍然只有一台。数据库停了，所有 Octop 都不可用。Octop 进程可以加机器。数据库的故障转移要另外准备，例如使用托管的 PostgreSQL，或者自己做复制，然后让所有 Octop 连那个地址。

【插图 1】单机和多台的对比

提示词：一张横向的技术架构对比图，白底，细线框，扁平，不要立体效果，不要人物，不要装饰图标堆砌。画面分成左右两半。左半标题写「单机」：一个浏览器图标用箭头指向方框「Octop」，Octop 下方再连一个小方框，文字是「SQLite」和「~/.octop」。右半标题写「多台」：浏览器指向方框「入口」，入口分出两条箭头，分别指向两个方框「Octop」，箭头旁标「cookie」；这两个 Octop 的箭头向下汇合，连到底部同一个大方框「PostgreSQL」。所有文字用简体中文，字迹清楚，留白充足。

## 2. 存在数据库里的内容

用户、角色、模型、连接器、通道、定时任务，以及 JWT 密钥，都在这个库里。技能包的源文件、知识库的原文和向量也在这里，向量使用 pgvector。专家如果没有单独指定记忆放在哪里，记忆会写到同一个库，每个专家使用自己的 schema，名字是 `agent_<id>`。在任何一台修改模型或上传知识，其他台读到的是同一份数据。

升级时可以先启动新进程，确认它已经连上数据库，再停掉旧进程。旧进程退出时会释放自己持有的通道和任务。新进程在下一轮检查时接手。已经打开的页面会断开一次，刷新后进入还在运行的那台，对话记录仍在数据库里。

定时任务和通道不会因为开了两台就执行两次。任务开始前要先拿到这一行的租约，通道也一样。租约大约保持 90 秒，持有它的那台大约每 30 秒续一次，进程退出时会释放。租约过期以后，其他台大约每 25 秒检查一次，先拿到的那台继续执行。所以可以同时开着两三台，同一条飞书连接、同一次定时任务仍然只在一台上面进行。

备份对着这一个库来做。`pg_dump` 会包含控制面、技能包源、知识库和专家记忆。

【插图 2】数据库里的内容和每台自己的磁盘

提示词：一张分层架构图，白底，细线框，扁平。画面中央是一个大矩形，标题「PostgreSQL」。矩形内用小标签列出五行：用户和模型、技能包源、知识库、专家记忆 agent_id、通道和任务租约。大矩形左右各有一个方框「Octop」，各自用箭头连向中央数据库。每个 Octop 旁边另画一块磁盘，磁盘上写两行：「本机工作区」「feishu-dedup.sqlite」。磁盘不要连到另一台 Octop。所有文字用简体中文，布局左右对称，不要卡通风格。

## 3. 什么时候用多台

页面和对话已经把一台机器占满，而账号和专家又要保持同一套时，就加 Octop 进程，继续共用这一台数据库。升级时如果希望旧进程先继续服务、等新进程起来再停，也可以这样部署。知识库和技能包放在数据库里之后，每台都能读到，备份也只需要备这一个库。

只有一台机器、一个管理员的时候，继续用 SQLite。多台部署要额外维护数据库和入口，还要确认专家的文件放在哪一台。

### 3.1 专家的文件

专家读写的文件不在控制面数据库里。SOUL、装进专家的技能、用户上传的附件，都由这个专家的后端决定存在哪里。默认后端是本机目录。在 Kubernetes 里，这个目录是 Pod 的临时盘，Pod 删除以后文件就没有了。集群里换成 PostgreSQL、OpenSandbox、S3、COS，或其他换机器以后还能继续用的后端。组合模式可以把几个后端拼在一起，文件具体落在哪一个后端，还是看里面选的那一个。技能包的源在数据库里，绑定到专家时会复制到工作区。工作区如果是本地磁盘，每台机器会各有一份。

### 3.2 已有的 SQLite

已经在用的 SQLite 数据不会自动迁过来。现在没有这个迁移工具。多台部署从一个新的 PostgreSQL 开始。

## 4. 一次请求会到哪一台

每台 Octop 启动时，都会把已启用的专家加载到自己的内存里。租约只限制通道和定时任务，规则见 [第 2 节](#2-存在数据库里的内容)。两个用户如果被分到不同的机器，就会各自使用那台机器上的专家。工作区如果是共享的对象存储，这两台可能同时写同一批文件。入口用 cookie 把同一个浏览器固定在一台，是为了让同一次对话的请求都到这台机器。

页面上的实时消息和轨迹由处理这次请求的进程推送，其他进程没有这份连接。请求如果换到另一台，页面上的输出会中断。刷新之后，入口会把浏览器送到还在运行的机器。

飞书用来判断消息是否重复的文件，是持有这条通道的那台机器上的 `feishu-dedup.sqlite`。这台机器换掉以后，短时间内可能会把飞书重新发来的消息再处理一次。

### 4.1 每台自己的数据目录

每台机器使用自己的数据目录。容器里这个目录是 `/data/.octop`。同一目录不要用 NFS 挂给多台同时写。飞书去重和默认工作区都是本机文件。各台共用的是数据库。

### 4.2 入口和管理员密码

对外使用一个地址，例如 `https://octop.example.com`。浏览器、通道回调和跨域配置都用这个地址。`OCTOP_CORS_ORIGINS` 写成带 `https://` 的完整地址。

入口按 cookie 固定浏览器，不要按来源 IP 固定。所有流量如果先经过同一台代理，Octop 看到的来源地址会是一样的，结果所有人都被分到同一台。

管理员密码至少 8 位，并且同时包含字母和数字，也不要使用常见弱密码。容器第一次启动时，密码符合这个要求才会创建管理员。密码不合格时，每台都会进入设置向导，向导口令写在这台自己的目录里，各台的初始设置会对不上。

【插图 3】一次对话的请求路径

提示词：一张从左到右的请求路径图，白底，细线框，扁平。最左边是浏览器，箭头指向中间的方框「入口」，箭头上写「cookie」。入口只引出一条实线，指向右边上方的方框「Octop A」，线旁写「同一次对话」。Octop A 内部写「内存中的专家」，并从它画一条虚线回到浏览器，虚线上写「实时消息」。右边下方再画「Octop B」，用灰色细线连到底部的「PostgreSQL」，表示它也连着数据库，但这次对话没有箭头指向它。Octop A 和 Octop B 都用实线连向同一个 PostgreSQL。在 Octop A 旁加一个小标签「飞书通道，持有租约」。简体中文，不要立体图标。

## 5. 在虚拟机上安装

已经有虚拟机或物理机，并且可以在前面放一台反向代理时，可以不用 Kubernetes。数据库可以单独放一台，也可以和其中一台 Octop 放在一起。先跑两台 Octop 就可以。

【插图 4】虚拟机上的部署

提示词：一张从左到右的部署图，白底，细线框，扁平。最左是方框「反向代理」，上方标「对外 443」。代理分出两条箭头，分别指向「Octop」和「Octop」，箭头上写「cookie」。两台 Octop 下面各画一块独立磁盘，分别标「数据目录 A」「数据目录 B」，容器端口都标「8088」。两台 Octop 再指向右侧方框「PostgreSQL 16」，数据库方框内写「pgvector」。简体中文，机器之间留出间距，不要画机房照片。

### 5.1 准备 PostgreSQL

数据库使用 PostgreSQL 16，并安装 `vector` 扩展。Octop 建表时不会执行 `CREATE EXTENSION`，所以在准备数据库时建好。先把数据库跑起来时，可以用仓库里的 Compose：

```bash
docker compose -f deploy/docker/docker-compose.postgres.yml up -d
```

默认连接是 `postgresql://octop:octop@127.0.0.1:5432/octop`。这个密码只适合开发。正式环境换成单独的密码，并且只允许 Octop 所在的网段访问 5432。数据库已经存在时，用有权限的账号执行：

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

有些托管数据库不允许业务账号自己创建扩展，需要先在控制台打开 pgvector。控制面的表不用这个扩展，知识库的向量需要它。

### 5.2 启动两台 Octop

每台 Octop 使用同一个版本。数据库相关的环境变量保持一致，数据目录各自独立。下面两台容器分别映射到宿主机的 8088 和 8089，方便分开检查。地址和密码改成实际使用的值。容器里的 `OCTOP_DATABASE_HOST` 必须是容器能够访问的地址。数据库如果在另一个 Docker 网络里，写容器网络里的地址，不要写 `127.0.0.1`。

```bash
docker volume create octop-a
docker volume create octop-b

docker run -d --name octop-a --restart unless-stopped \
  --ulimit nofile=65535:65535 \
  -p 8088:8088 \
  -v octop-a:/data/.octop \
  -e HOME=/data \
  -e OCTOP_BIND_HOST=0.0.0.0 \
  -e OCTOP_PORT=8088 \
  -e OCTOP_DATABASE_DRIVER=postgresql \
  -e OCTOP_DATABASE_HOST=172.16.0.10 \
  -e OCTOP_DATABASE_PORT=5432 \
  -e OCTOP_DATABASE_NAME=octop \
  -e OCTOP_DATABASE_USER=octop \
  -e OCTOP_DATABASE_PASSWORD='数据库密码' \
  -e OCTOP_ADMIN_USERNAME=admin \
  -e OCTOP_DEFAULT_PASSWORD='管理员密码至少8位且含字母和数字' \
  -e OCTOP_DEFAULT_TIMEZONE=Asia/Shanghai \
  -e OCTOP_CORS_ORIGINS=https://octop.example.com \
  ghcr.io/tencentcloud/octop:latest
```

第二台改容器名、端口和数据卷，其他环境变量与第一台相同，管理员密码也用同一个：

```bash
docker run -d --name octop-b --restart unless-stopped \
  --ulimit nofile=65535:65535 \
  -p 8089:8088 \
  -v octop-b:/data/.octop \
  -e HOME=/data \
  -e OCTOP_BIND_HOST=0.0.0.0 \
  -e OCTOP_PORT=8088 \
  -e OCTOP_DATABASE_DRIVER=postgresql \
  -e OCTOP_DATABASE_HOST=172.16.0.10 \
  -e OCTOP_DATABASE_PORT=5432 \
  -e OCTOP_DATABASE_NAME=octop \
  -e OCTOP_DATABASE_USER=octop \
  -e OCTOP_DATABASE_PASSWORD='数据库密码' \
  -e OCTOP_ADMIN_USERNAME=admin \
  -e OCTOP_DEFAULT_PASSWORD='管理员密码至少8位且含字母和数字' \
  -e OCTOP_DEFAULT_TIMEZONE=Asia/Shanghai \
  -e OCTOP_CORS_ORIGINS=https://octop.example.com \
  ghcr.io/tencentcloud/octop:latest
```

仓库里还有一份 Compose，把数据库和两台 Octop 放在同一个网络里，宿主机端口同样是 8088 和 8089：

```bash
OCTOP_DEFAULT_PASSWORD='管理员密码至少8位且含字母和数字' \
  docker compose -f deploy/docker/docker-compose.cluster.yml up -d
```

两台会同时执行初始化。后完成的那台如果发现管理员已经存在，会跳过创建并继续启动。如果两台同时插入管理员、碰到唯一约束，后一台会退出一次，重启后再跳过。两台使用同一个管理员密码。

不使用容器、直接在系统里运行时，每台配置相同的数据库变量和 `OCTOP_CORS_ORIGINS`，`OCTOP_HOME` 放在本机磁盘。只在第一台上执行 `octop init`，其他台执行 `octop run --host 0.0.0.0 --port 8088`。

### 5.3 前面的代理

8088 和 8089 用来检查，不要直接给用户访问。前面加一台代理，对外提供 443，并用 cookie 把后续请求和 WebSocket 送到同一台。下面是一份 HAProxy 配置，两台 Octop 分别是 `10.0.0.11:8088` 和 `10.0.0.12:8088`。证书路径改成实际文件。

```text
frontend octop
    bind :443 ssl crt /etc/haproxy/octop.pem
    default_backend octop

backend octop
    balance roundrobin
    cookie OCTOP_AFFINITY insert indirect nocache
    timeout server 1h
    timeout tunnel 1h
    server a 10.0.0.11:8088 check cookie a
    server b 10.0.0.12:8088 check cookie b
```

`timeout tunnel` 设得长一些，不然对话的 WebSocket 会被代理断开。上传大小和 `OCTOP_MAX_UPLOAD_MB` 保持一致，默认是 100MB。代理如果只能按来源 IP 分流，同一个网络出口后面的用户会进入同一台。用户少的时候可以先这样，用户多了以后改成按 cookie 分流。

### 5.4 检查两台是否共用一个库

用下面两条命令看两台是不是连着同一个库：

```bash
curl -fsS http://127.0.0.1:8088/api/health
curl -fsS http://127.0.0.1:8089/api/health
```

两边返回里的 `ok` 和 `db` 都是 true，`users_loaded` 的数字也相同。在一台创建一个用户或模型，另一台刷新后能看到。日志里，拿到租约的那台会执行通道和定时任务，其他台会记下自己跳过了。

增加第三台时，使用同一组数据库变量和新的数据目录，再把这台加到代理的后端列表里。

## 6. 在 Kubernetes 上安装

机器已经在 Kubernetes 里时，用 Helm 一次装上三部分：带 pgvector 的 PostgreSQL、默认两个副本的 Octop，以及对外的 Ingress。数据库是单副本，数据卷 20Gi，集群需要有默认的 StorageClass。要能拉取 `pgvector/pgvector:pg16` 和 `ghcr.io/tencentcloud/octop:<版本>`。需要 Kubernetes 1.25 或更新版本，以及 Helm 3。参数说明写在 [deploy/helm/octop/README_CN.md](../deploy/helm/octop/README_CN.md)。Chart 不安装 HorizontalPodAutoscaler，副本数只通过 `replicaCount` 修改。

安装直接用线上包 `oci://ghcr.io/tencentcloud/octop/charts/octop`，不必克隆仓库。打 `v*` 标签时流水线推这个包。镜像 tag 是 `1.0.3b5` 这种形式。Helm 要求 chart 版本是 SemVer，所以同一次发布里 chart 版本写成 `1.0.3-b5`；没有字母后缀的 `1.0.3` 两边相同。发布包里的 `appVersion` 已经是镜像 tag，安装命令不用再写 `image.tag`。要虚拟桌面、本地向量或 OCR 时，把 `image.tag` 设为 `<版本>-full`，并设 `shm.enabled=true`。改 chart 源码时仍用仓库目录 `deploy/helm/octop`。已经发出的 `v1.0.3b5` 不含这份 chart，要等下一次版本标签。

【插图 5】Kubernetes 里的三个部分

提示词：一张 Kubernetes 部署图，白底，细线框，扁平。外层大框标题「命名空间 octop」。框内从左到右三列。左列：方框「StatefulSet octop-pgvector」，下面一块圆柱标「20Gi」，旁边小字「Service octop-pgvector:5432」。中列：方框「Deployment octop」，里面两个小方框「Pod」和「Pod」，每个 Pod 下挂一块小磁盘，文字是「emptyDir」。右列：方框「Ingress」，上方写主机名「octop.example.com」，内部写「cookie OCTOP_AFFINITY」。Ingress 用箭头指向两个 Pod，两个 Pod 再用箭头指向左侧的数据库 Service。简体中文，不要画 Kubernetes 船舵以外的装饰，组件名称保持英文原名。

### 6.1 要准备的配置

Chart 不保存口令，也不会根据 values 生成 Secret。线上包的默认值用下面这条命令查看：

```bash
helm show values oci://ghcr.io/tencentcloud/octop/charts/octop --version 1.0.3-b5
```

仓库里的 `deploy/helm/octop/values.example.yaml` 是带注释的同一批参数，`secrets.example.yaml` 是口令样例。复制后改域名，占位符换成真实口令。填好的口令文件不要提交进仓库。

| 配置 | 是否必须 | 作用 |
|------|----------|------|
| Secret `octop-admin` 的 `username`、`password` | 必须 | 控制台登录账号。只在第一次初始化时用来创建管理员 |
| Secret `octop-pg` 的 `user`、`password`、`database` | 必须 | PostgreSQL 的库名、用户和口令。不是控制台密码 |
| `ingress.host` | 开启 Ingress 时必须 | 对外域名。跨域地址留空时会用 `https://<ingress.host>` |
| Secret `octop-tls` | TLS 保持开启时必须 | 这张域名的证书。默认 Secret 名字是 `octop-tls` |

管理员密码的要求见 [第 4.2 节](#42-入口和管理员密码)。不合格时不会创建管理员，每个 Pod 会各自进入设置向导。初始化完成以后，再改 `octop-admin` 不会改掉已经建好的控制台密码；再改 `octop-pg` 也不会改掉数据卷里已经建好的数据库账号。数据库账号要先执行 `ALTER USER`，再更新 Secret。控制台密码在登录后修改。

入口默认按 Ingress NGINX 编写，类名是 `nginx`，并用 cookie `OCTOP_AFFINITY` 粘住浏览器，同时把响应缓冲关掉、把代理超时设为 3600 秒。换用其他入口控制器时，修改 `ingress.className` 和 `ingress.annotations`。MicroK8s 自带的 Traefik 常见类名是 `public`。没有对外域名时，安装时加上 `--set ingress.enabled=false`，再用端口转发访问。

发布名称用 `octop`。数据库 Service、StatefulSet 和 Octop 的 Deployment 都按这个名字生成。下面的检查命令也按这个名字来写。

### 6.2 安装

数据库密码和管理员密码分成两个 Secret。`--version` 写成已经发布的 chart 版本。

```bash
kubectl create namespace octop

kubectl -n octop create secret generic octop-pg \
  --from-literal=user=octop \
  --from-literal=password="$(openssl rand -base64 24)" \
  --from-literal=database=octop

kubectl -n octop create secret generic octop-admin \
  --from-literal=username=admin \
  --from-literal=password='管理员密码至少8位且含字母和数字'

kubectl -n octop create secret tls octop-tls \
  --cert=fullchain.pem --key=privkey.pem

helm upgrade --install octop oci://ghcr.io/tencentcloud/octop/charts/octop \
  --version 1.0.3-b5 \
  -n octop \
  --set ingress.host=octop.example.com
```

两个副本可能同时初始化。后完成的那个发现管理员已经存在，就会跳过。如果碰到唯一约束，这个 Pod 会退出并再启动一次，然后跳过创建。

### 6.3 更换域名

更换对外域名时升级 release，并让 TLS 证书里的域名和 `ingress.host` 一致。跨域地址留空时会跟着这个域名走，不必再改 Deployment。关掉 TLS 时，把注解 `nginx.ingress.kubernetes.io/session-cookie-secure` 改成 `"false"`。

```bash
helm upgrade octop oci://ghcr.io/tencentcloud/octop/charts/octop \
  --version 1.0.3-b5 \
  -n octop \
  --reuse-values \
  --set ingress.host=octop.example.com
```

Ingress 用 cookie `OCTOP_AFFINITY` 把一个浏览器固定到一个 Pod，原因见 [第 4.2 节](#42-入口和管理员密码)。这个 Pod 消失后，下一次请求会到还在运行的副本。Service 不要按来源 IP 做会话保持。

### 6.4 检查是否装好

```bash
kubectl -n octop rollout status statefulset/octop-pgvector
kubectl -n octop rollout status deploy/octop

kubectl -n octop exec octop-pgvector-0 -- \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\dx"'

kubectl -n octop port-forward svc/octop 8088:8088
curl -fsS http://127.0.0.1:8088/api/health
```

`\dx` 的结果里应有 `vector`。健康接口里的 `ok` 和 `db` 为 true。然后用浏览器打开 Ingress 的域名，使用 `octop-admin` 里的用户名和密码登录。

### 6.5 托管数据库

数据库改用托管的 PostgreSQL 时，安装不要带上 chart 里的数据库。托管库需要事先提供 `vector`。`octop-pg` 仍然提供库名、用户和口令。表结构仍由 Octop 在启动时创建。

```bash
helm upgrade --install octop oci://ghcr.io/tencentcloud/octop/charts/octop \
  --version 1.0.3-b5 \
  -n octop \
  --set postgresql.enabled=false \
  --set database.host=pg.example.com \
  --set ingress.host=octop.example.com
```

### 6.6 调整副本数

```bash
helm upgrade octop oci://ghcr.io/tencentcloud/octop/charts/octop \
  --version 1.0.3-b5 \
  -n octop \
  --reuse-values \
  --set replicaCount=3
```

滚动更新会先启动新 Pod，再停止旧 Pod。旧 Pod 退出时释放通道和任务租约，新 Pod 在下一轮检查时接手。已经粘在旧 Pod 上的页面会断开，刷新后进入还在运行的副本。

## 7. 故障和备份

### 7.1 一台停止之后

一台 Octop 停止后，入口不再把新请求发给它。已经固定在这台上面的浏览器，刷新后会到其他台。它持有的通道和定时任务，大约在 90 秒内由其他台接手。数据库停止后，每台健康接口里的 `db` 都会失败，直到数据库恢复。只增加 Octop 副本不能代替这台数据库。

【插图 6】一台 Octop 停止之后

提示词：一张故障切换示意图，白底，细线框，扁平，从左到右。左边是浏览器和方框「入口」。入口原来指向中间灰色、带删除线的方框「Octop 已停止」，这条线画成灰色虚线。入口另有一条实线箭头，指向右边正常的方框「Octop 运行中」，线上写「新的请求」。已停止的 Octop 旁有一个小标签「释放租约」，用箭头指向运行中的 Octop，箭头上写「约 90 秒」。两台 Octop 下方都连着「PostgreSQL」；若要表现数据库也停止，把 PostgreSQL 画成灰色并标注「数据库停止后请求无法继续」。简体中文，不要警报灯和爆炸效果。

### 7.2 备份

备份使用 `pg_dump`。每台本地目录里主要是这台自己的运行文件。如果还有专家使用默认的本机工作区，那台机器的数据目录要单独备份。原来的 SQLite 备份不能直接还原到这套 PostgreSQL。

### 7.3 当前限制

- chart 自带的数据库没有自动故障转移，也没有定时备份。
- 实时对话不会自动换到另一台。入口如果没有按 cookie 固定，一次会话可能被分到两台，页面输出会中断。
- 专家没有单独的租约，每台都会加载已启用的专家。
- 飞书去重文件在持有通道的那台本地。
- 已有的 SQLite 数据不会自动迁入 PostgreSQL。
- Chart 不提供 HorizontalPodAutoscaler，副本数在 values 里手写。
