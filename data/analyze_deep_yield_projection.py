"""CPU-only cost-scoping gate (q-0009 / q-0007 / q-0008): is the "~84.7% expected
round-trip yield" that every recent deep-corpus answer inherits from e-0003 a valid
projection for data/deep's ADVANCED modules, or a foundational-module artifact?

e-0003's 84.7% (2,668/3,151) is the corpus_v3 POOLED round-trip pass rate. corpus_v3
spans foundational data-structure modules (Data.List/Finset/Int) AND advanced ones
(Analysis, MeasureTheory, NumberTheory, Topology). data/deep draws almost entirely
from the advanced areas. If round-trip yield varies by area, the pooled 84.7% is the
wrong number to scope the q-0009 Modal spend over the 633 wide-frontier targets.

This joins corpus_v3 per-decl verify pass/fail (data/corpus_v3/verify/*.json) bucketed
by TOP Mathlib namespace, then maps the 633 data/deep wide-frontier targets
(deep_wide_targets.json) onto those per-namespace rates to project the verified yield.
Pure stdlib; no Lean, no Modal.
"""
import json
import glob
import os
import collections

VERIFY_DIR = "data/corpus_v3/verify"
TARGETS = "data/corpus_v3/deep_wide_targets.json"
OUT = "data/corpus_v3/deep_yield_projection.json"


def top_ns(mod):
    # "Mathlib.Analysis.Normed.Group.Basic" -> "Analysis"
    parts = mod.split(".")
    return parts[1] if parts[0] == "Mathlib" and len(parts) > 1 else parts[0]


def main():
    # 1. corpus_v3 round-trip pass rate per top namespace
    ns = collections.defaultdict(lambda: [0, 0])  # ns -> [pass, total]
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
    pooled = pooled_pass / pooled_total

    # "advanced-math" pooled rate = everything except the foundational data-structure
    # + raw-logic buckets that dominate the failures.
    FOUNDATIONAL = {"Data", "Logic"}
    adv_p = sum(v[0] for k, v in ns.items() if k not in FOUNDATIONAL)
    adv_t = sum(v[1] for k, v in ns.items() if k not in FOUNDATIONAL)
    adv_pooled = adv_p / adv_t

    # 2. bucket the 633 wide-frontier targets by top namespace
    tgt = json.load(open(TARGETS))["targets"]
    tns = collections.Counter(top_ns(t["module"]) for t in tgt)

    # 3. project yield: per-target expected pass prob = corpus_v3 rate for its ns,
    #    else a fallback (advanced-math pooled, the right reference class for
    #    namespaces absent from corpus_v3 — RingTheory/LinearAlgebra/Probability/...).
    covered = uncovered = 0
    exp_mapped = exp_advfallback = exp_poolfallback = 0.0
    per_ns = {}
    for k, n in tns.items():
        if k in rate:
            covered += n
            r = rate[k]
            exp_mapped += n * r
            exp_advfallback += n * r
            exp_poolfallback += n * r
            per_ns[k] = {"n": n, "rate": round(r, 3), "source": "corpus_v3-matched"}
        else:
            uncovered += n
            exp_advfallback += n * adv_pooled
            exp_poolfallback += n * pooled
            per_ns[k] = {"n": n, "rate": None, "source": "unmapped"}

    n_tgt = len(tgt)
    result = {
        "description": "q-0009 cost-scoping gate: project data/deep round-trip yield "
        "from corpus_v3 per-namespace round-trip rates, vs the inherited pooled 84.7%.",
        "corpus_v3_pooled_rate": round(pooled, 4),
        "corpus_v3_advanced_pooled_rate": round(adv_pooled, 4),
        "corpus_v3_foundational_excluded": sorted(FOUNDATIONAL),
        "corpus_v3_rate_by_namespace": {
            k: {"pass": v[0], "total": v[1], "rate": round(v[0] / v[1], 3)}
            for k, v in sorted(ns.items())
        },
        "n_wide_targets": n_tgt,
        "targets_by_namespace": dict(tns.most_common()),
        "targets_covered_by_corpus_v3_ns": covered,
        "targets_unmapped_ns": uncovered,
        "projection": {
            "expected_verified_matched_only_over_covered": round(exp_mapped, 1),
            "covered_denom": covered,
            "expected_verified_advfallback_over_all": round(exp_advfallback, 1),
            "expected_verified_poolfallback_over_all": round(exp_poolfallback, 1),
            "naive_inherited_84p7_over_all": round(pooled * n_tgt, 1),
        },
        "per_ns_detail": per_ns,
    }

    json.dump(result, open(OUT, "w"), indent=1)

    # console report
    print("=== corpus_v3 round-trip pass rate by top namespace ===")
    for k, v in sorted(ns.items(), key=lambda x: -x[1][0] / x[1][1]):
        flag = "  (foundational, excluded from adv)" if k in FOUNDATIONAL else ""
        print(f"  {k:16s} {v[0]:4d}/{v[1]:<4d} {100*v[0]/v[1]:5.1f}%{flag}")
    print(f"  POOLED            {pooled_pass}/{pooled_total} = {100*pooled:.1f}%")
    print(f"  ADVANCED pooled (ex Data,Logic) = {100*adv_pooled:.1f}%")
    print()
    print(f"=== {n_tgt} wide-frontier targets by namespace ===")
    for k, n in tns.most_common():
        r = rate.get(k)
        tag = f"corpus_v3 {100*r:.1f}%" if r is not None else "UNMAPPED -> fallback"
        print(f"  {k:18s} {n:4d}   {tag}")
    print(f"\n  covered by corpus_v3 ns: {covered}/{n_tgt}   unmapped: {uncovered}")
    print("\n=== projected verified yield over 633 targets ===")
    print(f"  naive inherited pooled 84.7%      : {pooled*n_tgt:6.1f} verified")
    print(f"  per-ns, unmapped<-pooled 84.7%    : {exp_poolfallback:6.1f} verified "
          f"({100*exp_poolfallback/n_tgt:.1f}%)")
    print(f"  per-ns, unmapped<-advanced pooled : {exp_advfallback:6.1f} verified "
          f"({100*exp_advfallback/n_tgt:.1f}%)")
    print(f"  matched-only mean rate over covered: "
          f"{100*exp_mapped/covered:.1f}% ({exp_mapped:.1f}/{covered})")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
