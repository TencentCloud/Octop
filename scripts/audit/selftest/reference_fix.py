"""★ `AC-2` 参照修复：把 `providers` / `voice_providers` / `storage_backends` 三张表的
**6 个写入点**的凭据值改为【已验证的加密助手】调用，并把 3 处 f-string `UPDATE` 改成**静态 SQL**。

★★ 这不是可直接上线的产品补丁（**语义等价性未验证** · 无效字段会被写成 `NULL`）——
  它只是【判据验收】用的参照物：证明 `AUD-S6` **修好可变绿**（`AC-2`），
  并作为 `ATK2`..`ATK5` 的「已修」基线。★ 真修复 = 下一批卡 `T-PLAINTEXT-COLUMNS-ENCRYPT`。
★ 为什么必须把 `UPDATE` 也改成静态 SQL：硬要求② 规定「动态 SQL ⇒ `UNKNOWN`」⇒
  只加密值而 SQL 仍是 f-string ⇒ 判据恒 `UNKNOWN` ⇒ `AC-2` 不可能转绿（`PLAN:58` 的「前者更好」）。
"""
import pathlib

ENC = "encrypt_secret(SecretRepo(self._db), %s) if %s else None"
IMPORTS = (
    "from octop.infra.auth.sso.crypto import encrypt_secret\n"
    "from octop.infra.db.repos.secrets import SecretRepo\n"
)

REPLACEMENTS = {
    "src/octop/infra/db/repos/providers.py": [
        ("from octop.infra.db.pool import DatabasePool\n",
         "from octop.infra.db.pool import DatabasePool\n" + IMPORTS),
        ("                (name, kind, base_url, api_key, extra_json, models_json, note, ts, ts),",
         "                (name, kind, base_url, " + ENC % ("api_key", "api_key")
         + ", extra_json, models_json, note, ts, ts),"),
        ("""            conn.execute(f"UPDATE providers SET {', '.join(fields)} WHERE id = ?", params)""",
         """            conn.execute(
                "UPDATE providers SET kind = ?, base_url = ?, api_key = ?, extra_json = ?, "
                "models_json = ?, note = ?, enabled = ?, updated_at = ? WHERE id = ?",
                (
                    kind,
                    base_url,
                    """ + ENC % ("api_key", "api_key") + """,
                    extra_json,
                    models_json,
                    note,
                    bool_int(enabled) if enabled is not None else None,
                    now_ts(),
                    provider_id,
                ),
            )"""),
    ],
    "src/octop/infra/db/repos/voice_providers.py": [
        ("from octop.infra.db.pool import DatabasePool\n",
         "from octop.infra.db.pool import DatabasePool\n" + IMPORTS),
        ("                (name, kind, capability, base_url, api_key, extra_json, note, ts, ts),",
         "                (name, kind, capability, base_url, " + ENC % ("api_key", "api_key")
         + ", extra_json, note, ts, ts),"),
        ("""            conn.execute(f"UPDATE voice_providers SET {', '.join(fields)} WHERE id = ?", params)""",
         """            conn.execute(
                "UPDATE voice_providers SET kind = ?, capability = ?, base_url = ?, "
                "api_key = ?, extra_json = ?, note = ?, enabled = ?, updated_at = ? WHERE id = ?",
                (
                    kind,
                    capability,
                    base_url,
                    """ + ENC % ("api_key", "api_key") + """,
                    extra_json,
                    note,
                    bool_int(enabled) if enabled is not None else None,
                    now_ts(),
                    provider_id,
                ),
            )"""),
    ],
    "src/octop/infra/db/repos/backends.py": [
        ("from octop.infra.db.pool import DatabasePool\n",
         "from octop.infra.db.pool import DatabasePool\n" + IMPORTS),
        ("""                    access_key,
                    secret_key,""",
         "                    " + ENC % ("access_key", "access_key") + ",\n"
         "                    " + ENC % ("secret_key", "secret_key") + ","),
        ("""            conn.execute(
                f"UPDATE storage_backends SET {', '.join(fields)} WHERE id = ?",
                params,
            )""",
         """            conn.execute(
                "UPDATE storage_backends SET name = ?, kind = ?, endpoint = ?, access_key = ?, "
                "secret_key = ?, bucket = ?, region = ?, config_json = ?, note = ?, enabled = ?, "
                "updated_at = ? WHERE id = ?",
                (
                    name,
                    kind,
                    endpoint,
                    """ + ENC % ("access_key", "access_key") + """,
                    """ + ENC % ("secret_key", "secret_key") + """,
                    bucket,
                    region,
                    config_json,
                    note,
                    bool_int(enabled) if enabled is not None else None,
                    now_ts(),
                    backend_id,
                ),
            )"""),
    ],
}


def already_encrypted(tree):
    """★ L 批后仓库**自带**加密（`secret_codec.encrypt_value` 在写入点）⇒ 参照修复退化为 no-op。"""
    for rel in REPLACEMENTS:
        try:
            text = (pathlib.Path(tree) / rel).read_text(encoding="utf-8")
        except OSError:
            return False
        if "encrypt_value(" not in text:
            return False
    return True


def apply(tree):
    """★ 对副本树应用参照修复（★ 每处旧文本必须【恰好命中 1 次】，否则抛错 ⇒ 不静默半修）。

    ★★ `L` 批后本仓的写入点**已自带** `encrypt_value` ⇒ ★ 本函数退化为 **no-op**（返回原因串），
    不再改写任何文件（★ 否则会把已加密的值再包一层/或锚点失配抛错）。
    """
    if already_encrypted(tree):
        return ["（no-op）L 批后写入点已自带 `secret_codec.encrypt_value` ⇒ 参照修复无需应用"]
    for rel, pairs in REPLACEMENTS.items():
        path = pathlib.Path(tree) / rel
        text = path.read_text(encoding="utf-8")
        for old, new in pairs:
            hits = text.count(old)
            if hits != 1:
                raise AssertionError("%s：旧文本命中 %d 次（期望 1）⇒ 参照修复失败" % (rel, hits))
            text = text.replace(old, new)
        path.write_text(text, encoding="utf-8")
    return sorted(REPLACEMENTS)
