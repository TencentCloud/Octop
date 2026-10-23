# 信创老机器（麒麟 glibc 2.23 等）离线部署指南

> 适用对象：银河麒麟 ARM 定制机（glibc 2.23）、CentOS 7 系 x86 机（glibc 2.17）
> 等 glibc 基线较老的信创政务机。新机器（Ubuntu 20.04+/较新麒麟）用 standard 包即可，无需读本篇。

## 一、怎么判断用哪个包

安装前在目标机执行：

```bash
ldd --version | head -1
```

| 本机 glibc | 用哪个包 |
|---|---|
| ≥ 2.28 | `agentbuddy-offline-<platform>-cp312.tar.gz`（standard） |
| 2.17 ~ 2.27 | `agentbuddy-offline-legacy-<platform>-cp312.tar.gz`（legacy） |
| < 2.17 | 均不可用（manylinux2014 基线是 2.17，需先升级系统 glibc） |

选错也没关系：`install-offline.sh` 会先做 glibc 预检，本机版本低于包内 wheel
基线时直接报错并提示改用 legacy 包，不会装一半才失败。

## 二、legacy 包与 standard 包的差异

| | standard | legacy |
|---|---|---|
| wheel 标签档 | manylinux2014 + 2_17/2_26/2_28 四档 | 仅 manylinux2014 |
| 第三方版本 | 按 `uv.lock` 原样 | 部分包降级到有 2014 档的版本（见 `scripts/offline_bundle.sh` 内 `LEGACY_PINNED` 替换表） |
| PostgreSQL 模式 | 可用 | 可用（psycopg 钉 3.2.x 兼容版，未砍） |
| 附带 SQLite 兼容库 | 有 | 有 |
| 安装脚本 | 同一个 `install-offline.sh` | 同一个 |

legacy 替换表当前降级的包（版本以表内为准，随锁定树演进复核）：
numpy、pillow、greenlet、tiktoken、argon2-cffi(-bindings)、cryptography、lxml、
psycopg 系。均为小版本降级，API 兼容；若运行时撞到个别 API 差异，优先怀疑这几个。

## 三、安装

```bash
# tar.gz 与 SHA256SUMS-legacy.txt 在同一 Release 资产里,放到同一目录再解包
# (install-offline.sh 会在 offline-legacy/ 的上一层找 SHA256SUMS-legacy.txt 做校验)
tar -xzf agentbuddy-offline-legacy-<platform>-cp312.tar.gz
bash scripts/install-offline.sh <解包目录>/offline-legacy/
```

脚本自动处理三件事：

1. **glibc 预检**（见上，硬拦截）；
2. **SQLite 兼容**：octop 迁移 SQL 使用窗口函数（`ROW_NUMBER() OVER`）与
   `RETURNING`，需要系统 SQLite ≥ 3.35。老机器的系统 SQLite 往往 < 3.25，
   脚本检测到后会启用包内预编译的 `libsqlite3.so.0`（在 manylinux2014 容器中
   构建，glibc 2.17 基线），把 venv 的 `octop` 入口包成 wrapper 注入
   `LD_LIBRARY_PATH`——前台 `octop run` 与 systemd 常驻（ExecStart 指向同一
   bin）统一生效，不动系统文件、无需手工 `systemctl edit`。
3. **零出网安装**：`pip --no-index --find-links` 全量安装 5 个主包 + 全部依赖。

## 四、兜底：现场编译 SQLite（无预编译 .so 时）

若包内没有本机架构的 `libsqlite3.so.0`（如安装脚本提示），且目标机有 gcc：

```bash
# 包内自带源码与脚本
cp <解包目录>/offline-legacy/sqlite3/sqlite-amalgamation*.zip ~/
cp <解包目录>/offline-legacy/sqlite3/build_sqlite.sh ~/
bash ~/build_sqlite.sh          # 产物: ~/agentbuddy/sqlite3-new/libsqlite3.so.0
# 然后重跑 install-offline.sh,它会检测到产物并自动包 wrapper
```

无 gcc 时需要另找编译机（同架构 ARM/x86 Linux，glibc ≤ 2.23 环境）编译后拷入。

## 五、历史背景（2026-10 现场修复记录摘要）

legacy 包源于一次麒麟 ARM（glibc 2.23）现场部署的三个坑，现均已在包内解决：

1. **glibc 基线**：锁定树部分第三方包（numpy 2.5.x、argon2-cffi-bindings 26.x
   等）只有 manylinux_2_24+ 档 wheel，glibc 2.23 无法安装 → legacy 替换表降级；
2. **系统 SQLite 过老**：`octop init` 迁移报 `near "OVER": syntax error` →
   预编译 .so + wrapper 自动注入；
3. **包与清单不一致**（bundle 放了 mcp 2.x / anthropic 2.x，代码按 1.x API 写，
   启动即崩）→ CI 闸门做"清单 vs 实际 wheel"逐项比对，防复发。

原始修复记录见仓库 `kylin-fix/`（未入库，现场档案）。
