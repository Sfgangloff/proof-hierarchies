"""EFFECTIVE-n / power gate for the DATA/DEEP within-deep eval route -- the
e-0045 analogue on the corpus the project PIVOTED TO (q-0007/q-0001).

e-0045 (a-0045) fused two Stage-0.5 threads on corpus_v3 and found the headline
granularity eval is DEAD there: the held-out test split has 63 pairs but only
~5 are granularity-bearing (the rest are FORMAT-ONLY, e-0026/a-0026), and
McNemar's exact two-sided test needs >=6 same-direction discordant pairs to reach
alpha=0.05, so with a discordant ceiling of 5 the granularity effect has power
EXACTLY 0 under ANY effect size. Its terminal recommendation was explicit:

    "To make the granularity effect even POSSIBLE to resolve, the eval must draw
     its held-out set from granularity-bearing decls (the data/deep route) --
     corpus_v3's split cannot do it."

That recommendation was never QUANTIFIED. This gate does it: it computes the
effective-n and MDE of the data/deep within-deep eval route by MULTIPLYING the
three established deep-route numbers that no prior gate composed --

  (1) the within-deep module-disjoint eval SPLIT (e-0031/a-0031): an area-
      stratified, leakage-controlled every-5th-module holdout carves 131 eval
      targets (~115.8 expected verified) out of the 633 wide-frontier manifest;

  (2) the deep CONSTRUCT VALIDITY rate (e-0032/a-0032): a deep wide-frontier
      target is granularity-bearing iff it has a SUBSTANTIVE frontier (>=1 named
      have-node with its OWN non-empty proof body, the unit pi_root inlines and
      pi_leaf keeps named); 95.4% of the 633 clear >=2 -- the inverse of
      corpus_v3's 6.9%;

  (3) the per-namespace round-trip YIELD (e-0028/a-0028): only verified pairs
      become eval problems, so the granularity-bearing eval count must be
      discounted by each area's corpus_v3 round-trip rate (advanced-pooled for
      namespaces absent from corpus_v3).

The effective n for the granularity effect on the deep route is therefore the
number of eval-split targets that are BOTH granularity-bearing AND verified --
the deep analogue of e-0045's 5. Feed it through e-0040's own McNemar/Gaussian-
copula MDE machinery (imported UNCHANGED, exactly as e-0045 did) to get the
effective MDE, and contrast with e-0045's power-0 verdict on corpus_v3.

CAVEATS (inherited): verified counts are the e-0028 per-area PROJECTION, not an
actual round-trip (needs the Modal pass); module-disjoint is the standard but not
airtight leakage control (e-0031); substantive-frontier construct = inline-able
have presence, not the term-vs-tactic FORMAT confound, which the same-format
build (e-0033) removes by construction. Projects COUNTS not pass@k; the MDE is a
design-stage power calc on marginals the user still picks. Pure stdlib; no Lean,
no Modal; reuses data.analyze_eval_power_mde and the e-0031/e-0032/e-0028 logic.

  python3 -m data.analyze_deep_effective_n_power [--out path.json]
"""

from __future__ import annotations
import argparse, collections, glob, json, os, random, statistics
from pathlib import Path

