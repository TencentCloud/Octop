"""``octop plugin`` — install and manage plugins."""

from __future__ import annotations

import json
from pathlib import Path

import click

from octop.infra.agents.plugins.manager import PluginManager
from octop.infra.errors import OctopError
from octop.infra.utils.paths import PathLayout


@click.group()
def plugin() -> None:
    """Install and manage Octop plugins."""


def _manager() -> PluginManager:
    paths = PathLayout.from_env()
    paths.ensure_root()
    return PluginManager(plugins_dir=paths.plugins_dir, config_path=paths.config)


@plugin.command("list")
@click.pass_context
def list_plugins(ctx: click.Context) -> None:
    """List installed plugins."""
    items = _manager().list_installed()
    if ctx.obj.get("json_out"):
        click.echo(json.dumps(items, ensure_ascii=False, indent=2))
        return
    if not items:
        click.echo("No plugins installed.")
        return
    for item in items:
        if item.get("error"):
            click.echo(f"- {item['id']}: ERROR {item['error']}")
            continue
        loaded = "loaded" if item.get("loaded") else "not loaded"
        click.echo(f"- {item['id']} v{item.get('version')} ({item.get('kind')}) [{loaded}]")


@plugin.command("install")
@click.argument("source")
@click.option("--force", is_flag=True, help="Reinstall if the plugin id already exists.")
def install_plugin(source: str, force: bool) -> None:
    """Install from a local directory or ZIP URL."""
    mgr = _manager()
    path = Path(source).expanduser()
    try:
        if path.is_dir():
            loaded = mgr.install_path(path, force=force)
        elif source.startswith("http://") or source.startswith("https://"):
            loaded = mgr.install_url(source, force=force)
        else:
            raise click.ClickException(f"not a directory or URL: {source}")
    except OctopError as exc:
        raise click.ClickException(exc.message) from exc
    click.echo(f"Installed plugin {loaded.manifest.id} v{loaded.manifest.version}")


@plugin.command("uninstall")
@click.argument("plugin_id")
def uninstall_plugin(plugin_id: str) -> None:
    """Remove an installed plugin."""
    _manager().uninstall(plugin_id)
    click.echo(f"Uninstalled {plugin_id}")


@plugin.command("reload")
def reload_plugins() -> None:
    """Reload plugins from disk (offline; restart ``octop run`` to apply to agents)."""
    loaded = _manager().load_installed(install_deps=False)
    click.echo(f"Reloaded {len(loaded)} plugin(s). Restart octop run if the server is running.")
