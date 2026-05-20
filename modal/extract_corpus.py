"""
Stage 0c — batch-extract have-trees from a small Mathlib slice into the
Volume, producing per-module JSONL we can iterate the sections code on.

  .venv/bin/modal run --detach modal/extract_corpus.py::extract
  .venv/bin/modal run modal/extract_corpus.py::pull --module Mathlib.Order.Basic
"""

import pathlib
import modal

VOLUME_NAME = "proof-hierarchies-lean"
VOL_ROOT = "/lean"
NTP = f"{VOL_ROOT}/ntp-toolkit"
CORPUS = f"{VOL_ROOT}/corpus"
SRC_LOCAL = str(pathlib.Path(__file__).parent.parent / "extractor" / "ntp_module")

# Conservative first slice — small modules likely to contain tactic `have`s.
# Free-tier safe: sequential in one container, ~few minutes per module after
# warm Mathlib cache.
DEFAULT_MODULES = [
    "Mathlib.Logic.Basic",
    "Mathlib.Order.Basic",
    "Mathlib.Data.Nat.GCD.Basic",
    "Mathlib.Algebra.Order.Ring.Lemmas",
    "Mathlib.Logic.Equiv.Basic",
]

# Broader, diverse Mathlib slice for the Stage 0d gate signal.
# Names that don't exist at v4.26.0 will fail gracefully (handled per module).
BROADER_MODULES = [
    # Algebra
    "Mathlib.Algebra.Group.Basic",
    "Mathlib.Algebra.Order.Group.Defs",
    "Mathlib.Algebra.Ring.Basic",
    # Analysis
    "Mathlib.Analysis.Calculus.Deriv.Basic",
    "Mathlib.Analysis.Normed.Group.Basic",
    # Topology
    "Mathlib.Topology.Basic",
    "Mathlib.Topology.ContinuousOn",
    "Mathlib.Topology.MetricSpace.Basic",
    # Order
    "Mathlib.Order.Bounds.Basic",
    "Mathlib.Order.Lattice",
    "Mathlib.Order.WellFounded",
    # Logic / Function
    "Mathlib.Logic.Function.Basic",
    # Data
    "Mathlib.Data.Int.Basic",
    "Mathlib.Data.List.Basic",
    "Mathlib.Data.Set.Lattice",
    "Mathlib.Data.Finset.Basic",
    # Measure
    "Mathlib.MeasureTheory.MeasurableSpace.Basic",
    # Combinatorics
    "Mathlib.Combinatorics.SimpleGraph.Basic",
    # NumberTheory
    "Mathlib.NumberTheory.Divisors",
    # GroupTheory
    "Mathlib.GroupTheory.Subgroup.Basic",
    # CategoryTheory
    "Mathlib.CategoryTheory.Functor.Basic",
    # Tactic
    "Mathlib.Tactic.Linarith.Frontend",
]

app = modal.App("proof-hierarchies-extract")
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


