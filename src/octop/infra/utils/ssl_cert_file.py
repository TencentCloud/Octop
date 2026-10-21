"""Default ``SSL_CERT_FILE`` to certifi's CA bundle where the OS store is used."""

from __future__ import annotations

import os
import platform


def ensure_ssl_cert_file() -> None:
    """Point ``SSL_CERT_FILE`` at certifi's CA bundle on macOS/Windows.

    ``httpcore2`` (the OpenAI SDK's HTTP transport) verifies TLS chains via
    ``truststore`` — i.e. the OS keychain — on Darwin/Windows. The keychain
    rejects some otherwise-valid chains (e.g. ``api.kimi.com`` via RapidSSL)
    with errSSLBadCert, while certifi verifies them fine. ``httpcore2`` honors
    ``SSL_CERT_FILE`` with ``ssl.create_default_context`` instead, so model
    API calls keep working. A user-provided ``SSL_CERT_FILE`` always wins.
    """
    if platform.system() not in ("Windows", "Darwin"):
        return
    if os.environ.get("SSL_CERT_FILE"):
        return
    try:
        import certifi
    except ImportError:
        return
    os.environ["SSL_CERT_FILE"] = certifi.where()
