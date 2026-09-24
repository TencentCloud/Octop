# LDAP 目录登录

> Octop 支持接入企业目录（Active Directory、OpenLDAP 等）作为登录方式：用户在**现有登录表单**里直接输入域账号和密码，Octop 通过目录完成认证，并可自动创建本地账号、按目录组映射角色。

本文覆盖：功能与设计、跑起来（含本地 LDAP 开发服务器）、配置项参考、登录行为细则、HTTP API、测试方法、故障排查。

---

## 一、功能概览

| 能力 | 说明 |
|---|---|
| 登录方式 | 复用 `/api/auth/login`，无需新端点；本地密码校验失败后回退目录 |
| 检索方式 | 服务账号（或匿名）先检索用户 DN，再用该 DN 以用户密码二次 bind 验证 |
| 账号开通 | 首次目录登录自动创建 Octop 账号（可关闭） |
| 角色映射 | 按目录组成员关系判定 `admin` / `user`，仅在建号时判定一次 |
| 属性同步 | 登录时回写邮箱、显示名；**不动**已存在账号的角色 |
| 传输安全 | `ldaps://` 或 `ldap://` + StartTLS，证书校验可关（仅测试自签证书） |
| 凭据存储 | 绑定密码经 Fernet 加密后存 `sso_providers.client_secret_enc`，API 从不回传 |

### 设计要点

1. **不新增登录表单**。目录用户走原有的用户名/密码输入框，登录页只多一行提示（`login.ldapHint`），与现有交互一致。后端在本地密码校验失败后回退目录，因此同一入口同时服务本地账号与目录账号。
2. **角色只在开通时判定，之后不回写**。把已存在的用户挪进管理员组**不会**静默提权；角色变更由管理员在 Octop 内显式操作。
3. **零 schema 变更**。复用既有 SSO 表结构：配置行是 `sso_providers.kind = 'ldap'`（明细放在该行的 `extra` JSON），身份关联复用 `user_sso_identities`。
4. **目录故障 ≠ 密码错误**。目录不可达返回 `502 LDAP_UNAVAILABLE`，密码错误返回 `401 AUTH_FAILED`。若该用户名对应的是**有本地密码**的账号，即使目录宕机也只报 401（避免掩盖用户打错密码）。

---

## 二、工作原理

### 2.1 登录时序

```
用户提交 username / password
        │
        ├─ 1. 本地密码校验（UserManager.authenticate）
        │      成功 → 签发 JWT，结束
        │
        └─ 2. LDAP 已启用？否 → 401 AUTH_FAILED
               │
               ├─ 2.1 用服务账号 bind（bind_dn + 绑定密码；bind_dn 为空则匿名）
               ├─ 2.2 以 user_filter 检索（{username} 替换为转义后的输入）→ 用户 DN
               ├─ 2.3 用「该用户 DN + 用户输入的密码」二次 bind  ← 只 bind 检索结果，绝不 bind 用户输入值
               ├─ 2.4 读取属性（邮箱 / 显示名 / 所属组）
               ├─ 2.5 已有身份关联 → 更新资料（邮箱、显示名）后返回
               │      无关联 且 auto_provision → 建号 + 按组定角色 + 建立身份关联
               │      无关联 且 auto_provision=false → 403 LDAP_USER_NOT_PROVISIONED
               └─ 3. 签发 JWT（与本地登录完全同构）
```

所有网络与 bind 均为阻塞调用，通过 `run_in_executor` 执行，不阻塞事件循环。

### 2.2 数据落库

| 数据 | 位置 |
|---|---|
| 目录配置 | `sso_providers` 行，`kind='ldap'`；`enabled` / `display_name` 为列，其余在 `extra` JSON |
| 绑定密码 | 同行的 `client_secret_enc`（Fernet 加密，密钥在 `secrets` 表的 `sso_fernet`） |
| 身份关联 | `user_sso_identities(user_id, provider_id, subject)`，`subject` = 用户 DN |
| 新账号 | `users` 行，`password_hash IS NULL`（目录账号没有本地密码） |

> 目录账号的 `password_hash` 为 `NULL`，所以 `POST /api/auth/change-password` 会返回 `400 PASSWORD_NOT_SET`（而不是误导性的「当前密码错误」）。

---

## 三、跑起来

以下流程在**全新目录**中逐条验证过，可直接复制执行。

### 3.0 前置条件

