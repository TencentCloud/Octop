"""Unit tests for the harness_memory recall-quality patch (infra/agents/memory_recall_patch).

The patch monkey-patches three symbols inside the upstream ``harness-memory``
package at startup, so these tests only assert the wiring contract: the three
symbols are replaced, the originals are kept as the fallback, and a second call
is a no-op. The patched behaviour itself is covered by the memory eval corpus,
not here.
"""

from __future__ import annotations

import harness_memory.pipeline.recall.multi_source as multi_source
import harness_memory.pipeline.recall.router as router

from octop.infra.agents import memory_recall_patch as patch


def test_apply_patches_the_three_recall_symbols():
    """router.route + the two multi_source helpers are replaced, originals kept."""
    patch.apply_memory_recall_patch()

    assert router.route is patch._patched_route
    assert multi_source._per_token_atom_search is patch._patched_per_token_atom_search
    assert multi_source._gather_atoms is patch._patched_gather_atoms

    # The upstream implementations stay reachable as the fallback path.
    assert router._orig_route is not patch._patched_route
    assert multi_source._orig_per_token_atom_search is not patch._patched_per_token_atom_search
    assert multi_source._orig_gather_atoms is not patch._patched_gather_atoms


def test_apply_is_idempotent():
    """A second call must not re-wrap the originals (that would nest the patch)."""
    patch.apply_memory_recall_patch()
    original_route = router._orig_route
    original_gather = multi_source._orig_gather_atoms

    patch.apply_memory_recall_patch()

    assert router._orig_route is original_route
    assert multi_source._orig_gather_atoms is original_gather
    assert router.route is patch._patched_route
