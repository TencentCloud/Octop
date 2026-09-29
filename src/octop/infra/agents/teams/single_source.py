"""Single-source scanner for team facts (batch B2 · T01).

``scan`` is a **pure read**: it walks the tree, reads text files and returns an
immutable report. It never writes a file, never touches the database and never opens a
socket -- the four-token grep gate of PLAN §6 command 12 (the file-write / SQL-write /
db-handle words) staying at **0 hits** is part of the contract, not a style note, so
even this docstring avoids spelling those tokens out.

The only process-level effect lives in :func:`main`: argv parsing, stdout and the
four-state exit door (PLAN §2.3) -- ``0`` clean, ``1`` duplicate, ``2`` usage error,
``3`` empty-green (fail-closed: a fact name that does not bite any of the five
definition shapes means "nothing was scanned", never "clean"). Every byte this module
prints goes to **stdout**, including usage text, so ``I4`` ("唯一副作用 = stdout")
stays literally true.

Fact names are matched as **substrings, with no word boundary** (SPEC R9): a Chinese
fact name inside a longer phrase still counts, which is the deliberate "宁可多算不可
零命中" trade-off. The cost is double counting, so ``--json`` always ships the
``definitions`` detail array for a human to re-check, and the empty-green code ``3``
exists precisely so that a name which matches nothing can never read as "clean".

Counts (SPEC R10, all by line):

* definition point = one ``(fact, line)`` pair in one of the five verbatim shapes below;
* reference point = one ``(fact, line)`` pair where the name appears but **no** shape
  matches -- two mentions of the same fact on one line count once;
* ``duplicate_facts`` counts facts with **two or more** definition points anywhere in
  ``root``, the authority file included (a copy inside the authority file is still a
  second definition of the same fact).
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

#: The authority file holds the one definition; ``--authority`` may rename it.
AUTHORITY_FILENAME = "AUTHORITY.md"

#: The five definition shapes, verbatim (PLAN §2.3 / SPEC R8) -- ``名`` is the fact name.
DEFINITION_FORMS: tuple[str, ...] = ("## 名", "**名**：", "| 名 | 定义 |", "「名」：", "- 名：")

EXIT_OK, EXIT_DUPLICATE, EXIT_USAGE, EXIT_EMPTY = 0, 1, 2, 3

#: Text files worth reading; anything else (images, archives, binaries) is skipped, so
#: ``scannedFiles`` counts *files actually read*, not files seen.
TEXT_SUFFIXES: frozenset[str] = frozenset(
    {
        ".md",
        ".markdown",
        ".txt",
        ".rst",
        ".py",
        ".pyi",
        ".json",
        ".toml",
        ".yaml",
        ".yml",
        ".ini",
        ".cfg",
        ".sql",
        ".sh",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".html",
        ".css",
    }
)
#: VCS metadata and tool caches -- walked past so a scan of a real checkout stays useful.
SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        ".venv",
        "node_modules",
    }
)

USAGE = (
    "usage: python -m octop.infra.agents.teams.single_source <root> "
    "--fact <名> [--fact <名> …] [--json] [--authority AUTHORITY.md]\n"
    "exit: 0 干净 · 1 见到重复 · 2 用法错 · 3 空转绿（fail-closed）"
)


@dataclass(frozen=True)
class Definition:
    """One definition point: where a fact is defined and in which of the five shapes."""

    fact: str
    path: str
    line: int
    form: str
    in_authority: bool


@dataclass(frozen=True)
class ScanReport:
    """The immutable scan result (``f(x) == f(x)``; see SPEC Q7)."""

    matched_facts: int
    defs_in_authority: int
    defs_elsewhere_total: int
    duplicate_facts: int
    refs_total: int
    scanned_files: int
    definitions: tuple[Definition, ...]


def _definition_form(line: str, fact: str) -> str | None:
    """The first of the five shapes ``line`` uses for ``fact``, else ``None``."""
    if f"## {fact}" in line:
        return DEFINITION_FORMS[0]
    if f"**{fact}**：" in line:
        return DEFINITION_FORMS[1]
    stripped = line.strip()
    if stripped.startswith("|"):
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) >= 2 and cells[0] == fact:
            return DEFINITION_FORMS[2]
    if f"「{fact}」：" in line:
        return DEFINITION_FORMS[3]
    if f"- {fact}：" in line:
        return DEFINITION_FORMS[4]
    return None


def _text_files(root: Path) -> list[Path]:
    """Every readable text file under ``root``, in a deterministic order."""
    found: list[Path] = []
    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name not in SKIP_DIRS)
        for name in sorted(filenames):
            if Path(name).suffix.lower() in TEXT_SUFFIXES:
                found.append(Path(current) / name)
    return found


def _read_text(path: Path) -> str | None:
    """File text, or ``None`` when it cannot be read (a scan never crashes on IO)."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def scan(
    root: str | Path,
    facts: Sequence[str],
    *,
    authority: str = AUTHORITY_FILENAME,
) -> ScanReport:
    """Read ``root`` once and report where each fact of ``facts`` is defined.

    Read-only and stateless: no writes, no database, no network. The keyword-only
    ``authority`` keeps the frozen two-argument signature (§2.3) call-compatible while
    letting the CLI rename the authority file.
    """
    base = Path(root)
    unique_facts = tuple(dict.fromkeys(facts))
    authority_path = Path(authority).as_posix()

    scanned: list[tuple[str, list[str]]] = []
    for path in _text_files(base):
        text = _read_text(path)
        if text is None:
            continue
        scanned.append((path.relative_to(base).as_posix(), text.splitlines()))

    definitions: list[Definition] = []
    refs_total = 0
    for fact in unique_facts:
        for relative, lines in scanned:
            in_authority = relative == authority_path
            for number, line in enumerate(lines, start=1):
                if fact not in line:
                    continue
                form = _definition_form(line, fact)
                if form is None:
                    refs_total += 1
                    continue
                definitions.append(
                    Definition(
                        fact=fact,
                        path=relative,
                        line=number,
                        form=form,
                        in_authority=in_authority,
                    )
                )

    per_fact: dict[str, int] = {}
    for definition in definitions:
        per_fact[definition.fact] = per_fact.get(definition.fact, 0) + 1

    return ScanReport(
        matched_facts=len(per_fact),
        defs_in_authority=sum(1 for d in definitions if d.in_authority),
        defs_elsewhere_total=sum(1 for d in definitions if not d.in_authority),
        duplicate_facts=sum(1 for count in per_fact.values() if count >= 2),
        refs_total=refs_total,
        scanned_files=len(scanned),
        definitions=tuple(sorted(definitions, key=lambda d: (d.fact, d.path, d.line))),
    )


