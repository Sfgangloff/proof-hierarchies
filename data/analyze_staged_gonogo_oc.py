"""STAGED GO/NO-GO operating characteristics + expected compute (q-0007, q-0001).

e-0048/a-? closed the eval compute-budget gate with a one-line decision:

    "STAGE THE EVAL -- run the single-size pass@1 rough-vs-fine gap first (8.5x
     the proven-affordable run, resolves +0.11-0.16) and escalate to the
     multi-size interior-k interaction (34-204x) only once a single-size signal
     justifies the spend."

That recommendation was never made operational. It names no TRIGGER RULE (what
stage-1 result counts as "a single-size signal justifies it"), gives no
FALSE-ESCALATION RATE (how often you pay the 34-204x stage-2 when there is no
real effect), no EXPECTED COMPUTE for the staged plan vs always-run-full, and --
the decision-critical hole -- never checks that the stage-1 quantity (a
single-SIZE gap) is the right screen for the stage-2 quantity (the gap x
model-SIZE INTERACTION). This gate supplies all four, reusing e-0040's paired
McNemar Gaussian-copula machinery UNCHANGED and e-0048's published cost
multipliers, so the numbers compose with the existing chain.

DESIGN (the staged plan, made precise).
  Stage 1 (cheap screen): rough-SFT vs fine-SFT, pass@1, on the within-deep
    effective n=106 (>=2-frontier route, e-0046), run on the SMALL model -- so
    the screened gap is delta_small, the headline-relevant arm. Trigger = the
    paired McNemar exact test is significant at alpha=0.05 (equivalently the
    gap's 95% CI excludes 0). On a GO, escalate to stage 2; else STOP.
  Stage 2 (full): the interior-k pass@k multi-size interaction (the e-0047/e-0048
    recommended design).

OPERATING CHARACTERISTICS we compute (all from simulate_power, the e-0040 fn):
  (A) P(escalate | true single-size gap delta_small) = stage-1 power. At
      delta_small=0 this is the FALSE-ESCALATION rate, ~alpha.
  (B) EXPECTED COMPUTE of the staged plan, in units of the proven-affordable
      e-0006 run:  E[mult] = mult_s1 + P(escalate) * mult_s2, swept over the true
      gap, vs the one-shot "always run full" cost. Uses e-0048's published
      multiples (deep_eval_compute_budget.json): stage1 = 8.5x; stage2 in
      {cheap k=4/2size 33.9x, lean k=8/2size 67.8x, full k=16/3size 203.5x}.
  (C) The SCREEN-MISMATCH: stage-1 fires on the single-size MAIN effect, but the
      capstone is the INTERACTION (needs delta_small > delta_large). Under a PURE
      main effect (delta_small = delta_large = delta > 0, interaction EXACTLY 0),
      stage-1 still fires with probability = stage-1 power at delta -- HIGH for a
      detectable main effect -- yet stage-2's DiD is unresolvable. So a stage-1 GO
      is NECESSARY but NOT SUFFICIENT for the interaction: it cannot, by
      construction, distinguish "rough helps at every size" from "rough helps MORE
      as the model shrinks". We quantify this wasted-escalation probability.

HONEST SCOPE: design-stage operating characteristics, not an outcome. Inherits
e-0040's Gaussian-copula paired-Bernoulli approximation, rho=0.5, single seed.
Stage-1 cost/power use pass@1 (the cheap screen as recommended); a tuned-pass@k
screen would raise both power and stage-1 cost and is noted, not swept. Pure
stdlib; no Lean, no Modal, no numpy.
"""

import json
import os
import random

from analyze_eval_power_mde import simulate_power, ALPHA

SEED = 0
N_EFF = 106                      # within-deep >=2-frontier effective n (e-0046)
P_LO_GRID = [0.05, 0.10, 0.20]   # weaker-policy (fine) pass rate near the floor
RHO = 0.5                        # e-0040 assumption, unchanged
DELTA_GRID = [0.0, 0.04, 0.08, 0.11, 0.14, 0.16, 0.20, 0.25]  # true single-size gap

