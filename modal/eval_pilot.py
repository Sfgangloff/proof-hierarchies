"""
Stage 0.5 PILOT — end-to-end gen + verify + pass@1 on a fixed miniF2F_v2
subset (50 problems from miniF2F_v2s/test, seeded; see
`data/eval/minif2f_v2_subset.json`).

Architecture (three Modal entities, sharing the `proof-hierarchies-lean`
Volume so they see the frozen Lean v4.26.0 / Mathlib pin from Stage 0a):

1. `KiminaVerifier` — `@app.cls` on CPU. The Kimina Lean Server (FastAPI
   wrapper over Lean REPL) is installed once at image-build time via
   `image.run_commands(...)` (git clone + pip install + `prisma generate`,
   matching upstream's Dockerfile). At runtime, `@modal.enter()` just
   spawns `python -m server` from /opt/kimina-lean-server, pointing at the
   Volume's pre-built mathlib4 + repl via env vars — no Lean rebuild.
   Methods POST to `/verify` on localhost:8000.

2. `generate_zeroshot` — T4-GPU function. Loads `Qwen/Qwen2.5-0.5B`
   (the §8 scaling-down base), greedy-completes after `:= by` for a batch
   of (header, formal_statement) pairs. Pass@1, no sampling. This is the
   floor — base 0.5B with no SFT.

3. `run_pilot_baseline` — orchestrator. Loads the pinned subset, fans
   prompts into `generate_zeroshot.remote(...)`, then sends each
   (name, completion) into `KiminaVerifier.verify`, aggregates pass@1,
   writes `{VOL}/eval/pilot_baseline.json`.

This is the §9 pilot-gate harness. The criterion it tests is gate (iii):
"T4 + Kimina loop runs end-to-end on free-tier."

Usage (post `modal setup`):
    # 1. Push the pilot inputs onto the Volume (one-time):
    .venv/bin/modal volume put proof-hierarchies-lean \\
        data/eval/minif2f_v2_subset.json datasets/minif2f_v2_subset.json
    .venv/bin/modal volume put proof-hierarchies-lean \\
        data/eval/miniF2F_v2s.jsonl datasets/miniF2F_v2s.jsonl

    # 2. Smoke-test on 3 problems before the full subset (catches install /
    #    boot / REPL-fork issues for ~5 min of wall-clock):
    .venv/bin/modal run modal/eval_pilot.py::run_pilot_baseline --limit 3

    # 3. Full pilot baseline:
    .venv/bin/modal run --detach modal/eval_pilot.py::run_pilot_baseline
"""

import modal

VOLUME_NAME = "proof-hierarchies-lean"
VOL_ROOT = "/lean"
EVAL_DIR = f"{VOL_ROOT}/eval"
KIMINA_SRC = "/opt/kimina-lean-server"

# Standard miniF2F_v2s header. Pre-warmed *after* uvicorn is healthy
# (see KiminaVerifier.boot) — Kimina's built-in INIT_REPLS path has a 60s
# hardcoded prep timeout in manager.py that `import Mathlib` blows past,
# so we issue our own warmup /verify with a long timeout instead.
MINIF2F_HEADER = (
    "import Mathlib\nimport Aesop\n\nset_option maxHeartbeats 0\n\n"
    "open BigOperators Real Nat Topology Rat\n\n"
)

KIMINA_ENV = {
    "LEAN_SERVER_HOST": "127.0.0.1",
    "LEAN_SERVER_PORT": "8000",
    "LEAN_SERVER_ENVIRONMENT": "dev",
    "LEAN_SERVER_LEAN_VERSION": "v4.26.0",
    # 1 REPL is enough — we batch all codes into one /verify request and
    # rely on header-keyed reuse: split_snippet pulls `import Mathlib` out
    # of every miniF2F code as the cache key, so all N codes map to the
    # same REPL and serialize through it after the cold import.
    # More REPLs would scale memory (~8 GB each) faster than throughput.
    "LEAN_SERVER_MAX_REPLS": "1",
    # Default 60 s isn't enough: the run_checks() asyncio.gather submits N
    # codes in parallel and the (N-1) that don't grab the REPL first must
    # wait through earlier completions. Set generously above the per-batch
    # wall-clock ceiling.
    "LEAN_SERVER_MAX_WAIT": "3600",
    "LEAN_SERVER_PROJECT_DIR": f"{VOL_ROOT}/mathlib4",
    "LEAN_SERVER_REPL_PATH": f"{VOL_ROOT}/repl/.lake/build/bin/repl",
    "LEAN_SERVER_LOG_LEVEL": "INFO",
    "LEAN_SERVER_DATABASE_URL": "",
}

