"""In-process Office preview conversion: queue, cache, in-flight merge."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import shutil
import tempfile
import time
import zipfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any, cast

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.office_preview.convert import HelperConvertResult, convert_with_helper
from octop.infra.office_preview.formats import (
    is_convertible_filename,
    is_zip_container,
    trusted_input_name,
)
from octop.infra.office_preview.limits import (
    CACHE_MAX_ITEMS,
    CACHE_TTL_SECONDS,
    ENGINE_ID,
    MAX_CONCURRENCY,
    MAX_INPUT_BYTES,
    MAX_WAITING,
    MAX_ZIP_UNCOMPRESSED_BYTES,
)
from octop.infra.office_preview.read import assert_not_too_large, too_large_error
from octop.infra.office_preview.runtime import probe_runtime, probe_status_payload

ConvertFn = Callable[..., Awaitable[HelperConvertResult]]
LoadBytesFn = Callable[[], Awaitable[bytes]]
DisconnectedFn = Callable[[], Awaitable[bool]]


@dataclass(frozen=True)
class ConvertedPdf:
    pdf: bytes
    digest: str
    missing_fonts: tuple[str, ...]


@dataclass
class _CacheEntry:
    value: ConvertedPdf
    expires_at: float


@dataclass
class _InFlight:
    future: asyncio.Future[ConvertedPdf]
    cancel_convert: asyncio.Event
    waiters: int = 0
    task: asyncio.Task[None] | None = field(default=None)


class OfficePreviewService:
    """Process-local converter. Failures are not cached; cache is not shared across users."""

    def __init__(
        self,
        *,
        convert_fn: ConvertFn | None = None,
        probe_available: Callable[[], bool] | None = None,
        max_concurrency: int = MAX_CONCURRENCY,
        max_waiting: int = MAX_WAITING,
        cache_ttl: float = CACHE_TTL_SECONDS,
        cache_max_items: int = CACHE_MAX_ITEMS,
    ) -> None:
        self._convert_fn = convert_fn or convert_with_helper
        self._probe_available = probe_available or (lambda: probe_runtime().available)
        self._max_admitted = max_concurrency + max_waiting
        self._cache_ttl = cache_ttl
        self._cache_max_items = cache_max_items
        self._convert_slots = asyncio.Semaphore(max_concurrency)
        self._lock = asyncio.Lock()
        self._admitted = 0
        self._cache: dict[str, _CacheEntry] = {}
        self._inflight: dict[str, _InFlight] = {}

    def status(self) -> dict[str, object]:
        return probe_status_payload()

    async def convert(
        self,
        *,
        cache_scope: str,
        source_id: str,
        filename: str,
        load_bytes: LoadBytesFn,
        known_size: int | None = None,
        is_disconnected: DisconnectedFn | None = None,
    ) -> ConvertedPdf:
        if not is_convertible_filename(filename):
            raise OctopError(
                ErrorCode.OFFICE_PREVIEW_UNSUPPORTED,
                "this file type cannot be converted for preview",
            )
        if not await asyncio.to_thread(self._probe_available):
            raise OctopError(
                ErrorCode.OFFICE_PREVIEW_UNAVAILABLE,
                "office preview runtime is not installed",
            )
        if known_size is not None:
            assert_not_too_large(known_size)

        cancel_local = asyncio.Event()
        await self._admit()
        watcher: asyncio.Task[None] | None = None
        try:
            if is_disconnected is not None:
                watcher = asyncio.create_task(_watch_disconnect(is_disconnected, cancel_local))
            if cancel_local.is_set():
                raise asyncio.CancelledError
            data = await load_bytes()
            self._assert_input_bounds(filename, data)
            digest = hashlib.sha256(data).hexdigest()
            key = f"{cache_scope}|{source_id}|{digest}|{ENGINE_ID}"
            cached = self._cache_get(key)
            if cached is not None:
                return cached
            return await self._convert_or_join(
                key,
                filename,
                data,
                digest,
                cancel_local=cancel_local,
            )
        finally:
            if watcher is not None:
                watcher.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await watcher
            await self._leave()

    async def _convert_or_join(
        self,
        key: str,
        filename: str,
        data: bytes,
        digest: str,
        *,
        cancel_local: asyncio.Event,
    ) -> ConvertedPdf:
        async with self._lock:
            inflight = self._inflight.get(key)
            started = False
            if inflight is None:
                loop = asyncio.get_running_loop()
                inflight = _InFlight(
                    future=loop.create_future(),
                    cancel_convert=asyncio.Event(),
                )
                self._inflight[key] = inflight
                started = True
            inflight.waiters += 1

        if started:
            inflight.task = asyncio.create_task(
                self._produce(key, filename, data, digest, inflight)
            )

        try:
            return await self._wait_for_inflight(inflight, cancel_local)
        finally:
            async with self._lock:
                inflight.waiters -= 1
                if inflight.waiters <= 0:
                    if not inflight.future.done():
                        inflight.cancel_convert.set()
                        if inflight.task is not None:
                            inflight.task.cancel()
                    self._inflight.pop(key, None)

    async def _wait_for_inflight(
        self, inflight: _InFlight, cancel_local: asyncio.Event
    ) -> ConvertedPdf:
        loop = asyncio.get_running_loop()
        relay: asyncio.Future[ConvertedPdf] = loop.create_future()

        def _propagate(fut: asyncio.Future[ConvertedPdf]) -> None:
            if relay.done():
                return
            if fut.cancelled():
                relay.cancel()
                return
            exc = fut.exception()
            if exc is not None:
                relay.set_exception(exc)
                return
            relay.set_result(fut.result())

        inflight.future.add_done_callback(_propagate)
        if inflight.future.done():
            _propagate(inflight.future)

        cancel_wait = asyncio.create_task(cancel_local.wait())
        try:
            finished, _pending = await asyncio.wait(
                cast(list[asyncio.Future[Any]], [relay, cancel_wait]),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if cancel_wait in finished and not relay.done():
                raise asyncio.CancelledError
            return await relay
        finally:
            cancel_wait.cancel()

    async def _produce(
        self,
        key: str,
        filename: str,
        data: bytes,
        digest: str,
        inflight: _InFlight,
    ) -> None:
        await self._convert_slots.acquire()
        try:
            result = await self._run_helper(filename, data, cancel_event=inflight.cancel_convert)
            converted = ConvertedPdf(
                pdf=result.pdf,
                digest=digest,
                missing_fonts=result.missing_fonts,
            )
            self._cache_put(key, converted)
            if not inflight.future.done():
                inflight.future.set_result(converted)
        except asyncio.CancelledError:
            if not inflight.future.done():
                inflight.future.set_exception(
                    OctopError(
                        ErrorCode.OFFICE_PREVIEW_FAILED,
                        "office preview conversion was cancelled",
                    )
                )
            raise
        except BaseException as exc:
            if not inflight.future.done():
                inflight.future.set_exception(exc)
        finally:
            self._convert_slots.release()

    async def _admit(self) -> None:
        async with self._lock:
            if self._admitted >= self._max_admitted:
                raise OctopError(
                    ErrorCode.OFFICE_PREVIEW_QUEUE_FULL,
                    "too many office preview conversions are in progress",
                )
            self._admitted += 1

    async def _leave(self) -> None:
        async with self._lock:
            self._admitted = max(0, self._admitted - 1)

    def _cache_get(self, key: str) -> ConvertedPdf | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        if entry.expires_at <= time.monotonic():
            self._cache.pop(key, None)
            return None
        return entry.value

    def _cache_put(self, key: str, value: ConvertedPdf) -> None:
        now = time.monotonic()
        stale = [k for k, item in self._cache.items() if item.expires_at <= now]
        for stale_key in stale:
            self._cache.pop(stale_key, None)
        while len(self._cache) >= self._cache_max_items and self._cache:
            oldest = next(iter(self._cache))
            self._cache.pop(oldest, None)
        self._cache[key] = _CacheEntry(value=value, expires_at=now + self._cache_ttl)

    def _assert_input_bounds(self, filename: str, data: bytes) -> None:
        if len(data) > MAX_INPUT_BYTES:
            raise too_large_error()
        if not is_zip_container(filename):
            return
        try:
            uncompressed = _zip_uncompressed_size(data)
        except (zipfile.BadZipFile, OSError, ValueError) as exc:
            raise OctopError(
                ErrorCode.OFFICE_PREVIEW_CORRUPT,
                "office document could not be converted",
            ) from exc
        if uncompressed > MAX_ZIP_UNCOMPRESSED_BYTES:
            raise OctopError(
                ErrorCode.OFFICE_PREVIEW_TOO_LARGE,
                "office document exceeds the preview size limit",
            )

    async def _run_helper(
        self,
        filename: str,
        data: bytes,
        *,
        cancel_event: asyncio.Event,
    ) -> HelperConvertResult:
        tmp = Path(tempfile.mkdtemp(prefix="octop-office-preview-"))
        try:
            input_path = tmp / trusted_input_name(filename)
            output_path = tmp / "output.pdf"
            input_path.write_bytes(data)
            return await self._convert_fn(
                input_path,
                output_path,
                cancel_event=cancel_event,
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def _zip_uncompressed_size(data: bytes) -> int:
    with zipfile.ZipFile(BytesIO(data)) as zf:
        return int(sum(info.file_size for info in zf.infolist()))


async def _watch_disconnect(is_disconnected: DisconnectedFn, cancel_event: asyncio.Event) -> None:
    while not cancel_event.is_set():
        try:
            if await is_disconnected():
                cancel_event.set()
                return
        except Exception:
            return
        await asyncio.sleep(0.25)


_SERVICE: OfficePreviewService | None = None


def get_office_preview_service() -> OfficePreviewService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = OfficePreviewService()
    return _SERVICE


def reset_office_preview_service(service: OfficePreviewService | None = None) -> None:
    global _SERVICE
    _SERVICE = service