| 依赖 | 说明 |
|---|---|
| Python 3.12+ / uv | Octop 运行环境（仓库根目录 `uv sync` 一次） |
| Go 1.21+ | 仅用于构建本地 LDAP 开发服务器（glauth） |
| `ldapsearch`（可选） | OpenLDAP 客户端，用于手工验证目录；macOS 自带 |

Octop 侧依赖 `ldap3`，已加入 `pyproject.toml`，`uv sync` 后会安装。

### 3.1 启动本地 LDAP 服务器（glauth）

开发用目录选 [glauth](https://github.com/glauth/glauth)——Go 写的轻量 LDAP 服务，单二进制、配置文件驱动、不需要数据库或容器。

下面的示例把沙箱放在 `~/octop-ldap-dev/`（任意目录都行，**不要**放在 Octop 仓库内，避免污染工作区）：

```bash
LDAP_DEV=~/octop-ldap-dev
mkdir -p "$LDAP_DEV" && cd "$LDAP_DEV"

# 1) 克隆
git clone --depth 1 https://github.com/glauth/glauth.git ldap-glauth

# 2) 构建 —— 必须 GOWORK=off：上游是 Go workspace，会拒绝 -mod=mod
cd ldap-glauth/v2
GOWORK=off go build -o "$LDAP_DEV/glauth" .
```

新建 `~/octop-ldap-dev/glauth.cfg`（下方为完整内容，测试账号可自行增删）：

```toml
debug = false

[ldap]
  enabled = true
  listen = "127.0.0.1:3893"
  tls = false

[ldaps]
  enabled = false

[backend]
  datastore = "config"
  baseDN = "dc=example,dc=org"
  nameformat = "uid"
  groupformat = "cn"

[behaviors]
  LimitFailedBinds = true
  NumberOfFailedBinds = 10
  PeriodOfFailedBinds = 10
  BlockFailedBindsFor = 30

# 服务账号：仅用于检索
[[users]]
  name = "svc-octop"
  uidnumber = 6001
  primarygroup = 5501
  passsha256 = "ec9cea51278ff8572536540a2458a016872a2270b5876ec7ece0b31c885fdfde" # bindpw
    [[users.capabilities]]
    action = "search"
    object = "*"

[[users]]
  name = "alice"
  givenname = "Alice"
  sn = "Anderson"
  mail = "alice@example.org"
  uidnumber = 6002
  primarygroup = 5502
  passsha256 = "6624974ea2baffac164422e4490376c1c31313cd97724ae8ce62fb3f0a0370f2" # alicepw
    [[users.capabilities]]
    action = "search"
    object = "dc=example,dc=org"

[[users]]
  name = "bob"
  givenname = "Bob"
  sn = "Brown"
  mail = "bob@example.org"
  uidnumber = 6003
  primarygroup = 5503
  passsha256 = "e8f318657ce39ec4edeecbbee28fd72dea2261d8a6b2155ce4977393e0ea721b" # bobpw
    [[users.capabilities]]
    action = "search"
    object = "dc=example,dc=org"

[[users]]
  name = "carol"
  givenname = "Carol"
  sn = "Clark"
  mail = "carol@example.org"
  uidnumber = 6004
  primarygroup = 5501
  passsha256 = "d06dc93720809b81d6e0019579108a5745306ad6d37d976ddd6e66a1b2364758" # carolpw
    [[users.capabilities]]
    action = "search"
    object = "dc=example,dc=org"

[[groups]]
  name = "users"
  gidnumber = 5501

[[groups]]
  name = "admin"
  gidnumber = 5502

[[groups]]
  name = "engineering"
  gidnumber = 5503
```

`passsha256` 是明文密码的 SHA-256 小写十六进制：

```bash
printf '%s' 'mypassword' | shasum -a 256 | cut -d' ' -f1     # macOS
printf '%s' 'mypassword' | sha256sum | cut -d' ' -f1         # Linux
```

启动并自检：

```bash
~/octop-ldap-dev/glauth -c ~/octop-ldap-dev/glauth.cfg

# 另开一个终端：以服务账号检索
ldapsearch -LLL -x -H ldap://127.0.0.1:3893 \
  -D "uid=svc-octop,cn=users,dc=example,dc=org" -w bindpw \
  -b "dc=example,dc=org" "(uid=alice)" uid mail memberOf
```

预期输出（关键：`memberOf` 决定管理员角色）：

```
dn: uid=alice,cn=admin,ou=users,dc=example,dc=org
uid: alice
mail: alice@example.org
memberOf: cn=admin,ou=groups,dc=example,dc=org
```

### 3.2 启动 Octop（独立 HOME，避免污染现有实例）

用独立 `HOME` + `OCTOP_HOME` 起一个一次性实例，数据库与向导密码都落在临时目录：

```bash
cd <repo 根目录>
RUNTIME=/tmp/octop-ldap-dev
mkdir -p "$RUNTIME/home"

HOME="$RUNTIME/home" \
OCTOP_HOME="$RUNTIME/home/.octop" \
uv run octop run --host 127.0.0.1 --port 8799
```

首次启动会打印一次性的设置向导密码，同时写入 `$RUNTIME/home/octop-login.txt`：

```
╔══════════════════════════════════════════════════════════╗
║  Octop first-run wizard password (one-time use):          ║
║  xxxxxxxxxxxxxxxxxxxx                                     ║
║  File: ~/octop-login.txt                                  ║
╚══════════════════════════════════════════════════════════╝
```

### 3.3 完成初始化向导

**方式 A：浏览器向导（最简单）** — 打开 `http://127.0.0.1:8799`，粘贴上面的向导密码，按提示选数据库（SQLite 即可）、创建管理员账号、完成。

**方式 B：脚本化（可复现，下述命令均已验证）**

```bash
API=http://127.0.0.1:8799/api
RUNTIME=/tmp/octop-ldap-dev
PW=$(head -1 "$RUNTIME/home/octop-login.txt")

# 1) 校验向导密码 → 拿到一次性 wizard_token
TOK=$(curl -sS -X POST "$API/setup/verify-password" \
  -H 'Content-Type: application/json' -d "{\"password\":\"$PW\"}" \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["wizard_token"])')

# 2) 绑定控制面数据库（SQLite）
curl -sS -X POST "$API/setup/database" -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $TOK" -d '{"driver":"sqlite"}'
# → {"ok":true,"driver":"sqlite"}

# 3) 创建初始管理员（密码需满足强度策略：≥8 位且含字母与数字）
curl -sS -X POST "$API/setup/initial-admin" -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $TOK" \
  -d '{"username":"admin","password":"TestPass12"}'

# 4) 结束向导
curl -sS -X POST "$API/setup/finish" -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $TOK" -d '{"provider_draft":null}'
# → {"ok":true}
```

### 3.4 配置 LDAP

**方式 A：浏览器** — 用 `admin` 登录后进入 **管理 → 用户 → LDAP** 页，按 3.5 的表格填写，点「保存」再点「测试连接」。

**方式 B：API**

```bash
API=http://127.0.0.1:8799/api
AT=$(curl -sS -X POST "$API/auth/login" -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"TestPass12"}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

curl -sS -X PUT "$API/auth/ldap/config" -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $AT" -d '{
    "enabled": true,
    "display_name": "Corp Directory",
    "server_url": "ldap://127.0.0.1:3893",
    "bind_dn": "uid=svc-octop,cn=users,dc=example,dc=org",
    "bind_password": "bindpw",
    "user_base_dn": "dc=example,dc=org",
    "admin_groups": "admin",
    "auto_provision": true
  }'

# 测试连通性（服务账号 bind + 探测 user_base_dn）
curl -sS -X POST "$API/auth/ldap/config/test" -H "Authorization: Bearer $AT"
# → {"ok":true,"detail":"已连接 LDAP 目录服务 (ldap://127.0.0.1:3893)"}

# 登录页可读的公开状态
curl -sS "$API/auth/ldap/status"
# → {"enabled":true,"display_name":"Corp Directory"}
```

### 3.5 本地目录对应的配置值

| 表单/API 字段 | 值 | 说明 |
|---|---|---|
| 服务器地址 `server_url` | `ldap://127.0.0.1:3893` | |
| 绑定 DN `bind_dn` | `uid=svc-octop,cn=users,dc=example,dc=org` | 留空则匿名检索 |
| 绑定密码 `bind_password` | `bindpw` | 只写；省略则保留已存值 |
| 用户基准 DN `user_base_dn` | `dc=example,dc=org` | |
| 用户过滤器 `user_filter` | `(uid={username})` | 必须含字面量 `{username}` |
| 用户名字段 `username_attribute` | `uid` | |
| 邮箱字段 `email_attribute` | `mail` | |
| 显示名称字段 `display_name_attribute` | `givenName` | 见下方提示 |
| 所属组字段 `group_attribute` | `memberOf` | |
| 管理员组 `admin_groups` | `admin` | 逗号分隔，可填组 CN 或完整 DN |
| 首次登录自动创建 `auto_provision` | 开 | |

> **提示**：glauth 不把 `cn` 作为用户可检索属性，因此本地目录用 `display_name_attribute = "cn"` 取不到显示名（`givenName` 可以）。真实 OpenLDAP / AD 正常暴露 `cn`。

### 3.6 用目录账号登录

浏览器：退出当前登录 → 在登录页直接输入目录账号（会看到「使用 Corp Directory 账号登录」提示行）→ 拖过验证码 → 登录。

命令行：

```bash
API=http://127.0.0.1:8799/api
for u in alice:alicepw bob:bobpw carol:carolpw; do
  n=${u%%:*}; p=${u##*:}
  curl -sS -X POST "$API/auth/login" -H 'Content-Type: application/json' \
    -d "{\"username\":\"$n\",\"password\":\"$p\"}" \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print('$n ->', d['user']['role'])"
done
```

预期结果：

| 账号 | 密码 | 所属组 | Octop 角色 |
|---|---|---|---|
| `alice` | `alicepw` | `admin` | `admin` |
| `bob` | `bobpw` | `engineering` | `user` |
| `carol` | `carolpw` | `users` | `user` |
| `alice@example.org` | `alicepw` | — | 邮箱也能登录（默认过滤器含 `mail`） |

密码错误返回 `401 AUTH_FAILED`；目录宕机返回 `502 LDAP_UNAVAILABLE`。

---

## 四、配置项参考

| 字段 | 默认值 | 说明 |
|---|---|---|
| `enabled` | `false` | 关闭时登录不再回退目录；可保存未填完的草稿 |
| `display_name` | `""` | 登录页提示行里显示的名称 |
| `server_url` | `""` | `ldap://` 或 `ldaps://`；端口缺省 389 / 636 |
| `start_tls` | `false` | 对明文 `ldap://` 连接做 StartTLS 升级；**不可**与 `ldaps://` 同用 |
| `verify_tls` | `true` | 校验服务端证书；仅自签测试服务器才关 |
| `bind_dn` | `""` | 服务账号 DN；留空 = 匿名检索 |
| `bind_password` | — | 只写字段，从不回传；省略则保留已存值 |
| `user_base_dn` | `""` | 用户检索基准 DN，必填 |
| `user_filter` | `(\|(uid={username})(sAMAccountName={username})(mail={username}))` | 必须含字面量 `{username}`，会被转义后替换 |
| `username_attribute` | `uid` | 用于确定 Octop 用户名 |
| `email_attribute` | `mail` | 回写到账号邮箱 |
| `display_name_attribute` | `cn` | 回写到显示名 |
| `group_attribute` | `memberOf` | 多值属性，用于管理员组判定 |
| `admin_groups` | `""` | 逗号分隔；可填组 CN（`admin`）或完整 DN（`cn=ops,ou=groups,dc=x`） |
| `auto_provision` | `true` | 关闭后，仅已存在的 Octop 账号可目录登录 |
| `timeout_seconds` | `10` | 连接/接收超时，范围 1–60 |

保存已启用（`enabled=true`）的配置会做完整校验；保存草稿（`enabled=false`）允许字段不全，便于分次填写。

---

## 五、登录行为细则

| 场景 | 行为 |
|---|---|
| 用户名匹配 | 按 `user_filter` 检索；多条命中时优先与 `username_attribute` **完全相等**的那条 |
| 过滤器注入 | 输入值经 `escape_filter_chars` 转义，`*`、`(` 等不会扩大检索范围 |
| 组名比较 | 大小写不敏感；`admin` 与 `cn=admin,ou=groups,dc=x` 视为同一组 |
| 首次登录 | 建号：用户名取目录值（冲突自动加 `_2` 后缀），角色按 `admin_groups` 判定 |
| 再次登录 | 更新邮箱与显示名；**不**覆盖已有角色 |
| 邮箱冲突 | 目录邮箱若已被其他 Octop 账号占用，则该账号邮箱留空，不报错 |
| 账号被停用 | `403 USER_DISABLED` |
| 未开通且 `auto_provision=false` | `403 LDAP_USER_NOT_PROVISIONED` |
| 目录不可达 / 服务账号密码轮换失效 | `502 LDAP_UNAVAILABLE`（本地有密码的账号仍报 401） |
| 修改密码 | 目录账号无本地密码，`400 PASSWORD_NOT_SET` |
| 账号被删除 | 下次登录若 `auto_provision` 开启会重新建号 |

> **生产注意**：`admin_groups` 依赖目录返回 `memberOf`。Active Directory 默认返回；**OpenLDAP 需要启用 `memberof` overlay**，或改用 `groupOfNames` 检索——当前实现只读配置的 `group_attribute`，不做组条目二次检索。若你的目录不提供 `memberOf`，管理员身份需在 Octop 内手动授予（管理 → 用户 → 角色）。

---

## 六、HTTP API

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| `GET` | `/api/auth/ldap/status` | 公开 | `{enabled, display_name}`，供登录页提示 |
| `GET` | `/api/auth/ldap/config` | `sso` | 目录配置；`bind_password` 不返回，用 `has_bind_password` 表示是否已设 |
| `PUT` | `/api/auth/ldap/config` | `sso` | 新增/更新配置；`bind_password` 只写 |
| `POST` | `/api/auth/ldap/config/test` | `sso` | 服务账号 bind + 探测 `user_base_dn` → `{ok, detail}` |

登录本身复用 `POST /api/auth/login`（公开），无需新端点。错误码：

| 错误码 | HTTP | 含义 |
|---|---|---|
| `LDAP_BAD_REQUEST` | 400 | 配置非法（URL 协议、缺 `{username}`、属性名、超时范围等） |
| `LDAP_UNAVAILABLE` | 502 | 目录不可达 / 服务账号被拒 / 检索失败 |
| `LDAP_USER_NOT_PROVISIONED` | 403 | 目录账号未开通且未启用自动创建 |
| `PASSWORD_NOT_SET` | 400 | 试图为目录账号修改本地密码 |
| `AUTH_FAILED` | 401 | 凭据无效 |

---

## 七、测试

### 7.1 单元测试（无需目录）

```bash
uv run pytest tests/unit/auth/test_ldap_config.py tests/unit/auth/test_ldap_client.py -q
# → 34 passed
```

- `test_ldap_config.py`（19 项，含 9 个参数化校验用例）：URL 解析与默认端口、校验规则（协议/主机/StartTLS 冲突/属性名/超时范围/`{username}` 必填）、草稿保存、`extra` 往返、组名逗号切分、组名归一化。
- `test_ldap_client.py`（15 项）：登录成功/密码错误/未知用户、**服务账号 DN 不可冒用**、过滤器转义、邮箱登录、同名精确匹配、目录不可达与服务账号被拒的分类、匿名 bind、StartTLS 失败、属性缺失与类型转换。

### 7.2 集成测试（走真实 HTTP，仅替换 socket 边界）

```bash
uv run pytest tests/integration/test_auth_ldap.py -q
```

19 项，覆盖：开通与角色映射、非管理员组、**改组不提权**、密码错误、服务账号 DN 冒用、本地密码优先、`auto_provision` 开关、目录宕机分类、服务账号密码轮换、停用账号、目录账号改密、公开状态、权限校验、**绑定密码不外泄**、省略密码保留原值、非法配置本地化报错、连通性测试、未配置时完全跳过目录。

`tests/support/ldap_fake.py` 只替换 `ldap3.Connection`（忠实复刻它的 `open()` 返回 `None`、失败抛 `LDAPSocketOpenError` 等语义），其上层——客户端、服务、路由——全部是生产代码。

### 7.3 Live 测试（对真实目录）

需要 3.1 的目录在跑：

```bash
OCTOP_LDAP_TEST_URL=ldap://127.0.0.1:3893 \
OCTOP_LDAP_TEST_BIND_DN='uid=svc-octop,cn=users,dc=example,dc=org' \
OCTOP_LDAP_TEST_BIND_PASSWORD=bindpw \
OCTOP_LDAP_TEST_BASE_DN='dc=example,dc=org' \
OCTOP_LDAP_TEST_ADMIN_GROUP=admin \
OCTOP_LDAP_TEST_USER=alice \
OCTOP_LDAP_TEST_PASSWORD=alicepw \
OCTOP_LDAP_TEST_EXPECTED_ROLE=admin \
uv run pytest tests/live/test_ldap_live.py -m live -v
```

它经由真实 HTTP API 完成配置 → 连通性测试 → 目录登录 → `has_password=false` 校验 → 错误密码拒绝。换 `OCTOP_LDAP_TEST_USER` / `_PASSWORD` / `_EXPECTED_ROLE` 为 `bob`/`bobpw`/`user` 或 `carol`/`carolpw`/`user` 即可验证非管理员映射。缺任一环境变量则自动跳过，不会让 CI 变红。

### 7.4 浏览器验证要点

1. 管理 → 用户 → **LDAP** 页应回填已保存配置，「测试连接」显示 `已连接 LDAP 目录服务`。
2. 退出登录后，登录页密码框下出现「使用 Corp Directory 账号登录」提示（名称取自 `display_name`）。
3. 用 `bob/bobpw` 登录后进入 `/chat`，左侧导航**无**「管理」栏目（角色为 `user`）。

### 7.5 全量门禁

```bash
make all     # format-all + lint + typecheck + test（含 dashboard 构建）
cd dashboard && npx tsc -b
```

两者都必须通过。

---

## 八、故障排查

| 现象 | 错误码 / 状态 | 原因与处理 |
|---|---|---|
| 保存配置报 400 | `LDAP_BAD_REQUEST` | 看 `detail`：URL 缺 `ldap://`/`ldaps://`、`user_filter` 缺 `{username}`、属性名非法、超时不在 1–60 |
| 「测试连接」提示服务账号被拒 | `bind_failed` | `bind_dn` 或 `bind_password` 错；DN 写法需与目录一致（`cn=` / `uid=` / `ou=`） |
| 「测试连接」提示检索被拒 | `search_failed` | `user_base_dn` 越界，或服务账号没有该子树的检索权限（glauth 需 `[[users.capabilities]] action="search"`） |
| 登录报 502 | `LDAP_UNAVAILABLE` | 服务地址/端口不可达、服务账号密码已轮换、防火墙或证书校验失败（自签证书测试时关 `verify_tls`） |
| 登录报 403 未开通 | `LDAP_USER_NOT_PROVISIONED` | 开 `auto_provision`，或先在 Octop 内建同名账号 |
| 登录报 401 | `AUTH_FAILED` | 密码错、用户名在 `user_filter` 下检索不到（检查 `username_attribute` 与过滤器）、或解析出多条且无精确匹配 |
| 登录成功但不是管理员 | — | 用户不在 `admin_groups` 内；确认目录真的返回 `memberOf`（OpenLDAP 需 `memberof` overlay）；改组**不会**自动提权，需在 Octop 内改角色 |
| 显示名为空 | — | 目录未暴露该属性（glauth 的 `cn` 即如此，改用 `givenName`） |
| 改密码报 400 | `PASSWORD_NOT_SET` | 目录账号本就没有本地密码，属预期 |
| 绑定密码丢了 | — | `PUT` 时省略 `bind_password` 会保留原值；若改了 Fernet 密钥（`secrets.sso_fernet`）则需重新填写 |

---

## 九、生产环境准备清单

1. **服务账号**：建一个只读检索账号，授予 `user_base_dn` 子树读权限；不要用域管账号。
2. **传输安全**：优先 `ldaps://`，其次 `ldap://` + StartTLS；证书可信时保持 `verify_tls` 开启。
3. **过滤器**：按目录类型调整，AD 常用 `(&(objectClass=user)(sAMAccountName={username}))`；OpenLDAP 常用 `(&(objectClass=inetOrgPerson)(uid={username}))`。
4. **组映射**：确认目录返回 `memberOf`（OpenLDAP 需 overlay），或接受管理员手动授予。
5. **属性映射**：`display_name_attribute` 建议 `displayName`（AD）或 `cn`/`displayName`（OpenLDAP）。
6. **首次上线**：可用 `auto_provision=true` 便于导入；稳定后可关掉，改为管理员先在 Octop 内建号。

---

## 十、相关文件

| 路径 | 作用 |
|---|---|
| `src/octop/infra/auth/ldap/config.py` | 配置模型、校验、`extra` 序列化与组名解析 |
| `src/octop/infra/auth/ldap/client.py` | `ldap3` 客户端：服务 bind、检索、用户 bind 验证 |
| `src/octop/infra/auth/ldap/service.py` | 配置读写、开通账号、角色映射 |
| `src/octop/api/routers/auth_ldap.py` | 4 个 HTTP 端点 |
| `src/octop/api/routers/auth.py` | 登录时回退目录（`_authenticate_ldap`） |
| `dashboard/src/pages/Admin/Users/LdapPanel.tsx` | 管理端配置表单 |
| `tests/support/ldap_fake.py` | 测试用假目录（替换 `ldap3.Connection`） |
| `tests/live/test_ldap_live.py` | 对真实目录的端到端测试 |

文档 HTML 版本：`docs/ldap.html`，由 `scripts/render_docs_html.py` 从本文生成：

```bash
uv run python scripts/render_docs_html.py docs/ldap.md
```
