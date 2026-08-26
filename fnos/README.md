# Octop — 飞牛 FnOS 安装包

本目录包含将 [TencentCloud/Octop](https://github.com/TencentCloud/Octop) 打包为飞牛 fnOS `.fpk` 安装包所需的全部文件，并附带自动同步上游 + 自动构建的 GitHub Actions。

## First use (initial account)

After install, open the app (Docker: `http://<device-ip>:8088`, native: `http://<device-ip>:8089`) and sign in with the **initial admin account**:

| Field | Value |
|-------|-------|
| Username | `admin` |
| Password | `Octop123` |

> The password is a fixed initial value (same as the official Docker image default). **Change it right after first login** via the avatar menu → "Change password". If `OCTOP_ADMIN_USERNAME` / `OCTOP_DEFAULT_PASSWORD` were customized via env during install, those take precedence.

## 两种安装包

仓库同时产出 **两款** `.fpk`，用于满足不同部署偏好：

| 版本 | 包名 | 体积 | 运行方式 | 依赖 |
|------|------|------|----------|------|
| **Docker 版** | `octop-<ver>.fpk` | ~8 KB | 飞牛自动从 `ghcr.io/TencentCloud/octop:latest` 拉镜像运行 | 宿主需有 Docker 运行时 |
| **本地版（非 Docker）** | `octop-native-<ver>.fpk` | ~560 MB | 自带 Python 3.12 运行时 + 前端 + 全部附加组件 + Chromium，原生运行在飞牛主机 | 无需 Docker |

- **Docker 版**实现为 FnOS `docker-project`：包体只含 `docker-compose.yaml` 与向导配置，运行时由飞牛拉取 GHCR 镜像。镜像已内置全部附加组件（`browser` 浏览器自动化 + `desktop` 桌面控制）与前端。
- **本地版**实现为 FnOS 原生 `app`：包内自带独立 Python 3.12 运行时、Octop 全部依赖、前端构建产物、Playwright Chromium，以及 `data-share` 共享数据目录，直接以进程方式运行，不依赖 Docker。

> 两款包都在滚动发布 **`fnos-latest`**：<https://github.com/TencentCloud/Octop/releases/tag/fnos-latest>

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
│   │   └── install         # 安装向导（可配置管理员账号/密码、日志级别、LLM 密钥）
│   ├── app/
│   │   ├── docker/
│   │   │   └── docker-compose.yaml   # 引用 ghcr.io/TencentCloud/octop:latest
│   │   └── ui/
│   │       ├── config                # 桌面图标入口
│   │       └── images/icon-{64,256}.png
│   └── Dockerfile          # 从仓库源码构建镜像，安装全部附加组件（browser + desktop）
└── native/                 # 本地版（非 Docker 的 FnOS 原生 app）
    ├── manifest            # platform=all + 原生 app 元信息
    ├── cmd/                # 生命周期脚本（main / install_callback / config_callback）
    ├── config/
    │   ├── privilege       # 权限声明（root，用于补装 Chromium 系统库）
    │   └── resource        # data-share + usr-local-linker
    ├── app/
    │   ├── bin/octop       # 启动器（用自带 Python 运行时启动 octop init/run）
    │   └── ui/             # 桌面图标入口
    └── wizard/             # 安装/配置/卸载/升级向导
```

## 工作机制

1. **源码同步**：`.github/workflows/zz-sync-upstream.yml` 每 6 小时把上游 `TencentCloud/Octop` 的更新合并进本仓 `main` 分支（使用仓库自带 `GITHUB_TOKEN`，无需 PAT）。
2. **镜像构建**：`.github/workflows/fnos-build-fpk.yml` 的 `image` job 在 `main` 更新时，用 `fnos/docker/Dockerfile` 从仓库源码构建 Octop 镜像并推送到 `ghcr.io/TencentCloud/octop:latest`（含全部附加组件）。
3. **安装包构建**：同一 workflow 的 `fpk` job 用 `scripts/build-fpk.sh` 把 `fnos/docker/` 打成 Docker 版 `.fpk`；`native` job 用 python-build-standalone 构建 Python 3.12 运行时、安装全部依赖与 Playwright Chromium，把 `fnos/native/` 打成本地版 `.fpk`（`continue-on-error`，失败不阻塞 Docker 版）。两者均以滚动发布 `fnos-latest` 提供下载。

## 本地构建 .fpk（无需 Docker）

```bash
bash scripts/build-fpk.sh            # 仅 Docker 版  → dist/octop-<version>.fpk
bash scripts/build-fpk.sh docker     # 仅 Docker 版
bash scripts/build-fpk.sh native     # 仅本地版      → dist/octop-native-<version>.fpk
```

`.fpk` 为「双层 gzip tar」：外层含 `app.tgz / cmd / config / wizard / ICON.PNG / ICON_256.PNG / LICENSE / manifest`，内层 `app.tgz` 含 `app/` 内容。

## 在飞牛上安装

1. 飞牛「应用中心 → 设置 → 手动安装应用」选择对应 `.fpk`：
   - 想用 Docker 跑、主机已装 Docker → 选 `octop-<version>.fpk`
   - 不想依赖 Docker、希望自带运行时原生运行 → 选 `octop-native-<version>.fpk`
2. 安装向导中设置管理员账号/密码、日志级别、LLM 密钥（可选）。
3. 安装完成后桌面出现「Octop AI 助手」图标，浏览器打开 `http://<设备IP>:8088`。
4. Docker 版镜像首次会从 `ghcr.io/TencentCloud/octop:latest` 拉取；请确保该镜像为公开（workflow 已自动设为 public）。本地版无需联网拉镜像，首次启动会按需要补装 Chromium 系统库（需 root 权限，已尽力处理）。

> 服务端口固定为 `8088`（飞牛端口映射与桌面图标均据此）。附加组件（browser 浏览器自动化 + desktop 桌面控制）已在镜像中默认安装。
