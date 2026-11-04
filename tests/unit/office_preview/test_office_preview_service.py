from __future__ import annotations

import asyncio
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.office_preview.convert import HelperConvertResult
from octop.infra.office_preview.service import OfficePreviewService


def _docx_bytes() -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", "<w:document/>")
    return buf.getvalue()


PDF = b"%PDF-1.7\n1 0 obj\nendobj\n"


async def _load_docx() -> bytes:
    return _docx_bytes()


async def _load_xlsm() -> bytes:
    return b"xlsm"


async def _ok_convert(
    input_path: Path, output_path: Path, cancel_event: asyncio.Event | None = None
) -> HelperConvertResult:
    output_path.write_bytes(PDF)
    return HelperConvertResult(pdf=PDF, missing_fonts=("Noto Sans",))


@pytest.mark.asyncio
async def test_convert_unavailable() -> None:
    service = OfficePreviewService(probe_available=lambda: False, convert_fn=_ok_convert)
    with pytest.raises(OctopError) as raised:
        await service.convert(
            cache_scope="u1",
            source_id="a.docx",
            filename="a.docx",
            load_bytes=_load_docx,
        )
    assert raised.value.code is ErrorCode.OFFICE_PREVIEW_UNAVAILABLE


@pytest.mark.asyncio
async def test_convert_unsupported_xlsm() -> None:
    service = OfficePreviewService(probe_available=lambda: True, convert_fn=_ok_convert)
    with pytest.raises(OctopError) as raised:
        await service.convert(
            cache_scope="u1",
            source_id="a.xlsm",
            filename="a.xlsm",
            load_bytes=_load_xlsm,
        )
    assert raised.value.code is ErrorCode.OFFICE_PREVIEW_UNSUPPORTED


@pytest.mark.asyncio
async def test_convert_caches_success_not_failure() -> None:
    calls = {"n": 0}

    async def convert_fn(
        input_path: Path, output_path: Path, cancel_event: asyncio.Event | None = None
    ) -> HelperConvertResult:
        calls["n"] += 1
        output_path.write_bytes(PDF)
        return HelperConvertResult(pdf=PDF, missing_fonts=())

    service = OfficePreviewService(probe_available=lambda: True, convert_fn=convert_fn)
    payload = _docx_bytes()

    async def load() -> bytes:
        return payload

    first = await service.convert(
        cache_scope="user:1", source_id="a.docx", filename="a.docx", load_bytes=load
    )
    second = await service.convert(
        cache_scope="user:1", source_id="a.docx", filename="a.docx", load_bytes=load
    )
    assert first.pdf == PDF
    assert second.digest == first.digest
    assert calls["n"] == 1

    other = await service.convert(
        cache_scope="user:2", source_id="a.docx", filename="a.docx", load_bytes=load
    )
    assert calls["n"] == 2
    assert other.pdf == PDF


@pytest.mark.asyncio
async def test_inflight_merge_single_convert() -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    calls = {"n": 0}

    async def convert_fn(
        input_path: Path, output_path: Path, cancel_event: asyncio.Event | None = None
    ) -> HelperConvertResult:
        calls["n"] += 1
        started.set()
        await release.wait()
        output_path.write_bytes(PDF)
        return HelperConvertResult(pdf=PDF, missing_fonts=())

    service = OfficePreviewService(probe_available=lambda: True, convert_fn=convert_fn)
    payload = _docx_bytes()

    async def load() -> bytes:
        return payload

    first = asyncio.create_task(
        service.convert(
            cache_scope="user:1", source_id="a.docx", filename="a.docx", load_bytes=load
        )
    )
    await started.wait()
    second = asyncio.create_task(
        service.convert(
            cache_scope="user:1", source_id="a.docx", filename="a.docx", load_bytes=load
        )
    )
    await asyncio.sleep(0.05)
    release.set()
    results = await asyncio.gather(first, second)
    assert calls["n"] == 1
    assert results[0].pdf == results[1].pdf == PDF