app = modal.App("proof-hierarchies-eval-pilot")
vol = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)

# Verifier image: Python 3.12 + elan (for any stray Lean tooling Kimina may
# invoke) + Kimina server pre-installed, mirroring the upstream Dockerfile.
verify_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git", "curl", "build-essential", "ca-certificates", "unzip", "jq")
    .run_commands(
        "curl -fsSL https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh "
        "-o /tmp/elan-init.sh",
        "sh /tmp/elan-init.sh -y --default-toolchain leanprover/lean4:v4.26.0",
    )
    .env({"PATH": "/root/.elan/bin:/usr/local/bin:/usr/bin:/bin"})
    .run_commands(
        f"git clone --depth 1 https://github.com/project-numina/kimina-lean-server.git {KIMINA_SRC}",
        f"cd {KIMINA_SRC} && pip install --no-cache-dir -r requirements.txt",
        f"cd {KIMINA_SRC} && pip install --no-cache-dir -e .",
        f"cd {KIMINA_SRC} && prisma generate",
    )
)

# Generation image: HF transformers stack, no Lean.
gen_image = modal.Image.debian_slim(python_version="3.12").pip_install(
    "torch==2.4.1",
    "transformers==4.46.3",
    "accelerate==1.1.1",
    "huggingface_hub==0.26.2",
    "safetensors>=0.4.5",
)

driver_image = modal.Image.debian_slim(python_version="3.12").pip_install(
    "requests",
)


