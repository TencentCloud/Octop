"""Provider-neutral token usage normalization tests."""

from octop_harness.usage import normalize_usage_metadata


def test_normalize_openai_cache_hit_is_disjoint() -> None:
    usage = normalize_usage_metadata(
        {
            "input_tokens": 1_000,
            "output_tokens": 80,
            "input_token_details": {"cache_read": 700},
            "output_token_details": {"reasoning": 30},
        }
    )

    assert usage == {
        "input_tokens": 1_000,
        "uncached_input_tokens": 300,
        "cache_read_tokens": 700,
        "cache_write_tokens": 0,
        "output_tokens": 80,
        "reasoning_tokens": 30,
        "total_tokens": 1_080,
    }


def test_normalize_anthropic_cache_creation_is_disjoint() -> None:
    usage = normalize_usage_metadata(
        {
            "input_tokens": 1_200,
            "output_tokens": 20,
            "input_token_details": {
                "cache_read": 800,
                "cache_creation": 250,
            },
        }
    )

    assert usage["uncached_input_tokens"] == 150
    assert usage["cache_read_tokens"] == 800
    assert usage["cache_write_tokens"] == 250
    assert usage["input_tokens"] == 1_200


def test_normalize_deepseek_wire_cache_hit() -> None:
    usage = normalize_usage_metadata(
        {
            "prompt_tokens": 900,
            "completion_tokens": 40,
            "prompt_cache_hit_tokens": 600,
        }
    )

    assert usage["uncached_input_tokens"] == 300
    assert usage["cache_read_tokens"] == 600
    assert usage["total_tokens"] == 940
