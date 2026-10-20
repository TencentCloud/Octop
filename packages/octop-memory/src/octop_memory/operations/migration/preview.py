"""``--dry-run`` preview rendering (5.4, D49-C).

Two output formats:

- ``"text"`` (default): human-readable terminal table.
- ``"json"``: machine-parsable structured report. Used by CI to
  validate migrations programmatically; the CLI exposes both via
  ``--report-json out.json``.

The preview module is **format-only** — it never executes anything.
It takes a :class:`migration.rename.RenamePlan` (or any future plan
type that grows the same protocol) and renders it.
"""

from __future__ import annotations

import json
from io import StringIO
from typing import Literal

from octop_memory.operations.migration.rename import RenamePlan

PreviewFormat = Literal["text", "json"]


def render_rename_plan(plan: RenamePlan, *, fmt: PreviewFormat = "text") -> str:
    """Render ``plan`` as a string ready for ``click.echo``."""
    if fmt == "json":
        return _render_json(plan)
    if fmt == "text":
        return _render_text(plan)
    raise ValueError(f"unknown preview format: {fmt!r}")


def _render_text(plan: RenamePlan) -> str:
    out = StringIO()
    out.write(f"Migration plan: {plan.mode}\n")
    out.write(f"  db:   {plan.db_path}\n")
    out.write(f"  src:  {plan.src_namespace}\n")
    out.write(f"  dst:  {plan.dst_namespace}\n")
    out.write("\n")

    if not plan.steps:
        out.write(f"(no tables found for namespace {plan.src_namespace!r})\n")
        return out.getvalue()

    # --- main table ----------------------------------------------------
    rows = [(s.src_table, s.dst_table, s.row_count, s.is_fts_shadow) for s in plan.steps]
    src_w = max(8, *(len(r[0]) for r in rows))
    dst_w = max(8, *(len(r[1]) for r in rows))

    header = f"{'src':<{src_w}}  →  {'dst':<{dst_w}}  rows  kind"
    out.write(header + "\n")
    out.write("-" * len(header) + "\n")
    for src, dst, count, is_fts in rows:
        rows_label = "—" if count < 0 else str(count)
        kind = "fts" if is_fts else "data"
        out.write(f"{src:<{src_w}}  →  {dst:<{dst_w}}  {rows_label:>4}  {kind}\n")
    out.write("\n")

    # --- conflicts -----------------------------------------------------
    if plan.conflicts:
        out.write(f"⚠ Conflicts ({len(plan.conflicts)}):\n")
        for c in plan.conflicts:
            out.write(f"  - {c}\n")
        out.write("  Use --allow-overwrite to drop these before rename.\n")
        out.write("\n")

    out.write(f"Total: {len(plan.steps)} tables, {plan.total_rows} rows.\n")
    return out.getvalue()


def _render_json(plan: RenamePlan) -> str:
    payload = {
        "mode": plan.mode,
        "db_path": str(plan.db_path),
        "src_namespace": plan.src_namespace,
        "dst_namespace": plan.dst_namespace,
        "total_rows": plan.total_rows,
        "has_conflicts": plan.has_conflicts,
        "conflicts": list(plan.conflicts),
        "steps": [
            {
                "src_table": s.src_table,
                "dst_table": s.dst_table,
                "row_count": s.row_count,
                "is_fts_shadow": s.is_fts_shadow,
            }
            for s in plan.steps
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


__all__ = ["PreviewFormat", "render_rename_plan"]
