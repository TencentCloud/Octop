# 已有本地数据时认领账户：实现方案

> 对应 `DESKTOP_ARCHITECTURE.zh.md` §3.2 与 `../README.md` Accounts 中尚未覆盖的情况。
> 设备凭据续期已经完成。本文只解决：**本机 `OCTOP_HOME` 里已经有用户，但从未注册过设备凭据，安装新版桌面后落到登录页。**
> 本文是实现规格，代码尚未落地。

## 1. 问题

桌面首次安装没有用户时，初始化向导在 `OCTOP_REQUIRE_SETUP_PASSWORD=0` 下创建管理员，密码由服务端随机生成，壳把设备凭据绑到这个用户上。之后冷启动用 `POST /api/auth/device/token` 换 JWT，不再出现登录页。

一旦 `user_count > 0`，`GET /api/setup/status` 的 `setup_required` 为 false，向导不会出现。旧桌面、以及用 `octop run` 装过的服务端，都停在这里：库里有人，`secrets` 里没有匹配的 `desktop_device`，`renewDesktopSession()` 失败，界面是 `dashboard/src/pages/Login/index.tsx`。

新建一个本地账户不能代替认领。`POST /api/setup/initial-admin` 在已有用户时由 `_enforce_wizard_open` 拒绝。另建的用户也看不到原账户名下的智能体、会话和渠道，它们挂在原来的 `owner_user_id` 上。

凭据被删除、或用户行被移除之后回到登录页，仍然是架构文档里保留的死局，恢复方式仍是 `octop user passwd`。那不是本文的范围。

## 2. 决定

主路径是认领已有本地账户。登录页先走现有续期；续期失败且运行在桌面壳内时，用一次点击把设备凭据绑到选中的用户并进入 `/chat`。不静默进入。

新建本地账户是次要出口，只给明确不想使用现有数据的人。文案写明原有智能体和会话仍属于旧账户。

浏览器打开的服务端不出现这三块界面，三个新接口在未设置 `OCTOP_DESKTOP_SHELL=1` 时拒绝。

认领不改 `password_hash`。之后用命令行或浏览器，原来的密码仍然有效。

## 3. 谁可以认领

可认领用户同时满足：

- `disabled = 0`
- `password_hash` 非空

桌面第一次安装时生成的随机密码算本地密码。后来又绑定了单点登录、但本地密码还在的用户也可以认领。

纯单点登录或 LDAP、没有本地密码的用户不出现在列表里。登录页继续显示现有的单点登录按钮。

## 4. 安全

`POST /api/auth/device/token` 靠钥匙串里的设备凭证。认领时这张凭证尚未注册，不能只靠 loopback：同一台机器上的其他进程都能访问 `127.0.0.1`。壳标志位是 sidecar 自己的环境变量，不是调用方的密钥。

sidecar 在 `secrets.desktop_device` 不存在或已撤销时，向 `<OCTOP_HOME>/desktop-claim-nonce` 写入 32 字节随机数，权限 `0600`。已有有效设备凭据则不写这个文件。壳读取它，和设备凭证一起交给接口。渲染进程只通过 IPC 传递用户 id，看不到 nonce，也看不到设备凭证。

能读到 `OCTOP_HOME` 的进程本来就能读数据库和 JWT 密钥。读不到这个目录的进程，即使打到 loopback，也过不了 nonce。认领、新建成功，或本机凭据续期成功之后，删除该文件。nonce 用常量时间比较。用过的 nonce 再提交则拒绝。

失败节流沿用 `auth_device.py` 里设备令牌的按来源计数。

## 5. 接口

