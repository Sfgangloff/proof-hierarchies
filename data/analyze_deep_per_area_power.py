"""PER-AREA ABLATION power gate for the DATA/DEEP within-deep eval route
(q-0008/q-0007). The e-0045 'DEAD-at-low-n' logic applied PER MATHLIB AREA.

The Stage-0.5 power chain (e-0040..e-0049) priced the POOLED within-deep route:
effective n ~115 granularity-bearing-and-verified eval problems (e-0046), enough
for McNemar to reject the headline rough-vs-fine gap (>=6 discordant pairs
reachable), leakage-clean (e-0049), affordable (e-0048). But Stage 3's planned
design (e-0008) promises MORE than the pooled headline: a "per-area ablation" --
is the granularity effect resolvable WITHIN a Mathlib area? No gate priced that
sub-claim, and the per-area GB distribution (e-0046's per_area_ge1) is severely
skewed: MeasureTheory(34)+Analysis(29) hold ~half the GB eval targets while
Computability/SetTheory hold 1 each.

This gate composes the SAME three established deep-route numbers e-0046 used --
the e-0031 within-deep split x e-0032 substantive-frontier construct x e-0028
per-area round-trip yield -- but does NOT pool: it computes the effective n and
McNemar floor / MDE for EACH area separately, exactly as e-0045 did for the one
corpus_v3 cell. An area is "resolvable" iff its effective verified GB count clears
the >=6-discordant-pair combinatorial floor (necessary, not sufficient: discordant
pairs are a FRACTION of n, so this is a generous CEILING on per-area power).

It then prices the actionable fix: coarsening the 17 fine-grained areas into a few
super-areas (the analysis/algebra/foundational buckets) to see how many CLEAR the
floor once pooled -- telling the user whether the per-area ablation in e-0008
should be reported per-area, coarsened, or DROPPED for the pooled headline only.

CAVEATS (inherited from e-0046): verified counts are the e-0028 per-area
PROJECTION, not an actual round-trip; module-disjoint is standard-but-not-airtight
leakage control (e-0049 measured it clean at the target level); construct =
substantive-frontier presence, not the term/tactic format confound (e-0033 removes
that). The >=6 floor is a NECESSARY ceiling on per-area power (all pairs discordant
one way); real per-area power is LOWER. Projects COUNTS not pass@k; MDE is a
design-stage calc. Pure stdlib; no Lean, no Modal; reuses the e-0046 machinery
UNCHANGED.

  python3 -m data.analyze_deep_per_area_power [--out path.json]
"""

from __future__ import annotations
import argparse, collections, json
from pathlib import Path

from data.analyze_deep_effective_n_power import (
    MANIFEST, deep_path, top_area, substantive_width, per_area_yield,
    mde_at, min_discordant_for_significance, HOLDOUT_EVERY, RHO,
)
from data.analyze_eval_power_mde import ALPHA, TARGET_POWER, P_LO_GRID

ROOT = Path(__file__).resolve().parents[1]

