#!/usr/bin/env bash
# Assemble the standalone Hermes plugin repo from the monorepo source.
#
# Hermes `plugins install <git-url>` clones a whole repo and expects the
# plugin (plugin.yaml + __init__.py with register(ctx)) at the repo ROOT.
# Our provider lives in plugins/hermes/octopmemory/ inside the monorepo,
# so we copy the runtime files into a flat output dir ready to push as its
# own git repo (e.g. <org>/hermes-octopmemory).
#
# The provider's heavy dependency (octop-memory core) is NOT vendored —
# it is declared in plugin.yaml `pip_dependencies` and installed by Hermes
# into its own interpreter during `hermes memory setup`.
#
# Usage:
#   scripts/build-hermes-plugin.sh [OUTPUT_DIR]
# Default OUTPUT_DIR: build/hermes-octopmemory
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
src="$repo_root/plugins/hermes/octopmemory"
out="${1:-$repo_root/build/hermes-octopmemory}"

# Files that make up the installable plugin (everything except installer.py,
# which is the legacy copy+.pth path and must not ship in the plugin repo).
files=(
  __init__.py
  cli.py
  plugin.yaml
  after-install.md
  README.md
)

rm -rf "$out"
mkdir -p "$out"

for f in "${files[@]}"; do
  cp "$src/$f" "$out/$f"
done
cp "$repo_root/LICENSE" "$out/LICENSE"

echo "assembled Hermes plugin -> $out"
echo
echo "contents:"
ls -1 "$out"
echo
echo "Next: push this directory as its own git repo, then on a Hermes host:"
echo "  hermes plugins install --enable <git-url-of-that-repo>"
echo "  hermes memory setup        # select octopmemory"
echo "  hermes gateway restart"
