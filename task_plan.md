# Task Plan: Windows desktop packaging audit

## Goal
Determine whether Octop can be packaged as a Windows installer/executable for non-technical users and identify concrete compatibility gaps.

## Phases
- [x] Phase 1: Define audit scope and success criteria
- [x] Phase 2: Inspect packaging, launch, subprocess, filesystem, and platform-specific code
- [x] Phase 3: Check dependencies and Windows-oriented tests/CI
- [x] Phase 4: Synthesize risks and recommend the smallest viable desktop approach

## Key Questions
1. Can the current application be frozen into a Windows executable without requiring a separate deployment?
2. Which shell commands or POSIX assumptions break on Windows?
3. What architecture gives novice Windows users a one-click experience with the least rewrite?

## Decisions Made
- This is a read-only architecture/compatibility audit; no product code will be changed.
- Findings must cite concrete repository evidence and distinguish confirmed issues from packaging unknowns.
- Recommend an embedded WebView desktop host plus a frozen local backend, delivered as an installer.
- Recommend PyInstaller `onedir` rather than a literal `onefile` executable because of Playwright, native wheels, dynamic plugins, and startup/antivirus tradeoffs.

## Errors Encountered
- Initial `uv run` could not access the default cache under sandbox restrictions; reran with a task-specific cache under `/tmp`.

## Status
**Complete** - Audit written to `windows_packaging_audit.md`; no product source changed.
