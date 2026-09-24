"""Synchronous LDAP client (service bind, user lookup, user bind)."""

from __future__ import annotations

import contextlib
import ssl
from collections.abc import Sequence
from dataclasses import dataclass

from ldap3 import ANONYMOUS, NONE, SIMPLE, SUBTREE, Connection, Entry, Server, Tls
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars

from octop.infra.auth.ldap.config import LdapConfig

_RESULT_SUCCESS = 0
_RESULT_INVALID_CREDENTIALS = 49
_PROBE_SIZE_LIMIT = 5


class LdapUnavailable(RuntimeError):
    """The directory could not be reached, or the service bind was refused."""


@dataclass(frozen=True)
class LdapIdentity:
    """A directory entry that successfully bound with its own credentials."""

    dn: str
    username: str
    email: str | None
    display_name: str | None
    groups: tuple[str, ...]

    def is_member_of(self, groups: Sequence[str]) -> bool:
        """True when the entry belongs to any of the configured group names or DNs."""
        if not groups:
            return False
        normalized = {normalize_group_name(item) for item in self.groups}
        return any(normalize_group_name(item) in normalized for item in groups)


def normalize_group_name(value: str) -> str:
    """Compare ``cn=admin,ou=groups,dc=x`` and ``admin`` as the same group."""
    head = value.split(",", 1)[0]
    _, _, tail = head.partition("=")
    return (tail or head).strip().lower()


@dataclass(frozen=True)
class LdapProbeResult:
    """Outcome of a configuration test, with a machine-readable reason."""

    ok: bool
    code: str
    detail: str


