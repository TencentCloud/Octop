"""★ 三类结构化凭据列的存储边界编解码（`providers` / `voice_providers` / `storage_backends`）。

★★ 为什么本模块**自带** Fernet 助手，而不复用 `connectors/crypto.py` / `auth/sso/crypto.py`：
  · `AGENTS.md §5` 硬禁：`infra/db/repos/` → **任何非 DB 的 `infra` 包** ✗；
  · 且那两个模块把**键名硬编码**在自己域内（`connector_fernet` / `sso_fernet`）⇒ 复用即跨域耦合。
★ 本模块落在 `infra/db/` 内：只依赖 `cryptography` + 同包的 `repos/secrets.py`（`SecretRepo`）✓。

★★ 专用键【按域拆】（★ 不得复用 `connector_fernet` / `sso_fernet`）：
  · `providers_fernet` ⇒ `providers.api_key` ∧ `voice_providers.api_key`（同域）
  · `storage_fernet`   ⇒ `storage_backends.access_key` ∧ `.secret_key`
  ★ 理由：**域轮换**会让本三列【永久不可解】（J 批 `FIND-5` 同源裁定）。

★ 序依赖（与 J 批 `SL-2` 同源 · 缺一即缺陷）：
  ① **有密文而键行缺失 ⇒ 【拒绝静默生成】**（`ensure_key` 抛错）—— ★ 唯一防线（否则旧密文永久不可解）；
  ② **读侧【不生成】**（`resolve_key` 只读 · 缺键即抛错）⇒ 读路径不产生写入；
  ③ 写侧 `ensure_key` 才自举（`get_or_create` 首次即生成）。
★★ **存储形态 = Fernet 密文的 base64 文本**（用户裁定 ⓐ · `repair-2`）：★ 两引擎的 `TEXT` 列都能收
  ASCII ✓；★★ **base64 只是【密文的传输编码】· 不是加密** —— 保密性完全来自 Fernet 认证加密。
★ 读侧 fail-closed：★ **绝不** `except: return raw` / `return blob` / 明文兜底 ⇒ 失败**抛错**
  （★ 旧明文行 ⇒ 抛错 ⇒ 必须先跑迁移，这是【部署顺序】的一部分）。
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos.secrets import SecretRepo

PROVIDERS_KEY = "providers_fernet"
STORAGE_KEY = "storage_fernet"
# ★ 本模块管辖的两个专用键（迁移脚本的 `BOOTSTRAP_KEYS` 必须同步纳入）
BOOTSTRAP_KEYS = (PROVIDERS_KEY, STORAGE_KEY)

# ★ 域 → 该键管辖的 (表, 列) 清单（迁移面 / `stranded` 检查 / 数据面抽检共用同一张表）
DOMAINS: dict[str, tuple[tuple[str, str], ...]] = {
    PROVIDERS_KEY: (("providers", "api_key"), ("voice_providers", "api_key")),
    STORAGE_KEY: (("storage_backends", "access_key"), ("storage_backends", "secret_key")),
}

# ★ Fernet token 快筛（**不作判定**：判定 = `Fernet.decrypt` 成功 / `InvalidToken`）
#   ★★ 注意：落库形态 = **base64 文本** ⇒ 快筛要落在【base64 解码之后】的字节上
TOKEN_PREFIX = b"gAAAAA"


# ★★ 存储形态（用户裁定 ⓐ）：`Fernet` token ⇒ **base64 文本**（ASCII）
#   ★ 为什么：SQLite 与 PostgreSQL 的 `TEXT` 列**都能收 ASCII**（原始二进制在 PG 的 TEXT 列会类型不符）
#   ★★ **这不是加密**：base64 只是【密文的传输编码】—— ★ 保密性**完全**来自上一层 Fernet 认证加密；
#      ★ 单独出现 base64（没有 Fernet）**不构成**加密。
def encode_stored(token: bytes) -> str:
    """★ Fernet token ⇒ base64 **文本**（★ 传输编码 · 非加密）。"""
    return base64.urlsafe_b64encode(token).decode("ascii")


def decode_stored(value: bytes | str) -> bytes:
    """★ 落库文本 ⇒ Fernet token（★ 解码失败 ⇒ 抛 `SecretCodecError`，由调用方按「非密文」处理）。"""
    raw = value.encode("ascii", "strict") if isinstance(value, str) else bytes(value)
    try:
        return base64.urlsafe_b64decode(raw)
    except (ValueError, TypeError) as exc:
        raise SecretCodecError(f"落库值不是合法 base64 文本（{type(exc).__name__}）") from None


class SecretCodecError(RuntimeError):
    """★ 存储边界失败（fail-closed）：键缺失 / 键不可用 / 值不可解密。"""


@dataclass(frozen=True)
class ColumnRef:
    """★ 一个受管列（`table.column` + 所属专用键）。"""

    key_name: str
    table: str
    column: str

    @property
    def label(self) -> str:
        return f"{self.table}.{self.column}"


def managed_columns() -> tuple[ColumnRef, ...]:
    """★ 全部受管列（迁移 / 抽检 / `stranded` 的唯一清单来源）。"""
    return tuple(
        ColumnRef(key_name, table, column)
        for key_name, pairs in DOMAINS.items()
        for table, column in pairs
    )


def _fernet(key: bytes) -> Fernet:
    try:
        return Fernet(bytes(key))
    except (TypeError, ValueError) as exc:
        raise SecretCodecError(f"专用键不是合法 Fernet 键（{type(exc).__name__}）") from None


def fingerprint(key: bytes | None) -> str:
    """★ 键指纹（`sha256[:12]` · ★ 只记指纹不记值 ⇒ 迁移前后对账用）。"""
    if key is None:
        return "absent"
    return hashlib.sha256(bytes(key)).hexdigest()[:12]


def encrypt_value(key: bytes, plain: str) -> str:
    """★ 写侧纯函数：明文 ⇒ **Fernet 密文的 base64 文本**（★ 可直接落 `TEXT` 列）。

    ★★ 保密性来自 Fernet（认证加密）；★ base64 只是把密文编成 ASCII 的**传输编码**。
    """
    return encode_stored(_fernet(key).encrypt(plain.encode("utf-8")))


def decrypt_value(key: bytes, blob: bytes | str) -> str:
    """★ 读侧纯函数：**base64 文本 ⇒ 解码 ⇒ Fernet 解密 ⇒ 明文**。

    ★ 唯一判定 = `Fernet.decrypt` 成功 / `InvalidToken`（★ **不用**前缀 / 长度判定）·
    ★ 失败【抛错】（fail-closed · **绝不** `except: return raw`）。
    """
    try:
        token = decode_stored(blob)
        return _fernet(key).decrypt(token).decode("utf-8")
    except SecretCodecError:
        raise
    except (InvalidToken, ValueError, UnicodeDecodeError) as exc:
        raise SecretCodecError(
            f"受管列的值不可解密（{type(exc).__name__}）⇒ 拒绝按明文使用；★ 旧明文行必须先跑迁移"
        ) from None


def resolve_key(db: DatabasePool, key_name: str) -> bytes:
    """★ **只读**取专用键：缺失 ⇒ 抛错（★ 读路径**不生成**键 · 不产生写入）。"""
    row = SecretRepo(db).get(key_name)
    if row is None:
        raise SecretCodecError(
            f"专用键行缺失（k={key_name}）⇒ 受管列无法解密；★ 请先跑迁移/写路径自举"
        )
    return bytes(row)


def _scan_table(conn: Any, ref: ColumnRef, sql: str) -> bool:
    """★ 单列快筛（★ SQL 必须是**字面量**：本判据面不引入不透明 SQL 站点）。"""
    try:
        rows = conn.execute(sql).fetchall()
    except Exception:  # noqa: BLE001 - 表/列可能尚未建出（全新库）
        return False
    for row in rows:
        if row[0] is None:
            continue
        if looks_encrypted(row[0]):
            return True
    return False


def _domain_has_ciphertext(db: DatabasePool, key_name: str) -> list[ColumnRef]:
    """★ 该域内是否存在【Fernet 形态】的落库值（★ 无键可 `try-decrypt` ⇒ 快筛 + 保守拒绝）。"""
    hits: list[ColumnRef] = []
    with db.connect() as conn:
        for ref in managed_columns():
            if ref.key_name != key_name:
                continue
            if ref.table == "providers" and ref.column == "api_key":
                found = _scan_table(conn, ref, "SELECT api_key FROM providers")
            elif ref.table == "voice_providers" and ref.column == "api_key":
                found = _scan_table(conn, ref, "SELECT api_key FROM voice_providers")
            elif ref.table == "storage_backends" and ref.column == "access_key":
                found = _scan_table(conn, ref, "SELECT access_key FROM storage_backends")
            elif ref.table == "storage_backends" and ref.column == "secret_key":
                found = _scan_table(conn, ref, "SELECT secret_key FROM storage_backends")
            else:
                found = False
            if found:
                hits.append(ref)
    return hits


def ensure_key(db: DatabasePool, key_name: str) -> bytes:
    """★ **写侧**自举：键存在 ⇒ 复用；缺失 ∧ 无密文 ⇒ 生成；★ 有密文而缺键 ⇒ **拒绝静默生成**。"""
    repo = SecretRepo(db)
    existing = repo.get(key_name)
    if existing is not None:
        return bytes(existing)
    stranded = _domain_has_ciphertext(db, key_name)
    if stranded:
        labels = " · ".join(ref.label for ref in stranded)
        raise SecretCodecError(
            f"检测到 Fernet 形态的落库值但专用键行缺失（k={key_name} · 受影响列 = {labels}）⇒ "
            "★ 拒绝静默生成新钥（否则既有密文永久不可解）"
        )
    return bytes(repo.get_or_create(key_name, Fernet.generate_key))


def get_key_for_selfcheck() -> bytes:
    """★ F-L1(b) 自检用临时键（★ 不落库 · 仅供往返自检）。"""
    return Fernet.generate_key()


def looks_encrypted(value: object) -> bool:
    """★ 快筛（**不作判定**）：**base64 解码之后**是否为 Fernet token 形态。"""
    raw = value if isinstance(value, bytes) else str(value).encode("utf-8")
    try:
        return base64.urlsafe_b64decode(raw).startswith(TOKEN_PREFIX)
    except (ValueError, TypeError):
        return False


def encode_row_value(key: bytes, value: str | None) -> str | None:
    """★ 写边界助手（`None` 透传 = 写 NULL；非空 ⇒ 加密）。"""
    if value is None:
        return None
    return encrypt_value(key, value)


def decode_row_value(key: bytes, value: bytes | str | None) -> str | None:
    """★ 读边界助手（`None` 透传；非空 ⇒ 解密 · 失败抛错）。"""
    if value is None:
        return None
    return decrypt_value(key, value)


def base64_token(value: bytes) -> str:
    """★ 诊断用（★ 只用于**长度/形态**对账，不用于判定）。"""
    return encode_stored(value)
