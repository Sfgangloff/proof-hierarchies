# Modal infrastructure

All heavy compute (Lean/Mathlib env, verification, training, eval) runs on
Modal against a persistent Volume, frozen to the project pin
(`EXPERIMENT.md` §8): **Lean `v4.26.0`, Mathlib `v4.26.0` ref**.

## One-time setup (you must do the interactive auth step)

The Modal CLI lives in the project venv `.venv` (system Python 3.14 is not
Modal-compatible; `.venv` is Python 3.12, created with `uv`). Either prefix
commands with `.venv/bin/` or `source .venv/bin/activate` first.

1. CLI install (already done): `uv pip install -p .venv modal`
   → `modal client version: 1.4.2`.
2. **Interactive — run this yourself** (opens a browser to your free-tier
   account; the agent cannot authenticate for you). In a Claude Code session
   type it inline:

   ```
   ! .venv/bin/modal setup
   ```

## Build the frozen Lean/Mathlib environment (Stage 0a, physical)

```
.venv/bin/modal run modal/build_env.py::build      # slow once: clone + lake exe cache get
.venv/bin/modal run modal/build_env.py::show_pin   # prints the captured MATHLIB_COMMIT
.venv/bin/modal run modal/build_env.py::sanity     # compiles a trivial Mathlib proof
```

`build` writes `PIN.txt` (the resolved Mathlib/repl commits) to the
`proof-hierarchies-lean` Volume — that hash becomes the single source of
truth and gets copied back into `EXPERIMENT.md` §8 and memory.

## Free-tier notes

- The `build` step is the only very slow one (~5–15 GB `lake exe cache
  get`); it persists to the Volume so later runs are fast.
- Watch the free-tier CPU/RAM/time caps; `build` has a 3 h timeout set.
- If `modal` API calls error due to a version mismatch, only the decorated
  wrappers need adjusting — the shell build logic is version-independent.
