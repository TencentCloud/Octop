"""Synchronous LDAP client (service bind, user lookup, user bind)."""

from __future__ import annotations

import contextlib
import logging
import ssl
from collections.abc import Sequence
from dataclasses import dataclass

from ldap3 import ANONYMOUS, NONE, SIMPLE, SUBTREE, Connection, Entry, Server, Tls
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars

from octop.infra.auth.ldap.config import LdapConfig

logger = logging.getLogger(__name__)

_RESULT_SUCCESS = 0
#: A truncated search is still a successful search; the server just stopped early.
_RESULT_SIZE_LIMIT_EXCEEDED = 4
_RESULT_INVALID_CREDENTIALS = 49
_PROBE_SIZE_LIMIT = 5
#: Small, but comfortably wider than "the exact match plus a couple of decoys":
#: too tight and the exact match could fall outside the returned window.
_SEARCH_SIZE_LIMIT = 10
#: Identity-key candidates, in the order a directory is likely to expose them.
_SUBJECT_ATTRIBUTE_CANDIDATES = ("entryUUID", "objectGUID")
#: Group membership is read whole (truncation would silently drop group grants),
#: so cap it well above any realistic membership count.
_GROUP_SEARCH_SIZE_LIMIT = 256


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
    #: Directory-stable identity key (``entryUUID`` / ``objectGUID``). Falls back
    #: to the DN when the directory does not expose the configured attribute.
    subject: str = ""
    subject_is_dn_fallback: bool = False

    def is_member_of(self, groups: Sequence[str]) -> bool:
        """True when the entry belongs to any of the configured groups.

        A configured value containing ``=`` is treated as a full DN and must match
        the whole entry DN, so ``cn=admin,ou=staff,…`` never matches a same-named
        group in another OU. A bare name is compared against the RDN value only.
        """
        if not groups:
            return False
        member_dns = {normalize_dn(item) for item in self.groups if item}
        member_names = {rdn_value(item) for item in self.groups if item}
        for wanted in groups:
            candidate = wanted.strip()
            if not candidate:
                continue
            if "=" in candidate:
                if normalize_dn(candidate) in member_dns:
                    return True
            elif rdn_value(candidate) in member_names:
                return True
        return False


def normalize_dn(value: str) -> str:
    """Case- and whitespace-insensitive DN for equality comparison."""
    return ",".join(part.strip() for part in value.split(",") if part.strip()).lower()


def rdn_value(value: str) -> str:
    """Return the value of the first RDN: ``cn=admin,ou=x`` → ``admin``."""
    head = value.split(",", 1)[0]
    _, _, tail = head.partition("=")
    return (tail or head).strip().lower()


@dataclass(frozen=True)
class LdapProbeResult:
    """Outcome of a configuration test, with a machine-readable reason."""

    ok: bool
    code: str
    detail: str
    #: Which directory-stable identity attribute the probe found, if any. Lets the
    #: admin pick ``entryUUID`` (OpenLDAP) or ``objectGUID`` (AD) instead of
    #: guessing and silently falling back to the entry DN.
    detected_subject_attribute: str | None = None

    def suggestion(self) -> str | None:
        """The configured identity key, when the probe found a usable one."""
        return self.detected_subject_attribute


def _hex_if_binary(value: object) -> str:
    """``objectGUID`` comes back as bytes on AD; hex keeps it printable and stable."""
    if isinstance(value, bytes):
        return value.hex()
    return str(value)


