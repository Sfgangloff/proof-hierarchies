#!/usr/bin/env python3
"""Stage 0.5 analysis (e-0054): does the construct-valid DEEP study route
structurally support an INTERMEDIATE granularity (pi_mid), i.e. does it reopen
q-0005's multi-level / U-shape contrast that corpus_v3 closed as binary?

Context. q-0005 was answered "binary rough vs fine" on corpus_v3. But the whole
Stage-0.5 power/cost chain (a-0044..a-0051) then PIVOTED the headline to the
deep route precisely because corpus_v3 is construct-poor (only ~6.9% of pairs
carry granularity not format signal, a-0026/e-0026). The canonical deep study
target set is data/corpus_v3/deep_wide_targets.json: 633 decls with a top-level
named frontier of >=2 subgoals. That file stores ONLY the flat top frontier
(frontier_width, frontier_chars) and discards the nested have-tree -- so whether
the deep targets admit a genuine intermediate cut (a 3rd antichain BETWEEN
pi_root and pi_leaf) was never measured.

This script measures it from the raw have-trees in data/deep/*.json:

  named-nesting-depth(target) = longest root->leaf chain counting only NAMED
      have nodes (name != "_"). It is the number of stacked named antichains a
      section policy can choose between:
        depth 0 -> no named have: rough == fine (no contrast at all)
        depth 1 -> one named frontier: BINARY rough/fine only (no pi_mid)
        depth >=2 -> >=2 nested named frontiers: an INTERMEDIATE granularity
                     pi_mid exists -> a 3-level U-shape contrast is available.

Pure-stdlib, CPU-only. Reports the distribution over (a) all raw deep targets
and (b) the 633 canonical wide-frontier study targets matched by name.
"""
import glob
import json
from collections import Counter


def named_depth(nodes):
    """Longest root->leaf chain counting only named (name != '_') nodes."""
    best = 0
    for n in nodes:
        sub = named_depth(n.get("children", []))
        is_named = bool(n.get("name")) and n["name"] != "_"
        best = max(best, (1 if is_named else 0) + sub)
    return best


def load_raw():
    raw = {}
    for f in glob.glob("data/deep/*.json"):
        for t in json.load(open(f)):
            raw[t["name"]] = t
    return raw


def summarize(depths):
    dist = dict(sorted(Counter(depths).items()))
    n = len(depths)
    return {
        "n": n,
        "depth_distribution": dist,
        "no_named_have_depth0": sum(1 for d in depths if d == 0),
        "binary_only_depth1": sum(1 for d in depths if d == 1),
        "intermediate_available_depth_ge2": sum(1 for d in depths if d >= 2),
        "frac_intermediate_available": round(
            sum(1 for d in depths if d >= 2) / n, 3
        ),
        "four_level_available_depth_ge3": sum(1 for d in depths if d >= 3),
    }


if __name__ == "__main__":
    raw = load_raw()
    all_depths = [named_depth(t.get("have_tree", [])) for t in raw.values()]

    wide = json.load(open("data/corpus_v3/deep_wide_targets.json"))["targets"]
    matched, missing = [], 0
    for w in wide:
        t = raw.get(w["name"])
        if t is None:
            missing += 1
            continue
        matched.append(named_depth(t.get("have_tree", [])))

    res = {
        "all_raw_deep_targets": summarize(all_depths),
        "canonical_633_wide_targets": {
            "matched": len(matched),
            "missing_from_raw": missing,
            **summarize(matched),
        },
    }
    print(json.dumps(res, indent=2))
