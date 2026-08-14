"""Security policy configuration API (admin)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from harness_agent.security.models import DEFAULT_HITL_TOOLS, SecurityPolicy
from pydantic import BaseModel, Field

from octop.api.deps import get_server, require_permission
from octop.i18n.domains.tools import hitl_tool_catalog
from octop.infra.db.repos.audit import ACTOR_ADMIN

router = APIRouter()


class SecurityPolicyBody(BaseModel):
    hitl: dict[str, Any] | None = None
    filesystem: dict[str, Any] | None = None
    pii: dict[str, Any] | None = None
    skill_scan: dict[str, Any] | None = None
    tool_guard: dict[str, Any] | None = None


class SecurityPolicyResponse(BaseModel):
    hitl: dict[str, Any]
    filesystem: dict[str, Any]
    pii: dict[str, Any]
    skill_scan: dict[str, Any]
    tool_guard: dict[str, Any]


def _to_response(policy: SecurityPolicy) -> SecurityPolicyResponse:
    data = policy.to_dict()
    return SecurityPolicyResponse(
        hitl=data["hitl"],
        filesystem=data["filesystem"],
        pii=data["pii"],
        skill_scan=data["skill_scan"],
        tool_guard=data["tool_guard"],
    )


@router.get("", summary="Get global security policy")
async def get_security_policy(
    _: Any = Depends(require_permission("security")),
    server: Any = Depends(get_server),
) -> SecurityPolicyResponse:
    return _to_response(server.app_runtime.agent_registry.security.load())


@router.put("", summary="Update global security policy")
async def put_security_policy(
    body: SecurityPolicyBody,
    _: Any = Depends(require_permission("security")),
    server: Any = Depends(get_server),
) -> SecurityPolicyResponse:
    current = server.app_runtime.agent_registry.security.load().to_dict()
    payload = {**current}
    if body.hitl is not None:
        payload["hitl"] = {**current.get("hitl", {}), **body.hitl}
    if body.filesystem is not None:
        payload["filesystem"] = {**current.get("filesystem", {}), **body.filesystem}
    if body.pii is not None:
        payload["pii"] = {**current.get("pii", {}), **body.pii}
    if body.skill_scan is not None:
        payload["skill_scan"] = {**current.get("skill_scan", {}), **body.skill_scan}
    if body.tool_guard is not None:
        payload["tool_guard"] = {**current.get("tool_guard", {}), **body.tool_guard}
    policy = server.app_runtime.agent_registry.save_security(payload)
    server.services.audit_repo.write(
        actor=ACTOR_ADMIN,
        action="security.policy.update",
        target="global",
    )
    return _to_response(policy)


class ToolGuardRuleItem(BaseModel):
    id: str
    tools: list[str]
    params: list[str]
    category: str
    severity: str
    description: str
    remediation: str = ""
    patterns: list[str]
    exclude_patterns: list[str] = Field(default_factory=list)


class ToolGuardRulesResponse(BaseModel):
    rules: list[ToolGuardRuleItem]
    path: str = Field(description="User-editable rules file path")
    rule_count: int


class ToolGuardRulesRawResponse(BaseModel):
    path: str
    content: str


class ToolGuardRulesRawBody(BaseModel):
    content: str


class ToolGuardRulesSaveResponse(BaseModel):
    path: str
    rule_count: int


class HitlToolCatalogItem(BaseModel):
    name: str
    label_zh: str
    label_en: str


class SecurityDefaultsResponse(BaseModel):
    hitl_tools: list[str]
    hitl_tool_catalog: list[HitlToolCatalogItem]
    tool_guard_rules: list[ToolGuardRuleItem]


def _rules_store(server: Any) -> Any:
    return server.app_runtime.agent_registry.tool_guard_rules


@router.get("/tool-guard/rules", summary="List active command guard rules")
async def get_tool_guard_rules(
    _: Any = Depends(require_permission("security")),
    server: Any = Depends(get_server),
) -> ToolGuardRulesResponse:
    store = _rules_store(server)
    raw = store.list_catalog()
    rules = [ToolGuardRuleItem(**item) for item in raw]
    return ToolGuardRulesResponse(
        rules=rules,
        path=store.display_path(),
        rule_count=len(rules),
    )


@router.get("/tool-guard/rules/raw", summary="Get editable command guard rules YAML")
async def get_tool_guard_rules_raw(
    _: Any = Depends(require_permission("security")),
    server: Any = Depends(get_server),
) -> ToolGuardRulesRawResponse:
    store = _rules_store(server)
    return ToolGuardRulesRawResponse(path=store.display_path(), content=store.read_text())


@router.put("/tool-guard/rules/raw", summary="Save command guard rules YAML")
async def put_tool_guard_rules_raw(
    body: ToolGuardRulesRawBody,
    _: Any = Depends(require_permission("security")),
    server: Any = Depends(get_server),
) -> ToolGuardRulesSaveResponse:
    store = _rules_store(server)
    registry = server.app_runtime.agent_registry
    count, errors = store.save_text(body.content)
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})
    registry.reload_harness_agents()
    server.services.audit_repo.write(
        actor=ACTOR_ADMIN,
        action="security.tool_guard_rules.update",
        target=store.display_path(),
        payload=f"rules={count}",
    )
    return ToolGuardRulesSaveResponse(path=store.display_path(), rule_count=count)


@router.post("/tool-guard/rules/reset", summary="Reset command guard rules to shipped defaults")
async def post_tool_guard_rules_reset(
    _: Any = Depends(require_permission("security")),
    server: Any = Depends(get_server),
) -> ToolGuardRulesRawResponse:
    store = _rules_store(server)
    registry = server.app_runtime.agent_registry
    content = store.reset_to_bundled()
    registry.reload_harness_agents()
    server.services.audit_repo.write(
        actor=ACTOR_ADMIN,
        action="security.tool_guard_rules.reset",
        target=store.display_path(),
    )
    return ToolGuardRulesRawResponse(path=store.display_path(), content=content)


@router.get("/defaults", summary="Security defaults and active rule catalogs")
async def get_security_defaults(
    _: Any = Depends(require_permission("security")),
    server: Any = Depends(get_server),
) -> SecurityDefaultsResponse:
    store = _rules_store(server)
    raw = store.list_catalog()
    return SecurityDefaultsResponse(
        hitl_tools=list(DEFAULT_HITL_TOOLS),
        hitl_tool_catalog=[
            HitlToolCatalogItem(name=e.name, label_zh=e.label_zh, label_en=e.label_en)
            for e in hitl_tool_catalog()
        ],
        tool_guard_rules=[ToolGuardRuleItem(**item) for item in raw],
    )
