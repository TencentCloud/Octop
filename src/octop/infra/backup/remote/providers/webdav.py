"""WebDAV remote backup provider (httpx)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote, urljoin, urlparse

import httpx

from octop.infra.backup.remote.registry import register_provider
from octop.infra.backup.remote.types import MirrorResult, RemoteObject
from octop.infra.errors import ErrorCode, OctopError

logger = logging.getLogger(__name__)

_DEFAULT_CONNECT_TIMEOUT_S = 10.0
_DEFAULT_READ_TIMEOUT_S = 120.0
_DEFAULT_PUT_BUDGET_S = 600.0
_DEFAULT_RECHECK_DELAY_S = 1.5
_DAV_NS = {"d": "DAV:"}


def redact_secrets(text: str, *, password: str | None = None) -> str:
    """Strip credentials and Authorization material from error text."""
    cleaned = text
    if password:
        cleaned = cleaned.replace(password, "***")
    cleaned = re.sub(r"(?i)(authorization:\s*basic\s+)\S+", r"\1***", cleaned)
    cleaned = re.sub(r"(?i)(authorization:\s*bearer\s+)\S+", r"\1***", cleaned)
    cleaned = re.sub(r"://([^:@/]+):([^@/]+)@", r"://\1:***@", cleaned)
    return cleaned


def _reject_userinfo(url: str) -> None:
    parsed = urlparse(url)
    if parsed.username is not None or parsed.password is not None:
        raise OctopError(
            ErrorCode.SLASH_BAD_ARGS,
            "WebDAV URL must not contain userinfo; put credentials in dedicated fields",
        )


@dataclass(frozen=True)
class WebDavSettings:
    base_url: str
    username: str
    password: str
    verify_ssl: bool
    connect_timeout_s: float = _DEFAULT_CONNECT_TIMEOUT_S
    read_timeout_s: float = _DEFAULT_READ_TIMEOUT_S
    put_budget_s: float = _DEFAULT_PUT_BUDGET_S
    recheck_delay_s: float = _DEFAULT_RECHECK_DELAY_S


class WebDavBackupProvider:
    """Upload/list/download/delete backup archives over WebDAV."""

    def __init__(self, settings: WebDavSettings) -> None:
        self._settings = settings

    @classmethod
    def from_settings(
        cls,
        *,
        url: str,
        username: str,
        password: str,
        base_dir: str = "",
        verify_ssl: bool = True,
        allow_insecure: bool = False,
        connect_timeout_s: float = _DEFAULT_CONNECT_TIMEOUT_S,
        read_timeout_s: float = _DEFAULT_READ_TIMEOUT_S,
        put_budget_s: float = _DEFAULT_PUT_BUDGET_S,
        recheck_delay_s: float = _DEFAULT_RECHECK_DELAY_S,
    ) -> WebDavBackupProvider:
        raw = (url or "").strip()
        if not raw:
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, "WebDAV URL is required")
        _reject_userinfo(raw)
        parsed = urlparse(raw)
        scheme = (parsed.scheme or "").lower()
        if scheme not in {"http", "https"}:
            raise OctopError(
                ErrorCode.SLASH_BAD_ARGS,
                f"WebDAV URL scheme must be http or https, got {scheme!r}",
            )
        if scheme == "http" and not allow_insecure:
            raise OctopError(
                ErrorCode.SLASH_BAD_ARGS,
                "http:// WebDAV requires allow_insecure=true (credentials travel in cleartext)",
            )
        base = raw if raw.endswith("/") else raw + "/"
        rel = (base_dir or "").strip().lstrip("/")
        if rel:
            base = urljoin(base, rel.rstrip("/") + "/")
        return cls(
            WebDavSettings(
                base_url=base,
                username=username or "",
                password=password or "",
                verify_ssl=verify_ssl if scheme == "https" else False,
                connect_timeout_s=connect_timeout_s,
                read_timeout_s=read_timeout_s,
                put_budget_s=put_budget_s,
                recheck_delay_s=recheck_delay_s,
            )
        )

    def _object_url(self, remote_name: str) -> str:
        name = (remote_name or "").replace("\\", "/").strip()
        if not name or "/" in name or name in {".", ".."} or name.endswith(".part"):
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, "invalid remote archive name")
        return urljoin(self._settings.base_url, quote(name, safe=""))

    def _client(self) -> httpx.AsyncClient:
        timeout = httpx.Timeout(
            self._settings.put_budget_s,
            connect=self._settings.connect_timeout_s,
            read=self._settings.read_timeout_s,
            write=self._settings.read_timeout_s,
        )
        auth = None
        if self._settings.username or self._settings.password:
            auth = (self._settings.username, self._settings.password)
        return httpx.AsyncClient(
            timeout=timeout,
            verify=self._settings.verify_ssl,
            auth=auth,
            # Redirects rewrite PUT/MOVE/PROPFIND to GET and can fake success.
            follow_redirects=False,
        )

    def _reason(self, text: str) -> str:
        return redact_secrets(text, password=self._settings.password)

    async def test(self) -> None:
        async with self._client() as client:
            try:
                response = await client.request(
                    "PROPFIND",
                    self._settings.base_url,
                    headers={"Depth": "0"},
                    content=(
                        '<?xml version="1.0" encoding="utf-8"?>'
                        '<d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/></d:prop>'
                        "</d:propfind>"
                    ),
                )
            except httpx.HTTPError as exc:
                raise OctopError(
                    ErrorCode.NETWORK_ERROR,
                    self._reason(f"WebDAV connectivity failed: {exc}"),
                ) from exc
        if response.status_code not in {207, 200}:
            raise OctopError(
                ErrorCode.NETWORK_ERROR,
                self._reason(f"WebDAV connectivity failed: HTTP {response.status_code}"),
            )

    async def put(self, local_path: Path, remote_name: str) -> MirrorResult:
        if not local_path.is_file():
            return MirrorResult(status="remote_failed", reason="local archive missing")
        size = local_path.stat().st_size
        url = self._object_url(remote_name)
        temp_url = url + ".part"
        try:
            async with self._client() as client:
                put_status = await self._put_bytes(client, temp_url, local_path)
                # Prefer temp + MOVE so a truncated final key is less likely.
                moved = await self._try_move(client, temp_url, url)
                if moved:
                    # Keep the temp PUT status so 201 async gateways still re-check.
                    return await self._verify_put(
                        client, url, expected_size=size, put_status=put_status
                    )
                # Fallback: put directly to the final name.
                put_status = await self._put_bytes(client, url, local_path)
                with contextlib.suppress(httpx.HTTPError):
                    await client.delete(temp_url)
                return await self._verify_put(
                    client, url, expected_size=size, put_status=put_status
                )
        except OctopError as exc:
            return MirrorResult(status="remote_failed", reason=self._reason(str(exc)))
        except httpx.HTTPError as exc:
            return MirrorResult(
                status="remote_failed",
                reason=self._reason(f"WebDAV upload failed: {exc}"),
            )
        except Exception as exc:  # noqa: BLE001 — map unexpected I/O into mirror status
            logger.exception("webdav put failed")
            return MirrorResult(
                status="remote_failed",
                reason=self._reason(f"WebDAV upload failed: {exc}"),
            )

    async def _put_bytes(self, client: httpx.AsyncClient, url: str, local_path: Path) -> int:
        size = local_path.stat().st_size

        async def _body():
            def _read_chunk(handle: object, n: int) -> bytes:
                return handle.read(n)  # type: ignore[attr-defined]

            with local_path.open("rb") as handle:
                while True:
                    chunk = await asyncio.to_thread(_read_chunk, handle, 1024 * 1024)
                    if not chunk:
                        break
                    yield chunk

        response = await client.put(
            url,
            content=_body(),
            headers={"Content-Length": str(size)},
        )
        if response.status_code not in {200, 201, 204}:
            raise OctopError(
                ErrorCode.NETWORK_ERROR,
                f"WebDAV PUT failed: HTTP {response.status_code}",
            )
        return int(response.status_code)

    async def _try_move(self, client: httpx.AsyncClient, src: str, dest: str) -> bool:
        try:
            response = await client.request(
                "MOVE",
                src,
                headers={"Destination": dest, "Overwrite": "T"},
            )
        except httpx.HTTPError:
            return False
        # Do not treat 200 as MOVE success: redirected GET often returns 200.
        return response.status_code in {201, 204}

    async def _head_meta(
        self, client: httpx.AsyncClient, url: str
    ) -> tuple[int | None, str | None]:
        response = await client.head(url)
        if response.status_code >= 400:
            return None, None
        length_raw = response.headers.get("Content-Length")
        length: int | None
        try:
            length = int(length_raw) if length_raw is not None else None
        except ValueError:
            length = None
        etag = response.headers.get("ETag")
        return length, etag

    async def _verify_put(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        expected_size: int,
        put_status: int,
    ) -> MirrorResult:
        size1, etag1 = await self._head_meta(client, url)
        if size1 is None:
            return MirrorResult(
                status="remote_failed",
                reason="WebDAV HEAD after PUT failed or missing Content-Length",
            )
        if size1 != expected_size:
            return MirrorResult(
                status="remote_failed",
                reason=f"remote size {size1} != local size {expected_size}",
            )
        # Ordinary completed PUT (200/204) + size match → ok.
        if put_status in {200, 204}:
            return MirrorResult(status="remote_ok", reason="put verified")
        # 201 often means "created / accepted"; require a stronger signal.
        if self._settings.recheck_delay_s > 0:
            await asyncio.sleep(self._settings.recheck_delay_s)
        size2, etag2 = await self._head_meta(client, url)
        if size2 != expected_size:
            return MirrorResult(
                status="unverified",
                reason="size changed after delayed re-check",
            )
        if etag1 and etag2 and etag1 == etag2:
            return MirrorResult(status="remote_ok", reason="etag stable after re-check")
        return MirrorResult(
            status="unverified",
            reason="PUT 201 with size match but no stable ETag completion signal",
        )

    async def list(self) -> list[RemoteObject]:
        async with self._client() as client:
            try:
                response = await client.request(
                    "PROPFIND",
                    self._settings.base_url,
                    headers={"Depth": "1"},
                    content=(
                        '<?xml version="1.0" encoding="utf-8"?>'
                        '<d:propfind xmlns:d="DAV:"><d:prop>'
                        "<d:resourcetype/><d:displayname/>"
                        "<d:getcontentlength/><d:getlastmodified/>"
                        "</d:prop></d:propfind>"
                    ),
                )
            except httpx.HTTPError as exc:
                raise OctopError(
                    ErrorCode.NETWORK_ERROR,
                    self._reason(f"WebDAV list failed: {exc}"),
                ) from exc
        if response.status_code not in {207, 200}:
            raise OctopError(
                ErrorCode.NETWORK_ERROR,
                self._reason(f"WebDAV list failed: HTTP {response.status_code}"),
            )
        return _parse_propfind(response.text, base_url=self._settings.base_url)

    async def get(self, remote_name: str, dest: Path) -> None:
        url = self._object_url(remote_name)
        async with self._client() as client:
            try:
                async with client.stream("GET", url) as response:
                    if response.status_code in {404, 410}:
                        raise OctopError(
                            ErrorCode.NOT_FOUND,
                            self._reason(f"WebDAV download failed: HTTP {response.status_code}"),
                        )
                    if response.status_code != 200:
                        raise OctopError(
                            ErrorCode.NETWORK_ERROR,
                            self._reason(f"WebDAV download failed: HTTP {response.status_code}"),
                        )
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with dest.open("wb") as handle:
                        async for chunk in response.aiter_bytes():
                            await asyncio.to_thread(handle.write, chunk)
            except OctopError:
                raise
            except httpx.HTTPError as exc:
                raise OctopError(
                    ErrorCode.NETWORK_ERROR,
                    self._reason(f"WebDAV download failed: {exc}"),
                ) from exc

    async def delete(self, remote_name: str) -> None:
        url = self._object_url(remote_name)
        async with self._client() as client:
            try:
                response = await client.delete(url)
            except httpx.HTTPError as exc:
                raise OctopError(
                    ErrorCode.NETWORK_ERROR,
                    self._reason(f"WebDAV delete failed: {exc}"),
                ) from exc
        if response.status_code not in {200, 204, 404}:
            raise OctopError(
                ErrorCode.NETWORK_ERROR,
                self._reason(f"WebDAV delete failed: HTTP {response.status_code}"),
            )


def _parse_propfind(xml_text: str, *, base_url: str) -> list[RemoteObject]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise OctopError(
            ErrorCode.NETWORK_ERROR,
            "WebDAV list returned non-PROPFIND XML",
        ) from exc
    base_path = unquote(urlparse(base_url).path.rstrip("/"))
    items: list[RemoteObject] = []
    for response in root.findall("d:response", _DAV_NS):
        href_el = response.find("d:href", _DAV_NS)
        if href_el is None or not href_el.text:
            continue
        href = href_el.text
        path = urlparse(href).path if "://" in href else href
        path = unquote(path.rstrip("/"))
        name = Path(path).name
        if not name or path == base_path or name.endswith(".part"):
            continue
        prop = response.find("d:propstat/d:prop", _DAV_NS)
        if prop is not None:
            rtype = prop.find("d:resourcetype", _DAV_NS)
            if rtype is not None and rtype.find("d:collection", _DAV_NS) is not None:
                continue
        size = 0
        modified: str | None = None
        if prop is not None:
            length_el = prop.find("d:getcontentlength", _DAV_NS)
            if length_el is not None and length_el.text:
                try:
                    size = int(length_el.text)
                except ValueError:
                    size = 0
            mod_el = prop.find("d:getlastmodified", _DAV_NS)
            if mod_el is not None and mod_el.text:
                modified = mod_el.text
        items.append(RemoteObject(name=name, size=size, modified_at=modified))
    return items


def _as_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _as_float(value: object, default: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value.strip())
        except ValueError:
            return default
    return default


def _factory(**kwargs: object) -> WebDavBackupProvider:
    return WebDavBackupProvider.from_settings(
        url=str(kwargs.get("url") or ""),
        username=str(kwargs.get("username") or ""),
        password=str(kwargs.get("password") or ""),
        base_dir=str(kwargs.get("base_dir") or ""),
        verify_ssl=_as_bool(kwargs.get("verify_ssl"), True),
        allow_insecure=_as_bool(kwargs.get("allow_insecure"), False),
        connect_timeout_s=_as_float(kwargs.get("connect_timeout_s"), _DEFAULT_CONNECT_TIMEOUT_S),
        read_timeout_s=_as_float(kwargs.get("read_timeout_s"), _DEFAULT_READ_TIMEOUT_S),
        put_budget_s=_as_float(kwargs.get("put_budget_s"), _DEFAULT_PUT_BUDGET_S),
        recheck_delay_s=_as_float(kwargs.get("recheck_delay_s"), _DEFAULT_RECHECK_DELAY_S),
    )


register_provider("webdav", _factory)
