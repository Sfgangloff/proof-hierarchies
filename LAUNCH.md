# Launching Claude Code on this project

## First time (per machine / after fresh clone)

```bash
cd /Users/silveregangloff/Desktop/proof-hierarchies
bash bin/setup.sh                       # installs git hooks into .git/hooks/
claude --permission-mode acceptEdits
```

## Every other time

```bash
cd /Users/silveregangloff/Desktop/proof-hierarchies
claude --permission-mode acceptEdits
```

## After `git pull` that touches `.githooks/` or `bin/setup.sh`

```bash
bash bin/setup.sh
```

The hooks are *copied* into `.git/hooks/` (per-clone). Re-running `setup.sh` re-syncs them.

## What `--permission-mode acceptEdits` gives you

- Read / Edit / Write run without prompts.
- All `git`, `python3`, `modal`, `lake`, common shell tools run without prompts (allow-listed in `.claude/settings.json`).
- **You will be prompted** for: `git push`, `git commit --amend`, `pip install`, `WebFetch`, `WebSearch`.
- **Hard-blocked** (no prompt, just refused): `rm`, `sudo`, `git push --force`, `git reset --hard`, `modal volume delete`, `modal app delete`, reads of `~/.ssh` / `~/.aws` / `~/.claude/sessions`.

## Notifications (macOS)

- Glass ping → turn complete, findings ready.
- Funk ping → Claude is waiting for your input (permission prompt or question).

If notifications don't fire: System Settings → Notifications → Script Editor → enable.

## If something feels off

- `cat .claude/settings.json` — current Claude policy (allow / ask / deny).
- `ls -la .git/hooks/pre-commit .git/hooks/pre-push` — confirm git hooks installed.
- `git config --get core.hooksPath` — should be empty (we use `.git/hooks/` directly).
- `CLAUDE.md` — the behavioral rules Claude should be following.
