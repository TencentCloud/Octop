"""Installer CLI for the OctopMemory Hermes provider package."""

from __future__ import annotations

import shutil
from pathlib import Path

import click
from octopmemory.install_lib import (
    DEFAULT_HERMES_HOME,
    PLUGIN_ID,
    REQUIRED_PLUGIN_FILES,
    activate_provider,
    hermes_venv_python,
    missing_plugin_files,
    python_can_import_octop_memory,
    python_site_packages,
    read_memory_provider,
)

import octop_memory


@click.group()
def main() -> None:
    """Install / inspect the OctopMemory Hermes provider."""


@main.command(name="install")
@click.option(
    "--hermes-home",
    type=click.Path(file_okay=False, path_type=Path),
    default=DEFAULT_HERMES_HOME,
    show_default=True,
    help="Hermes home directory containing config.yaml.",
)
@click.option(
    "--hermes-source",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Hermes source checkout. Defaults to <hermes-home>/hermes-agent.",
)
@click.option(
    "--source-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="This provider's source directory. Defaults to the directory installer.py lives in.",
)
@click.option("--force", is_flag=True, default=False, help="Replace an existing octopmemory provider directory.")
@click.option(
    "--write-pth/--no-write-pth",
    default=True,
    show_default=True,
    help="Best-effort: add the installed octop_memory package location to Hermes venv via a .pth file.",
)
def install_cmd(
    hermes_home: Path,
    hermes_source: Path | None,
    source_dir: Path | None,
    force: bool,
    write_pth: bool,
) -> None:
    """Install this provider package into Hermes and activate it."""
    hermes_home = hermes_home.expanduser().resolve()
    hermes_source = (hermes_source or hermes_home / "hermes-agent").expanduser().resolve()
    source_dir = (source_dir or Path(__file__).resolve().parent).expanduser().resolve()
    dest = hermes_source / "plugins" / "memory" / PLUGIN_ID

    _validate_source_dir(source_dir)
    if dest.exists():
        if not force:
            raise click.UsageError(f"provider directory already exists: {dest}; pass --force to replace it")
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        source_dir,
        dest,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "installer.py"),
    )

    hermes_home.mkdir(parents=True, exist_ok=True)
    config_path = hermes_home / "config.yaml"
    backup_path = activate_provider(config_path)

    click.echo(f"installed {source_dir} -> {dest}")
    if backup_path is not None:
        click.echo(f"backed up {config_path} -> {backup_path}")
    click.echo(f"set memory.provider = {PLUGIN_ID}")

    if write_pth:
        _write_octop_memory_path_hint(hermes_source)

    click.echo("")
    click.echo(f"Verify: octop-memory-hermes doctor --hermes-home {hermes_home} --hermes-source {hermes_source}")


@main.command(name="doctor")
@click.option(
    "--hermes-home",
    type=click.Path(file_okay=False, path_type=Path),
    default=DEFAULT_HERMES_HOME,
    show_default=True,
)
@click.option(
    "--hermes-source",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Hermes source checkout. Defaults to <hermes-home>/hermes-agent.",
)
def doctor_cmd(hermes_home: Path, hermes_source: Path | None) -> None:
    """Check whether the OctopMemory Hermes provider is installed and active."""
    hermes_home = hermes_home.expanduser().resolve()
    hermes_source = (hermes_source or hermes_home / "hermes-agent").expanduser().resolve()
    plugin_dir = hermes_source / "plugins" / "memory" / PLUGIN_ID
    config_path = hermes_home / "config.yaml"
    failed: list[str] = []

    def ok(msg: str) -> None:
        click.echo(f"  [OK]   {msg}")

    def fail(msg: str) -> None:
        click.echo(f"  [FAIL] {msg}")
        failed.append(msg)

    def warn(msg: str) -> None:
        click.echo(f"  [WARN] {msg}")

    click.echo(f"Checking {config_path} ...")
    if not config_path.exists():
        fail(f"Hermes config not found: {config_path}")
    else:
        provider = read_memory_provider(config_path.read_text(encoding="utf-8"))
        if provider == PLUGIN_ID:
            ok(f"memory.provider = {PLUGIN_ID}")
        elif provider is None:
            fail("memory.provider is unset (run `octop-memory-hermes install`)")
        else:
            fail(f"memory.provider = {provider!r}, not {PLUGIN_ID!r}")

    click.echo(f"\nChecking {plugin_dir} ...")
    if not plugin_dir.exists():
        fail(f"provider directory missing: {plugin_dir}")
    else:
        ok(f"provider directory exists ({plugin_dir})")
        for name in REQUIRED_PLUGIN_FILES:
            path = plugin_dir / name
            if path.exists():
                ok(f"{name} exists")
            else:
                fail(f"{name} missing: {path}")

    click.echo("\nChecking Hermes Python environment ...")
    hermes_python = hermes_venv_python(hermes_source)
    if not hermes_python.exists():
        warn(f"Hermes venv python not found: {hermes_python}")
    elif python_can_import_octop_memory(hermes_python):
        ok("Hermes Python can import octop_memory")
    else:
        fail(f"Hermes Python cannot import octop_memory: {hermes_python}")

    click.echo("")
    if failed:
        click.echo(f"{len(failed)} check(s) failed.")
        raise click.exceptions.Exit(1)
    click.echo("All required checks passed.")


def _validate_source_dir(source_dir: Path) -> None:
    missing = missing_plugin_files(source_dir)
    if missing:
        missing_text = ", ".join(missing)
        raise click.UsageError(f"invalid OctopMemory Hermes provider source {source_dir}; missing: {missing_text}")


def _write_octop_memory_path_hint(hermes_source: Path) -> None:
    hermes_python = hermes_venv_python(hermes_source)
    if not hermes_python.exists():
        return
    package_root = Path(octop_memory.__file__).resolve().parents[1]
    site_packages = python_site_packages(hermes_python)
    if site_packages is None:
        return
    pth = site_packages / "octopmemory-octop-memory.pth"
    pth.write_text(str(package_root) + "\n", encoding="utf-8")
    click.echo(f"added {package_root} to Hermes Python path ({pth})")


if __name__ == "__main__":
    main()