# reuse the e-0040 paired-McNemar Gaussian-copula machinery UNCHANGED (as e-0045)
from data.analyze_eval_power_mde import (
    simulate_power, ALPHA, TARGET_POWER, M, P_LO_GRID, DELTA_GRID,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/corpus_v3/deep_wide_targets.json"
DEEP_DIR = ROOT / "data/deep"
VERIFY_DIR = ROOT / "data/corpus_v3/verify"

HOLDOUT_EVERY = 5   # e-0031's area-stratified module-disjoint ~80/20 holdout
RHO = 0.5           # e-0040's central assumption
SEED = 0
FOUNDATIONAL = {"Data", "Logic"}


def deep_path(module: str) -> Path:
    stem = module.removeprefix("Mathlib.").replace(".", "__")
    return DEEP_DIR / f"{stem}.json"


def top_area(module: str) -> str:
    parts = module.split(".")
    return parts[1] if module.startswith("Mathlib.") and len(parts) > 1 else parts[0]


def substantive_width(rec: dict) -> int:
    """e-0032 logic: # top-level named haves with their OWN non-empty proof body
    (the inline-or-name granularity unit; empty-body nodes are hypothesis/obtain
    binders, not granularity-bearing)."""
    sub = 0
    for n in rec.get("have_tree", []):
        b = (n.get("body") or "").strip()
        if b != "":          # "by" / "by ..." / term-mode all count; "" does not
            sub += 1
    return sub


def per_area_yield() -> tuple[dict, float]:
    """e-0028 per-namespace corpus_v3 round-trip pass rate + advanced-pooled."""
    ns = collections.defaultdict(lambda: [0, 0])
    for f in glob.glob(str(VERIFY_DIR / "*.json")):
        if "_overall" in f:
            continue
        s = json.load(open(f))["summary"]
        a = top_area(s["module"])
        ns[a][0] += s["pass"]
        ns[a][1] += s["total"]
    rate = {k: v[0] / v[1] for k, v in ns.items()}
    adv_p = sum(v[0] for k, v in ns.items() if k not in FOUNDATIONAL)
    adv_t = sum(v[1] for k, v in ns.items() if k not in FOUNDATIONAL)
    return rate, adv_p / adv_t


def mcnemar_min_two_sided_p(d: int) -> float:
    """Smallest achievable two-sided McNemar exact p with d discordant pairs."""
    return 1.0 if d <= 0 else min(1.0, 2.0 * (0.5 ** d))


def min_discordant_for_significance(alpha: float) -> int:
    d = 1
    while mcnemar_min_two_sided_p(d) >= alpha and d <= 100:
        d += 1
    return d


def mde_at(n: int) -> dict:
    """smallest absolute gap reaching TARGET_POWER at this n, per p_lo (e-0040)."""
    rng = random.Random(SEED)
    out = {}
    for p_lo in P_LO_GRID:
        mde = None
        for delta in DELTA_GRID:
            pw = simulate_power(n, p_lo, delta, RHO, rng)
            if pw is None:
                break
            if pw >= TARGET_POWER:
                mde = delta
                break
        out[str(p_lo)] = mde
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data/corpus_v3/deep_effective_n_power.json"))
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

    # ---- e-0032 substantive-frontier construct width per eval target ----
    cache: dict[Path, dict] = {}

    def rec_for(t: dict):
        p = deep_path(t["module"])
        if p not in cache:
            recs = json.loads(p.read_text()) if p.exists() else []
            cache[p] = {r["name"]: r for r in recs}
        return cache[p].get(t["name"])

    n_eval = len(evald)
    missing = 0
    gb1 = gb2 = 0                       # granularity-bearing (>=1 / >=2 substantive)
    ver_total = ver_gb1 = ver_gb2 = 0.0  # yield-weighted expected verified counts
    area_gb1 = collections.Counter()
    for t in evald:
        r = rec_for(t)
        y = yld(t["module"])
        ver_total += y
        if r is None:
            missing += 1
            continue
        sw = substantive_width(r)
        if sw >= 1:
            gb1 += 1
            ver_gb1 += y
            area_gb1[top_area(t["module"])] += 1
        if sw >= 2:
            gb2 += 1
            ver_gb2 += y

    # ---- effective n: verified AND granularity-bearing eval problems ----
    n_eff_ge1 = int(round(ver_gb1))   # the granularity effect's effective sample size
    n_eff_ge2 = int(round(ver_gb2))
    n_eval_verified = int(round(ver_total))

    d_needed = min_discordant_for_significance(ALPHA)
    floor = {
        "min_discordant_pairs_for_alpha_0.05": d_needed,
        "deep_ge1_can_ever_reject": n_eff_ge1 >= d_needed,
        "deep_ge2_can_ever_reject": n_eff_ge2 >= d_needed,
        "corpusv3_test_ge1_can_ever_reject": False,  # e-0045: n_eff=5 < 6
    }

    mde_eff_ge1 = mde_at(n_eff_ge1) if n_eff_ge1 > 0 else {str(p): None for p in P_LO_GRID}
    mde_eff_ge2 = mde_at(n_eff_ge2) if n_eff_ge2 > 0 else {str(p): None for p in P_LO_GRID}

    def fmt(m):
        return {k: (v if v is not None else ">0.50/unreachable") for k, v in m.items()}

    report = {
        "what": (
            "Effective-n / power gate for the DATA/DEEP within-deep eval route -- "
            "the e-0045 analogue on the pivoted-to corpus. Composes the within-deep "
            "module-disjoint eval split (e-0031) x deep substantive-frontier "
            "construct validity (e-0032) x per-area round-trip yield (e-0028) to get "
            "the number of eval problems that are BOTH granularity-bearing AND "
            "verified -- the effective n for the granularity effect -- then feeds it "
            "through e-0040's McNemar/Gaussian-copula MDE machinery (unchanged)."
        ),
        "within_deep_eval_split": {
            "holdout": f"e-0031 area-stratified module-disjoint, every {HOLDOUT_EVERY}th module (~80/20)",
            "eval_targets": n_eval,
            "eval_modules": len(eval_modules),
            "eval_missing_record": missing,
            "eval_expected_verified": round(ver_total, 1),
        },
        "granularity_bearing_in_eval": {
            "substantive_ge1": gb1,
            "substantive_ge1_frac": round(gb1 / n_eval, 4) if n_eval else None,
            "substantive_ge2": gb2,
            "substantive_ge2_frac": round(gb2 / n_eval, 4) if n_eval else None,
            "per_area_ge1": dict(area_gb1.most_common()),
        },
        "effective_n": {
            "n_eval_nominal": n_eval,
            "n_eval_verified": n_eval_verified,
            "n_effective_granularity_ge1": n_eff_ge1,
            "n_effective_granularity_ge2": n_eff_ge2,
            "note": ("effective n = expected VERIFIED granularity-bearing eval "
                     "problems (yield-weighted). corpus_v3 analogue (e-0045): 5."),
        },
        "mcnemar_combinatorial_floor": floor,
        "mde": {
            "deep_effective_n_GRANULARITY_ge1": fmt(mde_eff_ge1),
            "deep_effective_n_GRANULARITY_ge2": fmt(mde_eff_ge2),
            "note": ("smallest absolute rough-fine pass@1 gap reaching 80% power at "
                     "the deep effective n, per weaker-policy rate p_lo."),
        },
        "vs_corpusv3_e0045": {
            "corpusv3_n_effective_granularity": 5,
            "corpusv3_power": "EXACTLY 0 (discordant ceiling 5 < 6 needed)",
            "deep_n_effective_granularity_ge1": n_eff_ge1,
            "deep_restores_power": n_eff_ge1 >= d_needed,
        },
        "rho": RHO, "alpha": ALPHA, "target_power": TARGET_POWER, "M": M, "seed": SEED,
        "caveats": (
            "Verified counts are the e-0028 per-area PROJECTION, not an actual "
            "round-trip (needs the Modal pass). Module-disjoint is the standard but "
            "not airtight leakage control (e-0031). Construct = substantive-frontier "
            "PRESENCE (inline-able have), not the term-vs-tactic FORMAT confound, "
            "which the same-format build (e-0033) removes by construction. Projects "
            "COUNTS not pass@k; MDE is a design-stage calc on marginals/rho the user "
            "still picks; the gap x model-SIZE interaction (the true headline) needs "
            "MORE power than this single-comparison MDE, so it is a LOWER bound."
        ),
    }

    report["interpretation"] = (
        f"The within-deep module-disjoint eval holdout (e-0031) carves {n_eval} eval "
        f"targets, of which {gb1} ({100*gb1/n_eval:.0f}%) are granularity-bearing "
        f"(>=1 substantive named have) and {gb2} ({100*gb2/n_eval:.0f}%) have a >=2 "
        f"frontier -- the inverse of corpus_v3's 8% (e-0045). After discounting by "
        f"e-0028 per-area round-trip yield, the effective n for the granularity "
        f"effect is ~{n_eff_ge1} verified-AND-granularity-bearing eval problems "
        f"(>=2 frontier: ~{n_eff_ge2}), vs corpus_v3's 5. McNemar's exact test needs "
        f">={d_needed} same-direction discordant pairs to reach alpha={ALPHA}; with a "
        f"discordant ceiling of ~{n_eff_ge1} the deep route CAN reject "
        f"(power > 0), where corpus_v3's ceiling of 5 < {d_needed} gave power exactly "
        f"0. At this effective n the detectable absolute rough-fine pass@1 gap is "
        f"{', '.join(f'{k}->{v}' for k, v in fmt(mde_eff_ge1).items())} (p_lo->MDE). "
        f"So e-0045's recommendation is QUANTIFIED: the data/deep route turns the "
        f"granularity effect from un-resolvable (power 0) into resolvable at a "
        f"single-comparison MDE comparable to the e-0040 n=116 column -- the within-"
        f"deep eval is the construct-valid AND adequately-powered path for q-0007's "
        f"headline that corpus_v3 cannot provide. The interaction (gap x size) still "
        f"needs the larger DiD power budget (e-0041/e-0043)."
    )

    print(json.dumps(report, indent=2))
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
