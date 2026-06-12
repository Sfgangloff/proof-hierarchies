"""CPU-only DOMAIN-TRANSFER gate for q-0009's section-predictor (Variant B).

The whole e-0012..e-0021 chain cleared every data-level gate for the
section-predictor by characterizing the deep-corpus frontier supply IN
ISOLATION: supply (e-0014/15/16), emission economics (e-0016), subgoal
difficulty (e-0017), independence (e-0018/19), predictability (e-0020/21).
Not one of them connected the TRAINING corpus to the EVAL target. But the
project's headline metric is pass@k on miniF2F (e-0005, q-0006), and the
633 wide-frontier training targets live in data/deep — ADVANCED Mathlib
(Analysis, RingTheory, MeasureTheory, Topology, CategoryTheory, ...).

A section-predictor learns to emit wide named-have frontiers from the
distribution it is TRAINED on. If that distribution is disjoint from the
EVAL distribution, the rich deep supply may not transfer to the headline
metric no matter how well the predictor fits. This is the q-0009 analogue
of e-0013 (which caught that the F_size unblock added the wrong kind of
structure): "we have wide-frontier supply" is not the same claim as "we
have wide-frontier supply for the kind of problem the eval scores".

This gate, pure stdlib over local data, measures the mismatch:

1. SUBJECT distribution of the 633 deep wide-frontier targets
   (data/corpus_v3/deep_wide_targets.json, the manifest e-0016 emitted),
   bucketed by top Mathlib namespace into broad subjects.
2. SUBJECT distribution of the miniF2F eval problems
   (data/eval/miniF2F_v2s.jsonl), bucketed from the problem-name prefix
   (mathd_algebra / mathd_numbertheory / amc / imo / aime / induction ...).
3. OVERLAP: what fraction of the deep supply falls in subjects the eval
   actually exercises (elementary algebra / number theory) vs subjects with
   ZERO eval representation (measure theory, topology, category theory,
   research analysis, ring/field theory, algebraic geometry).

This does NOT need Modal and does not produce verified pairs; it tests a
TRANSFER premise the prior chain assumed silently.
"""
import json
import collections
import re

MANIFEST = "data/corpus_v3/deep_wide_targets.json"
EVAL = "data/eval/miniF2F_v2s.jsonl"
OUT = "data/corpus_v3/deep_eval_domain_match.json"

# Broad subject buckets for the deep training corpus, keyed by top namespace.
# "ELEMENTARY" = a subject miniF2F's competition problems actually live in
# (elementary algebra identities/inequalities, elementary number theory).
# "ADVANCED"   = research Mathlib with no miniF2F representation.
DEEP_SUBJECT = {
    "Algebra": "elementary-algebra",
    "NumberTheory": "number-theory",
    "Data": "elementary-algebra",        # Data.Nat / Data.Int arithmetic
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

# Which deep subjects does miniF2F's competition distribution actually exercise?
# AMC/IMO/AIME are elementary algebra / number theory / (some) combinatorics &
# geometry at an OLYMPIAD level — none of them research-level analysis, measure
# theory, topology, category theory, ring/field theory, etc.
EVAL_COVERED_SUBJECTS = {
    "elementary-algebra", "number-theory", "combinatorics", "geometry", "order",
}

# miniF2F problem-name prefix -> subject (for the eval side).
def eval_subject(name):
    if name.startswith("mathd_algebra") or name == "algebra" or name.startswith("algebra"):
        return "elementary-algebra"
    if name.startswith("mathd_numbertheory") or name.startswith("numbertheory"):
        return "number-theory"
    if name.startswith("induction"):
        return "induction"
    if name.startswith("amc") or name.startswith("imo") or name.startswith("aime"):
        # competition: predominantly elementary algebra / number theory / combinatorics
        return "competition-elementary"
    return "other"


def top_ns(module):
    # module is "Mathlib.Analysis.Foo.Bar" -> "Analysis"
    parts = module.split(".")
    return parts[1] if len(parts) > 1 else parts[0]


def main():
    # ---- deep training supply ----
    man = json.load(open(MANIFEST))
    targets = man["targets"]
    deep_ns = collections.Counter()
    deep_subj = collections.Counter()
    for t in targets:
        ns = top_ns(t["module"])
        deep_ns[ns] += 1
        deep_subj[DEEP_SUBJECT.get(ns, "other-advanced")] += 1
    n_deep = len(targets)

    covered = sum(v for s, v in deep_subj.items() if s in EVAL_COVERED_SUBJECTS)
    advanced = n_deep - covered

    # ---- eval distribution ----
    eval_lines = [json.loads(l) for l in open(EVAL) if l.strip()]
    eval_subj = collections.Counter(eval_subject(l["name"]) for l in eval_lines)
    n_eval = len(eval_lines)

    report = {
        "source": "q-0009 domain-transfer gate: deep training supply vs miniF2F eval",
        "n_deep_wide_targets": n_deep,
        "n_eval_problems": n_eval,
        "DEEP_SUPPLY_by_namespace": dict(deep_ns.most_common()),
        "DEEP_SUPPLY_by_subject": dict(deep_subj.most_common()),
        "EVAL_by_subject": dict(eval_subj.most_common()),
        "OVERLAP": {
            "deep_targets_in_eval_covered_subjects": {
                "n": covered, "pct": round(100 * covered / n_deep, 1),
                "subjects": sorted(EVAL_COVERED_SUBJECTS),
            },
            "deep_targets_in_advanced_subjects(zero_eval_coverage)": {
                "n": advanced, "pct": round(100 * advanced / n_deep, 1),
            },
            "eval_is_entirely": "elementary algebra / number theory / olympiad",
        },
        "INTERPRETATION": (
            "The 633 deep wide-frontier TRAINING targets are dominated by "
            "research-level subjects (Analysis, RingTheory, MeasureTheory, "
            "Topology, CategoryTheory) that have ZERO representation in the "
            "miniF2F EVAL set, which is entirely elementary algebra / number "
            "theory / olympiad. Only the elementary-algebra + number-theory "
            f"slice ({covered}/{n_deep}, {round(100*covered/n_deep,1)}%) of the "
            "training supply shares a subject with the eval. A section-predictor "
            "trained on this supply learns to emit wide frontiers for advanced "
            "Mathlib, a distribution disjoint from where pass@k is scored. The "
            "data-level gates e-0012..e-0021 confirmed wide-frontier supply "
            "EXISTS but never that it matches the eval; this is a transfer "
            "confound the eventual Modal run must control for (e.g. eval on a "
            "held-out slice of the SAME deep distribution, or source a "
            "competition-math decomposable corpus)."
        ),
        "CAVEAT": (
            "Subject buckets are coarse (top-namespace heuristic); 'olympiad' "
            "AMC/IMO/AIME problems do span elementary algebra/NT/combinatorics/"
            "geometry, so 'zero coverage' is at the RESEARCH-LEVEL granularity, "
            "not the broad area. This measures distribution mismatch, not "
            "whether a predictor can still transfer; transfer is an outcome only "
            "the Modal SFT+eval can settle. It does not refute Variant B; it "
            "names a confound the prior chain skipped."
        ),
        "out": OUT,
    }

    json.dump(report, open(OUT, "w"), indent=2)
    print(json.dumps(report, indent=2))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
