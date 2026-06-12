"""CPU-only SYNTHESIS gate (q-0009, also q-0007): compose the filter funnel.

The e-0012..e-0028 chain characterized the data/deep wide-frontier supply
one filter at a time, each in isolation:
  - e-0016: 633 wide-frontier targets (>=2 top-level named frontier).
  - e-0022: only ~24% of the 633 live in subjects the miniF2F eval exercises
            (elementary algebra / number theory / combinatorics / geometry /
            order); ~76% are research-level subjects with ZERO eval coverage.
  - e-0028: round-trip verification yield VARIES by area (Data 73.8% ...
            Analysis 92.6%); per-area projection over all 633 -> ~558 verified.

No experiment MULTIPLIED these together. The decision-relevant number for the
Modal go/no-go is not "how many targets verify" (e-0028: ~558) nor "how many
are eval-relevant" (e-0022: ~24%) in isolation, but their COMPOSITION: how many
VERIFIED, EVAL-RELEVANT wide-frontier training targets survive the whole funnel.
That is the actual on-domain training signal a section-predictor (q-0009) — or
the headline granularity-as-data retrain (q-0007) — would get for the metric the
paper scores (pass@k on miniF2F, q-0006).

This gate composes the two established filters (eval-domain bucket from e-0022,
per-namespace yield from e-0028) over the 633-target manifest and reports the
funnel. Pure stdlib over local data; no Lean, no Modal. It produces no verified
pairs — it projects how many the planned spend would yield ON-DOMAIN.
"""
import json
import glob
import os
import collections

VERIFY_DIR = "data/corpus_v3/verify"
MANIFEST = "data/corpus_v3/deep_wide_targets.json"
OUT = "data/corpus_v3/deep_eval_relevant_yield.json"

# Eval-domain bucketing (identical to e-0022 / analyze_deep_eval_domain_match.py):
# which top namespaces map to a subject the miniF2F eval actually exercises.
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
    "RepresentationTheory": "ring/field-advanced",
    "ModelTheory": "set-theory",
}
EVAL_COVERED_SUBJECTS = {
    "elementary-algebra", "number-theory", "combinatorics", "geometry", "order",
}

# A section-predictor needs enough supervised frontiers to SFT. The chain's own
# anchors: ~27 (corpus_v3) was called "far too few" (e-0012); ~850 (data/deep
# total >=2) was called "ample" (e-0014). We report against a conservative
# minimum-trainable band rather than a single hard threshold.
MIN_TRAINABLE = 100   # below this, an LoRA section-predictor is data-starved
AMPLE = 300           # comfortably trainable per the chain's "ample" framing


def top_ns(mod):
    parts = mod.split(".")
    return parts[1] if parts[0] == "Mathlib" and len(parts) > 1 else parts[0]


