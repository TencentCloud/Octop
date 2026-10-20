"""Unit tests for ui/token_bar.py."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from octop_harness.cli.ui.token_bar import _format_k, format_token_bar, format_token_bar_minimal


class TestFormatK:
    def test_small_numbers(self):
        assert _format_k(0) == "0"
        assert _format_k(999) == "999"

    def test_thousands(self):
        assert _format_k(1000) == "1k"
        assert _format_k(36000) == "36k"
        assert _format_k(128000) == "128k"

    def test_millions(self):
        assert _format_k(1_000_000) == "1.0M"
        assert _format_k(2_500_000) == "2.5M"


class TestFormatTokenBar:
    def test_low_usage_green(self):
        result = format_token_bar(30000, 2000, 128000, 2.0)
        assert "[green]" in result
        assert "25%" in result
        assert "128k" in result

    def test_medium_usage_yellow(self):
        result = format_token_bar(60000, 5000, 128000, 3.0)
        assert "[yellow]" in result
        assert "50%" in result

    def test_high_usage_red(self):
        result = format_token_bar(100000, 10000, 128000, 5.0)
        assert "[red]" in result
        assert "85%" in result

    def test_elapsed_time_shown(self):
        result = format_token_bar(10000, 1000, 128000, 2.3)
        assert "2.3s" in result

    def test_zero_max_tokens_fallback(self):
        # Should not crash with max_tokens=0
        result = format_token_bar(1000, 100, 0, 1.0)
        assert "128k" in result  # falls back to 128000

    def test_progress_emojis(self):
        r1 = format_token_bar(10000, 0, 128000, 1.0)  # ~8%
        assert "◔" in r1
        r2 = format_token_bar(40000, 0, 128000, 1.0)  # ~31%
        assert "◑" in r2
        r3 = format_token_bar(80000, 0, 128000, 1.0)  # ~62%
        assert "◕" in r3
        r4 = format_token_bar(100000, 0, 128000, 1.0)  # ~78%
        assert "●" in r4


class TestFormatTokenBarMinimal:
    def test_basic(self):
        result = format_token_bar_minimal(36000, 2000, 1.5)
        assert "1.5s" in result
        assert "↑36k" in result
        assert "↓2k" in result

    def test_dim_style(self):
        result = format_token_bar_minimal(1000, 500, 0.5)
        assert "[dim]" in result
