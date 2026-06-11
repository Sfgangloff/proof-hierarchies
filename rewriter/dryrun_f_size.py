"""Dry-run estimator for F_size(τ) over the existing corpus.

Question this answers, without spending Modal credit:
  If we shrink the frontier so that lemmas with proof-body ≤ τ tokens are
  expanded into interior nodes, how many theorems become decomposable
  (≥ 2 interior nodes)? How does depth distribute?

Inputs (local, already on disk):
  data/corpus_v3/proof_terms/*.jsonl  — elaborated proof terms (one per decl)
  data/corpus_v2/corpus/*.jsonl        — have-tree records per theorem
  data/corpus_v2/corpus/premises/*.jsonl — invoked-constant lists per theorem

The "size pool" is built from proof_terms: body_size[declName] = whitespace
token count of the elaborated term. Lemmas not in the pool stay opaque
under every τ (we cannot expand what we have not extracted) — so all
numbers below are LOWER BOUNDS on what a richer extractor pass would
expose.

  python3 -m rewriter.dryrun_f_size [--out path.json]
"""

from __future__ import annotations
import argparse, glob, json, sys
from collections import Counter
from pathlib import Path
from statistics import mean, median

from rewriter.sections import (
    ProofTree, F_named, F_size, is_user_decl, _is_user_lemma,
)


ROOT = Path(__file__).resolve().parents[1]
PROOF_TERMS_DIR = ROOT / "data/corpus_v3/proof_terms"
HAVE_TREES_DIR  = ROOT / "data/corpus_v2/corpus"
PREMISES_DIR    = ROOT / "data/corpus_v2/corpus/premises"

TAUS = [50, 100, 200, 500, 1000, 2000]


def load_size_pool() -> dict[str, int]:
    """body_size[declName] = whitespace token count of the elaborated term."""
    pool: dict[str, int] = {}
    for path in sorted(glob.glob(str(PROOF_TERMS_DIR / "*.jsonl"))):
        for line in open(path):
            line = line.strip()
            if not line: continue
            try: d = json.loads(line)
            except json.JSONDecodeError: continue
            name = d.get("declName")
            term = d.get("term", "")
            if name:
                pool[name] = len(term.split())
    return pool


def load_premises_index() -> dict[str, set[str]]:
    """decl_name → set of premise constant names actually invoked."""
    idx: dict[str, set[str]] = {}
    for path in sorted(glob.glob(str(PREMISES_DIR / "*.jsonl"))):
        for line in open(path):
            line = line.strip()
            if not line: continue
            try: d = json.loads(line)
            except json.JSONDecodeError: continue
            idx[d["name"]] = {dep["name"] for dep in d.get("dependents", [])}
    return idx


def load_have_records() -> list[dict]:
    """Each row: {module, declName, have_nodes}. User-decls only."""
    out: list[dict] = []
    for path in sorted(glob.glob(str(HAVE_TREES_DIR / "*.jsonl"))):
        for line in open(path):
            line = line.strip()
            if not line: continue
            try: d = json.loads(line)
            except json.JSONDecodeError: continue
            if "declName" not in d: continue
            if not is_user_decl(d["declName"]): continue
            out.append(d)
    return out


