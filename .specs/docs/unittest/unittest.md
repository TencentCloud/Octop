# 单元测试规范（环境 / 生成 / 运行调试）

> 让任意成员（或 AI Agent）能在本地把单元测试**装得起、写得对、跑得通、出错查得到**。
> 三段式结构：① 环境搭建 / ② 生成规范 / ③ 运行调试。
>
> **若仓库存在项目 unittest 规则文件**（`.codebuddy/rules/unittest_*.md`、`.cursor/rules/unittest_*.md`、`.windsurf/rules/` 等，见 `CODEBUDDY.md` 文末「项目既有规则」），那是权威来源：本文以摘录 + 链接形式承接，不另起冲突；调整本文必须同步 rules。

> Source: <信息源：tests/ 目录 + Makefile / package.json / pyproject.toml + CI 配置 + 项目规则文件（unittest_*.md 等）>
> Last-verified: <YYYY-MM-DD>

---

## 一、环境搭建与依赖安装

### 0. 推荐技术选型

| 类别 | 推荐 | 备选 |
|------|------|------|
| 解释器 / 运行时管理 | **pyenv**（Python）/ nvm（Node）/ rustup / sdkman | asdf |
| 虚拟环境隔离 | **venv**（Python 标准库自带）| poetry / pipenv / conda |
| 测试框架 | <填项目实际：pytest / pytest-bdd / unittest / vitest / jest / go test / cargo test …> | — |
| Mock / Stub | <填：unittest.mock / pytest-mock / sinon / mockito …> | — |
| 覆盖率 | <填：coverage.py + pytest-cov / c8 / nyc / go cover …> | — |

> **为什么 pyenv + venv（Python 项目）**：
> - `pyenv` 解决"项目所需 Python 版本与系统 Python 不一致"；可同机多版本共存
> - `venv` 是 Python 自带虚拟环境，零额外依赖、与 IDE 兼容性最好、产物路径稳定（默认 `./venv/`）
> - 二者组合 = 「精确锁定 Python 版本」+「依赖隔离在仓库目录内」

### 1. 前置依赖检查清单（先查再装）

> 任何一项已满足就跳过对应安装步骤，不要无脑 `rm -rf venv` 重建。

```bash
# (1) 解释器版本管理器
command -v pyenv >/dev/null && echo "pyenv OK" || echo "需要安装 pyenv"

# (2) 项目所需的解释器版本
pyenv versions | grep -E "^[ *] *<X.Y.Z>" >/dev/null && echo "Python <X.Y.Z> OK" || echo "需要安装"

# (3) 虚拟环境
test -x venv/bin/python && venv/bin/python --version | grep -F "<X.Y>" \
  && echo "venv OK" || echo "venv 缺失或版本不对"

# (4) 关键依赖
venv/bin/python -c "import <pkg1>, <pkg2>, <pkg3>" 2>/dev/null \
  && echo "deps OK" || echo "缺少依赖"

# (5) 项目特有产物（locale / proto 编译 / native 模块等，按需）
test -f <产物路径> && echo "extra OK" || echo "需要构建"
```

判断逻辑：5 项全过 → 直接执行测试；某项失败 → **只修复失败项**，不要全量重建（除非解释器版本不对）。

### 2. 分步安装（仅在上面检查失败时执行）

#### Step 1: 安装 pyenv

```bash
# macOS
brew install pyenv

# Linux
curl https://pyenv.run | bash

# 写入 shell 配置（仅首次）
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"
```

#### Step 2: 安装项目所需 Python 版本

```bash
PY_VERSION="<X.Y.Z>"            # ← 与项目根 .python-version / pyproject.toml 一致
pyenv install $PY_VERSION --skip-existing
pyenv local $PY_VERSION         # 在仓库根写入 .python-version
```

#### Step 3: 创建 venv 并安装依赖

```bash
python3 -m venv venv
venv/bin/python -m pip install -U pip setuptools wheel
venv/bin/python -m pip install -r requirements.txt
# 或：venv/bin/python -m pip install -e ".[dev,test]"
```

#### Step 4: 编译 / 准备运行期产物（按项目实际）

> 例：i18n locale、protobuf 生成文件、native 扩展、测试 fixture 数据下载等。

#### Step 5: 一键脚本（如有）

> 项目通常会提供 `make test-setup` / `bash scripts/setup_test.sh` 等。**优先用一键脚本**，本节是其语义说明。

### 3. 环境变量与配置

| 变量 | 用途 | 示例 |
|------|------|------|
| <例：`<APP>_ETC_PATH`> | 加载测试专用配置目录 | `<APP>_ETC_PATH=./tests/conf` |
| <例：`PYTHONPATH`> | 注入项目根 / 模块路径 | `PYTHONPATH=.` |
| <例：`<MOCK_FLAG>`> | 强制启用本地 mock，禁止真实外部调用 | `<MOCK_FLAG>=1` |

> 测试相关环境变量必须**在测试 runner 内部设置**（如 `pytest.ini` / `conftest.py` / `Makefile` target），避免成员手动 export。

---

## 二、单元测试生成规范

### 1. 通用强制条款（红线）

