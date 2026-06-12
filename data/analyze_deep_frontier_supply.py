"""CPU-only supply gate: does the deeper `data/deep/` have-tree extraction break
the ~4% named-have-frontier ceiling that blocks q-0007/q-0008/q-0009?

e-0012 (section_predictor_feasibility) found that on the 607-pair corpus_v3 only
4.4% of verified decls expose a >=2-subgoal named frontier, and e-0013 showed
that ceiling is structurally pinned regardless of F_size. The graph's stated
unblock for all three open questions is "proofs that genuinely contain more
named have-steps (deeper/longer source proofs)". `data/deep/` is a have-tree
extraction over 646 distinct, deeper Mathlib modules (1,261 decls) — exactly that
candidate corpus. This script counts the named-subgoal-frontier supply there and
compares it to the corpus_v3 ceiling.

A "named have-node" = a have_tree node with name != "_" and a non-empty `type`
(the ppType a section-predictor would have to emit), matching the e-0012 notion.
Anonymous binders (name "_") and bare term aliases (empty type) are not subgoals.

Pure stdlib, no Modal. Not a verified corpus (no round-trip) — a supply estimate,
the same role e-0004 played for decomposability over 1,715 theorems.
"""
import json
import glob
import statistics as st

DEEP = "data/deep/*.json"
OUT = "data/corpus_v3/deep_frontier_supply.json"


def count_named(nodes):
    """Recursively count named-with-type have-nodes in a have_tree forest."""
    n = 0
    for nd in nodes:
        name = nd.get("name", "_")
        typ = (nd.get("type") or "").strip()
        if name != "_" and typ != "":
            n += 1
        kids = nd.get("children") or []
        n += count_named(kids)
    return n


def main():
    files = glob.glob(DEEP)
    counts = []          # named-have-node count per decl
    per_module = {}      # module -> list of counts
    examples = []        # decls with rich frontiers, for sanity
    for f in files:
        for e in json.load(open(f)):
            ht = e.get("have_tree") or []
            c = count_named(ht)
            counts.append(c)
            per_module.setdefault(e["module"], []).append(c)
            if c >= 4:
                examples.append((e["module"], e["name"], c))

    n = len(counts)
    dist = {}
    for c in counts:
        key = c if c <= 7 else "8+"
        dist[str(key)] = dist.get(str(key), 0) + 1

    ge1 = sum(1 for c in counts if c >= 1)
    ge2 = sum(1 for c in counts if c >= 2)
    ge3 = sum(1 for c in counts if c >= 3)
    nonzero = [c for c in counts if c >= 1]

    # modules ranked by how many >=2-frontier decls they contribute
    mod_rich = sorted(
        ((m, sum(1 for c in cs if c >= 2), len(cs)) for m, cs in per_module.items()),
        key=lambda t: -t[1],
    )

    result = {
        "source": "data/deep (have-tree extraction over deeper Mathlib modules)",
        "n_decls": n,
        "n_modules": len(per_module),
        "have_node_count_distribution": dist,
        "named_frontier_supply": {
            ">=1": {"n": ge1, "pct": round(100 * ge1 / n, 1)},
            ">=2": {"n": ge2, "pct": round(100 * ge2 / n, 1)},
            ">=3": {"n": ge3, "pct": round(100 * ge3 / n, 1)},
        },
        "among_decls_with_any_frontier": {
            "n": len(nonzero),
            "mean": round(st.mean(nonzero), 2) if nonzero else 0,
            "median": st.median(nonzero) if nonzero else 0,
            "max": max(nonzero) if nonzero else 0,
        },
        "corpus_v3_baseline_e0012": {
            ">=1_pct": 6.9, ">=2_pct": 4.4, ">=3_pct": 2.5,
            "note": "607 verified pairs; the ~4% ceiling e-0013 showed is F_size-invariant",
        },
        "top_modules_by_>=2_frontier_decls": [
            {"module": m, "ge2": g, "decls": d} for m, g, d in mod_rich[:15] if g > 0
        ],
        "example_rich_decls(>=4)": [
            {"module": m, "name": nm, "named_haves": c} for m, nm, c in
            sorted(examples, key=lambda t: -t[2])[:15]
        ],
    }
    json.dump(result, open(OUT, "w"), indent=2)
    print(json.dumps(result, indent=2))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
