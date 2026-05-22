#!/bin/bash
# One-time per-clone setup: install git hooks + verify Claude Code policy.
# Run this immediately after cloning the repo.
set -e
cd "$(dirname "$0")/.."

# Wire the tracked hooks directory into git.
git config core.hooksPath .githooks
chmod +x .githooks/* 2>/dev/null || true
echo "[setup] git core.hooksPath -> .githooks"

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
