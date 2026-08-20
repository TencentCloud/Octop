# 安装 TCCLI

**首选：装进 Octop 自带的 Python 虚拟环境（venv）**——与 Octop 运行环境一致、版本可控、不污染系统 Python、无需 sudo。Octop 专家的 Agent 命令执行时继承该环境。

**定位 Octop venv**（通过 octop 主进程的工作目录）：

```sh
OCTOP_PID=$(pgrep -f '\.venv/bin/octop run' | head -1)
OCTOP_ROOT=$([ -n "$OCTOP_PID" ] && readlink -f /proc/$OCTOP_PID/cwd || echo /workspace/octop)
```

**安装方式（按优先级）**：

```sh
# 方式一（推荐）：uv 装进 Octop venv
uv pip install --python "$OCTOP_ROOT/.venv/bin/python3" tccli

# 方式二：无 uv 时，用 venv 自带 pip（需先 ensurepip）
"$OCTOP_ROOT/.venv/bin/python3" -m ensurepip --upgrade
"$OCTOP_ROOT/.venv/bin/python3" -m pip install tccli

# 方式三：系统 pip（桌面/CLI 独立使用 tccli 时）
pip install tccli

# 若从 3.0.252.3 以下版本升级，需先卸载再装：
# pip uninstall tccli jmespath && pip install tccli
```

升级同理，加 `-U`：`uv pip install --python "$OCTOP_ROOT/.venv/bin/python3" -U tccli`

其他系统安装方式：

```sh
# macOS Homebrew
brew tap tencentcloud/tccli
brew install tccli
# 更新：brew upgrade tccli

# 源码安装
# git clone https://github.com/TencentCloud/tencentcloud-cli.git && cd tencentcloud-cli && python setup.py install
```

验证安装：

```sh
"$OCTOP_ROOT/.venv/bin/tccli" --version   # venv 内验证
tccli --version                            # 系统安装验证
```
