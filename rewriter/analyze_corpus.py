"""Corpus-level stats over extracted have-trees + section-policy outputs.

  python3 -m rewriter.analyze_corpus data/corpus_v1/corpus
"""

from __future__ import annotations
import argparse, glob, json
from collections import Counter
from statistics import median, mean
from rewriter.sections import ProofTree, POLICIES


def load_premises(root: str) -> dict[str, set[str]]:
    """decl_name → set of premise constant names (from ntp-toolkit `premises`)."""
    out: dict[str, set[str]] = {}
    for path in sorted(glob.glob(f"{root}/premises/*.jsonl")):
        for line in open(path):
            line = line.strip()
            if not line: continue
            try: d = json.loads(line)
            except json.JSONDecodeError: continue
            out[d["name"]] = {dep["name"] for dep in d.get("dependents", [])}
    return out


def load_corpus(root: str) -> list[ProofTree]:
    """Load have_tree records AND join with premises (per EXPERIMENT.md §2)."""
    premises = load_premises(root)
    trees: list[ProofTree] = []
    for path in sorted(glob.glob(f"{root}/*.jsonl")):
        for line in open(path):
            line = line.strip()
            if not line: continue
            try: d = json.loads(line)
            except json.JSONDecodeError: continue
            prems = premises.get(d["declName"], set())
            trees.append(ProofTree.join_with_premises(d, prems))
    return trees


def hist(label: str, buckets: list[tuple[str, int]]):
    width = max((c for _, c in buckets), default=1)
    for lbl, c in buckets:
        bar = "█" * (c * 30 // max(width, 1))
        print(f"  {lbl:>10}  {c:>5}  {bar}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus", help="directory of *.jsonl files")
    args = ap.parse_args()
    trees = load_corpus(args.corpus)

    n = len(trees)
    sizes = [len(t.nodes) for t in trees]
    decomposable = [t for t in trees if len(t.nodes) >= 2]
    edges = [sum(len(d) for d in t.deps.values()) for t in trees]
    depths = [max((t.depth_of(x) for x in t.by_name), default=0) for t in trees]

    print(f"\nProofs: {n}")
    print(f"  with ≥1 node : {sum(1 for s in sizes if s >= 1)}  ({100*sum(1 for s in sizes if s >= 1)/max(n,1):.0f}%)")
    print(f"  with ≥2 nodes: {len(decomposable)}  ({100*len(decomposable)/max(n,1):.0f}%)")
    print(f"  nodes/proof  : mean {mean(sizes):.1f}, median {median(sizes):.1f}, max {max(sizes, default=0)}")
    print(f"  edges/proof  : mean {mean(edges):.1f}, max {max(edges, default=0)}")
    print(f"  max depth    : mean {mean(depths):.1f}, max {max(depths, default=0)}")

    print("\nNode-count distribution:")
    bands = [("0", lambda s: s == 0), ("1", lambda s: s == 1),
             ("2-3", lambda s: 2 <= s <= 3), ("4-7", lambda s: 4 <= s <= 7),
             ("8-15", lambda s: 8 <= s <= 15), ("16+", lambda s: s >= 16)]
    hist("nodes", [(lbl, sum(1 for s in sizes if f(s))) for lbl, f in bands])

    if decomposable:
        print(f"\nSection-policy sizes on the {len(decomposable)} decomposable proofs:")
        for name, policy in POLICIES.items():
            ss = [len(policy(t)) for t in decomposable]
            print(f"  {name:>7}: mean {mean(ss):4.1f}  median {median(ss):.0f}  "
                  f"min {min(ss)}  max {max(ss)}")

        # A couple of richest examples
        rich = sorted(decomposable, key=lambda t: -len(t.nodes))[:3]
        print("\nRichest proofs (by node count):")
        for t in rich:
            print(f"\n  {t.module} :: {t.decl_name}  ({len(t.nodes)} nodes, depth {max(t.depth_of(x) for x in t.by_name)})")
            for name, policy in POLICIES.items():
                print(f"    π_{name:<6} → {sorted(policy(t))}")


if __name__ == "__main__":
    main()