class LdapClient:
    """Thin wrapper around ``ldap3`` for the search-then-bind login pattern."""

    def __init__(self, config: LdapConfig, bind_password: str) -> None:
        self._config = config
        self._bind_password = bind_password

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
            conn.search(
                self._config.user_base_dn,
                "(objectClass=*)",
                search_scope=SUBTREE,
                attributes=[
                    self._config.username_attribute,
                    *_SUBJECT_ATTRIBUTE_CANDIDATES,
                ],
                size_limit=_PROBE_SIZE_LIMIT,
            )
            if not self._search_succeeded(conn):
                return LdapProbeResult(False, "search_failed", self._result_message(conn))
            # An empty base DN is a valid (if useless) configuration; the bind is
            # what this probe verifies.
            return LdapProbeResult(
                True,
                "ok",
                self._config.server_url,
                detected_subject_attribute=self._detect_subject_attribute(conn),
            )
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
            group_attribute = self._config.group_attribute
            attributes = [
                self._config.username_attribute,
                self._config.email_attribute,
                self._config.display_name_attribute,
                self._config.subject_attribute,
            ]
            if not self._config.group_search and group_attribute:
                attributes.append(group_attribute)
            try:
                conn.search(
                    self._config.user_base_dn,
                    ldap_filter,
                    search_scope=SUBTREE,
                    attributes=attributes,
                    size_limit=_SEARCH_SIZE_LIMIT,
                )
            except LDAPException as exc:
                raise LdapUnavailable(f"user search failed: {exc}") from exc
            if not self._search_succeeded(conn):
                # A bad base DN or lost read rights must not read as "wrong
                # password": that would leak a credential verdict and spend the
                # caller's brute-force budget on an operational fault.
                raise LdapUnavailable(f"user search failed: {self._result_message(conn)}")
            entry = self._pick_entry(list(conn.entries), username)
            if entry is None:
                return None
            dn = str(entry.entry_dn)
            resolved_username = self._attribute(entry, self._config.username_attribute) or username
            subject = self._attribute(entry, self._config.subject_attribute)
            groups = self._resolve_groups(conn, dn, resolved_username, entry)
            return LdapIdentity(
                dn=dn,
                username=resolved_username,
                email=self._attribute(entry, self._config.email_attribute),
                display_name=self._attribute(entry, self._config.display_name_attribute),
                groups=groups,
                subject=subject or dn,
                subject_is_dn_fallback=not subject,
            )
        finally:
            conn.unbind()

    def _resolve_groups(
        self, conn: Connection, dn: str, username: str, entry: Entry
    ) -> tuple[str, ...]:
        """Collect the user's groups, either from ``memberOf`` or by group search."""
        if self._config.group_search:
            return self._search_groups(conn, dn, username)
        attribute = self._config.group_attribute
        return tuple(self._attributes(entry, attribute)) if attribute else ()

    def _search_groups(self, conn: Connection, dn: str, username: str) -> tuple[str, ...]:
        """Directories without the ``memberOf`` overlay store members on the group.

        The member value is not standardised: ``member``/``uniqueMember`` hold the
        member's DN, while ``memberUid`` (the classic OpenLDAP ``posixGroup``
        layout) holds the bare username. Matching both in one OR covers either
        convention without adding a knob to configure — both are exact equality
        matches, so a stray hit is not a realistic risk.
        """
        member_attribute = self._config.group_member_attribute.strip() or "member"
        candidates = [escape_filter_chars(dn)]
        if username and username != dn:
            candidates.append(escape_filter_chars(username))
        clauses = "".join(f"({member_attribute}={value})" for value in candidates)
        ldap_filter = f"(|{clauses})" if len(candidates) > 1 else clauses
        try:
            conn.search(
                self._config.effective_group_search_base,
                ldap_filter,
                search_scope=SUBTREE,
                attributes=["cn"],
                size_limit=_GROUP_SEARCH_SIZE_LIMIT,
            )
        except LDAPException as exc:
            raise LdapUnavailable(f"group search failed: {exc}") from exc
        if not self._search_succeeded(conn):
            raise LdapUnavailable(f"group search failed: {self._result_message(conn)}")
        # Zero matches is a normal outcome (the user is in no group under this
        # base), not a failure — ldap3 reports both as a ``False`` return.
        return tuple(str(item.entry_dn) for item in conn.entries)

    def _detect_subject_attribute(self, conn: Connection) -> str | None:
        """Which identity-key attribute the sampled entries actually carry."""
        for attribute in _SUBJECT_ATTRIBUTE_CANDIDATES:
            for entry in conn.entries:
                if self._attribute(entry, attribute):
                    return attribute
        return None

    def _search_succeeded(self, conn: Connection) -> bool:
        """Whether the last search actually ran.

        ``ldap3`` returns ``False`` both for a broken search and for a successful
        one that matched nothing, so the result code decides — never the boolean.
        """
        return self._result_code(conn) in (_RESULT_SUCCESS, _RESULT_SIZE_LIMIT_EXCEEDED)

    def _verify_password(self, dn: str, password: str) -> bool:
        """Bind as the user. Connection problems propagate as :class:`LdapUnavailable`.

        Swallowing them here would report a directory outage as a wrong password.
        """
        conn = self._open_bound(dn, password)
        if conn is None:
            return False
        conn.unbind()
        return True

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
            # Following referrals could hand the bind password to another server.
            auto_referrals=False,
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

    def _pick_entry(self, entries: list[Entry], username: str) -> Entry | None:
        """Return the one entry this login may safely be verified against.

        "Exact" means the input equals an attribute that is documented as a login
        identifier — the configured username attribute (``uid`` /
        ``sAMAccountName``) or the email attribute. Anything else returns ``None``:
        a fuzzy hit would bind somebody else's DN with the supplied password, and
        with a filter like ``(uid={username}*)`` typing ``al`` would silently sign
        the caller in as ``alice``.
        """
        wanted = username.strip().lower()
        if not wanted:
            return None
        identifiers = [self._config.username_attribute]
        if self._config.email_attribute:
            identifiers.append(self._config.email_attribute)
        matched = [
            entry
            for entry in entries
            if any(
                (value := self._attribute(entry, attribute)) is not None and value.lower() == wanted
                for attribute in identifiers
            )
        ]
        if len(matched) == 1:
            return matched[0]
        if entries:
            logger.info(
                "LDAP lookup for %r matched %d entries with %d exact identifier match(es); refusing",
                username,
                len(entries),
                len(matched),
            )
        return None

    def _attributes(self, entry: Entry, attribute: str) -> list[str]:
        try:
            values = entry[attribute].values
        except (KeyError, LDAPException, TypeError):
            return []
        if not values:
            return []
        return [_hex_if_binary(item) for item in values]

    def _attribute(self, entry: Entry, attribute: str) -> str | None:
        values = self._attributes(entry, attribute)
        return values[0] if values else None