@app.function(image=image, volumes={VOL_ROOT: vol}, timeout=60 * 60 * 2)
def extract(modules: str = ""):
    """Run `lake exe have_tree` over each module; persist to CORPUS/<mod>.jsonl.
    `modules` is a comma-separated list; empty → DEFAULT_MODULES."""
    import subprocess, os, json
    mods = [m.strip() for m in modules.split(",") if m.strip()] or DEFAULT_MODULES
    os.makedirs(CORPUS, exist_ok=True)
    summary = []
    for m in mods:
        dest = f"{CORPUS}/{m}.jsonl"
        print(f"\n=== {m} -> {dest} ===", flush=True)
        with open(dest, "w") as f:
            r = subprocess.run(["lake", "exe", "have_tree", m],
                               cwd=NTP, stdout=f, stderr=subprocess.STDOUT)
        ok = r.returncode == 0
        with open(dest) as f:
            lines = sum(1 for _ in f)
        summary.append({"module": m, "ok": ok, "decls": lines})
        print(f"   {'OK' if ok else 'FAIL'}  {lines} decls")
    with open(f"{CORPUS}/_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    vol.commit()
    print("\n=== extraction summary ===")
    print(json.dumps(summary, indent=2))


@app.function(image=image, volumes={VOL_ROOT: vol}, timeout=60 * 60 * 2)
def extract_premises(modules: str = ""):
    """Run ntp-toolkit's existing `premises` exe over each module; persist
    per-module premise edges to CORPUS/premises/<mod>.jsonl. EXPERIMENT.md
    §2 nodes = in-proof haves ∪ invoked lemmas; this provides the lemma
    edges to join with have_tree output."""
    import subprocess, os, json
    mods = [m.strip() for m in modules.split(",") if m.strip()] or DEFAULT_MODULES
    out_dir = f"{CORPUS}/premises"
    os.makedirs(out_dir, exist_ok=True)
    summary = []
    for m in mods:
        dest = f"{out_dir}/{m}.jsonl"
        print(f"\n=== premises {m} -> {dest} ===", flush=True)
        with open(dest, "w") as f:
            r = subprocess.run(["lake", "exe", "premises", m],
                               cwd=NTP, stdout=f, stderr=subprocess.STDOUT)
        ok = r.returncode == 0
        lines = sum(1 for _ in open(dest))
        summary.append({"module": m, "ok": ok, "decls": lines})
        print(f"   {'OK' if ok else 'FAIL'}  {lines} decls")
    with open(f"{out_dir}/_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    vol.commit()
    print(json.dumps(summary, indent=2))


@app.function(image=image, volumes={VOL_ROOT: vol}, timeout=60 * 60 * 3)
def extract_broader(modules: str = ""):
    """Sequential have_tree + premises over BROADER_MODULES (or CSV override).
    One Modal container, detach-safe (unlike `.map` which can't coexist with
    `--detach` — the parent disconnects and parallel inputs are cancelled)."""
    import subprocess, os, json
    mods = [m.strip() for m in modules.split(",") if m.strip()] or BROADER_MODULES
    os.makedirs(CORPUS, exist_ok=True)
    os.makedirs(f"{CORPUS}/premises", exist_ok=True)
    summary = []
    for i, m in enumerate(mods, 1):
        print(f"\n[{i}/{len(mods)}] {m}", flush=True)
        out_h = f"{CORPUS}/{m}.jsonl"
        out_p = f"{CORPUS}/premises/{m}.jsonl"
        with open(out_h, "w") as f:
            r1 = subprocess.run(["lake", "exe", "have_tree", m],
                                cwd=NTP, stdout=f, stderr=subprocess.STDOUT)
        with open(out_p, "w") as f:
            r2 = subprocess.run(["lake", "exe", "premises", m],
                                cwd=NTP, stdout=f, stderr=subprocess.STDOUT)
        rec = {
            "module": m,
            "have_ok": r1.returncode == 0,
            "premises_ok": r2.returncode == 0,
            "have_lines": sum(1 for _ in open(out_h)),
            "premises_lines": sum(1 for _ in open(out_p)),
        }
        summary.append(rec)
        print(f"   have:{rec['have_ok']}({rec['have_lines']}) "
              f"prem:{rec['premises_ok']}({rec['premises_lines']})")
        vol.commit()                       # checkpoint each module
    with open(f"{CORPUS}/_summary_broader.json", "w") as f:
        json.dump(summary, f, indent=2)
    vol.commit()
    print("\n=== summary ===")
    print(json.dumps(summary, indent=2))


@app.function(image=image, volumes={VOL_ROOT: vol}, timeout=60 * 5)
def pull(module: str = "Mathlib.Logic.Basic"):
    """Print one module's JSONL (for local inspection / quick debugging)."""
    p = f"{CORPUS}/{module}.jsonl"
    print(open(p).read())
