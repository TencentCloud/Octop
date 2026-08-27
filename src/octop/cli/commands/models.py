"""octop models — provider presets and resolved model list."""

from __future__ import annotations

import json as _json
import sys
from typing import Any

import click


@click.group("models")
def models() -> None:
    """Model catalog and active-model settings."""


@models.command("presets")
def presets() -> None:
    """List built-in provider templates from harness-agent."""
    from octop.cli.support.ctx import json_output_enabled
    from octop.cli.support.offline_ops import load_provider_presets_offline

    rows = load_provider_presets_offline()
    if json_output_enabled():
        click.echo(_json.dumps(rows, indent=2))
        return
    for p in rows:
        name = p.get("name") or p.get("id", "")
        kind = p.get("kind") or p.get("id", "")
        model_count = len(p.get("models") or [])
        click.echo(f"  {name} ({kind}) — {model_count} preset model(s)")


@models.command("list")
def list_models() -> None:
    """List all resolved models across enabled providers."""
    from rich.console import Console
    from rich.table import Table

    from octop.cli.support.ctx import json_output_enabled
    from octop.cli.support.offline_ops import list_resolved_models_offline

    rows = list_resolved_models_offline()
    if json_output_enabled():
        click.echo(_json.dumps(rows, indent=2))
        return
    table = Table(title="Resolved models")
    for col in ("provider", "model", "reasoning"):
        table.add_column(col)
    for m in rows:
        table.add_row(
            m.get("provider_name", ""),
            m.get("model", ""),
            str(bool(m.get("reasoning"))),
        )
    Console(file=sys.stdout).print(table)


@models.command("active")
@click.option("--provider", "provider_name", default=None)
@click.option("--model", "model_id", default=None)
def active_model(provider_name: str | None, model_id: str | None) -> None:
    """Show or set the global default model (admin)."""
    from octop.cli.support.offline_ops import get_active_model_offline, set_active_model_offline

    if provider_name and model_id:
        body = set_active_model_offline(provider_name, model_id)
        click.echo(_json.dumps(body, indent=2))
        return
    body = get_active_model_offline()
    click.echo(f"{body.get('provider_name', '?')} / {body.get('model', '?')}")


