"""Feasibility gate for q-0009 (Variant B: a section-predictor + solver).

Question this answers WITHOUT spending Modal credit:
  A section-predictor is a model trained to emit, from a theorem statement,
  the subgoal frontier (the named `have` steps) that a solver then closes.
  Such a model can only be trained where the corpus actually CONTAINS a
  non-trivial named frontier. So: of the 607 VERIFIED (rough, fine) pairs,
  how many have >= 1 and >= 2 named have-nodes (the prediction target)?
  If almost none do, Variant B has no within-corpus training signal on the
  current corpus -- the same structural-supply problem that gates q-0008.

Inputs (local, already on disk):
  data/corpus_v3/pairs.jsonl            -- the 607 verified decls (declName)
  data/corpus_v2/corpus/*.jsonl         -- have-tree records (have_nodes[].ppType)

Each have_node carries a `ppType` (the subgoal statement the predictor would
emit) and `userName`. A "non-trivial section to predict" = a decl whose
verified proof exposes >= 2 named have-nodes (a frontier of >= 2 subgoals);
>= 1 is the weaker "any structure at all" bar.

  python3 -m data.analyze_section_predictor_feasibility [--out path.json]
"""

from __future__ import annotations
import argparse, glob, json
from collections import Counter
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[1]
PAIRS = ROOT / "data/corpus_v3/pairs.jsonl"
HAVE_TREES_DIR = ROOT / "data/corpus_v2/corpus"


def load_verified_declnames() -> list[str]:
    names = []
    for line in open(PAIRS):
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        if d.get("declName"):
            names.append(d["declName"])
    return names


def load_have_index() -> dict[str, list[dict]]:
    """declName -> list of have_nodes (each a dict with ppType/userName)."""
    idx: dict[str, list[dict]] = {}
    for path in sorted(glob.glob(str(HAVE_TREES_DIR / "*.jsonl"))):
        for line in open(path):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "declName" in d:
                idx[d["declName"]] = d.get("have_nodes", []) or []
    return idx


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    verified = load_verified_declnames()
    have_idx = load_have_index()

    n_total = len(verified)
    counts = []          # have-node count per verified decl
    missing = 0          # verified decl with no have-tree record at all
    for name in verified:
        if name not in have_idx:
            missing += 1
            counts.append(0)
        else:
            counts.append(len(have_idx[name]))

    n_ge1 = sum(1 for c in counts if c >= 1)
    n_ge2 = sum(1 for c in counts if c >= 2)
    n_ge3 = sum(1 for c in counts if c >= 3)
    dist = Counter(counts)

    nonzero = [c for c in counts if c >= 1]

    report = {
        "n_verified_pairs": n_total,
        "n_missing_have_record": missing,
        "n_with_ge1_have": n_ge1,
        "n_with_ge2_have": n_ge2,
        "n_with_ge3_have": n_ge3,
        "pct_ge1_have": round(100 * n_ge1 / n_total, 1),
        "pct_ge2_have": round(100 * n_ge2 / n_total, 1),
        "pct_ge3_have": round(100 * n_ge3 / n_total, 1),
        "have_count_distribution": {str(k): dist[k] for k in sorted(dist)},
        "among_decls_with_any_have": {
            "n": len(nonzero),
            "mean": round(mean(nonzero), 2) if nonzero else 0,
            "median": median(nonzero) if nonzero else 0,
            "max": max(nonzero) if nonzero else 0,
        },
    }

    print(json.dumps(report, indent=2))
    print()
    print(f"VERDICT: of {n_total} verified pairs, {n_ge2} ({report['pct_ge2_have']}%) "
          f"expose a non-trivial named frontier (>=2 have-nodes) to predict; "
          f"{n_ge1} ({report['pct_ge1_have']}%) expose any (>=1).")

    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2))
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