@app.cls(
    image=verify_image,
    volumes={VOL_ROOT: vol},
    cpu=4.0,
    memory=20480,
    timeout=60 * 60 * 3,
)
class KiminaVerifier:
    @modal.enter()
    def boot(self):
        """Spawn `python -m server` from /opt/kimina-lean-server, point it at
        our Volume's mathlib4+repl via env, wait for /health to respond.

        Pre-warm via LEAN_SERVER_INIT_REPLS happens server-side and may take
        2-5 min on first boot — uvicorn is up immediately, but the warm REPL
        finishes loading Mathlib in the background. We don't block on it here
        (init_repls is fire-and-forget upstream); first /verify on a cold
        REPL will see the load tax, subsequent calls are fast.
        """
        import os, sys, subprocess, threading, time
        import requests

        os.makedirs(EVAL_DIR, exist_ok=True)

        # Sanity-check Volume paths before launching — fast-fail with a clear
        # message if the frozen Lean env isn't where we expect.
        repl_bin = KIMINA_ENV["LEAN_SERVER_REPL_PATH"]
        proj_dir = KIMINA_ENV["LEAN_SERVER_PROJECT_DIR"]
        if not os.path.exists(repl_bin):
            raise RuntimeError(f"missing REPL binary at {repl_bin}")
        if not os.path.isdir(proj_dir):
            raise RuntimeError(f"missing project dir at {proj_dir}")
        print(f"[boot] repl={repl_bin} (ok), project={proj_dir} (ok)", flush=True)

        env = {**os.environ, **KIMINA_ENV}
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "server"],
            cwd=KIMINA_SRC,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        # Drain server stdout to container logs so failures inside Kimina /
        # the REPL are visible. Without this the proc stdout buffer fills and
        # Kimina silently hangs.
        def _drain():
            assert self.proc.stdout is not None
            for line in self.proc.stdout:
                print(f"[kimina] {line.rstrip()}", flush=True)

        threading.Thread(target=_drain, daemon=True).start()

        # Probe / — uvicorn is up before any REPL work happens.
        for i in range(180):
            time.sleep(1)
            if self.proc.poll() is not None:
                raise RuntimeError(f"kimina exited rc={self.proc.returncode}")
            try:
                r = requests.get("http://127.0.0.1:8000/", timeout=2)
                if r.status_code < 500:
                    print(f"[boot] kimina healthy after {i+1}s, status={r.status_code}", flush=True)
                    break
            except Exception:
                pass
        else:
            raise RuntimeError("kimina did not become healthy within 180s")
        # No boot-time warmup: Kimina discards the warmup REPL before the
        # real batch arrives, so it just adds 5 min per cold start with no
        # caching benefit. First call to verify_batch pays the import cost.

    @modal.method()
    def verify_batch(
        self,
        codes: list[dict],
        per_snippet_timeout: int = 60,
        request_timeout_s: int = 60 * 90,
    ) -> list[dict]:
        """POST a batch of Lean source strings to Kimina in one request.

        `codes`: [{"custom_id": str, "proof": str}, ...]
        returns: parallel list of [{"custom_id", "ok", "errors", "raw"}]

        Batching matters: Kimina reuses REPLs across codes inside a single
        /verify call (header-keyed cache; all miniF2F codes share `import
        Mathlib\\nimport Aesop`) but spins fresh ones across calls — so one
        batch ⇒ one Mathlib import for the whole pilot subset.

        per_snippet_timeout overrides Kimina's 300 s default: held-out
        miniF2F proofs from a base 0.5B are either fast (rare success) or
        tactic-loops grinding past `maxHeartbeats 0` — 60 s lets the bad
        ones fail quickly instead of eating 5 min apiece.
        """
        import requests
        r = requests.post(
            "http://127.0.0.1:8000/verify",
            json={
                "codes": codes,
                "infotree_type": None,
                "timeout": per_snippet_timeout,
            },
            timeout=request_timeout_s,
        )
        r.raise_for_status()
        data = r.json()
        results = data.get("results") or data.get("data") or []
        # Index by custom_id so we can re-align with caller order regardless
        # of server-side reordering.
        by_id: dict[str, dict] = {}
        for first in results:
            resp = first.get("response") or {}
            msgs = resp.get("messages") or []
            errors = [m for m in msgs if (m.get("severity") or "").lower() == "error"]
            ok = not errors and not first.get("error")
            by_id[first.get("custom_id", "")] = {
                "custom_id": first.get("custom_id"),
                "ok": ok,
                "errors": errors,
                "raw": first,
            }
        return [by_id.get(c["custom_id"], {"custom_id": c["custom_id"], "ok": False, "errors": [{"data": "missing in response"}]}) for c in codes]

    @modal.exit()
    def shutdown(self):
        proc = getattr(self, "proc", None)
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except Exception:
                proc.kill()


@app.function(
    image=gen_image,
    gpu="T4",
    timeout=60 * 60,
    memory=12288,
)
def generate_zeroshot(
    prompts: list[dict],
    model_id: str = "Qwen/Qwen2.5-0.5B",
    max_new_tokens: int = 256,
) -> list[dict]:
    """
    prompts: [{"name": str, "header": str, "formal_statement": str}, ...]
    returns: [{"name": str, "completion": str}, ...]

    Greedy zero-shot. Continues from after `:= by` in the formal_statement.
    """
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(model_id)
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        torch_dtype=torch.float16,
        device_map="cuda",
    )
    model.eval()

    out: list[dict] = []
    for p in prompts:
        prompt_text = f"{p['header']}{p['formal_statement']}"
        inputs = tok(prompt_text, return_tensors="pt").to("cuda")
        with torch.no_grad():
            gen = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                pad_token_id=tok.pad_token_id,
            )
        full = tok.decode(gen[0], skip_special_tokens=True)
        completion = full[len(prompt_text):]
        # Stop at the next top-level declaration so we don't ship a syntax-
        # broken trailing theorem alongside the proof attempt.
        for stop in ("\n\ntheorem ", "\n\nlemma ", "\n\nexample ", "\n\ndef ", "\n\n--"):
            idx = completion.find(stop)
            if idx != -1:
                completion = completion[:idx]
        out.append({"name": p["name"], "completion": completion})
        print(f"[gen] {p['name']}: {completion[:120]!r}", flush=True)
    return out