@pytest.mark.asyncio
async def test_queue_full() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def convert_fn(
        input_path: Path, output_path: Path, cancel_event: asyncio.Event | None = None
    ) -> HelperConvertResult:
        started.set()
        await release.wait()
        output_path.write_bytes(PDF)
        return HelperConvertResult(pdf=PDF, missing_fonts=())

    service = OfficePreviewService(
        probe_available=lambda: True,
        convert_fn=convert_fn,
        max_concurrency=1,
        max_waiting=0,
    )
    payload = _docx_bytes()

    async def load() -> bytes:
        return payload

    first = asyncio.create_task(
        service.convert(
            cache_scope="user:1", source_id="a.docx", filename="a.docx", load_bytes=load
        )
    )
    await started.wait()
    with pytest.raises(OctopError) as raised:
        await service.convert(
            cache_scope="user:1", source_id="b.docx", filename="b.docx", load_bytes=load
        )
    assert raised.value.code is ErrorCode.OFFICE_PREVIEW_QUEUE_FULL
    release.set()
    await first


@pytest.mark.asyncio
async def test_queue_full_does_not_start_disconnect_watcher() -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    polls = {"n": 0}

    async def convert_fn(
        input_path: Path, output_path: Path, cancel_event: asyncio.Event | None = None
    ) -> HelperConvertResult:
        started.set()
        await release.wait()
        output_path.write_bytes(PDF)
        return HelperConvertResult(pdf=PDF, missing_fonts=())

    async def is_disconnected() -> bool:
        polls["n"] += 1
        return False

    service = OfficePreviewService(
        probe_available=lambda: True,
        convert_fn=convert_fn,
        max_concurrency=1,
        max_waiting=0,
    )
    payload = _docx_bytes()

    async def load() -> bytes:
        return payload

    first = asyncio.create_task(
        service.convert(
            cache_scope="user:1", source_id="a.docx", filename="a.docx", load_bytes=load
        )
    )
    await started.wait()
    with pytest.raises(OctopError) as raised:
        await service.convert(
            cache_scope="user:1",
            source_id="b.docx",
            filename="b.docx",
            load_bytes=load,
            is_disconnected=is_disconnected,
        )
    assert raised.value.code is ErrorCode.OFFICE_PREVIEW_QUEUE_FULL
    assert polls["n"] == 0
    await asyncio.sleep(0.4)
    assert polls["n"] == 0
    release.set()
    await first


@pytest.mark.asyncio
async def test_known_size_rejects_before_load() -> None:
    loaded = {"n": 0}

    async def load() -> bytes:
        loaded["n"] += 1
        return _docx_bytes()

    service = OfficePreviewService(probe_available=lambda: True, convert_fn=_ok_convert)
    with pytest.raises(OctopError) as raised:
        await service.convert(
            cache_scope="u",
            source_id="a.docx",
            filename="a.docx",
            load_bytes=load,
            known_size=51 * 1024 * 1024,
        )
    assert raised.value.code is ErrorCode.OFFICE_PREVIEW_TOO_LARGE
    assert loaded["n"] == 0


@pytest.mark.asyncio
async def test_too_large(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("octop.infra.office_preview.service.MAX_INPUT_BYTES", 8)
    service = OfficePreviewService(probe_available=lambda: True, convert_fn=_ok_convert)
    with pytest.raises(OctopError) as raised:
        await service.convert(
            cache_scope="u",
            source_id="a.docx",
            filename="a.docx",
            load_bytes=_load_docx,
        )
    assert raised.value.code is ErrorCode.OFFICE_PREVIEW_TOO_LARGE


@pytest.mark.asyncio
async def test_cancel_last_waiter_stops_convert() -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def convert_fn(
        input_path: Path, output_path: Path, cancel_event: asyncio.Event | None = None
    ) -> HelperConvertResult:
        started.set()
        assert cancel_event is not None
        try:
            await cancel_event.wait()
        finally:
            cancelled.set()
        raise asyncio.CancelledError

    service = OfficePreviewService(probe_available=lambda: True, convert_fn=convert_fn)
    payload = _docx_bytes()

    async def load() -> bytes:
        return payload

    task = asyncio.create_task(
        service.convert(
            cache_scope="user:1", source_id="a.docx", filename="a.docx", load_bytes=load
        )
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.wait_for(cancelled.wait(), timeout=2)
