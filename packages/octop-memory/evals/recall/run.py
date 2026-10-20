"""Recall evaluation runner — P@5 / MRR over synthetic fixtures.

Two pipelines compared by default:

- **baseline**: ``recall_multi_source`` (raw FTS, no rerank).
- **candidate**: ``recall_for_prompt`` (full pipeline).

Output is per-query-class P@5 / MRR plus the overall delta. The
synthetic fixtures (see ``fixtures.py``) bias toward easy entity-
lookup queries and do not establish production recall quality. The legacy
P@5 label measures precision over the returned top five results, dividing
by the number returned rather than always by five.

Usage::

    uv run python -m evals.recall.run \\
        --baseline raw_fts --candidate full_pipeline

Programmatic entry point :func:`run` returns a :class:`EvalReport`
dataclass for unit tests / CI gating.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from evals.recall.fixtures import EvalCorpus, EvalQuery, seed_memory
from octop_memory.core import Memory
from octop_memory.pipeline.recall import RecallSnippet, recall_for_prompt, recall_multi_source
from octop_memory.storage.backends.sqlite import SqliteMemoryBackend


@dataclass
class QueryResult:
    """Per-query evaluation outcome."""

    qid: str
    klass: str
    snippets_returned: list[str]  # atom ids in result order
    expected: set[str]
    p_at_5: float
    rr: float


@dataclass
class EvalReport:
    """Full eval result. Aggregates per-class + overall metrics."""

    pipeline_name: str
    per_query: list[QueryResult] = field(default_factory=list)
    per_class: dict[str, dict[str, float]] = field(default_factory=dict)
    overall_p_at_5: float = 0.0
    overall_mrr: float = 0.0


def _ids_from_snippets(snippets: list[RecallSnippet]) -> list[str]:
    return [s.source_id for s in snippets]


def _evaluate_query(
    fn: Callable[[str, EvalQuery], list[RecallSnippet]],
    query: EvalQuery,
) -> QueryResult:
    snippets = fn(query.query, query)
    returned_ids = _ids_from_snippets(snippets)
    expected_set = set(query.expected_source_ids)

    top5 = returned_ids[:5]
    p5 = sum(1 for sid in top5 if sid in expected_set) / max(1, len(top5))

    rr = 0.0
    for idx, sid in enumerate(returned_ids):
        if sid in expected_set:
            rr = 1.0 / (idx + 1)
            break

    return QueryResult(
        qid=query.qid,
        klass=query.klass,
        snippets_returned=returned_ids,
        expected=expected_set,
        p_at_5=p5,
        rr=rr,
    )


def _aggregate(per_query: list[QueryResult]) -> tuple[dict[str, dict[str, float]], float, float]:
    by_class: dict[str, list[QueryResult]] = {}
    for r in per_query:
        by_class.setdefault(r.klass, []).append(r)
    per_class_metrics: dict[str, dict[str, float]] = {}
    for klass, results in by_class.items():
        n = len(results)
        per_class_metrics[klass] = {
            "n": float(n),
            "p_at_5": sum(r.p_at_5 for r in results) / n,
            "mrr": sum(r.rr for r in results) / n,
        }
    n_total = max(1, len(per_query))
    overall_p5 = sum(r.p_at_5 for r in per_query) / n_total
    overall_mrr = sum(r.rr for r in per_query) / n_total
    return per_class_metrics, overall_p5, overall_mrr


def run(
    corpus: EvalCorpus,
    *,
    pipeline: str = "full_pipeline",
    limit: int = 5,
) -> EvalReport:
    """Evaluate the chosen pipeline against the labeled queries.

    Pipeline choices:

    - ``"raw_fts"`` — only consult raw events.
    - ``"atom_fts"`` — atom + raw fallback, no rerank.
    - ``"full_pipeline"`` — reranked + diversified + suppressed.
    """

    def _baseline(q: str, query: EvalQuery) -> list[RecallSnippet]:
        result = recall_multi_source(corpus.memory, q, sources=("raw",), limit=limit)
        return result.snippets

    def _atom_fts(q: str, query: EvalQuery) -> list[RecallSnippet]:
        result = recall_multi_source(corpus.memory, q, sources=("atom", "raw"), limit=limit)
        return result.snippets

    def _full(q: str, query: EvalQuery) -> list[RecallSnippet]:
        result = recall_for_prompt(
            corpus.memory,
            q,
            thread_id=query.thread_id,
            limit=limit,
        )
        return result.snippets

    fn_map = {
        "raw_fts": _baseline,
        "atom_fts": _atom_fts,
        "full_pipeline": _full,
    }
    if pipeline not in fn_map:
        raise ValueError(f"unknown pipeline: {pipeline!r}; choose from {list(fn_map)}")

    per_query = [_evaluate_query(fn_map[pipeline], q) for q in corpus.queries]
    per_class, p5, mrr = _aggregate(per_query)
    return EvalReport(
        pipeline_name=pipeline,
        per_query=per_query,
        per_class=per_class,
        overall_p_at_5=p5,
        overall_mrr=mrr,
    )


def _print_report(name: str, report: EvalReport) -> None:
    print(f"\n=== {name} ({report.pipeline_name}) ===")
    print(f"{'klass':<18} {'n':>3} {'P@5':>8} {'MRR':>8}")
    for klass, m in sorted(report.per_class.items()):
        print(f"{klass:<18} {int(m['n']):>3} {m['p_at_5']:>8.3f} {m['mrr']:>8.3f}")
    print(f"{'overall':<18} {len(report.per_query):>3} {report.overall_p_at_5:>8.3f} {report.overall_mrr:>8.3f}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synthetic recall evaluation")
    parser.add_argument("--baseline", default="raw_fts", help="baseline pipeline name")
    parser.add_argument("--candidate", default="full_pipeline", help="candidate pipeline name")
    parser.add_argument("--gate-p5-delta", type=float, default=0.0, help="exit-1 if candidate P@5 < baseline + delta")
    args = parser.parse_args(argv)

    workdir = Path(tempfile.mkdtemp(prefix="eval_recall_"))
    db_path = workdir / "evals.sqlite"
    backend = SqliteMemoryBackend(namespace="eval", db_path=db_path)
    memory = Memory(namespace="eval", backend=backend)
    corpus = seed_memory(memory)

    print(f"seeded {len(corpus.queries)} queries; workdir={workdir}")

    base = run(corpus, pipeline=args.baseline)
    cand = run(corpus, pipeline=args.candidate)
    _print_report("baseline", base)
    _print_report("candidate", cand)

    delta = cand.overall_p_at_5 - base.overall_p_at_5
    print(f"\noverall P@5 delta: {delta:+.3f}")
    if delta < args.gate_p5_delta:
        print(f"GATE FAIL: delta {delta:+.3f} < required {args.gate_p5_delta:+.3f}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
