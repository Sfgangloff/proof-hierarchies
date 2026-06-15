"""Interaction (difference-in-differences) power / MDE gate for the CAPSTONE
claim (q-0001), refining e-0040/a-0038.

e-0040 computed the minimum detectable rough-vs-fine pass@1 gap for a SINGLE
paired comparison at one model size, and flagged -- but did NOT quantify -- that
the actual headline is a gap x model-SIZE INTERACTION: the rough/fine gap is
claimed to GROW as the model shrinks. That is a difference-in-differences (DiD),
which e-0040 said "needs MORE power ... so these MDEs are a LOWER bound." This
script supplies the missing number: how much larger must the small-model gap be
(over the large-model gap) for the planned eval to RESOLVE the interaction at
80% power, at the same affordable n the project can buy?

DESIGN. Four per-problem binary outcomes on the SAME held-out theorems:
  small model x {fine, rough},  large model x {fine, rough}.
The interaction statistic per problem is
  D_i = (rough_small_i - fine_small_i) - (rough_large_i - fine_large_i)  in {-2..2}.
The capstone predicts E[D] > 0 (the rough/fine gap is bigger for the small model).
H0: E[D] = 0 (gap does not change with size). We test the mean of D with a
two-sided z-test (mean / (sd/sqrt(n)), |z|>1.96); the normal approximation for a
sample mean over n>=50 is standard, and we VERIFY its calibration by measuring
the empirical type-I error at DiD=0 (should land near alpha).

GENERATIVE MODEL (one-factor Gaussian copula, pure stdlib). Each problem draws a
common latent W and four idiosyncratic noises; outcome j passes iff
  sqrt(rho)*W + sqrt(1-rho)*eps_j  <  thr_j,
giving all six pairwise correlations equal to rho (the same exchangeable positive
correlation e-0040 used between the two SFT variants, now extended to the size
axis as well -- four variants of one base on the same problems).

MARGINALS. The large model sits a fixed "size lift" above the small one. We sweep
the small-model fine pass rate s_f in {0.05,0.10,0.20} (near the e-0005 floor),
set large-model fine rate = s_f + LIFT, fix the large-model gap delta_large = 0
(the null sub-case: no granularity effect for the big model), and find the
smallest small-model gap delta_small = DiD reaching 80% power. Reporting against
delta_large=0 makes the number directly comparable to e-0040's single-gap MDE:
it shows the SURCHARGE for having to demonstrate the gap is DIFFERENTIAL.

HONEST SCOPE: a DESIGN-stage power calc, not an outcome; assumes marginals/rho/
LIFT the user must still pick; exchangeable rho across all four arms is a
simplification (same-base correlations likely exceed cross-size ones, which would
RAISE power -- so this is conservative on that axis but optimistic on assuming a
clean zero large-model gap). Pure stdlib (random, math); deterministic seed; no
Lean, no Modal, no numpy.
"""

import math
import random

SEED = 0
M = 1500            # Monte-Carlo trials per cell
ALPHA = 0.05
ZCRIT = 1.959963985  # two-sided 0.05 normal critical value
TARGET_POWER = 0.80
N_GRID = [50, 63, 116, 200]
S_F_GRID = [0.05, 0.10, 0.20]    # small-model fine (weaker) pass rate, near floor
LIFT = 0.10                       # large-model base sits this far above the small one
RHO = 0.5                         # exchangeable outcome correlation across all 4 arms
DELTA_GRID = [round(0.01 * k, 2) for k in range(1, 51)]  # candidate DiD: 0.01..0.50