def interior_node_count(tree: ProofTree, tau: int | None, sizes: dict[str, int]) -> int:
    """Number of nodes that are NOT opaque leaves under the given frontier.

    Under F_named (tau=None): only have-nodes count as interior.
    Under F_size(τ): have-nodes + lemma-nodes with body_size ≤ τ."""
    have_count = len(tree.nodes)
    if tau is None:
        return have_count
    interior_lemmas = sum(
        1 for L in tree.lemma_nodes
        if (s := sizes.get(L.name)) is not None and s <= tau
    )
    return have_count + interior_lemmas


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "data/dryrun_f_size.json",
                    help="JSON summary output path")
    args = ap.parse_args()

    print("Loading size pool (proof_terms) ...", file=sys.stderr)
    sizes = load_size_pool()
    print(f"  pool: {len(sizes)} decls, "
          f"size range {min(sizes.values())}..{max(sizes.values())} tokens, "
          f"mean {mean(sizes.values()):.0f}", file=sys.stderr)

    print("Loading premises index ...", file=sys.stderr)
    premises = load_premises_index()
    print(f"  premises rows: {len(premises)}", file=sys.stderr)

    print("Loading have-tree records ...", file=sys.stderr)
    have_records = load_have_records()
    print(f"  theorems: {len(have_records)} (after dropping auto-vars)", file=sys.stderr)

    # Build one ProofTree per theorem under F_named (current default).
    trees: list[ProofTree] = []
    for hr in have_records:
        prems = premises.get(hr["declName"], set())
        # Keep ALL invoked lemmas (filtered by _is_user_lemma) — that's the
        # F_named graph. Body sizes go in metadata so the policies can pick.
        tree = ProofTree.join_with_premises(
            hr, prems, keep_only_user_lemmas=True,
            frontier=F_named, lemma_body_sizes=sizes,
            frontier_label="F_named",
        )
        trees.append(tree)

    # F_named baseline: decomposability is "≥ 2 interior nodes" where interior = haves only.
    n_total = len(trees)
    n_have_nodes = [len(t.nodes) for t in trees]
    base_decomp = sum(1 for t in trees if len(t.nodes) >= 2)
    base_one    = sum(1 for t in trees if len(t.nodes) == 1)
    base_zero   = sum(1 for t in trees if len(t.nodes) == 0)
    print(f"\nF_named baseline: {n_total} theorems")
    print(f"  haves==0: {base_zero}  ({100*base_zero/n_total:.1f}%)")
    print(f"  haves==1: {base_one}   ({100*base_one/n_total:.1f}%)")
    print(f"  haves≥2:  {base_decomp} ({100*base_decomp/n_total:.1f}%)")
    print(f"  mean haves/proof: {mean(n_have_nodes):.2f}  max: {max(n_have_nodes)}")

    # Coverage of the size pool over invoked lemmas.
    print("\nSize-pool coverage of invoked lemmas (per theorem):")
    invoked_per = [len(t.lemma_nodes) for t in trees]
    pool_covered = [
        sum(1 for L in t.lemma_nodes if L.name in sizes)
        for t in trees
    ]
    if any(invoked_per):
        mean_invoked = mean(invoked_per)
        mean_known = mean(pool_covered)
        print(f"  mean invoked lemmas / theorem: {mean_invoked:.1f}")
        print(f"  mean with body size known:    {mean_known:.1f}  "
              f"({100*mean_known/max(mean_invoked, 1e-9):.0f}% covered)")

    # Per-τ sweep.
    results = {
        "pool_size": len(sizes),
        "theorems": n_total,
        "F_named": {
            "decomposable_count": base_decomp,
            "haves_eq_0": base_zero,
            "haves_eq_1": base_one,
            "haves_ge_2": base_decomp,
        },
        "F_size_sweep": {},
    }
    print(f"\nDecomposability (≥ 2 interior nodes) per F_size(τ):")
    print(f"  {'τ':>5}  {'expandable lemmas/thm':>22}  "
          f"{'theorems with ≥1 expandable':>28}  "
          f"{'decomposable (≥2 interior)':>27}  {'Δ vs F_named':>13}")
    for tau in TAUS:
        # Per-theorem stats under F_size(τ).
        expandable_counts = [
            sum(1 for L in t.lemma_nodes
                if (s := sizes.get(L.name)) is not None and s <= tau)
            for t in trees
        ]
        n_with_expandable = sum(1 for x in expandable_counts if x >= 1)
        interior_counts = [
            interior_node_count(t, tau, sizes) for t in trees
        ]
        decomp = sum(1 for c in interior_counts if c >= 2)
        delta = decomp - base_decomp
        print(f"  {tau:>5}  {mean(expandable_counts):>22.1f}  "
              f"{n_with_expandable:>28}  {decomp:>27}  {delta:>+13}")
        results["F_size_sweep"][str(tau)] = {
            "mean_expandable_per_theorem": round(mean(expandable_counts), 2),
            "theorems_with_at_least_one_expandable": n_with_expandable,
            "decomposable_count": decomp,
            "delta_vs_F_named": delta,
        }

    # Distribution of expandable-lemma counts at the largest τ (max signal).
    big_tau = TAUS[-1]
    bigs = [
        sum(1 for L in t.lemma_nodes
            if (s := sizes.get(L.name)) is not None and s <= big_tau)
        for t in trees
    ]
    print(f"\nDistribution of expandable-lemma counts at τ={big_tau}:")
    bands = [(0,0), (1,1), (2,3), (4,7), (8,15), (16,9999)]
    for lo, hi in bands:
        c = sum(1 for x in bigs if lo <= x <= hi)
        lbl = f"{lo}" if lo == hi else (f"{lo}-{hi}" if hi < 9999 else f"{lo}+")
        bar = "█" * (c * 30 // max(n_total, 1))
        print(f"  {lbl:>6}  {c:>5}  {bar}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=2))
    print(f"\nSummary JSON written to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