| # | 红线 |
|---|------|
| 1 | 不修改被测业务代码以让测试通过 |
| 2 | 不调用真实外部服务 / 真实写库 |
| 3 | 不在测试间共享可变状态 / 不依赖执行顺序 |
| 4 | 不删除已有测试代码，只追加 |
| 5 | 新 Mock / step / fixture 只能追加到对应文件**尾部** |
| 6 | 不硬编码环境信息（域名 / 路径 / 凭证） |

### 2. 测试类型与适用场景

| 测试类型 | 适用 | 文件命名 / 位置 | 风格 |
|---------|------|----------------|------|
| 函数级单元测试 | 单个 / 少量函数小改 | `tests/<module>/test_<fname>.py` 或 `<Action>_test.py` | <填> |
| 大文件批量函数测试 | 同一文件多函数需测 | 同上，按类组织 | <填> |
| 接口 / 入口级测试 | 端到端入口 entry 流程 | `tests/<module>/<Action>_test.py` + `.feature`（BDD 时）| <填> |

### 3. 文件命名硬约束

- 测试文件名**与被测代码文件 1:1 对应**（不附加函数名后缀）
- 同一被测文件的多个函数 / 多个场景测试**统一放进同一个 `<被测文件>_test.py`**；新增 → 追加，不新建并列文件
- BDD 项目：`.feature` 与 `_test.py` 文件名严格成对

### 4. Mock 策略

| 类别 | 默认策略 |
|------|---------|
| 项目内函数 | 默认允许真实调用（utils / 校验器 / 纯函数）|
| 外部依赖（DB / HTTP / MQ / 文件系统 / 第三方 SDK）| 必须 Mock |
| 可观测性（日志 / 监控 / 指标上报）| 不 Mock |
| 时间 / 随机 | 用 `freezegun` / `monkeypatch` 显式控制 |
| 全局常量 | 用 `monkeypatch` / `try-finally` 自动恢复 |

### 5. 用例设计自检清单

> 详见 `plans/_template/04-ut.md` § 用例设计清单（输入 / 状态 / 依赖 / 幂等四维度全覆盖）。

### 6. 与项目 rules 承接

- 若仓库存在项目 unittest 规则文件（`.codebuddy/rules/unittest_*.md`、`.cursor/rules/` 等）：本文 §二 改为指向该 rules 锚点，不重复写
- 否则使用本文规范作为最低基线

---

## 三、运行与调试规范

### 1. 标准执行命令

```bash
# 全量
<填：sh run_test.sh / make test / npm test / go test ./... / cargo test>

# 指定文件 / 目录
<填：sh run_test.sh tests/<module>/<file>_test.py>

# 关键字匹配
<填：sh run_test.sh -k "<pattern>">

# 仅重跑失败用例
<填：sh run_test.sh --lf>

# 带覆盖率
<填：sh run_test.sh --cov=<module>>

# 按标记 / tag
<填：sh run_test.sh -m <marker>>
```

> **必须**与 CI 中跑的命令一致；本地能过、CI 失败的多半是环境变量 / 路径差异。

### 2. 测试 runner 通常做了什么（如有 wrapper 脚本）

> 例：`run_test.sh` 通常负责：
> 1. 设置必要环境变量（`<APP>_ETC_PATH` 等）
> 2. 清理上次运行残留（`__pycache__` / `.pytest_cache` 等）
> 3. patch 已知第三方库 bug（幂等）
> 4. 调用 `venv/bin/<runner> "$@"`，把命令行参数透传

### 3. 调试套路

| 现象 | 优先排查 | 排查命令 |
|------|---------|---------|
| 全量失败 | 环境 / 依赖 / locale / 配置 | 走 § 一的 5 项检查清单 |
| 单文件失败 | 隔离复现 | `<runner> tests/<path>/file -vvs` |
| 偶发失败 | 顺序污染 / 全局状态 | `<runner> --lf` + 检查 fixture scope |
| 覆盖率不达标 | 看未覆盖行 | `coverage report -m` / 看 HTML 报告 |
| import 报错 | venv 损坏 / 路径错 | `venv/bin/python -c "import <pkg>"` |
| Mock 没生效 | patch 路径错 | "在哪 import 就 patch 哪"（`module.<被 import 名>`）|

### 4. 不要 / 慎用

| 项 | 原因 |
|----|------|
| 修改 `conftest.py` / `pytest.ini` / `run_test.sh` 等共享配置 | 影响全员，需走 PR 评审 |
| 启用并行（如 `-n auto`）| 多数旧测试架构不支持 xdist 并行，会引入偶发失败 |
| 在测试中 `print` 大量调试信息 | 改用 `-vvs` + `caplog` |
| 关闭某些用例（`@skip`）以"让 CI 过"| 必须在 04-ut.md 备注原因 + 跟踪修复 |

### 5. 测试产物

| 产物 | 路径 | 用途 |
|------|------|------|
| HTML 测试报告 | `<填：unittest_report.html / report.html>` | 浏览器查看 |
| 覆盖率 XML | `<填：coverage.xml>` | CI / SonarQube 摄取 |
| 覆盖率 HTML | `<填：htmlcov/>` | 本地交互式查看 |
| 终端摘要 | stdout | 通过 / 失败 / 未覆盖行 |

### 6. CI 集成

- CI 中跑测试必须**与本地命令一致**（仅可加 `--junitxml` / `--cov-report` 等输出参数）
- 失败必须阻塞合入
- 覆盖率回退（如低于 baseline N%）应触发警告或阻塞，由项目自定阈值