class LdapClient:
    """Thin wrapper around ``ldap3`` for the search-then-bind login pattern."""

    def __init__(self, config: LdapConfig, bind_password: str) -> None:
        self._config = config
        self._bind_password = bind_password

    # ----- public API -----

    def authenticate(self, username: str, password: str) -> LdapIdentity | None:
        """Return the identity when the directory accepts the credentials.

        ``None`` means "wrong credentials or no such user"; the caller decides how
        to report that. Connection or service-bind problems raise
        :class:`LdapUnavailable` so they are never mistaken for a bad password.
        """
        if not username or not password:
            return None
        identity = self._lookup(username)
        if identity is None:
            return None
        return identity if self._verify_password(identity.dn, password) else None

    def test(self) -> LdapProbeResult:
        """Bind with the service account and probe ``user_base_dn``."""
        conn: Connection | None = None
        try:
            conn = self._open_bound(self._config.bind_dn, self._bind_password)
        except LdapUnavailable as exc:
            return LdapProbeResult(False, "unreachable", str(exc))
        if conn is None:
            return LdapProbeResult(
                False,
                "bind_failed",
                "the service account rejected the configured bind DN or password",
            )
        try:
            found = conn.search(
                self._config.user_base_dn,
                "(objectClass=*)",
                search_scope=SUBTREE,
                attributes=[self._config.username_attribute],
                size_limit=_PROBE_SIZE_LIMIT,
            )
            if not found:
                return LdapProbeResult(False, "search_failed", self._result_message(conn))
            return LdapProbeResult(True, "ok", self._config.server_url)
        except LDAPException as exc:
            return LdapProbeResult(False, "search_failed", str(exc))
        finally:
            conn.unbind()

    def _lookup(self, username: str) -> LdapIdentity | None:
        """Find the directory entry for ``username`` using the service bind."""
        conn = self._open_bound(self._config.bind_dn, self._bind_password)
        if conn is None:
            raise LdapUnavailable("the service account rejected the configured bind DN or password")
        try:
            ldap_filter = self._config.user_filter.replace(
                "{username}", escape_filter_chars(username)
            )
            attributes = [
                self._config.username_attribute,
                self._config.email_attribute,
                self._config.display_name_attribute,
                self._config.group_attribute,
            ]
            try:
                if not conn.search(
                    self._config.user_base_dn,
                    ldap_filter,
                    search_scope=SUBTREE,
                    attributes=attributes,
                ):
                    return None
            except LDAPException as exc:
                raise LdapUnavailable(f"user search failed: {exc}") from exc
            entries = list(conn.entries)
            if not entries:
                return None
            entry = self._pick_entry(entries, username)
            return LdapIdentity(
                dn=str(entry.entry_dn),
                username=self._attribute(entry, self._config.username_attribute) or username,
                email=self._attribute(entry, self._config.email_attribute),
                display_name=self._attribute(entry, self._config.display_name_attribute),
                groups=tuple(self._attributes(entry, self._config.group_attribute)),
            )
        finally:
            conn.unbind()

    def _verify_password(self, dn: str, password: str) -> bool:
        try:
            conn = self._open_bound(dn, password)
        except LdapUnavailable:
            return False
        if conn is None:
            return False
        conn.unbind()
        return True

    # ----- connection plumbing -----

    def _server(self) -> Server:
        tls = Tls(validate=ssl.CERT_REQUIRED if self._config.verify_tls else ssl.CERT_NONE)
        return Server(
            host=self._config.host,
            port=self._config.port,
            use_ssl=self._config.use_ssl,
            tls=tls,
            get_info=NONE,
            connect_timeout=self._config.timeout_seconds,
        )

    def _open_bound(self, dn: str, password: str) -> Connection | None:
        """Open (and optionally StartTLS) a connection, then bind.

        Returns ``None`` when the directory rejected the credentials; raises
        :class:`LdapUnavailable` when the server is unreachable or the protocol
        exchange failed.
        """
        anonymous = not dn.strip()
        conn = Connection(
            self._server(),
            user=None if anonymous else dn,
            password=None if anonymous else password,
            authentication=ANONYMOUS if anonymous else SIMPLE,
            auto_bind=False,
            raise_exceptions=False,
            receive_timeout=self._config.timeout_seconds,
        )
        try:
            # ``open()`` returns ``None`` on success and raises
            # ``LDAPSocketOpenError`` when the socket cannot be established.
            conn.open()
            if conn.closed:
                raise LdapUnavailable("could not open a connection to the LDAP server")
            if self._config.start_tls and not self._config.use_ssl and not conn.start_tls():
                raise LdapUnavailable(f"StartTLS failed: {self._result_message(conn)}")
            if not conn.bind():
                if self._result_code(conn) == _RESULT_INVALID_CREDENTIALS:
                    conn.unbind()
                    return None
                raise LdapUnavailable(f"bind failed: {self._result_message(conn)}")
        except LDAPException as exc:
            self._safe_unbind(conn)
            raise LdapUnavailable(str(exc)) from exc
        except LdapUnavailable:
            self._safe_unbind(conn)
            raise
        return conn

    @staticmethod
    def _safe_unbind(conn: Connection) -> None:
        # Releasing a broken socket must never mask the original failure.
        with contextlib.suppress(Exception):
            conn.unbind()

    @staticmethod
    def _result_code(conn: Connection) -> int:
        result = conn.result
        value = result.get("result") if isinstance(result, dict) else None
        return value if isinstance(value, int) else -1

    @staticmethod
    def _result_message(conn: Connection) -> str:
        result = conn.result
        if not isinstance(result, dict):
            return "unknown LDAP error"
        code = result.get("result")
        if code == _RESULT_SUCCESS:
            return "unknown LDAP error"
        description = result.get("description") or "error"
        message = result.get("message")
        return f"{description} ({code})" + (f": {message}" if message else "")

    # ----- entry helpers -----

    def _pick_entry(self, entries: list[Entry], username: str) -> Entry:
        """Prefer the entry whose username attribute matches exactly."""
        attribute = self._config.username_attribute
        for entry in entries:
            value = self._attribute(entry, attribute)
            if value is not None and value.lower() == username.lower():
                return entry
        return entries[0]

    def _attributes(self, entry: Entry, attribute: str) -> list[str]:
        try:
            values = entry[attribute].values
        except (KeyError, LDAPException, TypeError):
            return []
        if not values:
            return []
        return [str(item) for item in values]

    def _attribute(self, entry: Entry, attribute: str) -> str | None:
        values = self._attributes(entry, attribute)
        return values[0] if values else None
