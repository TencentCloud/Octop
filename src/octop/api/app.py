"""FastAPI app factory."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from scalar_fastapi import get_scalar_api_reference

from octop.api.middleware.jwt_auth import install as install_jwt_auth
from octop.api.middleware.setup_lockdown import install as install_setup_lockdown
from octop.api.openapi_meta import API_DESCRIPTION, OPENAPI_TAGS, configure_openapi
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.server import OctopServer
from octop.infra.utils.locale import resolve_request_locale

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _RouterMount:
    router: Any
    prefix: str
    tags: Sequence[str]


def _mount_routers(app: FastAPI, mounts: Sequence[_RouterMount]) -> None:
    for spec in mounts:
        app.include_router(spec.router, prefix=spec.prefix, tags=list(spec.tags))


def _install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(OctopError)
    async def _octop(request: Request, exc: OctopError) -> JSONResponse:
        locale = resolve_request_locale(request)
        return JSONResponse(status_code=exc.status, content=exc.to_envelope(locale=locale))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled exception in %s", request.url.path)
        locale = resolve_request_locale(request)
        err = OctopError.localized(ErrorCode.INTERNAL_ERROR, locale)
        return JSONResponse(status_code=err.status, content=err.to_envelope())


def build_app(server: OctopServer) -> FastAPI:
    cfg = server.services.config if server.services else None
    enable_dashboard = cfg.enable_dashboard if cfg else True
    enable_api_docs = cfg.enable_api_docs if cfg else False

    app = FastAPI(
        title="Octop API",
        version="0.1.0",
        description=API_DESCRIPTION,
        openapi_url="/api/openapi.json" if enable_api_docs else None,
        openapi_tags=OPENAPI_TAGS,
    )
    configure_openapi(app)
    app.state.octop_server = server
    _install_exception_handlers(app)

    if cfg and cfg.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cfg.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    install_jwt_auth(app, server)
    install_setup_lockdown(app, server)

    from octop.infra.setup.tls.challenge import challenge_store

    @app.get("/.well-known/acme-challenge/{token}", include_in_schema=False)
    async def acme_http01_challenge(token: str) -> PlainTextResponse:
        body = challenge_store.get(token)
        if body is None:
            raise HTTPException(status_code=404, detail="challenge not found")
        return PlainTextResponse(body)

    from octop.api.routers import (
        acp,
        admin,
        agent_files,
        agents,
        auth,
        backup,
        browser,
        channels,
        chat,
        connectors,
        cron,
        envs,
        experts,
        health,
        i18n,
        internal_mcp,
        mbti,
        memory,
        memory_portable,
        ollama_models,
        plugins,
        preferences,
        proactive_care,
        providers,
        setup,
        skills,
        slash,
        subagents,
        terminal,
        update,
        uploads,
        usage,
        users,
        voice,
        workspace,
    )
    from octop.api.routers.filesystem import router as filesystem_router
    from octop.api.routers.observability import router as observability_router
    from octop.api.routers.providers import admin_router as admin_providers_router
    from octop.api.routers.security import router as security_router
    from octop.api.routers.storage_backends import admin_router as admin_storage_router
    from octop.api.routers.storage_backends import user_router as storage_backends_user_router
    from octop.api.routers.tls import router as tls_router
    from octop.api.routers.voice import admin_router as admin_voice_router

    _mount_routers(
        app,
        [
            _RouterMount(setup.router, "/api", ["setup"]),
            _RouterMount(auth.router, "/api/auth", ["auth"]),
            _RouterMount(preferences.router, "/api", ["auth"]),
            _RouterMount(i18n.router, "/api", ["i18n"]),
            _RouterMount(health.router, "/api/health", ["health"]),
            _RouterMount(users.router, "/api/users", ["users"]),
            _RouterMount(agents.router, "/api/agents", ["agents"]),
            _RouterMount(acp.router, "/api", ["agents"]),
            _RouterMount(chat.router, "/api", ["chat"]),
            _RouterMount(slash.router, "/api", ["slash"]),
            _RouterMount(connectors.router, "/api", ["connectors"]),
            _RouterMount(internal_mcp.router, "/api", ["internal-mcp"]),
            _RouterMount(channels.router, "/api", ["channels"]),
            _RouterMount(cron.router, "/api", ["cron"]),
            _RouterMount(envs.router, "/api", ["envs"]),
            _RouterMount(providers.router, "/api/providers", ["providers"]),
            _RouterMount(voice.router, "/api/voice", ["voice"]),
            _RouterMount(admin.router, "/api/admin", ["admin"]),
            _RouterMount(backup.router, "/api/admin", ["admin"]),
            _RouterMount(admin_providers_router, "/api/admin/providers", ["admin"]),
            _RouterMount(admin_voice_router, "/api/admin/voice/providers", ["admin"]),
            _RouterMount(observability_router, "/api/admin/observability", ["observability"]),
            _RouterMount(tls_router, "/api/admin/tls", ["tls"]),
            _RouterMount(security_router, "/api/admin/security", ["security"]),
            _RouterMount(admin_storage_router, "/api/admin/storage-backends", ["admin"]),
            _RouterMount(
                storage_backends_user_router, "/api/storage-backends", ["storage-backends"]
            ),
            _RouterMount(filesystem_router, "/api/filesystem", ["filesystem"]),
            _RouterMount(mbti.router, "/api", ["mbti"]),
            _RouterMount(experts.router, "/api", ["experts"]),
            _RouterMount(workspace.router, "/api", ["workspace"]),
            _RouterMount(agent_files.router, "/api", ["agent_files"]),
            _RouterMount(memory.router, "/api", ["memory"]),
            _RouterMount(memory_portable.router, "/api", ["memory"]),
            _RouterMount(proactive_care.router, "/api", ["proactive-care"]),
            _RouterMount(usage.router, "/api", ["usage"]),
            _RouterMount(usage.admin_router, "/api/admin", ["admin"]),
            _RouterMount(skills.router, "/api", ["skills"]),
            _RouterMount(subagents.router, "/api", ["subagents"]),
            _RouterMount(terminal.router, "/api", ["terminal"]),
            _RouterMount(uploads.router, "/api", ["chat"]),
            _RouterMount(update.router, "/api", ["update"]),
            _RouterMount(browser.router, "/api", ["browser"]),
            _RouterMount(ollama_models.router, "/api", ["ollama"]),
            _RouterMount(plugins.router, "/api", ["plugins"]),
        ],
    )

    if enable_api_docs:

        @app.get("/api/docs", include_in_schema=False)
        async def api_docs() -> HTMLResponse:
            return get_scalar_api_reference(
                openapi_url=app.openapi_url,
                title="Octop API",
            )

    if enable_dashboard:
        dashboard_dir = Path(__file__).parent.parent / "dashboard"
        index_file = dashboard_dir / "index.html"
        if index_file.exists():

            @app.get("/{full_path:path}", include_in_schema=False)
            async def spa_fallback(full_path: str) -> FileResponse:
                if full_path.startswith(("api/", "ws/")):
                    raise HTTPException(status_code=404, detail="Not Found")

                # PWA shell files must never be cached, otherwise browsers may
                # pin the old service worker or stale manifest and break updates.
                no_cache_names = {"sw.js", "manifest.json", "index.html"}

                if full_path:
                    candidate = (dashboard_dir / full_path).resolve()
                    try:
                        candidate.relative_to(dashboard_dir.resolve())
                    except ValueError:
                        return FileResponse(index_file)
                    if candidate.is_file():
                        response = FileResponse(candidate)
                        if Path(full_path).name.lower() in no_cache_names:
                            response.headers["Cache-Control"] = "no-cache"
                        return response
                response = FileResponse(index_file)
                if "index.html" in no_cache_names:
                    response.headers["Cache-Control"] = "no-cache"
                return response

    return app
