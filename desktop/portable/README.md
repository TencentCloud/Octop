# Octop 绿色便携包（多平台）

解压即用：内置便携 CPython + Octop 及依赖，通过 `start.sh` / `start.bat` 启动。  
**不依赖**系统 Python，也**不包含** Wails / 桌面壳——用浏览器打开 Dashboard。  
首启走上游正常 setup wizard（本目录**不含** OOB / UI 裁剪）。

## 与上游解耦

本能力全部落在：

- `desktop/portable/**`（脚本 / 模板 / 本目录 Makefile）
- `.github/workflows/octop-portable.yml`（多平台 CI）
- 根 `.gitignore` 一行 `/green`（忽略构建产物）
- `tests/unit/test_green_launch.py`（launch.py PATH / addsitedir）

**不修改** `src/`、`dashboard/`、`pyproject.toml`、`uv.lock`、根 `Makefile`。  
合并上游时只需留意上述路径；日常用：

```bash
make -f desktop/portable/Makefile green
```

依赖版本必须以仓库根目录 `uv.lock` 为准：`package.sh` 使用
`uv export --frozen`，出包后跑 `desktop/portable/verify_imports.py`
校验关键包 pin 与 import（含 `langchain-openai` / `langchain-core` 配对），
避免「同安装、不同环境」因版本错配或原生扩展加载失败而偶发报错。
平台 overrides（`darwin-amd64` / `windows-arm64` 的 `cryptography==46.x`）
会一并传入校验，避免与 lock 中的 49.x 误报不一致。

## 产物布局

公开文件名：`Octop-portable-<plat>-<version>.zip`。zip 内目录仍是：

```
Octop-<plat>/
  runtime/       # python-build-standalone
  packages/      # Octop + 依赖（site-packages，可搬迁）
  launch.py      # 启动引导（site.addsitedir / Windows pywin32）
  start.sh       # macOS / Linux
  start.bat      # Windows
  README.txt
  data/          # 首次运行自动创建（用户数据）
```

支持平台：`darwin-arm64` `darwin-amd64` `linux-amd64` `linux-arm64` `windows-amd64` `windows-arm64`。

## 构建（在仓库根目录）

需已安装：`uv`、`curl`、`zip`（可选）、Node（编前端）。

```bash
# 一键：当前主机平台（前端 + 便携 CPython + zip）
make -f desktop/portable/Makefile green

# 或分步：
make build-frontend                  # 上游已有目标
bash desktop/portable/bootstrap-runtime.sh
bash desktop/portable/package.sh
```

本地一键重建（nvm 24）：

```bash
bash desktop/portable/rebuild.sh
```

交叉组装其它平台时，**带 C 扩展的包**必须在目标 ABI 上构建：

| 目标 | 推荐方式 |
|------|----------|
| 当前主机 | `make -f desktop/portable/Makefile green` |
| Linux（从 macOS/Windows） | `make -f desktop/portable/Makefile green-linux` |
| Windows | 在 Windows / CI 上执行同上 `green` |

### 离线包

```bash
bash desktop/portable/vendor-wheels.sh          # 按当前 uv.lock 预取 wheel
OCTOP_GREEN_OFFLINE=1 bash desktop/portable/package.sh
```

离线缓存必须来自**当前分支**的 `uv.lock`，不要复用旧分叉的 wheel 目录。

### macOS Intel（`darwin-amd64`）注意

锁定的 `cryptography` 49.x **不再发布** macOS x86_64 / universal2 wheel。若允许从 sdist 编译，会链到构建机 Homebrew 的 `/usr/local/opt/openssl@3`，用户机缺库即启动失败。

绿包脚本已做：

1. `darwin-amd64` 覆盖钉死 `cryptography==46.0.3`（仍有 `macosx_*_universal2` wheel）
2. 全平台 `--only-binary cryptography`，禁止源码编译
3. 打包后 `otool` 检查，拒绝 Homebrew/MacPorts 绝对路径
4. smoke import 覆盖 `cryptography.fernet`

### Windows / pywin32

`mcp` / `docker` 在 win32 上传递依赖 `pywin32`。打包脚本会：

1. 若 `packages/pywin32_system32` 缺失则显式 `uv pip install pywin32`
2. 把 `pywintypes*.dll` / `pythoncom*.dll` 拷到 `runtime/`
3. `launch.py` 用 `site.addsitedir` 处理 `.pth`，并 `os.add_dll_directory`

**不要**设置 `PYTHONPATH=packages`（会跳过 `.pth`，导致 `No module named pywintypes`）。

`windows-arm64` 另排除无 wheel 的 `psycopg-binary` / `sqlite-vec`，并把 `cryptography` 钉到 `46.0.0`（仅该版本提供 `win_arm64` wheel）。

## CI

[`.github/workflows/octop-portable.yml`](../../.github/workflows/octop-portable.yml) 在 6 个 runner 上出 zip：

`linux-amd64` `linux-arm64` `darwin-arm64` `darwin-amd64` `windows-amd64` `windows-arm64`

Actions 使用 GitHub 上游 PBS（`PBS_BASE_URL`），本机构建默认 npmmirror。产物以 `archive: false` 上传，避免 zip-in-zip。

## Electron 壳

壳只消费 `Octop-portable-<plat>-<version>.zip`（zip 内仍是 `Octop-<plat>/`），不要把绿包编进 asar。步骤见
[`AGENT_ELECTRON_INTEGRATION.md`](AGENT_ELECTRON_INTEGRATION.md)。