def main():
    # 1. corpus_v3 round-trip pass rate per top namespace (e-0028 logic).
    ns = collections.defaultdict(lambda: [0, 0])
    pooled_pass = pooled_total = 0
    for f in glob.glob(os.path.join(VERIFY_DIR, "*.json")):
        if "_overall" in f:
            continue
        s = json.load(open(f))["summary"]
        ns[top_ns(s["module"])][0] += s["pass"]
        ns[top_ns(s["module"])][1] += s["total"]
        pooled_pass += s["pass"]
        pooled_total += s["total"]
    rate = {k: v[0] / v[1] for k, v in ns.items()}
    FOUNDATIONAL = {"Data", "Logic"}
    adv_p = sum(v[0] for k, v in ns.items() if k not in FOUNDATIONAL)
    adv_t = sum(v[1] for k, v in ns.items() if k not in FOUNDATIONAL)
    adv_pooled = adv_p / adv_t

    def yield_rate(namespace):
        # corpus_v3 rate if measured, else advanced-pooled (e-0028 reference class).
        return rate.get(namespace, adv_pooled)

    # 2. the 633 targets, bucketed by namespace -> (eval-subject, yield).
    targets = json.load(open(MANIFEST))["targets"]
    n_total = len(targets)

    by_ns = collections.Counter(top_ns(t["module"]) for t in targets)

    # 3. compose the funnel.
    eval_relevant = []   # targets in an eval-covered subject
    for t in targets:
        namespace = top_ns(t["module"])
        subj = DEEP_SUBJECT.get(namespace, "other-advanced")
        if subj in EVAL_COVERED_SUBJECTS:
            eval_relevant.append((namespace, subj))

    n_eval_rel = len(eval_relevant)

    # expected VERIFIED over all 633 (cross-check e-0028 ~558)
    exp_verified_all = sum(yield_rate(top_ns(t["module"])) for t in targets)
    # expected VERIFIED AND eval-relevant (the composition no prior gate computed)
    exp_verified_evalrel = sum(yield_rate(nsv) for nsv, _ in eval_relevant)

    # per-namespace breakdown of the eval-relevant slice
    er_ns = collections.Counter(nsv for nsv, _ in eval_relevant)
    er_subj = collections.Counter(s for _, s in eval_relevant)

    report = {
        "source": "q-0009 synthesis: VERIFIED x EVAL-RELEVANT wide-frontier yield funnel",
        "inputs": {
            "manifest": MANIFEST,
            "eval_domain_filter": "e-0022 buckets",
            "yield_filter": "e-0028 per-namespace corpus_v3 round-trip rates",
            "corpus_v3_pooled_yield": round(pooled_pass / pooled_total, 3),
            "advanced_pooled_yield": round(adv_pooled, 3),
        },
        "FUNNEL": {
            "1_wide_frontier_targets": n_total,
            "2_expected_verified(all_subjects)": round(exp_verified_all, 1),
            "3_eval_relevant_targets(raw)": n_eval_rel,
            "3_eval_relevant_pct": round(100 * n_eval_rel / n_total, 1),
            "4_expected_verified_AND_eval_relevant": round(exp_verified_evalrel, 1),
            "4_as_pct_of_633": round(100 * exp_verified_evalrel / n_total, 1),
        },
        "eval_relevant_slice_by_namespace": dict(er_ns.most_common()),
        "eval_relevant_slice_by_subject": dict(er_subj.most_common()),
        "deep_supply_by_namespace": dict(by_ns.most_common()),
        "trainability": {
            "min_trainable_ref": MIN_TRAINABLE,
            "ample_ref": AMPLE,
            "verified_eval_relevant_vs_min": round(exp_verified_evalrel, 1),
            "verdict": (
                "AMPLE" if exp_verified_evalrel >= AMPLE
                else "MARGINAL" if exp_verified_evalrel >= MIN_TRAINABLE
                else "DATA-STARVED"
            ),
        },
        "INTERPRETATION": "",
        "CAVEAT": (
            "Composes two coarse data-level filters: (1) eval-domain buckets are "
            "top-namespace heuristics (e-0022) — olympiad AMC/IMO problems do span "
            "elementary algebra/NT, so 'eval-relevant' is a broad-area match, not a "
            "difficulty match; (2) per-namespace yield is the corpus_v3 round-trip "
            "rate (e-0028), with namespaces absent from corpus_v3 given the "
            "advanced-pooled rate. This projects COUNTS, not pass@k; it is a "
            "go/no-go scoping number, not an outcome. The MIN_TRAINABLE/AMPLE bands "
            "are reference anchors from the chain (e-0012's ~27 'far too few', "
            "e-0014's ~850 'ample'), not a measured SFT learning curve."
        ),
        "out": OUT,
    }

    v = report["FUNNEL"]["4_expected_verified_AND_eval_relevant"]
    report["INTERPRETATION"] = (
        f"Composing the eval-domain filter (e-0022) with per-area yield (e-0028) "
        f"over the 633 wide-frontier targets: ~{report['FUNNEL']['2_expected_verified(all_subjects)']} "
        f"verify in TOTAL (cross-checks e-0028's ~558), but only {n_eval_rel} "
        f"({report['FUNNEL']['3_eval_relevant_pct']}%) are in an eval-covered "
        f"subject, and after yield only ~{v} are BOTH verified AND eval-relevant "
        f"— {report['FUNNEL']['4_as_pct_of_633']}% of the headline 633. The rich "
        f"deep supply that 'unblocks' q-0009 is overwhelmingly off-domain for the "
        f"miniF2F metric: the on-domain verified training signal is ~{v} frontiers, "
        f"a {report['trainability']['verdict']} band. So the Modal go/no-go should "
        f"be scoped to this composed number, not the gross 633/558 — either accept "
        f"a section-predictor trained on advanced Mathlib and EVAL on a held-out "
        f"slice of the SAME distribution (the within-deep eval e-0022 suggested), "
        f"or source a competition-math decomposable corpus, rather than expecting "
        f"the 633 advanced targets to transfer to miniF2F."
    )

    json.dump(report, open(OUT, "w"), indent=2)
    print(json.dumps(report, indent=2))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
