from octop.infra.agents.providers.presets import _direct_minimax_models


def test_direct_minimax_catalog_orders_flash_then_m3_with_current_limits() -> None:
    models = _direct_minimax_models()
    assert [model["id"] for model in models] == ["MiniMax-M3.1-Flash", "MiniMax-M3"]
    assert models[0]["context_window"] == 1_000_000
    assert models[0]["max_output_tokens"] == 524_288
    assert models[0]["input"] == ["text", "image", "video"]
    assert models[1]["context_window"] == 1_000_000
    assert "max_output_tokens" not in models[1]
