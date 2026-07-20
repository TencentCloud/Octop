# Scripts

在**仓库根目录**运行以下命令。

## 安装 Octop（终端用户）

将 Octop 安装到隔离虚拟环境 `~/.octop/venv`，并创建 `~/.octop/bin/octop` 包装脚本加入 PATH。

### 远程一键安装（推荐）

| 平台 | 命令 |
|------|------|
| macOS / Linux | `curl -fsSL https://finnie-1258344699.cos.ap-guangzhou.myqcloud.com/octop/install.sh \| bash` |
| Windows (PowerShell) | `irm https://finnie-1258344699.cos.ap-guangzhou.myqcloud.com/octop/install.ps1 \| iex` |
| Windows (cmd) | 下载 `…/octop/install.bat` 后运行，或使用下方本地脚本 |

### 本地脚本（仓库内）

| 平台 | 命令 |
|------|------|
| macOS / Linux | `bash scripts/install.sh` |
| Windows (PowerShell) | `powershell -ExecutionPolicy Bypass -File scripts/install.ps1` |
| Windows (cmd) | `scripts\install.bat` |

### 常用选项

```bash
# 从 PyPI 安装最新版（默认）
bash scripts/install.sh

# 指定版本
bash scripts/install.sh --version 0.1.0

# 安装可选附加组件
bash scripts/install.sh --extras browser
bash scripts/install.sh --extras browser,channels-feishu

# 从本地源码安装（开发/离线）
bash scripts/install.sh --from-source
bash scripts/install.sh --from-source /path/to/orca

# 使用国内 PyPI 镜像加速依赖
bash scripts/install.sh --mirror https://mirrors.aliyun.com/pypi/simple
```

Windows PowerShell 等价参数：`-Version`、`-FromSource`、`-SourceDir`、`-Extras`。

### 环境变量

| 变量 | 说明 |
|------|------|
| `OCTOP_HOME` | 安装根目录，默认 `~/.octop` |
| `OCTOP_REPO` | `--from-source` 无本地目录时的 git 克隆地址 |
| `OCTOP_PYPI_MIRROR` | PyPI 镜像（与 `--mirror` 等效） |
| `PLAYWRIGHT_DOWNLOAD_HOST` | Playwright 浏览器下载镜像（`browser` 附加组件） |

安装脚本会优先复用系统已安装的 **Chrome / Chromium**（GUI 系统常见，如 macOS / Windows / Linux 桌面）：检测到后直接跳过体积较大的 Playwright 自带 Chromium 下载。如需强制使用 Playwright 自带版本，可手动运行 `python -m playwright install chromium`。

安装完成后：

```bash
octop init    # 初始化数据库与管理员
octop run     # 启动服务 → http://127.0.0.1:8088
```

---

## 构建 PyPI wheel

先构建前端（产物写入 `src/octop/dashboard/`，与 `dashboard/vite.config.ts` 的 `outDir` 一致），再打包 wheel。

```bash
bash scripts/wheel_build.sh
```

Windows:

```powershell
powershell -File scripts/wheel_build.ps1
```

输出：`dist/*.whl`、`dist/*.tar.gz`

发布前请确认 `pyproject.toml` 中的 `orcakit-harness-agent`、`harness-gateway` 等依赖已发布到 PyPI（`[tool.uv.sources]` 仅对 uv 本地开发生效，pip/PyPI 不读取）。

---

## 平台说明

- **macOS / Linux**：`install.sh` 支持自动安装 uv、创建 venv、可选 Playwright 系统依赖（`browser` extra）。检测到系统已装 Chrome/Chromium 时会跳过 Playwright Chromium 下载。
- **Windows**：使用 `install.ps1` 或 `install.bat`；PTY 终端、飞书 bot creator 等非阻塞 stdout 等功能在 Windows 上受限（见下方兼容性分析）。

完整跨平台兼容性分析见项目文档或 PR 说明。
