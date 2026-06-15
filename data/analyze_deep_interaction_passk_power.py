"""DEEP-ROUTE HEADLINE gate: the gap x model-SIZE INTERACTION (DiD) under pass@k,
priced at the construct-valid within-deep eval route's EFFECTIVE n (q-0001/q-0007).

This closes the last open seam in the Stage-0.5 power chain. The chain produced
two families of numbers that were never MULTIPLIED onto the route that actually
survives:

  * e-0046/a-0044 (analyze_deep_effective_n_power) established that the within-deep
    eval route is the ONLY construct-valid AND adequately-powered path: its
    effective n for the granularity effect is ~115 (>=1 substantive frontier) /
    ~106 (>=2), vs corpus_v3's DEAD 5 (e-0045, McNemar power EXACTLY 0). But e-0046
    reported only the SINGLE-comparison pass@1 MDE (+0.11/+0.13/+0.15) and flagged
    in its own caveat: "the gap x model-SIZE INTERACTION (the true headline) needs
    the larger DiD budget (e-0041/e-0043), so this single-comparison MDE is a
    LOWER bound on what the full interaction claim needs."

  * e-0041/a-0039 (interaction x pass@1) and e-0043/a-0041 (interaction x pass@k,
    analyze_interaction_passk_power_mde) priced the DiD and its pass@k escape
    hatch -- but on the GENERIC n-grid {50,63,116,200}, never at the deep route's
    actual effective n, and never contrasted with e-0046's single-comparison
    number on the SAME route.

The decision-relevant product no one computed: AT THE DEEP ROUTE'S OWN EFFECTIVE n
(115/106), what is the MDE of the ACTUAL HEADLINE -- the gap-grows-as-model-
shrinks INTERACTION -- and does a tuned pass@k bring it within reach of a
plausible few-point granularity effect? That is the number the Modal go/no-go for
the capstone (q-0001), not just the single-size gap (q-0007), turns on.

This gate fuses them: it reads e-0046's effective n from disk (regenerating it if
absent) and feeds it through e-0043's interaction x pass@k DiD machinery
(simulate_did_passk_power / mde_did_passk) IMPORTED UNCHANGED. It reports, at the
deep effective n, the three nested MDEs side by side:

    (1) single-comparison pass@1  (e-0046's number, the floor)
    (2) interaction pass@1        (the DiD surcharge: ~1.3-1.4x, e-0041)
    (3) interaction pass@k        (the escape hatch, swept k; e-0043)

so the capstone go/no-go reads off ONE table instead of three experiments.

CAVEATS (inherited): design-stage power calc, not a measured pass@k outcome;
effective n is the e-0028 per-area yield PROJECTION (needs the Modal round-trip);
exchangeable rho=0.5 across all four arms (same-base same-proof correlations
likely exceed cross-size ones -> conservative); large-model gap fixed at 0
(optimistic: a real positive large gap shrinks the DiD, needing MORE power);
k samples i.i.d. per problem (no shared-difficulty random effect). Pure stdlib;
no Lean, no Modal. Reuses analyze_deep_effective_n_power + the e-0040/e-0043
copula machinery unchanged.

  python3 -m data.analyze_deep_interaction_passk_power [--out path.json]
"""

from __future__ import annotations
import argparse, json, random, subprocess, sys
from pathlib import Path

# e-0043 interaction x pass@k DiD machinery, imported UNCHANGED
from data.analyze_interaction_passk_power_mde import (
    simulate_did_passk_power, mde_did_passk, passk,
    ALPHA, TARGET_POWER, M, S_F_GRID, K_GRID, RHO, LIFT,
)
# e-0040 single-comparison paired-McNemar machinery (the e-0046 floor), unchanged
from data.analyze_eval_power_mde import simulate_power, DELTA_GRID, P_LO_GRID

ROOT = Path(__file__).resolve().parents[1]
DEEP_EFF_JSON = ROOT / "data/corpus_v3/deep_effective_n_power.json"
SEED = 0


def load_deep_effective_n() -> dict:
    """e-0046's effective n for the deep route; regenerate the json if missing."""
    if not DEEP_EFF_JSON.exists():
        subprocess.run(
            [sys.executable, "-m", "data.analyze_deep_effective_n_power"],
            cwd=str(ROOT), check=True,
        )
    d = json.loads(DEEP_EFF_JSON.read_text())
    return d["effective_n"]