@app.function(
    image=driver_image,
    volumes={VOL_ROOT: vol},
    timeout=60 * 60 * 2,
)
def run_pilot_baseline(limit: int = 0):
    """Drive the full pilot: load subset, generate, verify, write summary.

    limit=0 → use full 50-problem subset; limit=N → first N (sorted by name)
    for smoke-testing.
    """
    import json, os, time

    os.makedirs(EVAL_DIR, exist_ok=True)

    subset_path = f"{VOL_ROOT}/datasets/minif2f_v2_subset.json"
    rows_path = f"{VOL_ROOT}/datasets/miniF2F_v2s.jsonl"
    if not (os.path.exists(subset_path) and os.path.exists(rows_path)):
        raise RuntimeError(
            f"missing {subset_path} or {rows_path}. "
            f"`modal volume put proof-hierarchies-lean data/eval/<f> datasets/<f>` first."
        )

    subset = json.load(open(subset_path))
    names = set(subset["names"])
    if limit:
        names = set(sorted(names)[:limit])

    rows = {}
    with open(rows_path) as f:
        for line in f:
            r = json.loads(line)
            if r["name"] in names and r["split"] == "test":
                rows[r["name"]] = r
    missing = names - set(rows)
    if missing:
        raise RuntimeError(f"subset names not found in v2s/test: {sorted(missing)[:5]}")

    prompts = [
        {"name": n, "header": rows[n]["header"], "formal_statement": rows[n]["formal_statement"]}
        for n in sorted(rows)
    ]
    print(f"[driver] generating {len(prompts)} completions on T4", flush=True)
    t0 = time.time()
    gens = generate_zeroshot.remote(prompts)
    gen_seconds = time.time() - t0
    print(f"[driver] gen done in {gen_seconds:.1f}s, verifying", flush=True)

    verifier = KiminaVerifier()
    codes = [
        {
            "custom_id": g["name"],
            "proof": f"{rows[g['name']]['header']}{rows[g['name']]['formal_statement']}{g['completion']}",
        }
        for g in gens
    ]
    print(f"[driver] verifying {len(codes)} codes in one batch", flush=True)
    t1 = time.time()
    verdicts = verifier.verify_batch.remote(codes=codes)
    verify_seconds = time.time() - t1

    by_id = {v["custom_id"]: v for v in verdicts}
    results: list[dict] = []
    n_pass = 0
    for g in gens:
        name = g["name"]
        v = by_id.get(name, {"ok": False, "errors": [{"data": "missing"}]})
        if v["ok"]:
            n_pass += 1
        results.append({
            "name": name,
            "completion": g["completion"],
            "ok": v["ok"],
            "errors": v["errors"][:3],
        })
        print(f"[verify] {name}: {'PASS' if v['ok'] else 'fail'}", flush=True)

    summary = {
        "model": "Qwen/Qwen2.5-0.5B",
        "subset": subset,
        "n": len(results),
        "pass": n_pass,
        "pass@1": n_pass / max(1, len(results)),
        "gen_seconds": gen_seconds,
        "verify_seconds": verify_seconds,
    }
    suffix = f"_n{limit}" if limit else ""
    out_path = f"{EVAL_DIR}/pilot_baseline{suffix}.json"
    with open(out_path, "w") as f:
        json.dump({"summary": summary, "results": results}, f, indent=2)
    vol.commit()
    print(json.dumps(summary, indent=2))
    return summary


@app.function(
    image=driver_image,
    volumes={VOL_ROOT: vol},
    timeout=60 * 5,
)
def diagnose():
    """Fast check that the frozen Lean env is where Kimina expects it."""
    import os
    checks = {
        "mathlib4 dir": f"{VOL_ROOT}/mathlib4",
        "mathlib4 lakefile": f"{VOL_ROOT}/mathlib4/lakefile.lean",
        "repl dir": f"{VOL_ROOT}/repl",
        "repl binary": f"{VOL_ROOT}/repl/.lake/build/bin/repl",
        "pin": f"{VOL_ROOT}/PIN.txt",
        "datasets dir": f"{VOL_ROOT}/datasets",
        "subset": f"{VOL_ROOT}/datasets/minif2f_v2_subset.json",
        "v2s rows": f"{VOL_ROOT}/datasets/miniF2F_v2s.jsonl",
    }
    print("Volume layout:")
    for label, path in checks.items():
        exists = os.path.exists(path)
        kind = "dir" if exists and os.path.isdir(path) else "file" if exists else "MISSING"
        print(f"  {label}: {kind} — {path}")
    return checks