def phi(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def inv_phi(p):
    """Standard normal quantile via bisection on phi (p in (0,1))."""
    if p <= 0.0:
        return -8.0
    if p >= 1.0:
        return 8.0
    lo, hi = -8.0, 8.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if phi(mid) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def simulate_did_power(n, s_f, delta_small, delta_large, rho, rng):
    """Power of the two-sided z-test on mean(D) for the DiD interaction.

    Arms (pass iff latent < thr): small-fine (s_f), small-rough (s_f+delta_small),
    large-fine (s_f+LIFT), large-rough (s_f+LIFT+delta_large). Returns rejection
    fraction; None if any marginal is out of (0,1)."""
    s_r = s_f + delta_small
    l_f = s_f + LIFT
    l_r = l_f + delta_large
    rates = [s_f, s_r, l_f, l_r]
    if any(r <= 0.0 or r >= 1.0 for r in rates):
        return None
    thr = [inv_phi(r) for r in rates]
    a = math.sqrt(rho)
    b = math.sqrt(max(0.0, 1.0 - rho))
    rejects = 0
    for _ in range(M):
        sd = 0.0
        sumD = 0.0
        sumD2 = 0.0
        for _ in range(n):
            w = rng.gauss(0.0, 1.0)
            outs = []
            for j in range(4):
                z = a * w + b * rng.gauss(0.0, 1.0)
                outs.append(1 if z < thr[j] else 0)
            # D = (rough_small - fine_small) - (rough_large - fine_large)
            d = (outs[1] - outs[0]) - (outs[3] - outs[2])
            sumD += d
            sumD2 += d * d
        mean = sumD / n
        var = (sumD2 - n * mean * mean) / (n - 1)
        if var <= 0.0:
            # all D_i identical; reject only if that constant is nonzero
            if mean != 0.0:
                rejects += 1
            continue
        z = mean / math.sqrt(var / n)
        if abs(z) > ZCRIT:
            rejects += 1
    return rejects / M


def main():
    rng = random.Random(SEED)
    print("=" * 78)
    print("INTERACTION (DiD) POWER / MDE for the gap x model-SIZE capstone (q-0001)")
    print(f"  two-sided z-test on mean(D), alpha={ALPHA}, target power={TARGET_POWER}")
    print(f"  M={M} trials/cell, rho={RHO} (exchangeable), size LIFT={LIFT},"
          f" delta_large=0")
    print("=" * 78)

    # --- calibration check: empirical type-I error at DiD=0 (delta_small=0) ---
    print("\n### calibration: empirical type-I error at the null (delta_small=0)")
    print(f"{'n':>5} {'s_f':>6} | {'type-I (should ~= 0.05)':>24}")
    print("-" * 40)
    for n in N_GRID:
        for s_f in S_F_GRID:
            t1 = simulate_did_power(n, s_f, 0.0, 0.0, RHO, rng)
            flag = "" if t1 is None or 0.02 <= t1 <= 0.09 else "  <-- OFF"
            print(f"{n:>5} {s_f:>6.2f} | {('%.3f' % t1) if t1 is not None else 'NA':>24}{flag}")

    # --- MDE on the DiD ---
    results = {}
    print("\n### interaction MDE: smallest small-model gap (delta_large=0) @80% power")
    print(f"{'n':>5} {'s_f':>6} | {'DiD-MDE (small-model gap)':>27} | {'power':>6}")
    print("-" * 52)
    for n in N_GRID:
        for s_f in S_F_GRID:
            mde = None
            mde_pw = None
            for delta in DELTA_GRID:
                pw = simulate_did_power(n, s_f, delta, 0.0, RHO, rng)
                if pw is None:
                    break
                if pw >= TARGET_POWER:
                    mde = delta
                    mde_pw = pw
                    break
            results[(n, s_f)] = mde
            if mde is None:
                print(f"{n:>5} {s_f:>6.2f} | {'> 0.50 (unreachable)':>27} | {'--':>6}")
            else:
                print(f"{n:>5} {s_f:>6.2f} | "
                      f"{('+%.2f gap @ small vs 0 @ large' % mde):>27} | "
                      f"{mde_pw:>6.2f}")

    # --- decision summary ---
    print("\n" + "=" * 78)
    print("DECISION SUMMARY")
    print("=" * 78)
    for n in N_GRID:
        mdes = [results[(n, s)] for s in S_F_GRID]
        clean = [m for m in mdes if m is not None]
        if clean:
            lo, hi = min(clean), max(clean)
            print(f"  n={n:>3}: interaction (DiD) MDE ranges {lo:.2f}-{hi:.2f} "
                  f"across small-model fine rate s_f in {S_F_GRID}")
        else:
            print(f"  n={n:>3}: NO DiD <=0.50 reaches 80% power at any s_f")
    print("\nINTERPRETATION:")
    print("  - This is the SMALLEST small-model rough/fine gap that, against a")
    print("    zero large-model gap, the planned paired eval can flag as a genuine")
    print("    gap-GROWS-as-model-shrinks INTERACTION at 80% power.")
    print("  - Compare to e-0040's SINGLE-comparison MDE at the same n: the")
    print("    interaction surcharge is the quantified cost of the capstone's DiD")
    print("    framing that e-0040 could only call 'strictly harder'.")
    print("  - Even the zero-large-gap case here UNDERSTATES the real requirement:")
    print("    a true positive large-model gap (delta_large>0) shrinks the DiD that")
    print("    must be resolved, demanding still more power.")


if __name__ == "__main__":
    main()
