"""GATE-GUARD: static nails that keep the quality gate from being silently removed.

These checks read the repository ``Makefile`` and ``.github/workflows/ci.yml`` as
**text**. They never invoke ``make`` and never spawn a subprocess, so they stay green
on machines without Node/npm and on Linux/Windows/macOS alike: the *wiring* is what is
pinned here, not the frontend toolchain itself.

Recipe collection follows **GNU make** semantics: a blank or ``#`` comment line
inside a recipe does **not** end it — only the next statement or the end of the
file does. A purely cosmetic edit therefore cannot hide a frontend command
inside ``test``, nor fake the removal of the one in ``test-frontend``.

Pinned wiring (gate-completeness verdicts ② and ③):

* ``all``           — must wire both ``lint-frontend`` and ``test-frontend``, so
                      the ship bar cannot quietly drop a frontend leg.
* ``test-frontend`` — must exist and actually call the dashboard suite
                      (``cd <dashboard> && npm run test`` or an equivalent form).
* ``precommit``     — must run ``lint-frontend`` but must **not** run
                      ``test-frontend``: deliberate design, so the nail is
                      two-sided (adding it fails, dropping it fails).
* ``test``          — must stay backend-only (no frontend command leaks in).
* ``check-all``     — must stay at parity with ``all`` and run ``test-frontend``.
* ``ci.yml``        — every job that runs the backend gate must also reach the
                      frontend legs — on both the Linux and the Windows job
                      (GATE-VERIFY R2: CI used to run ``make lint``/``typecheck``/
                      ``test`` only, i.e. the frontend was never gated at all).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

# <repo>/tests/unit/test_gate_wiring.py -> <repo>. pathlib only: no POSIX literals,
# so the module behaves identically on Linux, macOS and Windows.
REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = REPO_ROOT / "Makefile"

# `npm run test`, but not `npm run test:watch` / `test:coverage` / `testmon`.
_FRONTEND_TEST_CMD = r"npm\s+run\s+test(?![\w:-])"

# Accepted shapes for "run the dashboard suite".
_DASHBOARD_TEST_FORMS = (
    re.compile(rf"\bcd\s+[^\s&|;]*dashboard[^\s&|;]*\s*&&[^\n]*{_FRONTEND_TEST_CMD}", re.I),
    re.compile(r"npm\s+--prefix\s+[^\s&|;]*dashboard[^\s&|;]*\s+run\s+test(?![\w:-])", re.I),
)

# Any frontend toolchain call — used to prove `test` stays backend-only.
_FRONTEND_TOOL = re.compile(r"\b(npm|pnpm|yarn|npx|vitest|eslint|prettier)\b", re.I)


def _makefile_text() -> str:
    assert MAKEFILE.is_file(), f"Makefile not found at {MAKEFILE}"
    return MAKEFILE.read_text(encoding="utf-8")


def _header(target: str) -> re.Pattern[str]:
    # `^all\s*:` never matches `format-all:`; `^test\s*:` never matches
    # `test-frontend:`; `(?!=)` keeps variable assignments (`X := y`) out.
    return re.compile(rf"^{re.escape(target)}\s*:(?!=)")


def _prerequisites(target: str) -> list[str]:
    """Prerequisite list of ``target``, with backslash continuations joined."""
    lines = _makefile_text().splitlines()
    header = _header(target)
    for start, line in enumerate(lines):
        if line.startswith("\t") or not header.match(line):
            continue
        logical, cursor = line, start
        while logical.rstrip().endswith("\\") and cursor + 1 < len(lines):
            cursor += 1
            logical = f"{logical.rstrip()[:-1]} {lines[cursor].strip()}"
        rhs = logical.split(":", 1)[1].split("#", 1)[0]
        return rhs.split()
    raise AssertionError(f"Makefile target {target!r} not found in {MAKEFILE}")


def _ends_recipe(line: str) -> bool:
    """True when ``line`` terminates a recipe under **GNU make** semantics.

    Blank lines and comment-only lines are skipped inside a recipe, so they do
    *not* end one; anything else — the next target header, a variable
    assignment, a conditional, or a non-tab line make would reject with
    "missing separator" — does.
    """
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith("#") and not line.startswith("\t")


def _recipe(target: str, makefile_text: str | None = None) -> list[str]:
    """Tab-indented recipe lines of ``target``.

    The recipe runs until the next statement (see :func:`_ends_recipe`) or the
    end of the file — **not** until the first non-tab line. Stopping at the
    first non-tab line would read a cosmetic blank/comment line as the end of
    the recipe, so a frontend command hidden behind one would slip past the
    ``test`` nail (false green) and a blank line alone would fake a failure in
    ``test-frontend`` (false red). ``makefile_text`` is injectable so regression
    tests can exercise variants without touching the repository ``Makefile``.
    """
    lines = (makefile_text if makefile_text is not None else _makefile_text()).splitlines()
    header = _header(target)
    for start, line in enumerate(lines):
        if line.startswith("\t") or not header.match(line):
            continue
        recipe: list[str] = []
        for candidate in lines[start + 1 :]:
            if _ends_recipe(candidate):
                break
            if candidate.startswith("\t"):
                recipe.append(candidate.strip())
        return recipe
    raise AssertionError(f"Makefile target {target!r} not found in {MAKEFILE}")


def test_all_depends_on_frontend_test() -> None:
    prerequisites = _prerequisites("all")
    assert "test-frontend" in prerequisites, (
        f"`all` must depend on `test-frontend` (ship bar); got {prerequisites}"
    )


def test_all_depends_on_frontend_lint() -> None:
    prerequisites = _prerequisites("all")
    assert "lint-frontend" in prerequisites, (
        f"`all` must depend on `lint-frontend` (ship bar); got {prerequisites}"
    )


def test_test_frontend_target_runs_dashboard_suite() -> None:
    recipe = _recipe("test-frontend")  # AssertionError if the target was deleted
    joined = " && ".join(recipe)
    assert any(form.search(joined) for form in _DASHBOARD_TEST_FORMS), (
        "`test-frontend` must invoke the dashboard test script "
        "(`cd <dashboard> && npm run test` or an equivalent form); "
        f"got {recipe!r}"
    )


def test_precommit_runs_frontend_lint_but_not_frontend_test() -> None:
    prerequisites = _prerequisites("precommit")
    assert "lint-frontend" in prerequisites, (
        f"`precommit` must run `lint-frontend`; got {prerequisites}"
    )
    assert "test-frontend" not in prerequisites, (
        "`precommit` must stay cheap: `test-frontend` belongs to `all`, "
        f"not to the pre-commit hook; got {prerequisites}"
    )


def test_test_target_stays_backend_only() -> None:
    recipe = _recipe("test")
    joined = " ".join(recipe)
    assert not _FRONTEND_TOOL.search(joined), (
        f"`test` must stay backend-only (no frontend command); got {recipe!r}"
    )


# ─── Regression: recipe boundaries under GNU make (GATE-REV FIND-1) ──────────
#
# Verified against real `make` on /tmp copies: `make -n test-frontend` and
# `make -n test` exit 0 both with and without an extra blank/comment line in
# the recipe — i.e. the perturbation is legal and behaviour-preserving. The
# nails must agree with make in both directions.


def _recipe_variant(
    tmp_path: Path,
    target: str,
    *,
    filler: str,
    injected: str | None = None,
) -> str:
    """Makefile *text* with an extra recipe line added to ``target``.

    The variant is materialized under ``tmp_path`` — never the repository
    ``Makefile`` — and returned as text, so the perturbation is exercised
    without touching tracked files.
    """
    lines = _makefile_text().splitlines()
    header = _header(target)
    start = next(
        i for i, line in enumerate(lines) if not line.startswith("\t") and header.match(line)
    )
    first = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("\t"))
    extra = ([filler] if filler else []) + ([f"\t{injected}"] if injected else [])
    variant = lines[: first + 1] + extra + lines[first + 1 :]
    path = tmp_path / "Makefile.variant"
    path.write_text("\n".join(variant) + "\n", encoding="utf-8")
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("filler", ["", "# cosmetic comment inside the recipe"])
def test_blank_recipe_line_in_test_frontend_stays_green(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, filler: str
) -> None:
    """A blank/comment line in `test-frontend` must not fake a red nail."""
    variant = _recipe_variant(tmp_path, "test-frontend", filler=filler)
    monkeypatch.setattr(sys.modules[__name__], "_makefile_text", lambda: variant)
    test_test_frontend_target_runs_dashboard_suite()  # must not raise


@pytest.mark.parametrize("filler", ["", "# cosmetic comment inside the recipe"])
def test_frontend_command_behind_blank_recipe_line_is_red(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, filler: str
) -> None:
    """The dashboard suite injected into `test` must fail even behind a blank line."""
    variant = _recipe_variant(
        tmp_path, "test", filler=filler, injected="cd $(DASHBOARD_DIR) && npm run test"
    )
    monkeypatch.setattr(sys.modules[__name__], "_makefile_text", lambda: variant)
    with pytest.raises(AssertionError, match="backend-only"):
        test_test_target_stays_backend_only()


# ─── Regression: CI must actually reach the frontend (GATE-VERIFY R2) ─────────
#
# `lint` / `typecheck` / `test` are backend-only, so a workflow that calls only
# those three never runs the dashboard suite. These two nails close both ends:
# `check-all` stays at parity with `all`, and the workflow text must carry the
# frontend legs in every job that runs the backend gate. Text parsing only —
# no YAML import, so the module keeps working without PyYAML.

CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

# A job entry under `jobs:`: exactly two spaces of indent and a bare `key:`.
# Top-level keys are unindented, job settings 4 spaces, steps 6+.
_JOB_HEADER = re.compile(r"^  ([A-Za-z0-9_.-]+):\s*$")


def _ci_jobs() -> dict[str, str]:
    """Map ``ci.yml`` job id -> job body text (pure text, no YAML library)."""
    assert CI_WORKFLOW.is_file(), f"CI workflow not found at {CI_WORKFLOW}"
    jobs: dict[str, str] = {}
    current: str | None = None
    in_jobs = False
    for line in CI_WORKFLOW.read_text(encoding="utf-8").splitlines():
        if not in_jobs:
            in_jobs = line.rstrip() == "jobs:"
            continue
        match = _JOB_HEADER.match(line)
        if match:
            current = match.group(1)
            jobs[current] = ""
        elif current is not None:
            jobs[current] += f"{line}\n"
    return jobs


def test_check_all_matches_all_on_the_frontend_legs() -> None:
    """`check-all` must reach the dashboard legs, exactly like `all`."""
    prerequisites = _prerequisites("check-all")
    # `lint-frontend` arrives transitively through `lint-all`; `test-frontend` has
    # no aggregator, so it must be a direct prerequisite.
    assert "lint-all" in prerequisites, (
        f"`check-all` must keep pulling `lint-all` (lint + lint-frontend); got {prerequisites}"
    )
    assert "test-frontend" in prerequisites, (
        f"`check-all` must stay at parity with `all` and run `test-frontend`; got {prerequisites}"
    )


def test_ci_reaches_the_frontend_in_every_gated_job() -> None:
    """The Linux *and* Windows CI job must invoke the frontend legs."""
    jobs = _ci_jobs()
    for job_id in ("quality", "test-windows"):
        assert job_id in jobs, f"CI job {job_id!r} vanished from {CI_WORKFLOW}; got {sorted(jobs)}"
        body = jobs[job_id]
        for target in ("lint-frontend", "test-frontend"):
            assert target in body, (
                f"`make {target}` is never invoked by CI job {job_id!r}: the "
                "dashboard would be ungated on CI (GATE-VERIFY R2)"
            )
    # Invariant: a job that runs the backend gate must also reach the frontend,
    # so a renamed/added gated job cannot silently drop the dashboard legs.
    gated = {job_id: body for job_id, body in jobs.items() if "make lint" in body}
    assert gated, "no CI job runs `make lint` — the backend gate vanished"
    for job_id, body in gated.items():
        assert "test-frontend" in body, (
            f"CI job {job_id!r} runs the backend gate but never the frontend suite"
        )