@models.command("config")
def config_models() -> None:
    """Interactively create a provider from presets and set the active model."""
    from octop.cli.support import prompts as _prompts
    from octop.cli.support.embedded_ops import probe_provider
    from octop.cli.support.offline_ops import (
        create_provider_offline,
        load_provider_presets_offline,
        set_active_model_offline,
    )
    from octop.infra.errors import OctopError

    presets = load_provider_presets_offline()
    if not presets:
        raise click.ClickException("no provider presets available")

    labels = [f"{p.get('name', p.get('id', ''))} ({p.get('id', '')})" for p in presets]
    ids = [str(p.get("id", "")) for p in presets]
    labels.append("Custom (manual kind + base URL)")
    ids.append("__custom__")

    chosen = _prompts.select("Select provider preset:", choices=labels)
    preset_id = ids[labels.index(chosen)]

    if preset_id == "__custom__":
        kind = _prompts.text("Provider kind (e.g. openai-compatible):")
        base_url = _prompts.text("Base URL:")
        display_name = _prompts.text("Provider name:", default=kind)
        models_payload: list[dict[str, Any]] = []
        while _prompts.confirm("Add a model?", default=not models_payload):
            mid = _prompts.text("Model id:")
            mname = _prompts.text("Display name:", default=mid)
            models_payload.append({"id": mid, "name": mname, "enabled": True})
        body: dict[str, Any] = {
            "name": display_name,
            "kind": kind,
            "base_url": base_url,
            "models": models_payload,
        }
    else:
        preset = presets[ids.index(preset_id)]
        display_name = _prompts.text("Provider name:", default=str(preset.get("name", preset_id)))
        base_url = preset.get("base_url") or ""
        if base_url:
            base_url = _prompts.text("Base URL:", default=base_url)
        kind = str(preset.get("kind") or preset.get("protocol") or preset_id)
        raw_models = preset.get("models") or []
        models_payload = []
        for model in raw_models:
            model_id = model.get("id") or model.get("model_id")
            if not model_id:
                continue
            # Keep preset protocol/capability metadata.  Mixed-protocol
            # providers such as OpenCode Go cannot be reconstructed from the
            # provider kind and model id alone.
            entry = dict(model)
            entry.pop("model_id", None)
            entry["id"] = model_id
            entry["name"] = model.get("name") or model_id
            entry["enabled"] = True
            models_payload.append(entry)
        body = {
            "name": display_name,
            "kind": kind,
            "base_url": base_url or None,
            "models": models_payload,
        }

    if kind != "ollama":
        api_key = _prompts.password("API key (optional):") or None
        if api_key:
            body["api_key"] = api_key

    try:
        created = create_provider_offline(
            name=str(body["name"]),
            kind=str(body["kind"]),
            base_url=body.get("base_url"),
            api_key=body.get("api_key"),
            models=body.get("models"),
        )
    except OctopError as exc:
        raise click.ClickException(exc.message) from exc
    click.echo(
        click.style(
            f"✓ Provider created: {created.get('name')} (id={created.get('id')})", fg="green"
        )
    )

    if _prompts.confirm("Test provider now?", default=True):
        pid = created.get("id")
        if pid is not None:
            result = probe_provider(int(pid))
            if result.get("ok"):
                click.echo(f"  ping ok ({result.get('latency_ms', '?')} ms)")
            else:
                click.echo(click.style("  ping failed", fg="yellow"))

    models_list = created.get("models") or models_payload
    if not models_list:
        return
    if not _prompts.confirm("Set global active model from this provider?", default=True):
        return

    model_labels = [f"{m.get('name', m.get('id', ''))} ({m.get('id', '')})" for m in models_list]
    model_ids = [str(m.get("id", "")) for m in models_list]
    pick = _prompts.select("Default model:", choices=model_labels)
    model_id = model_ids[model_labels.index(pick)]
    provider_name = str(created.get("name", ""))
    try:
        set_active_model_offline(provider_name, model_id)
    except OctopError as exc:
        raise click.ClickException(exc.message) from exc
    click.echo(f"✓ Active model: {provider_name} / {model_id}")


@models.command("ollama-list")
def ollama_list() -> None:
    """List models available in the local Ollama daemon."""
    from rich.console import Console
    from rich.table import Table

    from octop.cli.support.ctx import json_output_enabled
    from octop.infra.utils.ollama_manager import OllamaModelManager

    try:
        models_info = OllamaModelManager.list_models()
    except (ImportError, OSError) as exc:
        raise click.ClickException(str(exc)) from exc
    rows = [m.model_dump() for m in models_info]
    if json_output_enabled():
        click.echo(_json.dumps(rows, indent=2))
        return
    table = Table(title="Ollama models")
    for col in ("name", "size", "modified_at"):
        table.add_column(col)
    for m in rows:
        size = m.get("size") or 0
        size_mb = f"{size / (1024 * 1024):.0f} MB" if size else ""
        table.add_row(m.get("name", ""), size_mb, m.get("modified_at") or "")
    Console(file=sys.stdout).print(table)


@models.command("ollama-pull")
@click.argument("name")
@click.option("--wait/--no-wait", default=True, help="Block until download completes.")
def ollama_pull(name: str, wait: bool) -> None:
    """Pull an Ollama model from the local daemon."""
    from octop.infra.utils.ollama_manager import OllamaModelManager

    if not wait:
        raise click.ClickException(
            "non-blocking pull is not supported in local mode; omit --no-wait"
        )
    try:
        info = OllamaModelManager.pull_model(name)
    except (ImportError, OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(click.style(f"✓ Pulled {name}", fg="green"))
    click.echo(_json.dumps(info.model_dump(), indent=2))


@models.command("ollama-rm")
@click.argument("name")
@click.option("--yes", is_flag=True, help="Skip confirmation.")
def ollama_rm(name: str, yes: bool) -> None:
    """Delete a model from the local Ollama daemon."""
    from octop.infra.utils.ollama_manager import OllamaModelManager

    if not yes:
        click.confirm(f"Delete Ollama model {name}?", abort=True)
    try:
        OllamaModelManager.delete_model(name)
    except (ImportError, OSError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(_json.dumps({"ok": True, "name": name}, indent=2))
