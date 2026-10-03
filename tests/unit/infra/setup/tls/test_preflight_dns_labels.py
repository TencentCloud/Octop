"""DNS preflight must degrade a malformed label instead of raising.

``socket.getaddrinfo`` raises ``UnicodeEncodeError`` (an ``UnicodeError``, *not* an
``OSError``) when a domain label cannot be encoded as IDNA -- e.g. a label longer
than 63 characters or an empty label.  ``run_preflight`` only guarded
``socket.gaierror``, so such a domain escaped as an unhandled traceback instead of
the ``dns`` check the result type promises.
"""

from __future__ import annotations

import socket
from unittest.mock import patch

import pytest

from octop.config import OctopConfig
from octop.infra.setup.tls.preflight import run_preflight

_PUBLIC_IP = "1.2.3.4"

# Every entry is a label shape that makes the IDNA encoder raise
# UnicodeEncodeError instead of failing later in the resolver.
_MALFORMED_LABELS = [
    "a" * 64 + ".example.com",  # label longer than 63 chars
    "sub." + "b" * 300 + ".example.com",  # same, on a non-root label
    "a..example.com",  # empty label
]


def _run(domain: str):
    """Run preflight with every other network-touching step stubbed out."""
    with (
        patch("octop.infra.setup.tls.preflight._port_available", return_value=True),
        patch("octop.infra.setup.tls.preflight._fetch_public_ip", return_value=_PUBLIC_IP),
    ):
        return run_preflight(domain, OctopConfig())


def test_malformed_label_does_not_escape_preflight():
    # Sanity check on the premise: these shapes raise UnicodeEncodeError, which is
    # neither an OSError nor a gaierror, so ``except socket.gaierror`` cannot catch it.
    with pytest.raises(UnicodeEncodeError):
        socket.getaddrinfo("a" * 64 + ".example.com", 80, type=socket.SOCK_STREAM)
    assert not issubclass(UnicodeEncodeError, OSError)

    for domain in _MALFORMED_LABELS:
        result = _run(domain)  # must not raise

        assert not result.ok
        assert any(c.id == "dns" and not c.ok for c in result.checks), domain


def test_unresolvable_domain_is_reported_as_a_failed_dns_check():
    # Control group: a well-formed domain that simply does not resolve must keep
    # producing the same "dns failed" check rather than an exception.
    def _boom(*args: object, **kwargs: object) -> set[str]:
        raise socket.gaierror("Name or service not known")

    with patch("octop.infra.setup.tls.preflight._resolve_domain_ips", side_effect=_boom):
        result = _run("nonexistent.invalid")

    assert not result.ok
    assert any(c.id == "dns" and not c.ok for c in result.checks)