def render(report: ScanReport) -> str:
    """Human-readable report: every definition point as ``文件:行号 · <form>``."""
    lines = [
        "单源化总扫："
        f"matchedFacts={report.matched_facts} defsInAuthority={report.defs_in_authority} "
        f"defsElsewhereTotal={report.defs_elsewhere_total} "
        f"duplicateFacts={report.duplicate_facts} refsTotal={report.refs_total} "
        f"scannedFiles={report.scanned_files}",
        "口径：中文事实名按**子串**匹配（无词边界，R9）；定义式 = 五种（PLAN §2.3）；"
        "引用点按 (事实, 行) 计（R10，同行两次算一次）",
    ]
    if not report.definitions:
        lines.append("- （无定义点：事实名与五种定义式都不咬合 —— 空转绿 exit 3，不得当作干净）")
        return "\n".join(lines)
    for definition in report.definitions:
        where = "权威" if definition.in_authority else "他处"
        lines.append(
            f"- {definition.path}:{definition.line} · {definition.form} · {definition.fact}（{where}）"
        )
    return "\n".join(lines)


def _as_json(report: ScanReport) -> str:
    """The six camelCase keys of SPEC A5, plus the detail array (rc never enters JSON)."""
    payload: dict[str, object] = {
        "matchedFacts": report.matched_facts,
        "defsInAuthority": report.defs_in_authority,
        "defsElsewhereTotal": report.defs_elsewhere_total,
        "duplicateFacts": report.duplicate_facts,
        "refsTotal": report.refs_total,
        "scannedFiles": report.scanned_files,
        "definitions": [
            {
                "fact": d.fact,
                "path": d.path,
                "line": d.line,
                "form": d.form,
                "inAuthority": d.in_authority,
            }
            for d in report.definitions
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False)


def _exit_code(report: ScanReport) -> int:
    """PLAN §2.3 order: duplicate (1) → empty-green (3) → clean (0)."""
    if report.duplicate_facts >= 1:
        return EXIT_DUPLICATE
    if report.matched_facts == 0 and report.defs_elsewhere_total == 0:
        return EXIT_EMPTY
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    """CLI: ``<root> --fact <名>… [--json] [--authority AUTHORITY.md]`` → exit code."""
    args = list(sys.argv[1:] if argv is None else argv)
    root: str | None = None
    facts: list[str] = []
    authority = AUTHORITY_FILENAME
    as_json = False
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--json":
            as_json = True
        elif arg in ("--fact", "--authority"):
            if index + 1 >= len(args):
                print(f"用法错：{arg} 缺少取值\n{USAGE}")
                return EXIT_USAGE
            value = args[index + 1]
            if arg == "--fact":
                facts.append(value)
            else:
                authority = value
            index += 1
        elif arg in ("-h", "--help"):
            print(USAGE)
            return EXIT_USAGE
        elif arg.startswith("-"):
            print(f"用法错：未知选项 {arg}\n{USAGE}")
            return EXIT_USAGE
        elif root is None:
            root = arg
        else:
            print(f"用法错：多余的位置参数 {arg}\n{USAGE}")
            return EXIT_USAGE
        index += 1

    if root is None:
        print(f"用法错：缺少位置参数 <root>\n{USAGE}")
        return EXIT_USAGE
    if not facts:
        print(f"用法错：至少需要一个 --fact\n{USAGE}")
        return EXIT_USAGE
    base = Path(root)
    if not base.is_dir():
        print(f"用法错：<root> 不存在或不是目录：{root}\n{USAGE}")
        return EXIT_USAGE

    report = scan(base, facts, authority=authority)
    code = _exit_code(report)
    print(_as_json(report) if as_json else render(report))
    return code


if __name__ == "__main__":  # SPEC 假设 3：入口守卫
    raise SystemExit(main())
