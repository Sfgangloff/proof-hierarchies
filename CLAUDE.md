# CLAUDE.md — proof-hierarchies

Project-specific guidance that complements `.claude/settings.json` (hard
enforcement) and `.githooks/` (git-level enforcement). Permissions block
the dangerous; this file shapes everyday behavior.

## Branch hygiene

- **Work branch:** `iclr-foundation`. All current Stage 0c/0.5 work lands
  here.
- **`main` is preserved.** Never commit to it, never push to it, never
  merge to it without explicit user confirmation. `.githooks/pre-commit`
  refuses commits to `main`; `.githooks/pre-push` refuses pushes to it.
- **New feature branches:** branch from `iclr-foundation`, named
  `stage<N>-<short-slug>` (e.g. `stage0.5-qlora`).
- **Never delete branches** without explicit user request.

## Commit policy

- **Autonomous commits are allowed at clear milestones.** Use the
  `Stage NX: <imperative summary>` prefix when the change advances a
  stage; otherwise lead with a verb (`Fix …`, `Refactor …`, `Doc …`).
- Body explains the *why* in 1–3 sentences. Reference the pipeline step
  if relevant (e.g., "extract → verify → join yields 607 pairs").
- One coherent change per commit. Do not bundle unrelated work.
- Never `--amend` without confirmation. Never `git reset --hard`,
  `git rebase`, or force-push (denied by permissions).
- Always check `git status` after committing to confirm the intended
  state.

## Push policy

- `git push` is in the `ask` list — user must confirm every push. Do
  not retry past a denial; re-evaluate first.

## Modal cost discipline

Modal is on free tier; credit is finite and not auto-visible.

- Before kicking off any `--detach` extract/verify/train job, check
  `modal app list` and bail if 2+ project apps are already running.
- Prefer the smallest dry-run path: one module → one app, inspect
  result, scale up only after the small case works.
- Never call `modal volume delete`, `modal app delete`, or
  `modal token …` (denied by permissions).
- After each major Modal job, note the rough wall-clock + scope in
  the report so the user can track usage.
- If you suspect credit is low (Modal queues warn, jobs evict early,
  containers fail to start), stop and report — do not retry blindly.

## Pipeline order (Stage 0c output → 0.5 input)

Stage 0c is complete (corpus `data/corpus_v3/`, 607 verified pairs).
To regrow the corpus:

1. Edit `BROADER_MODULES` in `modal/extract_corpus.py`.
2. `modal run modal/build_have_tree.py::build_ht` (rebuild proof_terms exe).
3. `modal run --detach modal/extract_corpus.py::extract_proof_terms`
4. `modal run --detach modal/extract_corpus.py::extract_full_proofs`
5. `modal run --detach modal/verify_corpus.py::verify_all`
6. `modal volume get` pulls into `data/corpus_v3/`.
7. `python data/build_pairs.py` → updated `pairs.jsonl`.
8. `python data/build_sft.py` → updated per-policy splits.

Don't skip steps. Don't reorder. Each step writes to a directory the
next reads from.

## Scope discipline

- Don't refactor outside the current task. A bug fix doesn't need
  surrounding cleanup; a new feature doesn't need an abstraction
  layer for hypothetical future use.
- Don't add tests, docs, or scripts the user didn't ask for. The
  research repo's surface area should stay small.
- When in doubt about scope, **stop and ask**. Cost of pausing is low;
  cost of speculative scope creep is high (review burden, drift from
  user intent).
- Never delete or rename existing files without explicit confirmation,
  even if they look obsolete — the user may have unwritten plans.

## Memory

Long-term project context lives at
`~/.claude/projects/-Users-silveregangloff-Desktop-proof-hierarchies/memory/`.
- Keep `MEMORY.md` index lines short (one-line hook each).
- Update existing memory files when state changes — don't accrete
  stale entries.
- Project state changes (Stage milestones, corpus counts, gate results)
  belong in project memory; conventions and code patterns do not.

## Reports & notifications

- A macOS notification fires on every turn end (Stop hook) and on every
  permission prompt (Notification hook). Don't add more noise hooks
  without user request.
- When reporting findings, lead with the bottom line: a number, a
  decision, a status. The user reads notifications first, full output
  later.
- For long-running Modal jobs: report the app ID, expected duration,
  and one command to monitor it. Then end the turn so the user gets the
  notification and can disengage.

## Setup (first clone)

```bash
bash bin/setup.sh        # wires .githooks/ to git
cd <repo> && claude --permission-mode acceptEdits
```
