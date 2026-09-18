"""`octop run` — start the FastAPI app in the foreground."""

from __future__ import annotations

import click

from octop.cli.support.errors import fail_octop
from octop.config import env_bind_overrides
from octop.infra.errors import OctopError, corrupt_config_error
from octop.infra.utils.json_file import (
    JsonFileCorruptError,
    read_json_object,
    write_json_atomic,
)
from octop.infra.utils.paths import PathLayout


def _run_uvicorn(**kwargs: object) -> None:
    """Indirection seam for tests; the real implementation runs uvicorn."""
    from octop.launch import run_foreground_blocking

    run_foreground_blocking(**kwargs)


def _maybe_generate_self_signed(
    ssl: bool, certfile: str | None, keyfile: str | None
) -> tuple[str | None, str | None]:
    if not ssl:
        return certfile, keyfile
    if certfile and keyfile:
        return certfile, keyfile
    paths = PathLayout.from_env()
    ssl_dir = paths.ensure_ssl_dir()
    cert = ssl_dir / "self_signed.crt"
    key = ssl_dir / "self_signed.key"
    if not cert.exists() or not key.exists():
        import datetime
        import ipaddress

        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "octop-self-signed")])
        cert_obj = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(priv.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow())
            .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
            .add_extension(
                x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
                critical=False,
            )
            .sign(priv, hashes.SHA256())
        )
        key.write_bytes(
            priv.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        cert.write_bytes(cert_obj.public_bytes(serialization.Encoding.PEM))
    return str(cert), str(key)


def _load_configfile_overrides() -> tuple[str | None, int | None]:
    """Read ``bind_host`` / ``port`` from ``config.json``.

    An absent or unreadable file falls back to the launch defaults, but a
    *corrupt* one raises: silently ignoring it would bind defaults while
    discarding every other setting, and boot would then die with a bare
    ``JSONDecodeError`` traceback instead of an actionable message.
    """
    cfg_path = PathLayout.from_env().config
    try:
        data = read_json_object(cfg_path)
    except JsonFileCorruptError as exc:
        raise corrupt_config_error(exc.path, exc.detail) from exc
    except OSError:
        return None, None
    if data is None:
        return None, None
    # Prefer new key "bind_host"; fall back to legacy "host" for old configs.
    host = data.get("bind_host") or data.get("host")
    port = data.get("port")
    return (
        host if isinstance(host, str) else None,
        port if isinstance(port, int) and not isinstance(port, bool) else None,
    )


def resolve_bind(host: str | None, port: int | None) -> tuple[str | None, int | None]:
    """Resolve the uvicorn bind address: CLI flag > env > config.json."""
    cfg_host, cfg_port = _load_configfile_overrides()
    env_host, env_port = env_bind_overrides()
    # Use ``is not None`` (not ``or``) so falsy-but-valid values like port=0
    # (OS-assigned random port) and host="0" are not silently overridden.
    resolved_host = host if host is not None else env_host if env_host is not None else cfg_host
    resolved_port = port if port is not None else env_port if env_port is not None else cfg_port
    return resolved_host, resolved_port


def _save_configfile_overrides(host: str | None, port: int | None) -> None:
    """Persist resolved host/port to config.json (read-merge-write, atomic).

    A corrupt config.json is a hard error, never an empty base: merging into
    ``{}`` and writing back destroys every other setting (issue #730 — one
    trailing comma plus ``octop run --port`` wiped the ``database`` section and
    silently flipped a PostgreSQL instance back to greenfield SQLite).
    """
    paths = PathLayout.from_env()
    paths.ensure_root()
    cfg_path = paths.config
    try:
        data = read_json_object(cfg_path)
    except JsonFileCorruptError as exc:
        raise corrupt_config_error(exc.path, exc.detail) from exc
    if data is None:
        data = {}
    if host is not None:
        data["bind_host"] = host
    if port is not None:
        data["port"] = port
    click.echo(f"Saved config to {cfg_path}")
    try:
        write_json_atomic(cfg_path, data)
    except OSError as exc:
        click.echo(f"Warning: could not save config.json: {exc}", err=True)


@click.command("run")
@click.option("--host", default=None, help="Override bind host")
@click.option("--port", default=None, type=int, help="Override port")
@click.option("--reload", is_flag=True, default=False, help="Enable uvicorn auto-reload (dev).")
@click.option("--workers", default=1, type=int, help="Worker process count (default 1).")
@click.option(
    "--log-level",
    type=click.Choice(
        ["critical", "error", "warning", "info", "debug", "trace"], case_sensitive=False
    ),
    default=None,
)
@click.option(
    "--ssl",
    is_flag=True,
    default=False,
    help="Enable HTTPS (auto-generates self-signed if no cert/key given).",
)
@click.option("--ssl-certfile", default=None, help="TLS certificate file.")
@click.option("--ssl-keyfile", default=None, help="TLS private key file.")
def run(
    host: str | None,
    port: int | None,
    reload: bool,
    workers: int,
    log_level: str | None,
    ssl: bool,
    ssl_certfile: str | None,
    ssl_keyfile: str | None,
) -> None:
    """Run octop-server in the foreground.

    Host and port are resolved with the following precedence: explicit CLI
    flags > ``OCTOP_BIND_HOST``/``OCTOP_PORT`` env > ``~/.octop/config.json``
    > launch defaults. When ``--host`` or ``--port`` is passed on the CLI,
    that override is persisted to ``config.json`` immediately before uvicorn
    starts.
    """
    cli_host, cli_port = host, port
    try:
        host, port = resolve_bind(host, port)
        if cli_host is not None or cli_port is not None:
            _save_configfile_overrides(cli_host, cli_port)
    except OctopError as exc:
        fail_octop(exc)
    certfile, keyfile = _maybe_generate_self_signed(ssl, ssl_certfile, ssl_keyfile)
    _run_uvicorn(
        host=host,
        port=port,
        reload=reload,
        workers=workers,
        log_level=log_level,
        ssl_certfile=certfile,
        ssl_keyfile=keyfile,
    )