三个接口都加在 `src/octop/api/routers/auth_device.py`，并列入 `src/octop/api/deps.py` 的 JWT 豁免精确路径。每个接口都要过现有的 `_require_desktop_loopback`，再校验 nonce。

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/auth/device/candidates` | 返回可认领用户的 `id`、`username`、`display_name` |
| POST | `/api/auth/device/claim` | 校验 nonce 与 `user_id`，写入 `desktop_device`，签发 JWT |
| POST | `/api/auth/device/local-user` | 新建本地用户，绑定设备凭证，签发 JWT |

nonce 放在请求头 `X-Octop-Claim-Nonce`，不放查询字符串。`claim` 与 `local-user` 的正文另含 `device_token`（以及新建时的用户字段）。`candidates` 只靠请求头。

`claim` 写入的 JSON 与现有 `register` 相同：`v`、`user_id`、`hash`、`label`、`created_at`，存在 `secrets` 表的一行 `desktop_device`。后一次认领覆盖前一次绑定。审计动作为 `auth.device_claimed`。

`user_id` 必须落在第 3 节的可认领集合里。不在集合中、用户已禁用、nonce 错误、非 loopback、未开桌面壳，都拒绝，并且不签发 JWT。

响应与 `POST /api/auth/device/token` 相同：`access_token`、`token_type`、`expires_in`。

## 6. 新建账户

`local-user` 的正文字段为 `username`、`display_name`、`email`、`locale`、`device_token`。不接受密码。

用户名校验走 `UserManager.create` 已有的规则。密码用 `secrets.token_urlsafe(32)` 生成后只写入哈希，调用方拿不到明文。角色是 `Role.USER`，不是第二个管理员。

创建成功后调用 `try_bootstrap_default_agent`，不传 `agent_id`。这样不会占用已有的 `main`，新用户在自己还没有智能体时得到默认的 `general-assistant`。旧账户的数据不动。

审计动作为 `auth.device_local_user_created`。设备行与 JWT 的写法和 `claim` 相同，成功后同样删除 nonce。

## 7. 壳与 IPC

`desktop/src/main/session/device-session.ts` 增加三个方法。主进程读取 nonce 文件和设备凭证，渲染进程不接触这两样。

| IPC | 渲染进程入参 | 主进程行为 |
|---|---|---|
| `session.candidates` | 无 | `GET /api/auth/device/candidates`，附带 nonce |
| `session.claim` | `userId` | `POST /api/auth/device/claim` |
| `session.createLocal` | `username`、`displayName`、`email`、`locale` | `POST /api/auth/device/local-user` |

通道名加在 `desktop/src/shared/ipc-contract.ts`，由 `desktop/src/preload/index.ts` 暴露，在 `desktop/src/main/index.ts` 接到 `DeviceSessionClient`。`dashboard/src/api/desktopSession.ts` 只包这三步调用。没有 `window.octopDesktop` 时返回空，浏览器构建不用条件编译。

`claim` 与 `createLocal` 在服务端已经写好 `desktop_device`。渲染进程拿到 JWT 后走现有的 `setAuthToken`；随后的 `register` 用同一枚设备凭证覆盖写同一行，结果相同。

## 8. 登录页

只改 `dashboard/src/pages/Login/index.tsx`。顺序固定：

1. 现有的 `renewDesktopSession()`。成功则 `setAuthToken` 并 `navigate("/chat")`。
2. 续期失败，且 `window.octopDesktop.session` 存在时，调用 `session.candidates()`。
3. 一个候选：主按钮「继续使用本机账户 {显示名}」，显示名空则用用户名。多个候选：每个显示名一个按钮。点击调用 `session.claim(id)`。
4. 用户名、密码和验证码收进「使用密码登录」，逻辑仍是现有的 `authApi.login`。
5. 「新建本机账户」收集用户名、显示名、邮箱，说明原有智能体和会话仍属于旧账户。提交调用 `session.createLocal`，成功后进入 `/chat`。

候选列表为空（库里只有纯单点登录用户，或还没有任何用户）时不显示认领按钮。没有任何用户时仍然由现有的 `setup_required` 转到 `/setup`，不在登录页新建。

文案加在 `dashboard/src/locales/zh.json` 与 `en.json` 的 `login` 下，键两边保持一致。

## 9. 改动位置

| 位置 | 改动 |
|---|---|
| `src/octop/api/routers/auth_device.py` | 三个接口、nonce 读写与删除 |
| `src/octop/api/deps.py` | 三条路径加入 `_JWT_EXEMPT_EXACT` |
| `src/octop/infra/setup/` 或 `auth_device.py` 旁的小模块 | nonce 文件路径与 `0600` 写入；启动时按第 4 节决定是否创建 |
| `desktop/src/main/session/device-session.ts` | `candidates` / `claim` / `createLocal` |
| `desktop/src/shared/ipc-contract.ts`、`preload/index.ts`、`main/index.ts` | IPC |
| `dashboard/src/api/desktopSession.ts` | 渲染进程包装 |
| `dashboard/src/pages/Login/index.tsx` | 第 8 节的顺序 |
| `dashboard/src/locales/zh.json`、`en.json` | `login.*` |
| `desktop/README.md` Accounts | 实现后把本文描述的行为写成现状，并删掉「尚未实现」 |

OpenAPI 沿用该路由文件已有的 `summary`。不新增数据表，不改迁移版本。

## 10. 验证

- 扩展 `tests/integration/test_desktop_device_session.py`：单个本地用户可认领并随后续期；多个用户必须带对的 `user_id`；禁用用户和 `password_hash` 为空的用户不在列表中；nonce 错误、用过、非 loopback、未开桌面壳都拒绝；新建用户角色为 `user`，且不接管已有 `main`；认领不改变原密码哈希。
- 扩展 `desktop/src/main/session/device-session.test.ts`：主进程附带 nonce 与设备凭证，渲染进程侧的包装不接收这两样。
- 登录页补一条桌面分支：续期失败后出现认领按钮，点击后进入 `/chat`。浏览器路径不渲染认领和新建。
- 文案键跑 `uv run pytest tests/unit/i18n -q`。
- 界面改动后跑 `cd dashboard && npx tsc -b`。

## 11. 不做的事

- 不静默登入，包括只有一个本地用户时。
- 不在认领时重置或清除密码。
- 不把纯单点登录或纯 LDAP 用户放进候选列表。
- 不复用 `POST /api/setup/initial-admin`。该接口在已有用户时必须继续返回 410。
- 不给新建用户管理员角色，也不把旧智能体改挂到新用户。
- 不改变浏览器部署的登录页。
