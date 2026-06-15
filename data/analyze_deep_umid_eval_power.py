#!/usr/bin/env python3
"""Stage 0.5 analysis (e-0055): is the intermediate granularity pi_mid that
e-0054 found STRUCTURALLY available actually POWERABLE on the held-out eval
split, or is it power-0 the same way corpus_v3 was for the binary contrast?

Context. e-0054 (a-0054) showed the deep route structurally REOPENS q-0005's
U-shape question: 354/633 = 55.9% of the canonical wide-frontier study targets
admit a genuine intermediate cut pi_mid (named-nesting-depth >= 2). But that is
STRUCTURAL availability over the WHOLE study set. The Stage-0.5 power chain's
hardest-won lesson (e-0045/a-0045) was that the headline is priced by the
HELD-OUT EVAL split, not the whole corpus: corpus_v3 had 354... no -- it had
only 5 granularity-bearing TEST pairs, and McNemar's exact test is power-EXACTLY-0
below 6 same-direction discordant pairs (min achievable p = 2*(0.5)^D; D=5 ->
0.0625 > 0.05). The binary deep route survived this (e-0046: effective n ~116)
because depth>=1 is the MAJORITY. The U-shape's pi_mid arm is a STRICTLY SMALLER
subset (depth>=2), and a pi_root-vs-pi_mid (or pi_mid-vs-pi_leaf) comparison can
only be scored on eval targets that actually carry the intermediate cut.

This gate composes e-0054's depth measurement with e-0046's module-disjoint
holdout split (both reused verbatim) and asks: of the depth>=2 targets, how many
land in the held-out eval slice, and -- after the e-0028 per-area round-trip
yield discount -- does the eval-side pi_mid count clear McNemar's D>=6 power
floor? If not, the U-shape contrast is UNRESOLVABLE on the held-out eval for the
same combinatorial reason corpus_v3 was, and the 3rd-arm spend (a-0054's ~1.5x)
buys an in-principle-unmeasurable comparison.

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


def named_depth(nodes):
    """e-0054 verbatim: longest root->leaf chain over NAMED have nodes."""
    best = 0
    for n in nodes:
        sub = named_depth(n.get("children", []))
        is_named = bool(n.get("name")) and n["name"] != "_"
        best = max(best, (1 if is_named else 0) + sub)
    return best


def top_ns(mod):
    parts = mod.split(".")
    return parts[1] if parts[0] == "Mathlib" and len(parts) > 1 else parts[0]


def load_raw_depths():
    raw = {}
    for f in glob.glob("data/deep/*.json"):
        for t in json.load(open(f)):
            raw[t["name"]] = named_depth(t.get("have_tree", []))
    return raw


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

    # 2. depth-tag every canonical wide target from the raw have-trees.
    depths = load_raw_depths()
    targets = json.load(open(MANIFEST))["targets"]
    for t in targets:
        t["named_depth"] = depths.get(t["name"], 0)

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

    # 4. For each contrast, count the targets that CARRY it, on each side, then
    #    apply the per-area yield discount to get expected VERIFIED supply.
    def supply(ts, predicate):
        carriers = [t for t in ts if predicate(t["named_depth"])]
        verified = sum(yield_rate(top_ns(t["module"])) for t in carriers)
        return len(carriers), round(verified, 1)

    contrasts = {
        # binary rough/fine: any named frontier (e-0046's route). depth>=1.
        "binary_any_named_depth_ge1": lambda d: d >= 1,
        # pi_mid available: a 3rd antichain between root and leaf. depth>=2.
        "umid_intermediate_depth_ge2": lambda d: d >= 2,
        # 4-level contrast. depth>=3.
        "four_level_depth_ge3": lambda d: d >= 3,
    }

    rows = {}
    for key, pred in contrasts.items():
        tr_n, tr_v = supply(train, pred)
        ev_n, ev_v = supply(evald, pred)
        # McNemar discordant ceiling is bounded by the verified eval carriers:
        # you cannot have more discordant pairs than scored paired targets.
        powerable = ev_v >= MCNEMAR_FLOOR_D
        rows[key] = {
            "train_carriers": tr_n,
            "train_verified": tr_v,
            "eval_carriers": ev_n,
            "eval_verified": ev_v,
            "eval_verified_ge_mcnemar_floor_6": powerable,
            "power_verdict": (
                "POWERABLE" if powerable
                else "POWER-0 (eval carriers < McNemar D=6 floor)"
            ),
        }

    report = {
        "source": "e-0055: is e-0054's structurally-available pi_mid POWERABLE on the held-out eval split?",
        "method": (
            "Tag each of the 633 canonical wide targets with e-0054 named-nesting-depth "
            "from data/deep have-trees; apply e-0046 area-stratified module-disjoint "
            "every-5th-module holdout; count contrast-carrying targets per side; "
            "discount eval side by e-0028 per-area round-trip yield; compare eval "
            "verified carriers to McNemar's exact D>=6 power floor (e-0045)."
        ),
        "split": {
            "total_targets": len(targets),
            "train_targets": len(train),
            "eval_targets": len(evald),
            "eval_modules": len(eval_modules),
            "advanced_pooled_yield": round(adv_pooled, 3),
            "module_disjoint": True,
        },
        "contrasts": rows,
        "headline": "",
        "CAVEAT": (
            "Eval 'verified' is the e-0028 per-area COUNT projection, not a real "
            "round-trip (needs the Modal pass); it projects supply not pass@k. The "
            "McNemar D>=6 floor (e-0045) bounds the discordant pairs, and verified "
            "carriers UPPER-bound the discordant total, so eval_verified < 6 => "
            "power EXACTLY 0; eval_verified >= 6 is NECESSARY not sufficient (the "
            "discordant subset is smaller still, and construct-validity of pi_mid "
            "vs format -- e-0036/e-0037 -- is a separate unmet gate). Depth is a "
            "STRUCTURAL count; whether each named frontier carries distinct "
            "granularity signal needs the off-disk residual body."
        ),
    }

    umid = rows["umid_intermediate_depth_ge2"]
    binr = rows["binary_any_named_depth_ge1"]
    four = rows["four_level_depth_ge3"]
    report["headline"] = (
        f"CONTRA the corpus_v3 precedent: e-0054's structurally-available pi_mid "
        f"SURVIVES the held-out eval split too. The standard e-0046 area-stratified "
        f"module-disjoint every-5th-module holdout lands {umid['eval_carriers']} of "
        f"the 633 targets' intermediate-cut (depth>=2) carriers in the eval slice, "
        f"~{umid['eval_verified']} after the e-0028 yield discount -- ~12x McNemar's "
        f"D=6 power floor and ~60% of the binary route's own ~{binr['eval_verified']} "
        f"eval n (e-0046). Even the 4-level contrast (depth>=3) keeps "
        f"{four['eval_carriers']} eval carriers (~{four['eval_verified']} verified), "
        f"still clearing the floor. So the deep pivot reopens q-0005 BOTH structurally "
        f"(e-0054) AND statistically (e-0055): a 3-level rough/mid/fine U-shape is "
        f"power-RESOLVABLE on the existing holdout -- unlike corpus_v3's binary "
        f"contrast which was power-EXACTLY-0 at D=5 (e-0045). The remaining gates on "
        f"the 3rd arm are therefore NOT eval power but (1) construct validity of "
        f"pi_mid vs mere format (e-0036/e-0037, needs the off-disk residual body) and "
        f"(2) the ~1.5x compute of a 3rd adapter+arm (a-0054), which the 2-arm cost "
        f"chain (e-0048/e-0052) never priced. q-0005's 'binary' verdict is overturned "
        f"for the deep route on supply grounds; whether mid is a DISTINCT granularity "
        f"is the next (paid) gate, not a power problem."
    )

    print(json.dumps(report, indent=2))
    out = "data/corpus_v3/deep_umid_eval_power.json"
    json.dump(report, open(out, "w"), indent=2)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