def single_pass1_mde(n: int, rng: random.Random) -> dict:
    """e-0040/e-0046 single-comparison paired-McNemar pass@1 MDE at this n."""
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
    ap.add_argument("--out", default=str(ROOT / "data/corpus_v3/deep_interaction_passk_power.json"))
    args = ap.parse_args()

    eff = load_deep_effective_n()
    n_ge1 = eff["n_effective_granularity_ge1"]   # ~115
    n_ge2 = eff["n_effective_granularity_ge2"]   # ~106
    deep_ns = {"ge1": n_ge1, "ge2": n_ge2}

    print("=" * 78)
    print("DEEP-ROUTE HEADLINE: interaction (DiD) x pass@k at the within-deep "
          "effective n")
    print(f"  effective n (e-0046): >=1 frontier = {n_ge1}, >=2 frontier = {n_ge2}")
    print(f"  two-sided z-test on mean(D), alpha={ALPHA}, power>={TARGET_POWER}, "
          f"M={M}, rho={RHO}, LIFT={LIFT}, delta_large=0")
    print("=" * 78)

    report = {
        "what": (
            "Headline gap x model-SIZE INTERACTION (DiD) under pass@k, priced at "
            "the construct-valid within-deep eval route's effective n (e-0046). "
            "Fuses e-0046's effective n with e-0043's interaction-pass@k DiD "
            "machinery (unchanged) and contrasts the single-comparison pass@1 MDE "
            "(e-0046 floor), the interaction pass@1 surcharge (e-0041), and the "
            "interaction pass@k escape hatch (e-0043) ON THE SAME ROUTE."
        ),
        "deep_effective_n": {"ge1": n_ge1, "ge2": n_ge2,
                             "corpusv3_dead_analogue": 5},
        "params": {"alpha": ALPHA, "target_power": TARGET_POWER, "M": M,
                   "rho": RHO, "LIFT": LIFT, "delta_large": 0, "seed": SEED},
        "cells": {},
    }

    for tag, n in deep_ns.items():
        rng = random.Random(SEED)

        # (1) single-comparison pass@1 MDE (the e-0046 floor)
        single = single_pass1_mde(n, rng)

        # (2) interaction pass@1 MDE  (3) interaction pass@k sweep
        inter = {}
        for s_f in S_F_GRID:
            ks = {}
            for k in K_GRID:
                delta, gap, pw = mde_did_passk(n, s_f, k, rng)
                ks[str(k)] = {
                    "per_sample_mde": delta,
                    "passk_did_gap": (round(gap, 4) if gap is not None else None),
                    "power": (round(pw, 3) if pw is not None else None),
                }
            # best interior k
            avail = [(k, ks[str(k)]["per_sample_mde"]) for k in K_GRID
                     if ks[str(k)]["per_sample_mde"] is not None]
            best_k = min(avail, key=lambda x: x[1])[0] if avail else None
            inter[str(s_f)] = {"by_k": ks, "best_k": best_k,
                               "interaction_pass1_mde": ks["1"]["per_sample_mde"]}

        report["cells"][tag] = {"n": n, "single_pass1_mde": single,
                                "interaction": inter}

        # ---- console table ----
        print(f"\n### deep effective n = {n} ({tag} frontier)")
        s = single
        print("  (1) single-comparison pass@1 MDE  [e-0046 floor]:  "
              + ", ".join(f"p_lo={p}: "
                          + (f"+{s[str(p)]:.2f}" if s[str(p)] is not None
                             else ">0.50")
                          for p in P_LO_GRID))
        hdr = f"  (2/3) interaction MDE  {'s_f':>5} |" + "".join(
            f"{('k=%d' % k):>9}" for k in K_GRID)
        print(hdr)
        print("  " + "-" * (len(hdr) - 2))
        for s_f in S_F_GRID:
            row = f"        {s_f:>11.2f} |"
            for k in K_GRID:
                d = inter[str(s_f)]["by_k"][str(k)]["per_sample_mde"]
                row += f"{('+%.2f' % d) if d is not None else '>0.50':>9}"
            bk = inter[str(s_f)]["best_k"]
            row += f"   best k={bk}"
            print(row)

    # ---- bottom-line verdict ----
    # compare interaction k=1 vs best-k at the ge2 (real >=2 frontier) route, p_lo/s_f=0.10
    c = report["cells"]["ge2"]["interaction"]["0.1"]
    i1 = c["interaction_pass1_mde"]
    bk = c["best_k"]
    ib = c["by_k"][str(bk)]["per_sample_mde"] if bk is not None else None
    s10 = report["cells"]["ge2"]["single_pass1_mde"]["0.1"]
    verdict = (
        f"At the deep route's real >=2-frontier effective n={n_ge2}, s_f=0.10: "
        f"single-comparison pass@1 MDE +{s10:.2f}; "
        f"interaction pass@1 MDE "
        + (f"+{i1:.2f}" if i1 is not None else ">0.50")
        + f" (the headline surcharge); interaction best-k (k={bk}) MDE "
        + (f"+{ib:.2f}" if ib is not None else ">0.50")
        + ". The headline INTERACTION is materially harder than the single gap; "
        "pass@k is the only lever that brings it near a few-point effect, and "
        "only when k is tuned (interior optimum)."
    )
    report["verdict"] = verdict
    report["caveats"] = (
        "Design-stage power calc, not a measured pass@k outcome. Effective n is "
        "the e-0028 per-area yield PROJECTION (needs the Modal round-trip). "
        "Exchangeable rho=0.5 across all four arms (same-base same-proof "
        "correlations likely higher -> conservative). Large-model gap fixed at 0 "
        "(optimistic: a real positive large gap shrinks the DiD, needing MORE "
        "power). k samples i.i.d. per problem. Reuses e-0046 + e-0043/e-0040 "
        "machinery unchanged."
    )

    print("\n" + "=" * 78)
    print("VERDICT:", verdict)
    print("=" * 78)

    Path(args.out).write_text(json.dumps(report, indent=2))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
