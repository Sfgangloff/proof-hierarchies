#!/bin/bash
# Per-clone setup: install git hooks + verify Claude Code policy.
# Run this after every clone AND after pulling changes to .githooks/.
#
# Why copy instead of `core.hooksPath = .githooks`: hooks must fire on
# EVERY branch, including older branches (e.g. main) that don't have
# .githooks/ in their tree. Files under .git/hooks/ are per-clone and
# branch-agnostic, so they always fire.
set -e
cd "$(dirname "$0")/.."

# Install tracked hooks into the local .git/hooks/ (overwrites).
mkdir -p .git/hooks
installed=()
for src in .githooks/*; do
  [ -f "$src" ] || continue
  dst=".git/hooks/$(basename "$src")"
  cp "$src" "$dst"
  chmod +x "$dst"
  installed+=("$(basename "$src")")
done
echo "[setup] installed git hooks: ${installed[*]}"

# Clear any stale core.hooksPath override (older docs used this).
if git config --get core.hooksPath >/dev/null 2>&1; then
  git config --unset core.hooksPath
  echo "[setup] cleared stale core.hooksPath"
fi

# Sanity: confirm the Claude policy file is present.
if [ ! -f .claude/settings.json ]; then
  echo "[setup] WARNING: .claude/settings.json missing — Claude Code will run with no project policy." >&2
fi

# Sanity: confirm we're not on main.
branch=$(git symbolic-ref --short HEAD 2>/dev/null || echo "")
if [ "$branch" = "main" ]; then
  echo "[setup] WARNING: currently on 'main'. Switch to a work branch before editing." >&2
fi

echo
echo "[setup] done. Launch Claude Code with:"
echo "  cd $(pwd) && claude --permission-mode acceptEdits"
