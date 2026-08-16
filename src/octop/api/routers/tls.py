"""TLS / Let's Encrypt admin API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from octop.api.deps import get_server, require_permission
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.setup.tls.manager import get_tls_manager
from octop.infra.setup.tls.modes import is_issue_eligible, validate_issue_domain
from octop.infra.setup.tls.preflight import PreflightResult
from octop.infra.utils.locale import resolve_request_locale

router = APIRouter()


class PreflightBody(BaseModel):
    domain: str = Field(..., min_length=1, description="FQDN for the certificate")


class IssueBody(BaseModel):
    domain: str = Field(..., min_length=1, description="FQDN for the certificate")
    staging: bool = Field(
        default=False,
        description="Use Let's Encrypt staging (for testing; browsers will not trust the cert).",
    )


class PreflightResponse(BaseModel):
    ok: bool
    checks: list[dict[str, Any]]
    renewal: bool = False


class TlsStatusResponse(BaseModel):
    tls: dict[str, Any]
    task: dict[str, Any]
    eligible: bool
    issue_mode: str | None = None
    renewal: bool = False


def _preflight_response(result: PreflightResult) -> PreflightResponse:
    d = result.to_dict()
    return PreflightResponse(
        ok=bool(d["ok"]),
        checks=list(d["checks"]),
        renewal=bool(d.get("renewal", False)),
    )


@router.get("/status", summary="TLS and issuance task status")
async def tls_status(
    _: Any = Depends(require_permission("tls")),
    server: Any = Depends(get_server),
) -> TlsStatusResponse:
    assert server.services is not None
    mgr = get_tls_manager()
    payload = mgr.status_payload(server.services.config, server.paths)
    return TlsStatusResponse(**payload)


@router.post("/preflight", summary="Check prerequisites for Let's Encrypt issuance")
async def tls_preflight(
    body: PreflightBody,
    request: Request,
    _: Any = Depends(require_permission("tls")),
    server: Any = Depends(get_server),
) -> PreflightResponse:
    assert server.services is not None
    locale = resolve_request_locale(request)
    mgr = get_tls_manager()
    result = await mgr.run_preflight(body.domain, server.services.config, locale=locale)
    return _preflight_response(result)


@router.post("/issue", summary="Start Let's Encrypt HTTP-01 issuance")
async def tls_issue(
    body: IssueBody,
    request: Request,
    _: Any = Depends(require_permission("tls")),
    server: Any = Depends(get_server),
) -> PreflightResponse:
    assert server.services is not None
    cfg = server.services.config
    locale = resolve_request_locale(request)
    mgr = get_tls_manager()

    if not is_issue_eligible(cfg):
        raise OctopError.localized(ErrorCode.TLS_NOT_ELIGIBLE, locale)

    try:
        validate_issue_domain(body.domain, cfg)
    except ValueError:
        raise OctopError.localized(ErrorCode.TLS_DOMAIN_MISMATCH, locale) from None

    try:
        result = await mgr.start_issue(
            domain=body.domain,
            config=cfg,
            paths=server.paths,
            staging=body.staging,
            locale=locale,
        )
    except RuntimeError as exc:
        if "already in progress" in str(exc):
            raise OctopError.localized(ErrorCode.TLS_ISSUE_IN_PROGRESS, locale) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _preflight_response(result)
