"""
Corpus-level rewriting script.

For every proof in data/raw/ that has genuine have-nodes (not just a synth-root),
apply all single-step rewriting operations (merge, split, reorder) and emit
training pairs.

Output
------
data/rewrites/<module>.json  — one file per source module.
  Each file is a list of RewriteRecord:
    {
      "original":  ProofTree dict,
      "rewrites": [
        {"op": "merge"|"split"|"reorder", "path": [...], "result": ProofTree dict},
        ...
      ]
    }

Run
---
  python -m rewriter.generate_rewrites          # all modules
  python -m rewriter.generate_rewrites --stats  # only print statistics, no write
"""

from __future__ import annotations
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from rewriter.tree import ProofTree
from rewriter.operations import all_merges, all_splits, all_reorders


def _is_synth_root(tree_dict: dict) -> bool:
    nodes = tree_dict.get("have_tree", [])
    return len(nodes) == 1 and nodes[0].get("name") == "_"


def process_record(record: dict) -> list[dict]:
    """Return list of {op, path, result} dicts for every 1-step rewrite."""
    tree = ProofTree.from_dict(record)
    rewrites = []

    for path, result in all_merges(tree):
        rewrites.append({"op": "merge", "path": path, "result": result.to_dict()})

    for path, child_idx, result in all_splits(tree):
        rewrites.append({"op": "split", "path": path, "child_index": child_idx, "result": result.to_dict()})

    for path, perm, result in all_reorders(tree):
        rewrites.append({"op": "reorder", "path": path, "perm": perm, "result": result.to_dict()})

    return rewrites


def run(write_output: bool = True) -> None:
    raw_dir = ROOT / "data" / "raw"
    out_dir = ROOT / "data" / "rewrites"
    if write_output:
        out_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(raw_dir.glob("*.json"))
    print(f"Processing {len(files)} modules from {raw_dir} …")

    total_proofs = 0
    total_have_proofs = 0
    total_rewriteable = 0
    total_rewrites = 0
    op_counts: Counter = Counter()
    rewrites_per_proof: list[int] = []

    for i, f in enumerate(files):
        records = json.loads(f.read_text())
        module_output = []

        for rec in records:
            total_proofs += 1
            if _is_synth_root(rec):
                continue
            total_have_proofs += 1

            rewrites = process_record(rec)
            if rewrites:
                total_rewriteable += 1
                total_rewrites += len(rewrites)
                rewrites_per_proof.append(len(rewrites))
                for rw in rewrites:
                    op_counts[rw["op"]] += 1
                module_output.append({"original": rec, "rewrites": rewrites})

        if write_output and module_output:
            dest = out_dir / f.name
            dest.write_text(json.dumps(module_output, indent=2))

        if (i + 1) % 500 == 0:
            print(f"  {i+1}/{len(files)} modules … {total_rewrites} rewrites so far")

    # Statistics
    print(f"\n=== Corpus rewriting statistics ===")
    print(f"Total proof records:          {total_proofs:>8,}")
    print(f"  — with real have-nodes:     {total_have_proofs:>8,}")
    print(f"  — with ≥1 rewrite:          {total_rewriteable:>8,}")
    print(f"Total rewrite pairs:          {total_rewrites:>8,}")
    print(f"  merge:                      {op_counts['merge']:>8,}")
    print(f"  split:                      {op_counts['split']:>8,}")
    print(f"  reorder:                    {op_counts['reorder']:>8,}")

    if rewrites_per_proof:
        import statistics
        print(f"\nRewrites per proof:")
        print(f"  min:    {min(rewrites_per_proof)}")
        print(f"  max:    {max(rewrites_per_proof)}")
        print(f"  mean:   {statistics.mean(rewrites_per_proof):.1f}")
        print(f"  median: {statistics.median(rewrites_per_proof):.1f}")
        # histogram buckets
        buckets = [0, 1, 2, 5, 10, 20, 50, float("inf")]
        labels  = ["0", "1", "2–4", "5–9", "10–19", "20–49", "50+"]
        counts  = [0] * len(labels)
        for v in rewrites_per_proof:
            for k, hi in enumerate(buckets[1:]):
                if v < hi:
                    counts[k] += 1
                    break
        print(f"\n  Distribution:")
        for lbl, cnt in zip(labels, counts):
            bar = "█" * (cnt * 40 // max(counts))
            print(f"    {lbl:>5}: {cnt:>6,}  {bar}")

    if write_output:
        print(f"\nOutput written to {out_dir}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stats", action="store_true", help="Print stats only, do not write output")
    args = parser.parse_args()
    run(write_output=not args.stats)