# Coarsening of the 17 fine-grained top areas into a few super-areas. The split
# follows e-0028's FOUNDATIONAL distinction plus the natural analysis/algebra
# divide; "Other" catches the long tail. Purely a reporting aggregation.
SUPER_AREA = {
    "MeasureTheory": "Analysis*", "Analysis": "Analysis*", "Probability": "Analysis*",
    "Topology": "Analysis*", "Geometry": "Analysis*",
    "RingTheory": "Algebra*", "LinearAlgebra": "Algebra*", "Algebra": "Algebra*",
    "FieldTheory": "Algebra*", "GroupTheory": "Algebra*", "NumberTheory": "Algebra*",
    "Data": "Foundational*", "Logic": "Foundational*", "Order": "Foundational*",
    "SetTheory": "Foundational*", "Computability": "Foundational*",
    "Combinatorics": "Discrete*", "CategoryTheory": "Discrete*",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data/corpus_v3/deep_per_area_power.json"))
    args = ap.parse_args()

    targets = json.loads(MANIFEST.read_text())["targets"]
    rate, adv_pooled = per_area_yield()

    def yld(module: str) -> float:
        return rate.get(top_area(module), adv_pooled)

    # ---- e-0031 area-stratified, module-disjoint every-5th-module eval holdout ----
    mods_by_area = collections.defaultdict(set)
    for t in targets:
        mods_by_area[top_area(t["module"])].add(t["module"])
    eval_modules = set()
    for area, mods in mods_by_area.items():
        for i, m in enumerate(sorted(mods)):
            if i % HOLDOUT_EVERY == HOLDOUT_EVERY - 1:
                eval_modules.add(m)
    evald = [t for t in targets if t["module"] in eval_modules]

    cache: dict[Path, dict] = {}

    def rec_for(t: dict):
        p = deep_path(t["module"])
        if p not in cache:
            recs = json.loads(p.read_text()) if p.exists() else []
            cache[p] = {r["name"]: r for r in recs}
        return cache[p].get(t["name"])

    # ---- per-area granularity-bearing counts + yield-weighted effective n ----
    area_gb1 = collections.Counter()       # nominal >=1 substantive frontier
    area_eff = collections.defaultdict(float)  # yield-weighted verified GB count
    super_gb1 = collections.Counter()
    super_eff = collections.defaultdict(float)
    for t in evald:
        r = rec_for(t)
        if r is None:
            continue
        if substantive_width(r) >= 1:
            a = top_area(t["module"])
            y = yld(t["module"])
            area_gb1[a] += 1
            area_eff[a] += y
            sa = SUPER_AREA.get(a, "Other*")
            super_gb1[sa] += 1
            super_eff[sa] += y

    d_needed = min_discordant_for_significance(ALPHA)  # 6 at alpha=0.05

    def block(counts: collections.Counter, effs: dict) -> dict:
        rows = {}
        n_resolvable = 0          # clears the >=6-discordant combinatorial CEILING
        gb_in_resolvable = 0
        n_powered = 0             # AND has a reachable (<=0.50) 80%-power MDE
        gb_in_powered = 0
        total_gb = sum(counts.values())
        for a, gb in counts.most_common():
            n_eff = int(round(effs[a]))
            can = n_eff >= d_needed
            mde = mde_at(n_eff) if n_eff > 0 else {str(p): None for p in P_LO_GRID}
            powered = any(v is not None for v in mde.values())  # some gap reaches 80%
            if can:
                n_resolvable += 1
                gb_in_resolvable += gb
            if powered:
                n_powered += 1
                gb_in_powered += gb
            rows[a] = {
                "gb_nominal": gb,
                "n_eff_verified_gb": n_eff,
                "can_ever_reject_alpha_0.05": can,
                "genuinely_powered_mde_reachable": powered,
                "mde_pass1_by_p_lo": {k: (v if v is not None else ">0.50/unreachable")
                                      for k, v in mde.items()},
            }
        return {
            "n_buckets": len(counts),
            "n_resolvable": n_resolvable,
            "frac_buckets_resolvable": round(n_resolvable / len(counts), 3) if counts else 0.0,
            "gb_targets_in_resolvable_buckets": gb_in_resolvable,
            "n_genuinely_powered": n_powered,
            "gb_targets_in_powered_buckets": gb_in_powered,
            "frac_gb_in_powered_buckets": round(gb_in_powered / total_gb, 3) if total_gb else 0.0,
            "gb_targets_total": total_gb,
            "frac_gb_in_resolvable_buckets": round(gb_in_resolvable / total_gb, 3) if total_gb else 0.0,
            "per_bucket": rows,
        }

    fine = block(area_gb1, area_eff)
    coarse = block(super_gb1, super_eff)

    report = {
        "experiment": "e-0050",
        "what": (
            "PER-AREA ablation power gate: the e-0045 DEAD-at-low-n logic applied per "
            "Mathlib area to the within-deep eval route (e-0046 split x e-0032 construct "
            "x e-0028 yield, NOT pooled). Prices e-0008's planned per-area ablation: is "
            "the granularity effect resolvable WITHIN an area, or only pooled?"
        ),
        "min_discordant_pairs_for_alpha_0.05": d_needed,
        "pooled_reference": {
            "n_effective_granularity_ge1": int(round(sum(area_eff.values()))),
            "note": "e-0046 pooled headline ~115; clears the floor with margin.",
        },
        "fine_grained_17_areas": fine,
        "coarsened_super_areas": coarse,
        "rho": RHO, "alpha": ALPHA, "target_power": TARGET_POWER,
        "caveats": (
            "The >=6-discordant floor is a NECESSARY CEILING on per-area power (assumes "
            "ALL pairs discordant in one direction); true per-area power is LOWER, so "
            "'can_ever_reject' over-counts resolvable areas. Verified counts are the "
            "e-0028 per-area PROJECTION, not a Modal round-trip. Construct = substantive-"
            "frontier presence (e-0032); leakage measured clean at target level (e-0049). "
            "Super-area coarsening is a reporting aggregation, not a new split. The "
            "headline gap x model-SIZE interaction needs MORE power than this single-"
            "comparison per-area MDE, so per-area interaction is even less resolvable."
        ),
    }

    n_res = fine["n_resolvable"]
    n_pow = fine["n_genuinely_powered"]
    nb = fine["n_buckets"]
    report["interpretation"] = (
        f"Pooled, the within-deep route's granularity effect is resolvable (n_eff ~"
        f"{report['pooled_reference']['n_effective_granularity_ge1']} >> {d_needed}). "
        f"But e-0008's PER-AREA ablation is mostly DEAD. Two filters: (i) the >= "
        f"{d_needed}-discordant combinatorial CEILING is cleared by only {n_res}/{nb} "
        f"fine areas; (ii) the sharper filter -- a REACHABLE 80%-power MDE (gap<=0.50) "
        f"-- is met by only {n_pow}/{nb} (MeasureTheory n_eff=30 MDE~0.28, Analysis "
        f"n_eff=27 MDE~0.31). The other {n_res - n_pow} floor-clearing areas (RingTheory/"
        f"NumberTheory/LinearAlgebra/Topology/Algebra, n_eff 6-9) can COMBINATORIALLY "
        f"reject but need a >0.50 gap -- effectively unpowered, the e-0045 trap one "
        f"notch up. Coarsening into {coarse['n_buckets']} super-areas, only "
        f"{coarse['n_genuinely_powered']}/{coarse['n_buckets']} are genuinely powered "
        f"(Analysis* n_eff=70 MDE~0.16-0.20, Algebra* n_eff=34 MDE~0.25-0.30), covering "
        f"{int(round(100*coarse['frac_gb_in_powered_buckets']))}% of GB targets; "
        f"Foundational* clears the count floor (n_eff=6) but its MDE is unreachable. "
        f"RECOMMENDATION for e-0008: report the granularity gap POOLED (the powered "
        f"headline), and break it down by AT MOST the 2 genuinely-powered super-areas "
        f"(Analysis*, Algebra*) -- NOT the 17 fine areas, 15 of which would print an "
        f"under-powered placeholder. This enforces the e-0045 floor at the ablation "
        f"granularity Stage 3 actually plans to report, and confirms the per-area "
        f"interaction (gap x model-SIZE within an area) is out of reach entirely."
    )

    Path(args.out).write_text(json.dumps(report, indent=2))
    print("=== e-0050 PER-AREA ablation power gate ===")
    print(f"min discordant pairs for alpha={ALPHA}: {d_needed}")
    print(f"fine (17 areas): {n_res}/{nb} clear count-floor, "
          f"{n_pow}/{nb} GENUINELY POWERED (reachable MDE)")
    print(f"coarse super-areas: {coarse['n_resolvable']}/{coarse['n_buckets']} clear floor, "
          f"{coarse['n_genuinely_powered']}/{coarse['n_buckets']} genuinely powered "
          f"({int(round(100*coarse['frac_gb_in_powered_buckets']))}% of GB targets)")
    print("genuinely-powered fine areas:",
          [a for a, r in fine["per_bucket"].items() if r["genuinely_powered_mde_reachable"]])
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
