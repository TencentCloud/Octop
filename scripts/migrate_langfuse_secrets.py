#!/usr/bin/env python3
"""一次性迁移：`secrets` 表里的明文凭据 ⇒ Fernet 密文（`langfuse_defect` 修复的配套步骤）。

★ 为什么需要它：写侧改为密文后，**存量明文行读不回来**（读侧 fail-closed）⇒ 迁移是
  **升级的一部分**，不是可选项。
★ 不可逆：密文 ⇒ 明文没有回退路径 ⇒ **迁移前必须先备份 `secrets` 全表**（本脚本自动做）。

设计约束（逐条 · 与 `team/2026-09-29-214748/PLAN.md` §3 一致）
  ① **唯一判定**「明文 / 密文」= `Fernet.decrypt` **成功** / `InvalidToken`
     ⇒ ★ `gAAAAA` 前缀**只作快筛**（仅用于「密钥缺失时的保守拒绝」），长度不作判定。
  ② **幂等**：再跑时 `try-decrypt` 成功即跳过；中断（事务回滚）后可直接重跑。
  ③ **单事务**：全部 `UPDATE` 在同一事务内（**禁逐行提交**），事务内自检
     「不可解密行数 = 0」⇒ 非 0 **抛错并整批回滚**（★ 禁跳过失败行 —— 跳过会被行数对照掩盖）。
  ④ **序依赖**：生成 `langfuse_fernet` 之前先查「是否已有依赖该密钥的密文」；
     有 ⇒ **拒绝静默生成**（否则旧密文永久不可解）；生成前后各记一次**密钥指纹**（只记指纹）。
  ⑤ **自举键白名单**（`jwt` / `connector_fernet` / `sso_fernet` / `langfuse_fernet`）**不进迁移面**。
  ⑥ **迁移后 `wal_checkpoint(TRUNCATE)`**：明文可能残留在 `-wal`（连接池常驻 ⇒ 残留窗口 = 整个运行期）。
  ⑦ **不打印任何凭据值**：只打印键名 / 行数 / 类型 / 长度 / 密钥指纹（sha256 前 12 位）。
  ⑧ **备份文件权限 = `0600`**（与真实库一致）：备份含【迁移前的明文凭据 + 主密钥行】⇒
     先以 `0o600` 独占创建（无 0644 窗口），收尾再 `chmod` 兜底；运行输出打印实际权限。

★ 备份文件的处置（`SL-7` · 逐字）
  · **保留位置** = 运行输出里的那一条路径（默认 `<库目录>/<库名>.secrets-backup-<时间戳>.db`）。
  · **权限** = `0600`（★ 脚本强制 · 运行输出会回显实测值）。
  · ★★ **请【人工按凭据处置】**：它**就是一份明文凭据副本**（含 `jwt` / `connector_fernet` /
    `sso_fernet` 三把主密钥）⇒ **不要**进版本库 / 云盘 / 目录级同步；确认迁移成功且无需回滚后
    **请自行删除**（★ 本脚本**不会**代删 —— 删除时机由人决定）。

★ 备份位置的风险（`SL-8` · 逐字）
  · ★ 默认把备份放在**与库同目录**（同盘同权限面）⇒ ★ **目录级同步 / 快照 / 备份会把明文副本一起扩散**
    （★ 该目录常被整目录同步 ⇒ 明文出了原暴露面）。
  · ★ 处置：改用 **`--backup-dir <受限目录>`**（建议不同盘 / 不在同步面的目录）；本脚本**不代建目录**。

本脚本**不覆盖**（如实声明 · `SL-4` / `SL-5`）
  · 历史**备份 / 归档**里已有的明文 —— 本批**不迁移备份**；
  · `providers.api_key` / `voice_providers.api_key` / `storage_backends.access_key` · `secret_key`
    三类明文列 —— 本批**不动** ⇒ ★ 凭据纪律仍只守住 **1/4**（**不是**「加密即安全」：
    密钥与密文**同库同表**，库/备份到手即可解密 ⇒ 增益只是**缩小暴露面**）。

范围限制（如实声明）
  · ★ 只支持 **SQLite**（`--db` 指向 `octop.db`）；PostgreSQL 部署**不在本脚本覆盖内**（会明确报错退出）。
  · ★ 需要 `cryptography` ⇒ 用仓库解释器：`.venv/bin/python scripts/migrate_langfuse_secrets.py …`
    （系统 `python3` 可能没有该依赖；缺依赖时本脚本以 `exit 2` 明确报错，不会静默空跑）。

用法
  .venv/bin/python scripts/migrate_langfuse_secrets.py --db ~/.octop/octop.db --dry-run
  .venv/bin/python scripts/migrate_langfuse_secrets.py --db ~/.octop/octop.db

退出码
  0 = 成功（含「无事可做」）· 1 = 拒绝 / 失败（未写库，或已整批回滚）· 2 = 用法或环境错误
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
import sys
import time
from pathlib import Path

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:  # pragma: no cover - 环境问题（缺依赖 ⇒ 不得静默空跑）
    print(
        "★ 缺少依赖 cryptography ⇒ 请用仓库解释器：.venv/bin/python scripts/migrate_langfuse_secrets.py",
        file=sys.stderr,
    )
    raise SystemExit(2) from None

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_USAGE = 2

# ★ 自举键白名单（不进迁移面）
BOOTSTRAP_KEYS = ("jwt", "connector_fernet", "sso_fernet", "langfuse_fernet")
# ★ 本批新增的专用密钥行（与 connector_fernet / sso_fernet 同级）
FERNET_KEY = "langfuse_fernet"
# ★ 本批缺陷行：langfuse 凭据
CREDENTIAL_KEY = "langfuse_secret_key"
# ★ 「该行是否已是密文」的判定键（唯一判定 = try-decrypt）
KNOWN_FERNET_KEYS = ("connector_fernet", "sso_fernet", "langfuse_fernet")
# ★ 快筛形态（不作判定）
TOKEN_PREFIX = b"gAAAAA"


class Refused(Exception):
    """★ 拒绝执行 / 自检失败（fail-closed）—— 不写库，或整批回滚。"""


def _fingerprint(value: bytes | None) -> str:
    """★ 密钥指纹（只记指纹 · 不记值）：`sha256` 前 12 位。"""
    if value is None:
        return "absent"
    return "sha256:" + hashlib.sha256(value).hexdigest()[:12]


def _as_bytes(value: object) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    raise Refused(f"secrets 行值类型不认识（{type(value).__name__}）⇒ 拒绝继续")


def _connect(db_path: Path, *, read_only: bool = False) -> sqlite3.Connection:
    """★ `read_only` 用 SQLite `mode=ro` URI（`dry-run` 的结构性保证：写会被拒）。"""
    if read_only:
        try:
            con = sqlite3.connect(
                db_path.resolve().as_uri() + "?mode=ro", uri=True, isolation_level=None
            )
        except sqlite3.OperationalError as exc:
            print(
                f"★ dry-run 只读打开失败（{type(exc).__name__}）⇒ 退化为普通连接但只发 SELECT",
                file=sys.stderr,
            )
            con = sqlite3.connect(str(db_path), isolation_level=None)
    else:
        con = sqlite3.connect(str(db_path), isolation_level=None)
    con.execute("PRAGMA busy_timeout = 5000")
    return con


def _has_secrets_table(con: sqlite3.Connection) -> bool:
    row = con.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'secrets'"
    ).fetchone()
    return row is not None


def _secrets_rows(con: sqlite3.Connection) -> list[tuple[str, object]]:
    return [(str(r[0]), r[1]) for r in con.execute("SELECT k, v FROM secrets ORDER BY k")]


def _fernets(rows: list[tuple[str, object]]) -> dict[str, Fernet]:
    """★ 已存在的已知 Fernet 键（用于「该行是否已是密文」的唯一判定）。"""
    out: dict[str, Fernet] = {}
    present = dict(rows)
    for name in KNOWN_FERNET_KEYS:
        if name not in present:
            continue
        try:
            out[name] = Fernet(_as_bytes(present[name]))
        except (TypeError, ValueError) as exc:
            raise Refused(
                f"secrets 行 k={name} 不是合法 Fernet 密钥（{type(exc).__name__}）⇒ 拒绝继续"
            ) from None
    return out


def _owner(fernets: dict[str, Fernet], value: bytes) -> str | None:
    """★ 唯一判定：可被某个已知密钥解密 ⇒ 返回该键名；否则 `None`。"""
    for name, fernet in fernets.items():
        try:
            fernet.decrypt(value)
        except (InvalidToken, TypeError, ValueError):
            continue
        return name
    return None


def _classify(
    rows: list[tuple[str, object]], fernets: dict[str, Fernet]
) -> tuple[list[str], list[tuple[str, str]], list[str], list[str]]:
    """⇒ (待迁移明文键名, 已是密文键名+归属键, 孤立密文键名, 白名单跳过键名)。"""
    plaintext: list[str] = []
    ciphertext: list[tuple[str, str]] = []
    stranded: list[str] = []
    skipped: list[str] = []
    for key, value in rows:
        if key in BOOTSTRAP_KEYS:
            skipped.append(key)
            continue
        raw = _as_bytes(value)
        owner = _owner(fernets, raw)
        if owner is not None:
            ciphertext.append((key, owner))
            continue
        if raw.startswith(TOKEN_PREFIX):
            # ★ 快筛命中而「已知键都解不开」⇒ 保守拒绝（不得当成明文重加密）。
            stranded.append(key)
            continue
        plaintext.append(key)
    return plaintext, ciphertext, stranded, skipped


def _mode_str(path: Path) -> str:
    """★ 打印文件权限（8 进制 · 如 `0600`）；★ 非 POSIX 平台可能不适用。"""
    try:
        return format(path.stat().st_mode & 0o777, "04o")
    except OSError:
        return "unknown"


def _backup_secrets(con: sqlite3.Connection, backup: Path) -> int:
    """★ 备份 `secrets` 全表（含键行）到独立 SQLite 文件 ⇒ 返回备份行数。

    ★★ 备份含【迁移前的明文凭据】+ 主密钥行 ⇒ 权限必须 **0600**（与真实库一致）：
    先以 `0o600` **独占创建**（闭合「创建 → chmod」之间那个 0644 窗口），收尾再 `chmod` 兜底。
    """
    if backup.exists():
        raise Refused(f"备份路径已存在，拒绝覆盖：{backup}")
    # ★ 第一步：用 0600 把文件建出来（umask 只能收紧、不能放宽 ⇒ 期间不存在宽松权限窗口）
    handle = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(handle)
    dest = sqlite3.connect(str(backup), isolation_level=None)
    try:
        dest.execute(
            "CREATE TABLE secrets ("
            "  k TEXT PRIMARY KEY,"
            "  v BLOB NOT NULL,"
            "  created_at INTEGER NOT NULL,"
            "  rotated_at INTEGER"
            ")"
        )
        rows = con.execute("SELECT k, v, created_at, rotated_at FROM secrets").fetchall()
        dest.execute("BEGIN IMMEDIATE")
        dest.executemany(
            "INSERT INTO secrets(k, v, created_at, rotated_at) VALUES (?, ?, ?, ?)",
            [tuple(r) for r in rows],
        )
        dest.execute("COMMIT")
    finally:
        dest.close()
    # ★ 第二步：收尾 chmod 兜底（含 SQLite 重建文件的情况）
    os.chmod(backup, 0o600)
    return len(rows)


def _run(args: argparse.Namespace) -> int:
    db_path = Path(args.db).expanduser()
    if not db_path.is_file():
        print(f"★ 用法/环境错误：数据库文件不存在：{db_path}", file=sys.stderr)
        return EXIT_USAGE

    con = _connect(db_path, read_only=args.dry_run)
    try:
        if not _has_secrets_table(con):
            print(
                f"★ 用法/环境错误：{db_path} 里没有 secrets 表（不是 Octop 的 SQLite 库？）",
                file=sys.stderr,
            )
            return EXIT_USAGE

        rows = _secrets_rows(con)
        fernets = _fernets(rows)
        key_before = dict(rows).get(FERNET_KEY)
        plaintext, ciphertext, stranded, skipped = _classify(rows, fernets)

        print(f"★ 目标库：{db_path}")
        print(
            f"★ 扫描 secrets = {len(rows)} 行 · 白名单跳过 = {len(skipped)}"
            f" · 已是密文 = {len(ciphertext)} · 待迁移 = {len(plaintext)}"
        )
        print(f"★ 密钥 k={FERNET_KEY} 指纹（迁移前）= {_fingerprint(key_before)}")
        if ciphertext:
            print(f"★ 已是密文（原样不动）：{', '.join(f'{k}@{owner}' for k, owner in ciphertext)}")

        if stranded:
            raise Refused(
                "检出 Fernet 形态的密文而行对应密钥行缺失 ⇒ 拒绝静默生成新钥（SL-2）"
                f"（受影响键名：{', '.join(sorted(stranded))}）"
            )

        if not plaintext:
            print("★ 迁移面 = 0 行 ⇒ 无事可做（幂等：已迁移或无需迁移）· 未写库")
            return EXIT_OK

        if args.dry_run:
            print(f"★ dry-run：待迁移键名 = {', '.join(sorted(plaintext))}")
            print("★ dry-run：不写库 / 不备份 / 不 checkpoint")
            return EXIT_OK

        stamp = time.strftime("%Y%m%dT%H%M%S")
        default_location = args.backup is None and args.backup_dir is None
        if args.backup:
            backup_path = Path(args.backup).expanduser()
        elif args.backup_dir:
            backup_dir = Path(args.backup_dir).expanduser()
            if not backup_dir.is_dir():
                raise Refused(f"--backup-dir 不是已存在的目录：{backup_dir}（本脚本不代建目录）")
            backup_path = backup_dir / f"{db_path.name}.secrets-backup-{stamp}.db"
        else:
            backup_path = db_path.parent / f"{db_path.name}.secrets-backup-{stamp}.db"
        backed_up = _backup_secrets(con, backup_path)
        print(
            f"★ 备份（不可逆操作的前置条件）：{backup_path} · secrets 全表 {backed_up} 行"
            f" · 权限 {_mode_str(backup_path)}"
        )
        print(
            "★ 备份处置（SL-7）：保留在上述路径 · 权限 0600 · ★ 它是一份【明文凭据副本】"
            "（含 jwt / connector_fernet / sso_fernet 主密钥）"
        )
        print("   ⇒ ★ 请【人工按凭据处置】：不进版本库 / 云盘 / 目录级同步；确认无需回滚后自行删除（脚本不代删）")
        if default_location:
            print(
                "★ 风险声明（SL-8）：默认备份与库【同目录同权限面】⇒ 目录级同步 / 快照 / 备份会把明文副本"
                "一起扩散；★ 若该目录会被同步，请改用 --backup-dir <受限目录>（建议不同盘 / 不在同步面）"
            )

        now = int(time.time())
        migrated: list[str] = []
        try:
            con.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as exc:
            raise Refused(f"无法开启事务：{exc}") from None
        try:
            key_row = con.execute("SELECT v FROM secrets WHERE k = ?", (FERNET_KEY,)).fetchone()
            if key_row is None:
                new_key = Fernet.generate_key()
                con.execute(
                    "INSERT INTO secrets(k, v, created_at) VALUES (?, ?, ?)",
                    (FERNET_KEY, new_key, now),
                )
                fernet = Fernet(new_key)
                print("★ 键行缺失且无孤立密文 ⇒ 生成专用密钥 k=" + FERNET_KEY)
            else:
                fernet = Fernet(_as_bytes(key_row[0]))

            for name in sorted(plaintext):
                # ★ 事务内 SELECT → UPDATE（迁移与在线写入竞态：写侧只写密文）
                row = con.execute("SELECT v FROM secrets WHERE k = ?", (name,)).fetchone()
                if row is None:
                    continue
                value = _as_bytes(row[0])
                if _owner({FERNET_KEY: fernet}, value) is not None:
                    continue  # ★ 唯一判定 = try-decrypt（幂等：已迁移行跳过）
                token = fernet.encrypt(value)
                con.execute(
                    "UPDATE secrets SET v = ?, rotated_at = ? WHERE k = ?", (token, now, name)
                )
                migrated.append(name)

            # ★ 事务内自检：不可解密行数 = 0（非 0 ⇒ 抛错 ⇒ 整批回滚）
            fernets_after = dict(fernets)
            fernets_after[FERNET_KEY] = fernet
            undecryptable = [
                key
                for key, value in _secrets_rows(con)
                if key not in BOOTSTRAP_KEYS and _owner(fernets_after, _as_bytes(value)) is None
            ]
            if undecryptable:
                raise Refused(
                    "事务内自检失败：不可解密行 = %d（%s）⇒ 整批回滚，禁跳过失败行"
                    % (len(undecryptable), ", ".join(sorted(undecryptable)))
                )
            con.execute("COMMIT")
        except BaseException:
            try:
                con.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise

        after_rows = _secrets_rows(con)
        print(f"★ 已迁移 = {len(migrated)} 行（{'、'.join(migrated) or '无'}）")
        print(f"★ 行数对照：迁移前 {len(rows)} 行 ⇒ 迁移后 {len(after_rows)} 行")
        print(f"★ 密钥 k={FERNET_KEY} 指纹（迁移后）= {_fingerprint(dict(after_rows).get(FERNET_KEY))}")
        print("★ 事务内自检：不可解密行 = 0")
    finally:
        con.close()

    if not args.dry_run:
        con2 = _connect(db_path)
        try:
            busy, log_frames, checkpointed = con2.execute(
                "PRAGMA wal_checkpoint(TRUNCATE)"
            ).fetchone()
        finally:
            con2.close()
        print(f"★ wal_checkpoint(TRUNCATE) ⇒ busy={busy} · log={log_frames} · checkpointed={checkpointed}")
        if busy:
            print(
                "★ 拒绝收尾：-wal 未能截断 ⇒ 明文可能仍残留在 WAL（有其它连接占用）"
                " ⇒ 请停服后重跑本脚本（数据已迁移并提交 · 幂等可续）",
                file=sys.stderr,
            )
            return EXIT_REFUSED
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Octop：把 secrets 表里的明文凭据一次性迁移为 Fernet 密文（幂等 · 单事务）",
        epilog=(
            "★ 只支持 SQLite · 需 cryptography（用 .venv/bin/python 跑）· 迁移前自动备份 secrets 全表\n"
            "★ 备份文件权限 = 0600（含明文凭据 + 主密钥行）\n"
            "★ 备份处置（SL-7）：保留在运行输出给出的路径 · ★ 请人工按凭据处置（不进版本库/云盘/目录级同步，"
            "确认无需回滚后自行删除）\n"
            "★ 备份位置风险（SL-8）：默认与库同目录（同盘同权限面）⇒ 目录级同步会扩散明文副本 ⇒ "
            "建议 --backup-dir <不同盘 / 不在同步面的受限目录>"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--db", required=True, help="SQLite 库路径（如 ~/.octop/octop.db）")
    parser.add_argument("--dry-run", action="store_true", help="只报告计划，不写库 / 不备份 / 不 checkpoint")
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--backup", default=None, help="备份文件路径（默认：与库同目录 + 时间戳）")
    where.add_argument(
        "--backup-dir",
        default=None,
        help="★ 备份目录（推荐：与库【不同盘 / 不在同步面】的受限目录；须已存在，文件名 = <库名>.secrets-backup-<时间戳>.db）",
    )
    args = parser.parse_args(argv)
    try:
        return _run(args)
    except Refused as exc:
        print(f"★ 拒绝执行（未写库 / 已回滚）：{exc}", file=sys.stderr)
        return EXIT_REFUSED
    except sqlite3.Error as exc:
        print(f"★ SQLite 错误：{type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_REFUSED


if __name__ == "__main__":
    raise SystemExit(main())
