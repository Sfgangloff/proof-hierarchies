#!/usr/bin/env python3
"""Stage 0.5 analysis (e-0057): does e-0055's POWERABLE pi_mid survive when the
nesting depth counts only CONSTRUCT-VALID (non-empty-body) named haves -- i.e.
is the U-shape reopening (a-0053) a granularity artifact or real?

Context. e-0055 (a-0053) showed the deep route REOPENS q-0005's intermediate
pi_mid contrast on the held-out eval: depth>=2 carriers land ~70 verified eval
targets, ~12x McNemar's D=6 floor. But a-0053's own headline caveat names the
unmet gate: "depth is a STRUCTURAL count; whether each named frontier carries
distinct granularity signal is the unmet construct-validity gate."

e-0055's named_depth (verbatim from e-0054) counts EVERY named have node, INCLUDING
nodes with an EMPTY body. But e-0026/analyze_deep_construct_validity.py already
established the construct unit precisely: a frontier node with an EMPTY body is a
hypothesis / destructuring binder (obtain/rcases/intro), NOT an independent
sub-derivation, so it carries NO inline-or-name granularity contrast. That
substantive-body filter was applied to the TOP frontier only -- never composed
into the NESTED depth that pi_mid depends on. So a chain
    named-have(empty binder) -> named-have(empty binder)
counts as depth>=2 under e-0055 yet offers NO genuine intermediate cut: neither
named level is an inline-able sub-result. The pi_mid eval-power verdict could be
inflated by these binder-only chains.

This gate re-runs e-0055's exact split + yield + McNemar floor (all verbatim),
swapping ONLY the depth definition: SUBSTANTIVE named depth = longest root->leaf
chain counting named nodes whose body is a real proof (non-empty), reusing
analyze_deep_construct_validity.py's body classification verbatim. It reports the
raw vs substantive contrast side-by-side so the construct-validity erosion is
explicit, and re-tests whether pi_mid (substantive depth>=2) still clears the
D>=6 power floor on the held-out eval.

If substantive pi_mid still clears the floor, a-0053's U-shape reopening is
construct-hardened (the intermediate cut is real sub-derivations, not binders),
shrinking the remaining 3rd-arm gate to the FORMAT confound (e-0036/e-0037, the
genuinely off-disk part) + compute alone. If it collapses below 6, the U-shape
reopening is downgraded: structurally available but construct-poor on the eval.

This part of the construct gate IS on-disk (bodies live in data/deep/*.json);
only the term-vs-tactic FORMAT half (e-0036/e-0037) needs the paid extract.

Pure-stdlib, CPU-only. No Lean, no Modal.
"""
import glob
import json
import os
import collections

VERIFY_DIR = "data/corpus_v3/verify"
MANIFEST = "data/corpus_v3/deep_wide_targets.json"
HOLDOUT_EVERY = 5          # e-0046's area-stratified ~80/20 module-disjoint holdout.
MCNEMAR_FLOOR_D = 6        # e-0045: exact two-sided McNemar needs >=6 discordant
                           # same-direction pairs to reach alpha=0.05.


def is_substantive(node):
    """analyze_deep_construct_validity.py verbatim: a named node carries the
    granularity construct iff it has its OWN proof body (non-empty). Empty body
    = hypothesis / obtain/rcases/intro binder, no inline-or-name contrast."""
    return (node.get("body") or "").strip() != ""


def named_depth_raw(nodes):
    """e-0054/e-0055 verbatim: longest root->leaf chain over ALL named nodes."""
    best = 0
    for n in nodes:
        sub = named_depth_raw(n.get("children", []))
        is_named = bool(n.get("name")) and n["name"] != "_"
        best = max(best, (1 if is_named else 0) + sub)
    return best


def named_depth_substantive(nodes):
    """Construct-valid variant: count a named node toward depth ONLY if it is
    BOTH named AND substantive (non-empty body = a real sub-derivation)."""
    best = 0
    for n in nodes:
        sub = named_depth_substantive(n.get("children", []))
        is_named = bool(n.get("name")) and n["name"] != "_"
        counts = is_named and is_substantive(n)
        best = max(best, (1 if counts else 0) + sub)
    return best


def top_ns(mod):
    parts = mod.split(".")
    return parts[1] if parts[0] == "Mathlib" and len(parts) > 1 else parts[0]


def load_depths():
    raw, sub = {}, {}
    for f in glob.glob("data/deep/*.json"):
        if "/._" in f:
            continue
        for t in json.load(open(f)):
            tree = t.get("have_tree", [])
            raw[t["name"]] = named_depth_raw(tree)
            sub[t["name"]] = named_depth_substantive(tree)
    return raw, sub


