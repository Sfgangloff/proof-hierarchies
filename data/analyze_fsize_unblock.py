"""Does the F_size re-extraction unblock actually add NAMED-SUBGOAL supply?

Question this answers WITHOUT spending Modal credit:
  Three answers in the reasoning graph (the q-0008 length unblock and the
  q-0009 section-predictor unblock) both point at the SAME remedy: re-extract
  proofs with a shrunk expansion frontier F_size, "which e-0004 showed raises
  decomposable counts." That is the single load-bearing recommendation behind
  every proposed Modal spend. This script tests whether it actually delivers
  what q-0009 needs.

  The subtlety: e-0004's F_size "decomposability" counts INTERIOR NODES =
  have-nodes + expandable library-lemma nodes (see dryrun_f_size.py,
  interior_node_count). In that function the have-node contribution is
  TAU-INVARIANT; the entire F_size delta comes from library lemmas becoming
  visible. But q-0009's section-predictor must EMIT a named subgoal frontier
  -- i.e. the `have` statements (each carrying a ppType). Library-lemma
  citations are not subgoals the predictor invents; the rough policy already
  names them.

  So: when F_size raises "decomposable count", how much of that rise is
  genuine named-subgoal supply (>=2 have-nodes) vs merely library-lemma
  citations (<2 have-nodes, pushed over the >=2-interior bar by lemmas)?
  If the have-driven part is flat across tau, then F_size CANNOT unblock
  q-0009: the named-subgoal supply is structurally fixed at the ~4% ceiling
  regardless of frontier size.

Inputs (local, already on disk) -- identical to rewriter/dryrun_f_size.py:
  data/corpus_v3/proof_terms/*.jsonl      -- elaborated proof terms (size pool)
  data/corpus_v2/corpus/*.jsonl            -- have-tree records per theorem
  data/corpus_v2/corpus/premises/*.jsonl   -- invoked-constant lists
  data/corpus_v3/pairs.jsonl               -- the 607 VERIFIED decl names

  python3 -m data.analyze_fsize_unblock [--out path.json]
"""

from __future__ import annotations
import argparse, glob, json, sys
from pathlib import Path
from statistics import mean

from rewriter.sections import ProofTree, F_named, is_user_decl

# Reuse the exact loaders the dryrun uses so numbers are comparable.
from rewriter.dryrun_f_size import (
    load_size_pool, load_premises_index, load_have_records, TAUS,
)

ROOT = Path(__file__).resolve().parents[1]
PAIRS = ROOT / "data/corpus_v3/pairs.jsonl"


def load_verified_declnames() -> set[str]:
    names: set[str] = set()
    for line in open(PAIRS):
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        if d.get("declName"):
            names.add(d["declName"])
    return names


def expandable_lemma_count(tree: ProofTree, tau: int, sizes: dict[str, int]) -> int:
    return sum(
        1 for L in tree.lemma_nodes
        if (s := sizes.get(L.name)) is not None and s <= tau
    )


def analyze(trees: list[ProofTree], sizes: dict[str, int], label: str) -> dict:
    n_total = len(trees)
    # have-driven supply is TAU-INVARIANT by construction.
    have_ge2 = sum(1 for t in trees if len(t.nodes) >= 2)
    have_ge1 = sum(1 for t in trees if len(t.nodes) >= 1)

    sweep = {}
    for tau in TAUS:
        decomposable = 0          # >=2 interior (have + expandable lemmas)
        have_driven = 0           # decomposable AND already >=2 have-nodes
        lemma_assisted = 0        # decomposable but <2 have-nodes (lemmas pushed it over)
        for t in trees:
            h = len(t.nodes)
            interior = h + expandable_lemma_count(t, tau, sizes)
            if interior >= 2:
                decomposable += 1
                if h >= 2:
                    have_driven += 1
                else:
                    lemma_assisted += 1
        sweep[str(tau)] = {
            "decomposable": decomposable,
            "have_driven": have_driven,          # == have_ge2, by construction
            "lemma_assisted": lemma_assisted,
        }

    return {
        "label": label,
        "n_total": n_total,
        "named_subgoal_supply_tau_invariant": {
            "have_ge1": have_ge1,
            "have_ge2": have_ge2,
            "pct_have_ge2": round(100 * have_ge2 / n_total, 1) if n_total else 0.0,
        },
        "F_size_sweep": sweep,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path,
                    default=ROOT / "data/corpus_v3/fsize_unblock.json")
    args = ap.parse_args()

    sizes = load_size_pool()
    premises = load_premises_index()
    have_records = load_have_records()
    verified = load_verified_declnames()

    # Build one ProofTree per theorem under F_named (same as the dryrun).
    all_trees: list[ProofTree] = []
    verified_trees: list[ProofTree] = []
    for hr in have_records:
        prems = premises.get(hr["declName"], set())
        tree = ProofTree.join_with_premises(
            hr, prems, keep_only_user_lemmas=True,
            frontier=F_named, lemma_body_sizes=sizes, frontier_label="F_named",
        )
        all_trees.append(tree)
        if hr["declName"] in verified:
            verified_trees.append(tree)

    full = analyze(all_trees, sizes, "all_have_records_1715")
    ver = analyze(verified_trees, sizes, "verified_607")

    report = {
        "taus": TAUS,
        "full": full,
        "verified": ver,
        "n_verified_matched": len(verified_trees),
        "n_verified_total": len(verified),
    }

    # ---- human-readable ----
    for blk in (full, ver):
        n = blk["n_total"]
        inv = blk["named_subgoal_supply_tau_invariant"]
        print(f"\n=== {blk['label']}  (n={n}) ===")
        print(f"NAMED-SUBGOAL supply (have-nodes), TAU-INVARIANT:")
        print(f"  have>=1: {inv['have_ge1']}   have>=2: {inv['have_ge2']} "
              f"({inv['pct_have_ge2']}%)  <-- q-0009 section-predictor target")
        print(f"\n  {'tau':>5}  {'decomposable':>12}  {'have-driven':>11}  "
              f"{'lemma-assisted':>14}  {'%decomp that is lemma-only':>27}")
        for tau in TAUS:
            s = blk["F_size_sweep"][str(tau)]
            pct_lemma = (100 * s["lemma_assisted"] / s["decomposable"]
                         if s["decomposable"] else 0.0)
            print(f"  {tau:>5}  {s['decomposable']:>12}  {s['have_driven']:>11}  "
                  f"{s['lemma_assisted']:>14}  {pct_lemma:>26.1f}%")

    print("\nVERDICT:")
    inv_f = full["named_subgoal_supply_tau_invariant"]
    inv_v = ver["named_subgoal_supply_tau_invariant"]
    print(f"  have-driven (>=2 named subgoals) is CONSTANT across every tau: "
          f"{inv_f['have_ge2']} (full) / {inv_v['have_ge2']} (verified). "
          f"F_size adds only library-lemma-citation nodes, not named subgoals.")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2))
    print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
