"""CPU-only refinement of e-0014: decompose the data/deep named-have supply into
FRONTIER WIDTH vs NESTING DEPTH.

e-0014 (a-0014) found that data/deep raises the named-have-node supply to 67%
(>=2 nodes), re-opening q-0009. But it counted named have-nodes RECURSIVELY over
the whole proof tree, conflating two structurally different things:

  * WIDTH  — how many named subgoals sit at the SAME cut (an antichain). This is
    exactly what a single-stage section-predictor (Variant B, q-0009) must emit:
    the set of parallel subgoals for one frontier.
  * DEPTH  — how deeply the have-tree nests. e-0004 found corpus_v3 proofs have
    max dependency-poset depth 3, and q-0005 was recalibrated AWAY from a
    multi-level / U-shape contrast to a binary rough-vs-fine ON THAT BASIS
    ("max depth 3 leaves no room for an interior optimum"). If data/deep proofs
    nest deeper, the multi-level granularity contrast is back on the table.

The richest decl (FloorPow.tendsto_div..., 26 named haves) has only 3 top-level
nodes — so its 26 is mostly depth, not width. This script measures both
distributions over data/deep so a-0014's "ample supply" can be read correctly:
supply for WHAT — a wider predictor target, a deeper granularity spectrum, or both.

A "named node" = have_tree node with name != "_" and non-empty type (the e-0012
section-predictor target). Pure stdlib, no Modal, not verified — a supply estimate.
"""
import json
import glob
import statistics as st

DEEP = "data/deep/*.json"
OUT = "data/corpus_v3/deep_frontier_shape.json"


def named(nd):
    return nd.get("name", "_") != "_" and (nd.get("type") or "").strip() != ""


def top_width(nodes):
    """# named nodes at the top level — the antichain a one-shot predictor emits."""
    return sum(1 for nd in nodes if named(nd))


def named_depth(nodes, d=1):
    """Max depth (1-indexed) at which a NAMED node occurs; 0 if none named."""
    best = 0
    for nd in nodes:
        here = d if named(nd) else 0
        kids = named_depth(nd.get("children") or [], d + 1)
        best = max(best, here, kids)
    return best


def width_by_level(nodes, d=1, acc=None):
    """Map depth -> count of named nodes at that depth (widest antichain proxy)."""
    if acc is None:
        acc = {}
    for nd in nodes:
        if named(nd):
            acc[d] = acc.get(d, 0) + 1
        width_by_level(nd.get("children") or [], d + 1, acc)
    return acc


def total_named(nodes):
    return sum((1 if named(nd) else 0) + total_named(nd.get("children") or [])
               for nd in nodes)


def dist(vals, cap=7):
    out = {}
    for v in vals:
        k = str(v) if v <= cap else f"{cap+1}+"
        out[k] = out.get(k, 0) + 1
    return out


def main():
    widths, depths, max_levels, totals = [], [], [], []
    # decls usable as a WIDE predictor target: top-level antichain >= 2
    wide_examples = []
    # decls usable for a MULTI-LEVEL granularity contrast: named depth >= 3
    deep_examples = []

    for f in glob.glob(DEEP):
        for e in json.load(open(f)):
            ht = e.get("have_tree") or []
            tw = top_width(ht)
            nd_depth = named_depth(ht)
            lvl = width_by_level(ht)
            maxlvl = max(lvl.values()) if lvl else 0
            tot = total_named(ht)
            widths.append(tw)
            depths.append(nd_depth)
            max_levels.append(maxlvl)
            totals.append(tot)
            if tw >= 2:
                wide_examples.append((e["name"], tw, nd_depth, tot))
            if nd_depth >= 3:
                deep_examples.append((e["name"], nd_depth, tw, tot))

    n = len(widths)

    def pct(cond_list, thr):
        c = sum(1 for v in cond_list if v >= thr)
        return {"n": c, "pct": round(100 * c / n, 1)}

    nz_w = [w for w in widths if w >= 1]
    nz_d = [d for d in depths if d >= 1]

    result = {
        "source": "data/deep — refines e-0014 (a-0014) by separating width vs depth",
        "n_decls": n,
        "TOP_LEVEL_FRONTIER_WIDTH (one-shot section-predictor target, q-0009)": {
            "distribution": dist(widths),
            ">=1": pct(widths, 1), ">=2": pct(widths, 2),
            ">=3": pct(widths, 3), ">=4": pct(widths, 4),
            "among_nonzero": {
                "mean": round(st.mean(nz_w), 2) if nz_w else 0,
                "median": st.median(nz_w) if nz_w else 0,
                "max": max(nz_w) if nz_w else 0,
            },
        },
        "MAX_LEVEL_WIDTH (widest antichain anywhere in the proof)": {
            "distribution": dist(max_levels),
            ">=2": pct(max_levels, 2), ">=3": pct(max_levels, 3),
        },
        "NAMED_NESTING_DEPTH (granularity levels available, q-0005)": {
            "distribution": dist(depths),
            ">=2": pct(depths, 2), ">=3": pct(depths, 3),
            ">=4": pct(depths, 4),
            "among_nonzero": {
                "mean": round(st.mean(nz_d), 2) if nz_d else 0,
                "median": st.median(nz_d) if nz_d else 0,
                "max": max(nz_d) if nz_d else 0,
            },
            "corpus_v3_max_dependency_depth_e0004": 3,
            "note": "q-0005 recalibrated to BINARY because corpus_v3 max depth was 3",
        },
        "TOTAL_NAMED (e-0014's recursive count, for reconciliation)": {
            "distribution": dist(totals),
            ">=2": pct(totals, 2),
            "note": "matches a-0014's 67.4% >=2 figure if scope identical",
        },
        "wide_target_examples(top_width>=2)": [
            {"name": nm, "top_width": tw, "depth": d, "total_named": t}
            for nm, tw, d, t in sorted(wide_examples, key=lambda x: -x[1])[:10]
        ],
        "deep_spectrum_examples(named_depth>=3)": [
            {"name": nm, "depth": d, "top_width": tw, "total_named": t}
            for nm, d, tw, t in sorted(deep_examples, key=lambda x: -x[1])[:10]
        ],
    }
    json.dump(result, open(OUT, "w"), indent=2)
    print(json.dumps(result, indent=2))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