# e-0048 published cost multiples (units of the proven-affordable 50-problem run).
MULT_STAGE1 = 8.5                # single-size pass@1 screen (k=1)
STAGE2 = {
    "cheap (k=4, 2 sizes)": 33.9,
    "lean  (k=8, 2 sizes)": 67.8,
    "full  (k=16, 3 sizes)": 203.5,
}
ONE_SHOT_FULL = 203.5            # skip staging, run the full design outright

OUT = os.path.join(os.path.dirname(__file__), "corpus_v3", "staged_gonogo_oc.json")


def main():
    rng = random.Random(SEED)
    print("=" * 78)
    print("STAGED GO/NO-GO operating characteristics  (within-deep n=106, e-0046)")
    print(f"  stage-1 trigger = paired McNemar significant at alpha={ALPHA} (pass@1)")
    print(f"  rho={RHO}, M from e-0040 machinery; seed={SEED}")
    print("=" * 78)

    # (A) P(escalate | true single-size gap) = stage-1 power.
    print("\n(A) P(escalate to stage 2 | true single-size gap delta_small)")
    print(f"    [delta=0.00 row is the FALSE-ESCALATION rate, target ~alpha={ALPHA}]")
    header = "delta_s |" + "".join(f"  p_lo={p:.2f}" for p in P_LO_GRID)
    print("    " + header)
    print("    " + "-" * (len(header)))
    p_escalate = {}
    for delta in DELTA_GRID:
        row = []
        for p_lo in P_LO_GRID:
            pw = simulate_power(N_EFF, p_lo, delta, RHO, rng)
            pw = 0.0 if pw is None else pw
            p_escalate[(delta, p_lo)] = pw
            row.append(pw)
        print("    " + f"{delta:6.2f}  |" + "".join(f"   {v:6.3f}" for v in row))

    # (B) Expected compute of the staged plan vs always-run-full.
    # Use the MIDDLE p_lo=0.10 for the headline table; escalation prob depends on it.
    print("\n(B) EXPECTED COMPUTE of the staged plan (units of the proven 50-prob run)")
    print("    E[mult] = stage1 (8.5x) + P(escalate) * stage2 ;  one-shot full = 203.5x")
    expected = {}
    for s2name, s2mult in STAGE2.items():
        print(f"\n    --- stage 2 = {s2name}  ({s2mult}x) ---")
        print("    delta_s |" + "".join(f"  p_lo={p:.2f}" for p in P_LO_GRID))
        for delta in DELTA_GRID:
            row = []
            for p_lo in P_LO_GRID:
                pe = p_escalate[(delta, p_lo)]
                em = MULT_STAGE1 + pe * s2mult
                expected[(s2name, delta, p_lo)] = em
                row.append(em)
            print("    " + f"{delta:6.2f}  |" + "".join(f"  {v:7.1f}x" for v in row))

    # (C) Screen mismatch: a stage-1 GO under a PURE main effect (interaction=0)
    # is wasted escalation. P(waste) = stage-1 power at that main-effect size.
    print("\n(C) SCREEN-MISMATCH -- stage-1 GO is necessary but NOT sufficient for the")
    print("    INTERACTION. Under a PURE main effect (delta_small=delta_large=delta,")
    print("    true interaction EXACTLY 0), stage-1 escalates anyway with prob =")
    print("    stage-1 power at delta; stage-2's DiD then finds nothing.")
    print("    delta (=both arms) | P(wasted escalation), p_lo=0.10 | stage2 cost paid")
    waste = {}
    for delta in [d for d in DELTA_GRID if d > 0]:
        pe = p_escalate[(delta, 0.10)]
        waste[delta] = pe
        print(f"      {delta:6.2f}           |        {pe:6.3f}                | "
              f"33.9-203.5x for a 0-interaction")

    # ---- decision summary ----
    print("\n" + "=" * 78)
    print("DECISION SUMMARY")
    print("=" * 78)
    pe0 = p_escalate[(0.0, 0.10)]
    e_null_full = MULT_STAGE1 + pe0 * ONE_SHOT_FULL
    print(f"  - FALSE-ESCALATION (true gap=0, p_lo=0.10): P(escalate)={pe0:.3f} ~ alpha.")
    print(f"    Staged expected cost under the null = {e_null_full:.1f}x vs {ONE_SHOT_FULL}x")
    print(f"    always-run-full -> staging saves ~{ONE_SHOT_FULL / e_null_full:.1f}x when")
    print(f"    there is NO effect (the common prior given the 0/50 floor, e-0005).")
    # a detectable gap (~MDE +0.14 single-size, e-0046) escalates near power 0.8
    pe_det = p_escalate.get((0.14, 0.10), 0.0)
    e_det_full = MULT_STAGE1 + pe_det * ONE_SHOT_FULL
    print(f"  - TRUE DETECTABLE gap (+0.14, the e-0046 single-size MDE): "
          f"P(escalate)={pe_det:.3f}")
    print(f"    staged expected cost = {e_det_full:.1f}x (you pay because signal is real).")
    print(f"  - SCREEN MISMATCH: a pure main effect of +0.14 (zero interaction) still")
    print(f"    escalates with P={pe_det:.3f}, spending 34-204x on an unresolvable DiD.")
    print(f"    => stage-1 must run on the SMALL model (screens delta_small) and a GO is")
    print(f"    NECESSARY-not-SUFFICIENT for the capstone; report it as a single-size")
    print(f"    main-effect screen, NOT as interaction evidence.")

    payload = {
        "what": ("Staged go/no-go operating characteristics for the e-0048 'stage the "
                 "eval' recommendation: trigger rule, false-escalation rate, expected "
                 "compute vs always-run-full, and the single-size-screen-vs-interaction "
                 "mismatch. Reuses e-0040 McNemar/copula + e-0048 cost multiples."),
        "design": {
            "n_eff": N_EFF, "stage1_trigger": f"McNemar significant alpha={ALPHA}, pass@1",
            "rho": RHO, "stage1_mult": MULT_STAGE1, "stage2_mults": STAGE2,
            "one_shot_full_mult": ONE_SHOT_FULL,
        },
        "p_escalate_by_gap_plo": {
            f"{d}|{p}": p_escalate[(d, p)] for d in DELTA_GRID for p in P_LO_GRID
        },
        "expected_mult": {
            f"{s2}|{d}|{p}": expected[(s2, d, p)]
            for s2 in STAGE2 for d in DELTA_GRID for p in P_LO_GRID
        },
        "false_escalation_rate_plo010": pe0,
        "staged_cost_under_null_full": e_null_full,
        "staged_savings_under_null_x": ONE_SHOT_FULL / e_null_full,
        "wasted_escalation_pure_main_effect_plo010": waste,
        "verdict": (
            f"The e-0048 'stage the eval' plan, made operational: stage-1 = single-size "
            f"pass@1 rough-vs-fine at n=106 on the SMALL model, escalate iff McNemar is "
            f"significant at alpha={ALPHA}. (1) FALSE-ESCALATION under a true zero gap is "
            f"P={pe0:.3f}~alpha, so the staged plan's expected cost under the null (the "
            f"common prior given the 0/50 floor) is only {e_null_full:.1f}x vs the "
            f"{ONE_SHOT_FULL}x of running the full design outright -- a ~{ONE_SHOT_FULL/e_null_full:.0f}x "
            f"compute saving for the realistic no-effect case, which is the entire value "
            f"of staging. (2) But the screen is MISALIGNED with the capstone: stage-1 "
            f"detects the single-SIZE main effect, while the headline is the gap x "
            f"model-SIZE INTERACTION. A PURE main effect (rough helps equally at both "
            f"sizes, interaction=0) escalates with prob = stage-1 power (~{pe_det:.2f} at a "
            f"+0.14 gap), spending 34-204x on a DiD that resolves nothing. So a stage-1 GO "
            f"is NECESSARY-NOT-SUFFICIENT for the interaction. Recommendation: run stage-1 "
            f"on the SMALL model so it screens delta_small (the headline-relevant arm), "
            f"set the trigger at McNemar significance, and report the stage-1 result as a "
            f"single-size main-effect screen -- the interaction claim still requires the "
            f"multi-size stage-2 spend, which staging only DEFERS (gating it on a cheap "
            f"8.5x screen) rather than avoids. CAVEAT: design-stage OC, e-0040 copula/"
            f"rho=0.5/single seed; pass@1 screen (a tuned-pass@k screen raises both power "
            f"and stage-1 cost)."
        ),
    }
    with open(OUT, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
