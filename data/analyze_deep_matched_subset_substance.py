"""CPU-only follow-up to e-0022's domain-transfer gate (q-0009, Variant B).

e-0022 found the 633 deep wide-frontier TRAINING targets are ~76% in
research-level subjects (measure theory, advanced analysis, ring/field,
topology, ...) with ZERO miniF2F eval coverage; only ~150 (23.7%) fall in
a subject the eval exercises (elementary algebra / number theory /
combinatorics / geometry / order). Its named remedy was either (1) eval on
a held-out slice of the SAME deep distribution, or (2) source a
competition-math decomposable corpus matched to miniF2F.

e-0022 measured the SIZE of the matched slice but never its SHAPE. Remedy 2
only has signal if those ~150 eval-relevant targets are still WIDE and
SUBSTANTIVE frontiers — not if the domain-matched supply is both SMALL
(e-0022) AND THIN (narrow, near-degenerate frontiers). If the wide-and-
substantive structure lives only in the advanced bulk, then the matched
supply is weaker than e-0022's headcount implies and remedy 2 is hollow;
if the matched slice matches the advanced bulk on width/substance, remedy 2
is concretely scoped at ~150 (→ ~127 after e-0003's 84.7% yield).

This reuses the e-0022 subject bucketing verbatim and partitions the 633
targets into EVAL-COVERED (domain-matched) vs ADVANCED (zero eval
coverage), then compares their frontier-WIDTH (#subgoals, the predictor's
one-shot emission target) and frontier-CHARS (emission burden) plus the
per-subgoal average size (chars/width, a substance proxy — e-0016 called
<=8-char subgoals degenerate). Pure stdlib over the local manifest; no
Modal, no verified pairs.
"""
import json
import collections
import statistics

MANIFEST = "data/corpus_v3/deep_wide_targets.json"
OUT = "data/corpus_v3/deep_matched_subset_substance.json"

# Verbatim from e-0022 (analyze_deep_eval_domain_match.py).
DEEP_SUBJECT = {
    "Algebra": "elementary-algebra",
    "NumberTheory": "number-theory",
    "Data": "elementary-algebra",
    "Combinatorics": "combinatorics",
    "Order": "order",
    "Analysis": "analysis-advanced",
    "RingTheory": "ring/field-advanced",
    "FieldTheory": "ring/field-advanced",
    "MeasureTheory": "measure/prob-advanced",
    "Probability": "measure/prob-advanced",
    "Topology": "topology-advanced",
    "CategoryTheory": "category-advanced",
    "LinearAlgebra": "linear-algebra-advanced",
    "AlgebraicGeometry": "alg-geometry-advanced",
    "AlgebraicTopology": "topology-advanced",
    "Geometry": "geometry",
    "GroupTheory": "group-theory-advanced",
    "SetTheory": "set-theory",
    "Computability": "computability",
    "Tactic": "tactic-meta",
    "Dynamics": "analysis-advanced",
}
EVAL_COVERED_SUBJECTS = {
    "elementary-algebra", "number-theory", "combinatorics", "geometry", "order",
}


def top_ns(module):
    parts = module.split(".")
    return parts[1] if len(parts) > 1 else parts[0]


def pctl(xs, p):
    if not xs:
        return None
    s = sorted(xs)
    k = (len(s) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 2)


def describe(xs):
    return {
        "n": len(xs),
        "p10": pctl(xs, 10), "p50": pctl(xs, 50), "p90": pctl(xs, 90),
        "max": max(xs) if xs else None,
        "mean": round(statistics.fmean(xs), 2) if xs else None,
    }


def main():
    man = json.load(open(MANIFEST))
    targets = man["targets"]

    matched, advanced = [], []
    matched_subj = collections.Counter()
    for t in targets:
        ns = top_ns(t["module"])
        subj = DEEP_SUBJECT.get(ns, "other-advanced")
        (matched if subj in EVAL_COVERED_SUBJECTS else advanced).append(t)
        if subj in EVAL_COVERED_SUBJECTS:
            matched_subj[subj] += 1

    def stratum(ts):
        widths = [t["frontier_width"] for t in ts]
        chars = [t["frontier_chars"] for t in ts]
        # per-subgoal average size = total frontier chars / #subgoals (substance proxy)
        persub = [t["frontier_chars"] / t["frontier_width"] for t in ts]
        return {
            "n": len(ts),
            "frontier_width": describe(widths),
            "frontier_chars": describe(chars),
            "per_subgoal_avg_chars": describe(persub),
            # fraction whose frontier is >=3 wide (richer one-shot target)
            "frac_width_ge3": round(sum(w >= 3 for w in widths) / len(ts), 3) if ts else None,
            # fraction whose per-subgoal avg <=8 chars (e-0016 degeneracy bar)
            "frac_degenerate_avg_le8": round(sum(p <= 8 for p in persub) / len(ts), 3) if ts else None,
        }

    m, a = stratum(matched), stratum(advanced)

    report = {
        "source": "q-0009 e-0023: shape of the eval-matched vs advanced deep wide-frontier supply",
        "n_total": len(targets),
        "MATCHED_eval_covered": m,
        "MATCHED_by_subject": dict(matched_subj.most_common()),
        "ADVANCED_zero_eval_coverage": a,
        "matched_usable_after_847_yield_est": round(m["n"] * 0.847, 1),
        "INTERPRETATION": (
            f"The eval-matched slice is n={m['n']} ({round(100*m['n']/len(targets),1)}%) of the 633 "
            f"wide-frontier targets (reproduces e-0022's ~150). SHAPE comparison: matched frontier "
            f"WIDTH p50={m['frontier_width']['p50']} (max {m['frontier_width']['max']}) vs advanced "
            f"p50={a['frontier_width']['p50']} (max {a['frontier_width']['max']}); per-subgoal avg "
            f"chars p50={m['per_subgoal_avg_chars']['p50']} (matched) vs "
            f"{a['per_subgoal_avg_chars']['p50']} (advanced). frac width>=3: matched "
            f"{m['frac_width_ge3']} vs advanced {a['frac_width_ge3']}. frac degenerate (avg<=8 chars): "
            f"matched {m['frac_degenerate_avg_le8']} vs advanced {a['frac_degenerate_avg_le8']}. This "
            f"says whether remedy-2 (a competition-matched decomposable corpus) inherits genuine wide/"
            f"substantive structure or only a small, thinner slice."
        ),
        "CAVEAT": (
            "frontier_width/chars come from the manifest (e-0016); per-subgoal AVG chars is a coarser "
            "substance proxy than e-0016's per-subgoal type-length distribution (it cannot see a wide "
            "frontier mixing one long and several degenerate subgoals). Subject buckets are the coarse "
            "top-namespace heuristic from e-0022. This characterizes SHAPE of the matched supply, not "
            "transfer; only the Modal SFT+eval settles whether a predictor trained on it scores pass@k."
        ),
        "out": OUT,
    }

    json.dump(report, open(OUT, "w"), indent=2)
    print(json.dumps(report, indent=2))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
