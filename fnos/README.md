# Octop — 飞牛 FnOS 安装包

本目录包含将 [TencentCloud/Octop](https://github.com/TencentCloud/Octop) 打包为飞牛 fnOS `.fpk` 安装包所需的全部文件，并附带自动同步上游 + 自动构建的 GitHub Actions。

## 首次使用（初始账号）

安装向导中设置管理员账号：用户名与密码必填，显示名称、邮箱可选。密码至少 8 位，且必须同时包含字母和数字（与应用侧密码策略一致；过于常见的密码如 `Octop123` 会被拒绝，无效输入会在安装时直接提示）。

密码由用户自己设定，不再自动生成。忘记时打开飞牛「文件管理」，进入应用共享里的 Octop 数据目录，查看 `octop-login.txt`（应用「设置」窗口会显示当前目录）。该文件只备份安装或应用「设置」改密时的密码，**网页改密后不会自动更新**。

> 若你在 Web 控制台「头像菜单 → 修改密码」中改过密码，请用网页密码登录。

### 官方命令行管理

本地版安装后自动注册官方 CLI 到 PATH（`/usr/local/bin/octop` → `octop-cli`），SSH 进飞牛即可使用全部官方管理命令（以 root 或 octop-native 身份执行最顺）：

```bash
octop --help            # 官方 CLI 全部子命令
octop version
octop provider list     # 模型 provider
octop agent list        # 专家/Agent
octop user list         # 用户管理
octop user passwd <用户名> --password <新密码>   # 离线改密（应用「设置」窗口改密也走这一命令）
octop skills --help     # 技能管理
octop backup --help     # 备份/恢复
```

> 注意：不要手动执行 `octop run`（会与飞牛应用中心托管的服务实例抢 8089 端口）；Web 服务一律由应用中心启停。

## 两种安装包

仓库同时产出 **三款** `.fpk`，用于满足不同部署偏好与 CPU 架构：

| 版本 | 包名 | 体积 | 运行方式 | 依赖 |
|------|------|------|----------|------|
| **Docker 版（推荐，尤其是 ARM）** | `Octop-fnos-docker-<ver>.fpk` | ~340 KB | 飞牛拉取 `ghcr.io/tencentcloud/octop:<本包版本>`（`amd64` / `arm64` 多架构），重启不再重拉 | 宿主需有 Docker，且能访问 `ghcr.io` |
| **本地版 x86_64** | `Octop-fnos-native-<ver>.fpk` | ~200 MB | 复用飞牛「Python 3.12」+ 包内核心依赖与前端 | 无需 Docker |
| **本地版 ARM64** | `Octop-fnos-native-arm64-<ver>.fpk` | ~200 MB | 同上，site-packages 为 aarch64；勿装到 x86 | 无需 Docker；ARM 飞牛无 Docker 时再用 |

- **Docker 版**实现为 FnOS `docker-project`：包体只含 `docker-compose.yaml` 与向导配置，运行时由飞牛从 GHCR 拉取镜像。x86 / ARM 飞牛共用这一份 FPK，Docker 按本机架构拉对应镜像层。ARM 飞牛优先用这一份。镜像已内置 `desktop` 桌面控制与前端；Playwright Chromium 不预装，可在控制台按需安装。
- **本地版**实现为 FnOS 原生 `app`：解释器复用飞牛「Python 3.12」开发工具；包内是 Octop 核心依赖与前端。专家 shell / 技能若要跑 `node` / `npx`，会复用飞牛已装的 Node.js（不强制安装）。扩展里的 `.so` 与 CPU 架构绑定，因此 x86 与 ARM 各打一份；装错架构会在安装或启动时报错。

> 上述包随正式版一起挂在 **`v*` GitHub Release** 上（例如 [v0.9.31](https://github.com/TencentCloud/Octop/releases/latest)）：`Octop-fnos-docker-<ver>.fpk` / `Octop-fnos-native-<ver>.fpk` / `Octop-fnos-native-arm64-<ver>.fpk`。

## 目录结构

```
fnos/
├── README.md
├── docker/                 # Docker 版（docker-project）
│   ├── manifest            # 应用元信息（platform=all / 名称/版本/桌面入口等）
│   ├── ICON.PNG / ICON_256.PNG
│   ├── LICENSE             # 复用仓库根 LICENSE（MIT）
│   ├── cmd/                # 生命周期脚本（main / install_callback / config_callback 等）
│   ├── config/
│   │   ├── privilege       # 权限声明（docker-octop 用户）
│   │   └── resource        # 资源声明（docker-project + 数据共享目录）
│   ├── wizard/
│   │   ├── install       # 安装向导（建账号 + 接下来怎么用）
│   │   ├── config        # 应用「设置」窗口（仅改密，不展示明文密码）
│   │   ├── upgrade       # 升级说明（不改网页密码）
│   │   └── uninstall     # 卸载向导（数据清理方式）
│   ├── app/
│   │   ├── docker/
│   │   │   └── docker-compose.yaml   # 引用 ghcr.io/tencentcloud/octop:<version>；卷挂 TRIM_DATA_SHARE_PATHS
│   │   └── ui/
│   │       ├── config                # 桌面图标入口
│   │       └── images/icon-{64,256}.png
│   └── Dockerfile          # 从仓库源码构建镜像，安装 desktop extra（不预装 Chromium）
└── native/                 # 本地版（非 Docker 的 FnOS 原生 app）
    ├── manifest            # platform=all + 原生 app 元信息
    ├── cmd/                # 生命周期脚本（main / install_callback / config_callback）
    ├── config/
    │   ├── privilege       # 权限声明（root，用于 sudo / 远程桌面等）
    │   └── resource        # data-share + usr-local-linker
    ├── app/
    │   ├── bin/octop       # 启动器（复用飞牛 Python 3.12，启动 octop init/run）
    │   ├── wizard/config.template   # 「设置」窗口表单模板（渲染当前用户名后落到已安装包 wizard/config）
    │   └── ui/             # 桌面图标入口
    └── wizard/             # 安装/配置/卸载/升级向导
```

## 工作机制

1. **发版链路**：`v*` tag → `release.yml`（PyPI + GitHub Release）与 `docker-publish.yml`（GHCR / Hub）并行；Release 成功后自动 `workflow_dispatch` 本工作流。
2. **镜像复用**：不再重新 build 镜像；`ensure-image` 轮询等待 `ghcr.io/tencentcloud/octop:{version}`（由 docker-publish 推送的 amd64+arm64 清单）。Docker 版 `.fpk` 仅打包 compose，运行时拉取该镜像。
3. **Wheel 复用**：Native 版优先从同版本 GitHub Release（`v*`）下载 `octop-*.whl`；若缺失再回退源码构建前端 + wheel。
4. **安装包构建**：`fpk` / `native` / `native-arm64` job 用 `scripts/build-fpk.sh` 打包。官方 fnpack 只有 linux-amd64，ARM 本地版先在 `ubuntu-24.04-arm` 上装好 aarch64 `site-packages`，再回到 amd64 runner 打包。产物挂到同一个 `v*` GitHub Release（与 wheel、桌面包并列）。

## 本地构建 .fpk（无需 Docker）

```bash
bash scripts/build-fpk.sh            # Docker 版 + 当前机器架构的本地版
bash scripts/build-fpk.sh docker     # 仅 Docker 版  → dist/Octop-fnos-docker-<version>.fpk
bash scripts/build-fpk.sh native     # 仅本地版      → dist/Octop-fnos-native-<version>.fpk
FPK_ARCH=arm64 bash scripts/build-fpk.sh native   # ARM 本地版（需已放入 aarch64 site-packages）
```

`.fpk` 为「双层 gzip tar」：外层含 `app.tgz / cmd / config / wizard / ICON.PNG / ICON_256.PNG / LICENSE / manifest`，内层 `app.tgz` 含 `app/` 内容。

## 在飞牛上安装

1. 飞牛「应用中心 → 设置 → 手动安装应用」选择对应 `.fpk`：
   - **优先**：已装 Docker（含 ARM 飞牛）→ `Octop-fnos-docker-<version>.fpk`（x86 / ARM 通用）
   - 不想依赖 Docker、x86_64 飞牛 → `Octop-fnos-native-<version>.fpk`
   - 不想依赖 Docker、ARM64 飞牛 → `Octop-fnos-native-arm64-<version>.fpk`（不要装到 x86）
2. 安装向导中设置管理员用户名与密码（显示名称、邮箱可选），并阅读「接下来怎么用」。
3. 等到应用中心显示「运行中」再点「打开」，或用浏览器访问 Docker 版 `http://<设备IP>:8088` / 本地版 `http://<设备IP>:8089`，用刚才设置的账号登录。
4. 登录后到控制台「设置 → 模型」配置 API Key。Docker 版首次会从 `ghcr.io` 拉取与本包版本相同的镜像（设备需能访问 GitHub Container Registry），请等下载完成；之后重启不会重拉。容器数据挂在飞牛 `data-share`（`TRIM_DATA_SHARE_PATHS`，一般为 `/volX/@appshare/octop/data`），应用重启后保留。本地版无需联网拉镜像。Playwright Chromium 不预装，需要远程浏览器时在控制台按需安装。

> Docker 版端口 `8088`，本地版端口 `8089`（飞牛端口映射与桌面图标均据此）。`desktop` 桌面控制已在 Docker 镜像中默认安装。
