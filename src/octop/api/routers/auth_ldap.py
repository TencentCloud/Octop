"""LDAP directory login HTTP routes."""

from __future__ import annotations

import asyncio
from typing import Any, cast

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from octop.api.deps import get_server, require_permission
from octop.i18n import tr
from octop.infra.auth.ldap.service import LdapAuthService
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.identity import User
from octop.infra.utils.locale import resolve_request_locale

router = APIRouter()


class LdapConfigBody(BaseModel):
    enabled: bool | None = None
    display_name: str | None = None
    server_url: str | None = Field(
        default=None, description="ldap:// or ldaps:// URL; the port defaults to 389/636."
    )
    start_tls: bool | None = Field(
        default=None,
        description="Required when enabling a plain ldap:// URL; passwords are otherwise sent in clear text.",
    )
    verify_tls: bool | None = Field(
        default=None, description="Verify the server certificate for ldaps/StartTLS."
    )
    bind_dn: str | None = Field(
        default=None, description="Service account DN; empty means an anonymous search."
    )
    bind_password: str | None = Field(
        default=None,
        max_length=1024,
        description="Write-only. Omit to keep the stored password.",
    )
    user_base_dn: str | None = None
    user_filter: str | None = Field(
        default=None, description="Must contain the literal {username} placeholder."
    )
    username_attribute: str | None = None
    email_attribute: str | None = None
    display_name_attribute: str | None = None
    subject_attribute: str | None = Field(
        default=None,
        description=(
            "Directory-stable identity key: entryUUID (OpenLDAP) or objectGUID (AD). "
            "Falls back to the DN when absent. Changing it orphans existing links."
        ),
    )
    group_attribute: str | None = Field(
        default=None, description="Multi-valued attribute holding group DNs, e.g. memberOf."
    )
    group_search: bool | None = Field(
        default=None,
        description="Resolve membership by searching group entries instead of reading group_attribute.",
    )
    group_search_base: str | None = Field(
        default=None, description="Base DN for the group search; defaults to the user base DN."
    )
    group_member_attribute: str | None = Field(
        default=None,
        description="Membership attribute on group entries, e.g. member or uniqueMember.",
    )
    admin_groups: str | None = Field(
        default=None,
        description=(
            "Comma-separated group CNs or DNs whose members become Octop admins. "
            "Only applied when the account is first provisioned."
        ),
    )
    allowed_groups: str | None = Field(
        default=None,
        description="When set, only members of these groups may sign in through the directory.",
    )
    auto_provision: bool | None = Field(
        default=None, description="Create an Octop account on a first directory login."
    )
    timeout_seconds: int | None = Field(default=None, ge=1, le=60)


class LdapStatusResponse(BaseModel):
    enabled: bool
    display_name: str = Field(description="Label shown on the login page hint.")


class LdapTestResponse(BaseModel):
    ok: bool
    detail: str = Field(description="Localized outcome or the underlying LDAP error.")
    warnings: list[str] = Field(
        default_factory=list, description="Non-blocking configuration risks."
    )
    detected_subject_attribute: str | None = Field(
        default=None,
        description=(
            "Identity-key attribute found on the sampled entries (entryUUID or "
            "objectGUID); suggest it as subject_attribute when that is still blank."
        ),
    )


class LdapConfigResponse(BaseModel):
    enabled: bool
    display_name: str
    server_url: str
    start_tls: bool
    verify_tls: bool
    bind_dn: str
    user_base_dn: str
    user_filter: str
    username_attribute: str
    email_attribute: str
    display_name_attribute: str
    subject_attribute: str = Field(description="Identity key attribute; empty means DN fallback.")
    group_attribute: str
    group_search: bool = Field(description="Membership resolved by group search.")
    group_search_base: str
    group_member_attribute: str
    admin_groups: str = Field(
        description="Comma-separated group CNs or DNs; applied at first provisioning only."
    )
    allowed_groups: str = Field(description="Comma-separated sign-in allow-list.")
    auto_provision: bool
    timeout_seconds: int
    has_bind_password: bool = Field(description="True when a bind password is stored.")
    warnings: list[str] = Field(
        default_factory=list, description="Non-blocking configuration risks."
    )


def _service(server: Any) -> LdapAuthService:
    return cast(LdapAuthService, server.ldap_service)


def _bad_request(exc: ValueError) -> OctopError:
    # ``detail`` must also travel in ``details``: the exception handler
    # re-localizes the message for the request locale, and a format-only kwarg
    # would be gone by then, leaving a literal ``{detail}`` in the response.
    detail = str(exc)
    return OctopError.localized(
        ErrorCode.LDAP_BAD_REQUEST, detail=detail, details={"detail": detail}
    )


@router.get(
    "/ldap/status",
    summary="LDAP login availability",
    response_model=LdapStatusResponse,
)
async def ldap_status(server: Any = Depends(get_server)) -> LdapStatusResponse:
    """Return whether directory login is available and its configured label."""
    return LdapStatusResponse.model_validate(_service(server).status())


@router.get(
    "/ldap/config",
    summary="Get LDAP directory configuration",
    response_model=LdapConfigResponse,
)
async def get_ldap_config(
    _: Any = Depends(require_permission("sso")), server: Any = Depends(get_server)
) -> LdapConfigResponse:
    """Return LDAP settings. The bind password is never included."""
    return LdapConfigResponse.model_validate(_service(server).get_config_for_admin())


@router.put(
    "/ldap/config",
    summary="Upsert LDAP directory configuration",
    response_model=LdapConfigResponse,
)
async def put_ldap_config(
    body: LdapConfigBody,
    user: User = Depends(require_permission("sso")),
    server: Any = Depends(get_server),
) -> LdapConfigResponse:
    """Create or update LDAP settings. The bind password is write-only.

    Saving a disabled provider accepts an incomplete configuration so it can be
    filled in over several visits; an enabled provider is validated in full.
    """
    try:
        saved = _service(server).put_config(
            body.model_dump(exclude_unset=True), actor=user.username
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc
    return LdapConfigResponse.model_validate(saved)


@router.post(
    "/ldap/config/test",
    summary="Test LDAP directory connectivity",
    response_model=LdapTestResponse,
)
async def test_ldap_config(
    request: Request,
    _: Any = Depends(require_permission("sso")),
    server: Any = Depends(get_server),
) -> LdapTestResponse:
    """Bind with the stored service account and probe the configured user base DN."""
    service = _service(server)
    try:
        probe = await asyncio.get_running_loop().run_in_executor(None, service.test_connection)
    except ValueError as exc:
        raise _bad_request(exc) from exc
    message = tr(f"ldap.test.{probe.code}", resolve_request_locale(request))
    if probe.detail:
        message = f"{message} ({probe.detail})"
    return LdapTestResponse(
        ok=probe.ok,
        detail=message,
        warnings=service.warnings(),
        detected_subject_attribute=probe.detected_subject_attribute,
    )