def main():
    # 1. e-0028/e-0029 per-namespace corpus_v3 round-trip yield (verbatim).
    ns = collections.defaultdict(lambda: [0, 0])
    for f in glob.glob(os.path.join(VERIFY_DIR, "*.json")):
        if "_overall" in f:
            continue
        s = json.load(open(f))["summary"]
        ns[top_ns(s["module"])][0] += s["pass"]
        ns[top_ns(s["module"])][1] += s["total"]
    rate = {k: v[0] / v[1] for k, v in ns.items()}
    FOUNDATIONAL = {"Data", "Logic"}
    adv_p = sum(v[0] for k, v in ns.items() if k not in FOUNDATIONAL)
    adv_t = sum(v[1] for k, v in ns.items() if k not in FOUNDATIONAL)
    adv_pooled = adv_p / adv_t

    def yield_rate(namespace):
        return rate.get(namespace, adv_pooled)

    # 2. depth-tag every canonical wide target, both definitions.
    raw_d, sub_d = load_depths()
    targets = json.load(open(MANIFEST))["targets"]
    for t in targets:
        t["raw_depth"] = raw_d.get(t["name"], 0)
        t["sub_depth"] = sub_d.get(t["name"], 0)

    # 3. e-0046 area-stratified, module-disjoint every-5th-module holdout (verbatim).
    mods_by_area = collections.defaultdict(set)
    for t in targets:
        mods_by_area[top_ns(t["module"])].add(t["module"])
    eval_modules = set()
    for area, mods in mods_by_area.items():
        for i, m in enumerate(sorted(mods)):
            if i % HOLDOUT_EVERY == HOLDOUT_EVERY - 1:
                eval_modules.add(m)

    train = [t for t in targets if t["module"] not in eval_modules]
    evald = [t for t in targets if t["module"] in eval_modules]

    # 4. supply = carriers x per-area yield discount, for a given depth field+pred.
    def supply(ts, field, thresh):
        carriers = [t for t in ts if t[field] >= thresh]
        verified = sum(yield_rate(top_ns(t["module"])) for t in carriers)
        return len(carriers), round(verified, 1)

    def contrast(field, thresh):
        tr_n, tr_v = supply(train, field, thresh)
        ev_n, ev_v = supply(evald, field, thresh)
        powerable = ev_v >= MCNEMAR_FLOOR_D
        return {
            "train_carriers": tr_n,
            "train_verified": tr_v,
            "eval_carriers": ev_n,
            "eval_verified": ev_v,
            "eval_verified_ge_mcnemar_floor_6": powerable,
            "power_verdict": (
                "POWERABLE" if powerable
                else "POWER-0 (eval verified carriers < McNemar D=6 floor)"
            ),
        }

    # The decision-critical comparisons: pi_mid (depth>=2) and 4-level (depth>=3),
    # each scored under e-0055's RAW depth and this gate's SUBSTANTIVE depth.
    rows = {
        "umid_depth_ge2_RAW(e-0055)": contrast("raw_depth", 2),
        "umid_depth_ge2_SUBSTANTIVE": contrast("sub_depth", 2),
        "four_level_depth_ge3_RAW(e-0055)": contrast("raw_depth", 3),
        "four_level_depth_ge3_SUBSTANTIVE": contrast("sub_depth", 3),
        "binary_depth_ge1_SUBSTANTIVE": contrast("sub_depth", 1),
    }

    # whole-study structural availability (a-0053 reported 55.9% on raw depth>=2).
    n = len(targets)
    raw_ge2 = sum(1 for t in targets if t["raw_depth"] >= 2)
    sub_ge2 = sum(1 for t in targets if t["sub_depth"] >= 2)
    raw_ge3 = sum(1 for t in targets if t["raw_depth"] >= 3)
    sub_ge3 = sum(1 for t in targets if t["sub_depth"] >= 3)

    umid_raw = rows["umid_depth_ge2_RAW(e-0055)"]
    umid_sub = rows["umid_depth_ge2_SUBSTANTIVE"]
    retention = (umid_sub["eval_verified"] / umid_raw["eval_verified"]
                 if umid_raw["eval_verified"] else 0.0)

    report = {
        "source": (
            "e-0057: construct-valid hardening of e-0055/a-0053's pi_mid eval-power "
            "verdict -- does pi_mid survive when nesting depth counts only "
            "substantive (non-empty-body) named haves, not binder-only chains?"
        ),
        "method": (
            "Re-run e-0055 verbatim (e-0046 split, e-0028 per-area yield, e-0045 "
            "D>=6 floor) swapping ONLY the depth: SUBSTANTIVE named depth counts a "
            "named node iff its body is a real proof (non-empty), reusing "
            "analyze_deep_construct_validity.py's body classification. Side-by-side "
            "vs e-0055's RAW named depth."
        ),
        "structural_availability_whole_study": {
            "total_targets": n,
            "raw_depth_ge2_pct": round(100 * raw_ge2 / n, 1),
            "substantive_depth_ge2_pct": round(100 * sub_ge2 / n, 1),
            "raw_depth_ge3_pct": round(100 * raw_ge3 / n, 1),
            "substantive_depth_ge3_pct": round(100 * sub_ge3 / n, 1),
        },
        "split": {
            "total_targets": len(targets),
            "train_targets": len(train),
            "eval_targets": len(evald),
            "eval_modules": len(eval_modules),
            "advanced_pooled_yield": round(adv_pooled, 3),
            "module_disjoint": True,
        },
        "contrasts": rows,
        "pi_mid_eval_verified_retention_substantive_over_raw": round(retention, 3),
        "headline": "",
        "CAVEAT": (
            "This hardens ONE half of a-0053's construct gate: the substantive-body "
            "(is-it-a-real-sub-derivation) half, which is on-disk. The OTHER half -- "
            "term-vs-tactic FORMAT confound (e-0036/e-0037) -- still needs the paid "
            "extract and is untouched. Eval 'verified' remains the e-0028 per-area "
            "COUNT projection, not a real round-trip; it projects supply not pass@k. "
            "Verified carriers UPPER-bound the McNemar discordant total, so >=6 is "
            "NECESSARY not sufficient. Body classification ('by'/term/empty) is "
            "syntactic; a one-token term-mode body still counts as substantive."
        ),
    }

    if umid_sub["eval_verified_ge_mcnemar_floor_6"]:
        report["headline"] = (
            f"pi_mid SURVIVES the construct-valid tightening. Counting only "
            f"substantive (non-empty-body) named haves, the intermediate-cut "
            f"(depth>=2) eval supply falls from e-0055's ~{umid_raw['eval_verified']} "
            f"to ~{umid_sub['eval_verified']} verified carriers "
            f"({round(100*retention)}% retained) -- still ~{umid_sub['eval_verified']/MCNEMAR_FLOOR_D:.1f}x "
            f"the McNemar D=6 floor. Whole-study availability holds at "
            f"{report['structural_availability_whole_study']['substantive_depth_ge2_pct']}% "
            f"(vs e-0054's {report['structural_availability_whole_study']['raw_depth_ge2_pct']}% raw). "
            f"So a-0053's U-shape reopening is NOT a binder-chain artifact: the "
            f"intermediate named level carries real inline-able sub-derivations, "
            f"and pi_mid stays power-resolvable on the existing holdout. The 4-level "
            f"depth>=3 arm drops to ~{rows['four_level_depth_ge3_SUBSTANTIVE']['eval_verified']} "
            f"verified ({rows['four_level_depth_ge3_SUBSTANTIVE']['power_verdict']}). "
            f"Remaining 3rd-arm gate shrinks to the FORMAT confound (e-0036/e-0037, "
            f"off-disk) + ~1.5x compute (a-0054) -- the on-disk construct half is now "
            f"cleared for the 3-level contrast."
        )
    else:
        report["headline"] = (
            f"pi_mid COLLAPSES under construct-valid tightening: substantive "
            f"intermediate-cut eval supply falls from ~{umid_raw['eval_verified']} "
            f"(e-0055 raw) to ~{umid_sub['eval_verified']} verified carriers "
            f"({round(100*retention)}% retained), BELOW McNemar's D=6 floor. So "
            f"a-0053's U-shape reopening was inflated by binder-only named chains "
            f"(obtain/rcases stacked but no real sub-derivation between root and "
            f"leaf). The 3-level contrast is structurally available "
            f"({report['structural_availability_whole_study']['substantive_depth_ge2_pct']}% "
            f"of targets) but power-poor on the held-out eval once empty-body binders "
            f"are excluded -- downgrading the U-shape reopening for the deep route."
        )

    print(json.dumps(report, indent=2))
    out = "data/corpus_v3/deep_umid_substantive_depth.json"
    json.dump(report, open(out, "w"), indent=2)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
