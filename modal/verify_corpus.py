"""
Stage 0c verification — round-trip the PP'd proof terms.

For each module M:
  1. Load `proof_terms/<M>.jsonl` (declName, type, term).
  2. Generate `tmp_verify_<M>.lean`:
        import M
        example := <term_i>     -- one per theorem; type inferred
  3. Compile via `lake env lean`. Parse stderr for per-example errors,
     map to declNames via line markers.
  4. Persist `verify/<M>.json` = {declName: 'pass' | 'fail'}.

  .venv/bin/modal run --detach modal/verify_corpus.py::verify_one --module Mathlib.Logic.Basic
  .venv/bin/modal run --detach modal/verify_corpus.py::verify_all
"""

import modal

VOLUME_NAME = "proof-hierarchies-lean"
VOL_ROOT = "/lean"
NTP = f"{VOL_ROOT}/ntp-toolkit"
CORPUS = f"{VOL_ROOT}/corpus"
VERIFY = f"{CORPUS}/verify"

app = modal.App("proof-hierarchies-verify")
vol = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git", "curl", "build-essential", "ca-certificates")
    .run_commands(
        "curl -fsSL https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh "
        "-o /tmp/elan-init.sh",
        "sh /tmp/elan-init.sh -y --default-toolchain none",
        "/root/.elan/bin/elan toolchain install leanprover/lean4:v4.26.0",
        "/root/.elan/bin/elan default leanprover/lean4:v4.26.0",
    )
    .env({"PATH": "/root/.elan/bin:/usr/local/bin:/usr/bin:/bin"})
)


def _build_lean(module: str, terms_path: str, out_path: str) -> list[str]:
    """Generate a verify-Lean file; return parallel list of declNames."""
    import json
    names: list[str] = []
    with open(terms_path) as fin, open(out_path, "w") as fout:
        fout.write(f"-- round-trip verify for {module}\n")
        fout.write(f"import {module}\n\n")
        for line in fin:
            line = line.strip()
            if not line: continue
            try: d = json.loads(line)
            except json.JSONDecodeError: continue
            term = d.get("term", "").strip()
            if not term: continue
            i = len(names)
            names.append(d["declName"])
            # Marker comment lets us map errors back: stderr cites Lean line nums.
            fout.write(f"-- IDX:{i}  {d['declName']}\n")
            fout.write(f"example := {term}\n\n")
    return names


def _parse_results(names: list[str], file_path: str, stderr: str) -> dict:
    """Map per-line errors back to declNames using the IDX comments.
    A decl is FAIL if any error line falls between its IDX marker and the
    next one; everything else is PASS."""
    # Build line→idx map by reading the generated file.
    line_to_idx: dict[int, int] = {}
    current = -1
    with open(file_path) as f:
        for lineno, line in enumerate(f, 1):
            if line.startswith("-- IDX:"):
                try: current = int(line.split(":", 1)[1].split()[0])
                except: pass
            line_to_idx[lineno] = current
    failed = set()
    for line in stderr.splitlines():
        if "error:" not in line: continue
        # Lean errors: "<path>:<line>:<col>: error: <msg>"
        parts = line.split(":")
        if len(parts) >= 3:
            try:
                ln = int(parts[1])
                idx = line_to_idx.get(ln, -1)
                if idx >= 0: failed.add(idx)
            except ValueError: pass
    return {n: ("fail" if i in failed else "pass") for i, n in enumerate(names)}


@app.function(image=image, volumes={VOL_ROOT: vol}, timeout=60 * 40)
def verify_one(module: str = "Mathlib.Logic.Basic"):
    import subprocess, os, json
    terms = f"{CORPUS}/proof_terms/{module}.jsonl"
    if not os.path.exists(terms):
        print(f"[skip] no proof_terms for {module}")
        return {"module": module, "ok": False, "reason": "no proof_terms"}
    os.makedirs(VERIFY, exist_ok=True)
    out_lean = f"{NTP}/_verify_{module.replace('.', '_')}.lean"
    names = _build_lean(module, terms, out_lean)
    print(f"[{module}] {len(names)} examples → {out_lean}")
    r = subprocess.run(["lake", "env", "lean", out_lean],
                       cwd=NTP, capture_output=True, text=True, timeout=60*30)
    results = _parse_results(names, out_lean, (r.stderr or "") + (r.stdout or ""))
    n_pass = sum(1 for v in results.values() if v == "pass")
    summary = {
        "module": module, "total": len(names), "pass": n_pass,
        "fail": len(names) - n_pass, "compile_rc": r.returncode,
    }
    with open(f"{VERIFY}/{module}.json", "w") as f:
        json.dump({"summary": summary, "results": results}, f, indent=2)
    vol.commit()
    print(json.dumps(summary, indent=2))
    return summary


@app.function(image=image, volumes={VOL_ROOT: vol}, timeout=60 * 60 * 4)
def verify_all():
    """Sequential verify over all modules with proof_terms data."""
    import os, json, glob, subprocess
    # Inline the per-module work to avoid nested .remote() under --detach.
    paths = sorted(glob.glob(f"{CORPUS}/proof_terms/*.jsonl"))
    overall = []
    os.makedirs(VERIFY, exist_ok=True)
    for p in paths:
        module = os.path.basename(p).removesuffix(".jsonl")
        out_lean = f"{NTP}/_verify_{module.replace('.', '_')}.lean"
        names = _build_lean(module, p, out_lean)
        if not names:
            overall.append({"module": module, "total": 0, "pass": 0, "fail": 0})
            continue
        print(f"\n[{module}] {len(names)} examples", flush=True)
        r = subprocess.run(["lake", "env", "lean", out_lean],
                           cwd=NTP, capture_output=True, text=True, timeout=60*30)
        results = _parse_results(names, out_lean, (r.stderr or "") + (r.stdout or ""))
        n_pass = sum(1 for v in results.values() if v == "pass")
        s = {"module": module, "total": len(names), "pass": n_pass,
             "fail": len(names) - n_pass, "compile_rc": r.returncode}
        overall.append(s)
        with open(f"{VERIFY}/{module}.json", "w") as f:
            json.dump({"summary": s, "results": results}, f, indent=2)
        print(f"   pass {n_pass}/{len(names)}  rc={r.returncode}")
        vol.commit()
    with open(f"{VERIFY}/_overall.json", "w") as f:
        json.dump(overall, f, indent=2)
    vol.commit()
    print("\n=== overall ===")
    print(json.dumps(overall, indent=2))
