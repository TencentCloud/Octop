"""Local ONNX embedding model cache API (Models admin — local tab).

Manages catalog download / probe / enable for local ONNX embedding weights.
This is not a chat Provider. Knowledge Bases consume these models for embedding.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from octop.api.deps import get_server, require_permission
from octop.infra.agents.providers.onnx_catalog import list_onnx_catalog_models
from octop.infra.agents.providers.onnx_service import (
    DOWNLOAD_MANAGER,
    OnnxServiceConfig,
    assert_catalog_model,
    delete_downloaded_model,
    ensure_local_embedding_deps_async,
    is_model_downloaded,
    probe_local_model,
    save_config,
    status_payload,
)

router = APIRouter(prefix="/onnx-models", tags=["onnx"])


class OnnxCatalogItem(BaseModel):
    id: str
    name: str
    recommended: bool = False
    downloaded: bool = False
    size_gb: float | None = None
    hf_source: str | None = None


class OnnxServiceConfigBody(BaseModel):
    enabled: bool = Field(..., description="Whether the local ONNX service is enabled")
    model: str = Field(..., min_length=1, description="Selected catalog model id")
    download_if_missing: bool = Field(
        True,
        description="When enabling, start a download if the model is not cached",
    )


class OnnxDownloadRequest(BaseModel):
    model: str = Field(..., min_length=1, description="Catalog model id to download")


class OnnxTestRequest(BaseModel):
    model: str = Field(..., min_length=1, description="Downloaded catalog model id to probe")


class OnnxTestResponse(BaseModel):
    ok: bool
    latency_ms: float | None = None
    error: str | None = None
    dim: int | None = None


def _settings_get(server: Any) -> Any:
    return server.services.settings_repo.get


def _settings_set(server: Any) -> Any:
    return server.services.settings_repo.set


def _http_from_value_error(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def _http_from_runtime(exc: RuntimeError) -> HTTPException:
    detail = str(exc)
    code = 503 if "local-embedding" in detail or "fastembed" in detail else 409
    return HTTPException(status_code=code, detail=detail)


@router.get("/catalog", response_model=list[OnnxCatalogItem], summary="List ONNX catalog")
async def get_catalog(_: Any = Depends(require_permission("onnx_models"))) -> list[OnnxCatalogItem]:
    return [
        OnnxCatalogItem(
            id=str(m["id"]),
            name=str(m.get("name") or m["id"]),
            recommended=bool(m.get("recommended")),
            downloaded=is_model_downloaded(str(m["id"])),
            size_gb=float(m["size_gb"]) if m.get("size_gb") is not None else None,
            hf_source=str(m["hf_source"]) if m.get("hf_source") else None,
        )
        for m in list_onnx_catalog_models()
    ]


@router.get("/models/{model_name:path}/meta", summary="ONNX model size / source metadata")
async def get_model_meta(
    model_name: str,
    _: Any = Depends(require_permission("onnx_models")),
) -> dict[str, Any]:
    from octop.infra.agents.providers.onnx_catalog import get_onnx_model_meta

    try:
        name = assert_catalog_model(model_name)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    meta = get_onnx_model_meta(name)
    meta["downloaded"] = is_model_downloaded(name)
    return meta


@router.get("/status", summary="Get local ONNX service status")
async def get_status(
    server: Any = Depends(get_server),
    _: Any = Depends(require_permission("onnx_models")),
) -> dict[str, Any]:
    return status_payload(_settings_get(server), DOWNLOAD_MANAGER.state)


@router.put("/config", summary="Enable/disable local ONNX service and select model")
async def put_config(
    body: OnnxServiceConfigBody,
    server: Any = Depends(get_server),
    _: Any = Depends(require_permission("onnx_models")),
) -> dict[str, Any]:
    try:
        model = assert_catalog_model(body.model)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    config = OnnxServiceConfig(enabled=body.enabled, model=model)
    deps_just_installed = False
    if config.enabled:
        try:
            deps_just_installed = (
                await ensure_local_embedding_deps_async(allow_install=True) == "installed"
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        # Without a download to fall back on, enabling a model that has no
        # weights on disk would persist enabled=True and report ready=False
        # forever — surface it instead of storing a service that cannot run.
        if not body.download_if_missing and not is_model_downloaded(config.model):
            raise HTTPException(
                status_code=409,
                detail="ONNX embedding model is not downloaded yet; download it before enabling",
            )
    save_config(_settings_set(server), config)
    download_started = False
    if config.enabled and body.download_if_missing and not is_model_downloaded(config.model):
        try:
            await DOWNLOAD_MANAGER.start_download(config.model)
            download_started = True
        except RuntimeError as exc:
            raise _http_from_runtime(exc) from exc
        except ValueError as exc:
            raise _http_from_value_error(exc) from exc
    payload = status_payload(_settings_get(server), DOWNLOAD_MANAGER.state)
    payload["download_started"] = download_started
    payload["deps_just_installed"] = deps_just_installed
    return payload


@router.post(
    "/test",
    response_model=OnnxTestResponse,
    summary="Probe a local ONNX embedding model",
)
async def post_test(
    body: OnnxTestRequest,
    _: Any = Depends(require_permission("onnx_models")),
) -> OnnxTestResponse:
    """Run a tiny local embedding to verify the model loads and works (admin only)."""
    result = await probe_local_model(body.model)
    return OnnxTestResponse(
        ok=bool(result.get("ok")),
        latency_ms=result.get("latency_ms"),
        error=result.get("error"),
        dim=result.get("dim"),
    )


@router.post("/download", summary="Download a local ONNX embedding model")
async def post_download(
    body: OnnxDownloadRequest,
    _: Any = Depends(require_permission("onnx_models")),
) -> dict[str, Any]:
    try:
        state = await DOWNLOAD_MANAGER.start_download(body.model.strip())
    except RuntimeError as exc:
        raise _http_from_runtime(exc) from exc
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    return state.to_dict()


@router.get("/download-status", summary="Poll ONNX model download progress")
async def get_download_status(
    _: Any = Depends(require_permission("onnx_models")),
) -> dict[str, Any]:
    return DOWNLOAD_MANAGER.state.to_dict()


@router.delete("/local/{model_name:path}", summary="Delete a cached local ONNX model")
async def delete_local_model(
    model_name: str,
    server: Any = Depends(get_server),
    _: Any = Depends(require_permission("onnx_models")),
) -> dict[str, Any]:
    try:
        name = assert_catalog_model(model_name)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    removed = delete_downloaded_model(name)
    return {
        "ok": True,
        "removed": removed,
        "status": status_payload(_settings_get(server), DOWNLOAD_MANAGER.state),
    }
