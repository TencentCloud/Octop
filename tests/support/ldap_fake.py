"""In-memory LDAP directory used as a test double for the network boundary.

The fake replaces ``ldap3.Connection`` so every layer above the socket
(:class:`octop.infra.auth.ldap.client.LdapClient`, the service, and the HTTP
routes) runs as production code. Live coverage against a real directory lives in
``tests/live/test_ldap_live.py``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ldap3.core.exceptions import LDAPException, LDAPSocketOpenError

_FILTER_ATTRIBUTE = re.compile(r"\(([A-Za-z][A-Za-z0-9.-]*)=([^()]*)\)")


@dataclass
class FakeLdapUser:
    """One directory entry with a password that can be bound."""

    dn: str
    password: str
    username: str
    email: str | None = None
    display_name: str | None = None
    groups: tuple[str, ...] = ()
    #: Extra attributes by name, e.g. ``{"entryUUID": ["a1b2…"]}``.
    extra: dict[str, list[str]] = field(default_factory=dict)

    def attributes(self, name: str) -> list[str]:
        lowered = name.lower()
        if lowered == "objectclass":
            # Real entries always carry objectClass, and probes search on it.
            return ["top", "person", "organizationalPerson", "inetOrgPerson"]
        if lowered in ("uid", "samaccountname"):
            return [self.username]
        if lowered == "mail":
            return [self.email] if self.email else []
        if lowered == "cn":
            return [self.display_name] if self.display_name else []
        if lowered == "memberof":
            return list(self.groups)
        for key, values in self.extra.items():
            if key.lower() == lowered:
                return list(values)
        return []

    def matches(self, filters: list[tuple[str, str]]) -> bool:
        """True when any ``(attr=value)`` clause matches, mirroring an ``(|…)`` filter."""
        for name, expected in filters:
            if any(_value_matches(value, expected) for value in self.attributes(name)):
                return True
        return False


@dataclass
class FakeLdapGroup:
    """A group entry, used by the group-search membership mode."""

    dn: str
    name: str
    members: tuple[str, ...] = ()
    member_attribute: str = "member"

    def attributes(self, name: str) -> list[str]:
        lowered = name.lower()
        if lowered == "objectclass":
            return ["top", "posixGroup"]
        if lowered == "cn":
            return [self.name]
        if lowered == self.member_attribute.lower():
            return list(self.members)
        return []

    def matches(self, filters: list[tuple[str, str]]) -> bool:
        for name, expected in filters:
            if any(_value_matches(value, expected) for value in self.attributes(name)):
                return True
        return False


def _value_matches(value: str, pattern: str) -> bool:
    """LDAP equality/substring match: ``*`` in the pattern is a wildcard."""
    if "*" not in pattern:
        return value.lower() == pattern.lower()
    regex = "^" + ".*".join(re.escape(part) for part in pattern.split("*")) + "$"
    return re.match(regex, value, re.IGNORECASE) is not None


class FakeLdapEntry:
    def __init__(self, dn: str, values: dict[str, list[str]]) -> None:
        self.entry_dn = dn
        self._values = values

    def __getitem__(self, name: str) -> Any:
        for key, value in self._values.items():
            if key.lower() == name.lower():
                return _FakeAttribute(value)
        raise KeyError(name)


class _FakeAttribute:
    def __init__(self, values: list[str]) -> None:
        self.values = list(values)


class FakeLdapDirectory:
    """A scriptable directory that records every bind and search."""

    def __init__(
        self,
        *,
        bind_dn: str = "",
        bind_password: str = "",
        users: list[FakeLdapUser] | None = None,
        groups: list[FakeLdapGroup] | None = None,
    ) -> None:
        self.bind_dn = bind_dn
        self.bind_password = bind_password
        self.users: list[FakeLdapUser] = list(users or [])
        self.groups: list[FakeLdapGroup] = list(groups or [])
        self.reachable = True
        self.start_tls_supported = True
        self.search_allowed = True
        self.binds: list[tuple[str, str]] = []
        self.searches: list[tuple[str, str]] = []
        self.size_limits: list[int] = []
        self.connections: list[FakeLdapConnection] = []
        self.opened = 0
        self.unbound = 0
        #: When set, that many further opens succeed before every open fails.
        self._healthy_opens_left: int | None = None

    def add(self, user: FakeLdapUser) -> FakeLdapUser:
        self.users.append(user)
        return user

    def add_group(self, group: FakeLdapGroup) -> FakeLdapGroup:
        self.groups.append(group)
        return group

    def outage_after_opens(self, healthy_opens: int) -> None:
        """Let ``healthy_opens`` connections through, then refuse every socket.

        Models "the service bind worked but the user bind could not connect".
        """
        self._healthy_opens_left = healthy_opens

    def install(self, monkeypatch: Any) -> FakeLdapDirectory:
        """Patch every ``ldap3.Connection`` created by the LDAP client."""
        monkeypatch.setattr("octop.infra.auth.ldap.client.Connection", self._connection)
        return self

    def _connection(self, server: Any, **kwargs: Any) -> FakeLdapConnection:
        conn = FakeLdapConnection(self, server, **kwargs)
        self.connections.append(conn)
        return conn

    def searchable(self) -> list[FakeLdapUser | FakeLdapGroup]:
        return [*self.users, *self.groups]

    def _authenticate(self, user: str | None, password: str | None) -> tuple[bool, int]:
        """Return ``(accepted, ldap_result_code)``."""
        if not user:
            return True, 0
        if user == self.bind_dn:
            accepted = password == self.bind_password
            return accepted, 0 if accepted else 49
        entry = next((item for item in self.users if item.dn == user), None)
        if entry is None:
            return False, 49
        accepted = password == entry.password
        return accepted, 0 if accepted else 49


class FakeLdapConnection:
    """Minimal ``ldap3.Connection`` surface: open, StartTLS, bind, search, unbind.

    ``open()`` mirrors ldap3 2.x exactly: it returns ``None`` on success, flips
    ``closed`` to ``False``, and raises ``LDAPSocketOpenError`` when the socket
    cannot be established.
    """

    def __init__(self, directory: FakeLdapDirectory, server: Any, **kwargs: Any) -> None:
        self._directory = directory
        self.server = server
        self.user = kwargs.get("user")
        self.password = kwargs.get("password")
        self.auto_referrals = kwargs.get("auto_referrals")
        self.result: dict[str, Any] | None = None
        self.closed = True
        self._bound = False
        self._entries: list[FakeLdapEntry] = []

    def open(self) -> None:
        directory = self._directory
        directory.opened += 1
        if not directory.reachable:
            raise LDAPSocketOpenError("unable to open socket")
        if directory._healthy_opens_left is not None:
            if directory._healthy_opens_left <= 0:
                raise LDAPSocketOpenError("unable to open socket")
            directory._healthy_opens_left -= 1
        self.closed = False

    def start_tls(self) -> bool:
        if not self._directory.start_tls_supported:
            self.result = {"result": 2, "description": "protocolError"}
            return False
        return True

    def bind(self) -> bool:
        self._directory.binds.append((self.user or "", self.password or ""))
        accepted, code = self._directory._authenticate(self.user, self.password)
        if accepted:
            self._bound = True
            self.result = {"result": 0, "description": "success"}
            return True
        self.result = {"result": code, "description": "invalidCredentials"}
        return False

    def unbind(self) -> None:
        if self.closed:
            return
        self._directory.unbound += 1
        self.closed = True
        self._bound = False

    @property
    def entries(self) -> list[FakeLdapEntry]:
        if not self._bound:
            raise LDAPException("not bound")
        return list(self._entries)

    def search(
        self,
        search_base: str,
        search_filter: str,
        *,
        search_scope: Any = None,
        attributes: list[str] | None = None,
        size_limit: int = 0,
        **_: Any,
    ) -> bool:
        del search_scope
        self._directory.searches.append((search_base, search_filter))
        if not self._directory.search_allowed:
            self.result = {"result": 50, "description": "insufficientAccessRights"}
            return False
        clauses = _FILTER_ATTRIBUTE.findall(search_filter)
        wanted = list(attributes or [])
        selected: list[FakeLdapUser | FakeLdapGroup] = [
            item
            for item in self._directory.searchable()
            if clauses and item.matches(clauses) and item.dn.endswith(search_base)
        ]
        # A server-side size limit truncates rather than reporting an error.
        truncated = bool(size_limit) and len(selected) > size_limit
        if truncated:
            selected = selected[:size_limit]
        self._entries = [
            FakeLdapEntry(item.dn, {name: item.attributes(name) for name in wanted})
            for item in selected
        ]
        self._directory.size_limits.append(size_limit)
        self.result = {
            "result": 4 if truncated else 0,
            "description": "sizeLimitExceeded" if truncated else "success",
        }
        # ldap3 returns False for a successful search that matched nothing, so a
        # real client must consult ``result`` rather than this value.
        return bool(self._entries)


def fake_user(
    username: str,
    password: str,
    *,
    base: str = "dc=example,dc=org",
    group: str = "users",
    **kwargs: Any,
) -> FakeLdapUser:
    """Build a user entry with glauth's ``uid=<name>,cn=<group>,<base>`` DN shape."""
    return FakeLdapUser(
        dn=f"uid={username},cn={group},{base}",
        password=password,
        username=username,
        **kwargs,
    )


__all__ = ["FakeLdapDirectory", "FakeLdapGroup", "FakeLdapUser", "fake_user"]
