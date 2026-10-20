"""Interactive provider setup wizard for first-run configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm, Prompt

from octop_harness.cli.providers.registry import PROVIDER_PRESETS, ProviderPreset


@dataclass
class SetupResult:
    """Result of a successful setup wizard run."""

    provider_key: str
    model_id: str

    @property
    def model_ref(self) -> str:
        """Return the fully-qualified model reference."""
        return f"{self.provider_key}/{self.model_id}"


def _detect_env_provider() -> tuple[str, str] | None:
    """Return (provider_id, api_key) if a provider is auto-detectable from env.

    Delegates to :func:`octop_harness.config.env.detect_providers_from_env`.
    Returns the first detected provider as ``(provider_id, api_key)``,
    or ``None`` if none found.
    """
    from octop_harness.config.env import detect_providers_from_env

    providers, _ = detect_providers_from_env()
    if not providers:
        return None
    first = providers[0]
    return first.id, first.api_key


def _model_config_entry(preset: ProviderPreset, model_id: str) -> dict[str, object]:
    """Build a config.json model entry from a preset model, when available."""
    for model in preset.models:
        if model.id == model_id:
            entry: dict[str, object] = {"id": model.id, "name": model.name}
            if model.input != ("text",):
                entry["input"] = list(model.input)
            if model.max_input_tokens:
                entry["max_input_tokens"] = model.max_input_tokens
            if model.effective_context_window:
                entry["context_window"] = model.effective_context_window
            if model.max_output_tokens:
                entry["max_output_tokens"] = model.max_output_tokens
            return entry
    return {"id": model_id}


def _write_provider_config(
    *,
    config_path: Path,
    provider_key: str,
    base_url: str,
    api_key: str,
    protocol: str,
    model_id: str,
    preset: ProviderPreset | None = None,
) -> None:
    """Write or merge provider configuration into config.json.

    Loads existing config (if any), adds the provider entry,
    sets default_model, creates agents.main if not present,
    and writes back to disk.
    """
    # Load existing config or start fresh
    data = json.loads(config_path.read_text()) if config_path.exists() else {}

    # Ensure providers section
    if "providers" not in data:
        data["providers"] = {}

    # Write provider entry
    model_entry = _model_config_entry(preset, model_id) if preset is not None else {"id": model_id}
    data["providers"][provider_key] = {
        "base_url": base_url,
        "api_key": api_key,
        "protocol": protocol,
        "models": [model_entry],
    }

    # Set default model
    data["default_model"] = f"{provider_key}/{model_id}"

    # Ensure agents section with a "main" agent
    if "agents" not in data:
        data["agents"] = {}
    if "main" not in data["agents"]:
        data["agents"]["main"] = {
            "provider": provider_key,
            "model": model_id,
        }

    # Set default agent
    data["default_agent"] = "main"

    # Write config
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(data, indent=2) + "\n")


def _select_from_list(prompt_text: str, options: list[str]) -> int:
    """Display a numbered list and prompt for selection.

    Returns the 0-based index of the chosen option.
    """
    console = Console()
    for i, option in enumerate(options, start=1):
        console.print(f"  {i}. {option}")

    while True:
        choice = Prompt.ask(prompt_text)
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                return idx
        except ValueError:
            pass
        console.print(f"[red]Please enter a number between 1 and {len(options)}[/red]")


def _select_model(preset: ProviderPreset) -> str:
    """Select a model from the preset.

    If the preset has only one model, returns it directly.
    Otherwise presents a selection list.
    """
    if len(preset.models) == 1:
        return preset.models[0].id

    options = [m.name for m in preset.models]
    idx = _select_from_list("Select model", options)
    return preset.models[idx].id


def _setup_custom(config_path: Path) -> SetupResult | None:
    """Run custom provider setup with free-form prompts."""
    console = Console()
    console.print("\n[bold]Custom Provider Setup[/bold]")

    provider_key = Prompt.ask("Provider key (e.g. my-provider)")
    if not provider_key:
        return None

    base_url = Prompt.ask("Base URL")
    if not base_url:
        return None

    api_key = Prompt.ask("API key", password=True)
    if not api_key:
        return None

    model_id = Prompt.ask("Model ID")
    if not model_id:
        return None

    _write_provider_config(
        config_path=config_path,
        provider_key=provider_key,
        base_url=base_url,
        api_key=api_key,
        protocol="openai",
        model_id=model_id,
    )
    return SetupResult(provider_key=provider_key, model_id=model_id)


def run_setup_wizard(config_path: Path) -> SetupResult | None:
    """Run the interactive provider setup wizard.

    Returns a SetupResult on success, or None if the user cancels.
    """
    console = Console()
    console.print("\n[bold yellow]No model provider configured.[/bold yellow]\nLet's set one up now.\n")

    # Step 1: Check environment for existing API keys
    detected = _detect_env_provider()
    if detected:
        provider_id, api_key = detected
        preset = PROVIDER_PRESETS[provider_id]
        console.print(f"[green]Detected[/green] {preset.name} (env: {preset.api_key_env})")
        if Confirm.ask(f"Use {preset.name}?", default=True):
            model_id = _select_model(preset)
            _write_provider_config(
                config_path=config_path,
                provider_key=provider_id,
                base_url=preset.base_url,
                api_key=api_key,
                protocol=preset.protocol,
                model_id=model_id,
                preset=preset,
            )
            return SetupResult(provider_key=provider_id, model_id=model_id)

    # Step 2: Show provider list
    presets = list(PROVIDER_PRESETS.values())
    options = [p.name for p in presets] + ["Custom"]
    console.print("[bold]Available providers:[/bold]")
    idx = _select_from_list("Select provider", options)

    # Custom option is last
    if idx == len(presets):
        return _setup_custom(config_path)

    preset = presets[idx]

    # Step 3: Get API key
    if preset.id == "ollama":
        api_key = "ollama"
    else:
        api_key = Prompt.ask(
            f"Enter your {preset.name} API key",
            password=True,
        )
        if not api_key:
            console.print("[red]Cancelled.[/red]")
            return None

    # Step 4: Select model
    model_id = _select_model(preset)

    # Step 5: Write config
    _write_provider_config(
        config_path=config_path,
        provider_key=preset.id,
        base_url=preset.base_url,
        api_key=api_key,
        protocol=preset.protocol,
        model_id=model_id,
        preset=preset,
    )

    console.print(f"\n[green]✓[/green] Configured [bold]{preset.name}[/bold] with model [bold]{model_id}[/bold]\n")
    return SetupResult(provider_key=preset.id, model_id=model_id)
