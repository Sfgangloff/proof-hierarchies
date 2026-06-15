"""Interaction (DiD) x pass@k power / MDE gate -- the missing 4th cell of the
design-power matrix for the CAPSTONE claim (q-0001).

The Stage-0.5 go/no-go power trilogy filled three cells of a 2x2:
  - e-0040/a-0038: SINGLE rough-vs-fine gap, pass@1 scoring.
  - e-0041/a-0039: the gap x model-SIZE INTERACTION (DiD), pass@1 scoring
    (~1.3-1.4x harder than the single gap).
  - e-0042/a-0040: SINGLE gap, pass@k scoring (cuts the per-sample MDE ~2-3x at
    low rates, but SATURATES and reverses once the weaker policy's pass@k rate
    climbs past ~0.5-0.6).
The 4th cell -- INTERACTION under pass@k -- was never computed, yet it is the
one the capstone actually needs: e-0042's pass@k rescue was only ever shown for
the SINGLE gap, and e-0041's interaction surcharge was only ever shown under
pass@1. Does pass@k also rescue the harder DiD target, or does saturation bite
EARLIER for the interaction (the large model sits a LIFT above the small one, so
its pass@k rate hits the ceiling first)? This script answers it by combining the
two machineries unchanged: e-0041's four-arm one-factor Gaussian copula + DiD
z-test, with each arm's per-problem outcome replaced by its pass@k transform
P(k)=1-(1-p)^k (e-0042).

DESIGN (identical to e-0041, only the outcome scale changes to pass@k):
  Four per-problem pass@k outcomes on the SAME held-out theorems --
    small x {fine, rough},  large x {fine, rough} --
  per-SAMPLE rates small-fine=s_f, small-rough=s_f+delta_small,
  large-fine=s_f+LIFT, large-rough=s_f+LIFT+delta_large (delta_large=0, the null
  sub-case, directly comparable to e-0041). Each arm's pass@k marginal is
  P=1-(1-rate)^k. Per-problem D = (rough_small-fine_small)-(rough_large-fine_large)
  in {-2..2}; two-sided z-test on mean(D), |z|>1.96. One-factor copula gives all
  six pairwise correlations = rho. Sweep per-SAMPLE small-model gap to find the
  smallest reaching 80% power, as a function of k.

WHY THE LARGE ARM MATTERS UNDER pass@k: with delta_large=0 the two large arms
share a per-sample rate (s_f+LIFT), so their pass@k rates are EQUAL -> the
large-model pass@k gap is exactly 0 in expectation, and once s_f+LIFT saturates
(pass@k -> 1) both large outcomes become a near-deterministic 1, so
(rough_large - fine_large) -> 0 with LOW variance. That actually REDUCES the
noise the DiD pays for the second difference -- a mechanism absent from the
single-gap e-0042. The small-model gap is amplified exactly as in e-0042. So a
priori pass@k could rescue the interaction even better than the single gap; the
competing force is that the small arms themselves saturate at high k. Only the
Monte-Carlo settles which wins -- that is the point of computing the cell.

HONEST SCOPE: design-stage power calc, not an outcome. Inherits every e-0041 /
e-0042 caveat: exchangeable rho=0.5 across all four arms applied in pass@k space
(real pass@k correlation likely higher -> more power, conservative); k samples
i.i.d. per problem (no shared-difficulty random effect); delta_large=0 is
optimistic (a real positive large gap shrinks the DiD). Pure stdlib (random,
math via erf/bisection); deterministic seed; no numpy/scipy, no Lean, no Modal.
"""

import math
import random

SEED = 0
M = 1200            # Monte-Carlo trials per cell (matches e-0042's k-sweep budget)
ALPHA = 0.05
ZCRIT = 1.959963985  # two-sided 0.05 normal critical value
TARGET_POWER = 0.80
N_GRID = [50, 63, 116, 200]
S_F_GRID = [0.05, 0.10, 0.20]    # small-model fine (weakest) per-SAMPLE rate, near floor
K_GRID = [1, 2, 4, 8, 16]
LIFT = 0.10                       # large-model base sits this far above the small one (e-0041)
RHO = 0.5                         # exchangeable outcome correlation across all 4 arms
DELTA_GRID = [round(0.01 * k, 2) for k in range(1, 51)]  # candidate per-sample DiD: 0.01..0.50


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


def passk(p, k):
    """pass@k marginal for per-sample rate p over k i.i.d. samples."""
    return 1.0 - (1.0 - p) ** k


def simulate_did_passk_power(n, s_f, delta_small, delta_large, k, rho, rng):
    """Power of the two-sided z-test on mean(D) for the DiD interaction under
    pass@k scoring. Per-SAMPLE rates -> pass@k marginals -> four-arm copula.
    Returns rejection fraction; None if any per-sample marginal is out of (0,1)."""
    s_r = s_f + delta_small
    l_f = s_f + LIFT
    l_r = l_f + delta_large
    rates = [s_f, s_r, l_f, l_r]                      # per-SAMPLE rates
    if any(r <= 0.0 or r >= 1.0 for r in rates):
        return None
    P = [passk(r, k) for r in rates]                  # pass@k marginals
    P = [min(p, 1.0 - 1e-9) for p in P]
    thr = [inv_phi(p) for p in P]
    a = math.sqrt(rho)
    b = math.sqrt(max(0.0, 1.0 - rho))
    rejects = 0
    for _ in range(M):
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
            if mean != 0.0:
                rejects += 1
            continue
        z = mean / math.sqrt(var / n)
        if abs(z) > ZCRIT:
            rejects += 1
    return rejects / M


def mde_did_passk(n, s_f, k, rng):
    """Smallest per-SAMPLE small-model gap (delta_large=0) reaching 80% power
    under a pass@k DiD eval. Returns (delta, passk_did_gap, power) or (None,..)."""
    for delta in DELTA_GRID:
        pw = simulate_did_passk_power(n, s_f, delta, 0.0, k, RHO, rng)
        if pw is None:
            break
        if pw >= TARGET_POWER:
            # the realized DiD on the pass@k scale == small-model pass@k gap
            # (large gap is 0 because delta_large=0)
            passk_gap = passk(s_f + delta, k) - passk(s_f, k)
            return delta, passk_gap, pw
    return None, None, None


def main():
    rng = random.Random(SEED)
    print("=" * 78)
    print("INTERACTION (DiD) x pass@k POWER / MDE -- the 4th cell (q-0001 capstone)")
    print(f"  two-sided z-test on mean(D), alpha={ALPHA}, target power={TARGET_POWER}")
    print(f"  M={M} trials/cell, rho={RHO} (exchangeable, pass@k space),"
          f" size LIFT={LIFT}, delta_large=0")
    print("=" * 78)

    # --- calibration: empirical type-I error at the null (delta_small=0) ---
    print("\n### calibration: type-I error at the null DiD=0 (should ~= 0.05)")
    print(f"{'n':>5} {'s_f':>6} {'k':>4} | {'type-I':>8}")
    print("-" * 32)
    for n in (50, 116):
        for s_f in S_F_GRID:
            for k in (1, 4, 16):
                t1 = simulate_did_passk_power(n, s_f, 0.0, 0.0, k, RHO, rng)
                flag = "" if t1 is None or 0.02 <= t1 <= 0.09 else "  <-- OFF"
                val = ("%.3f" % t1) if t1 is not None else "NA"
                print(f"{n:>5} {s_f:>6.2f} {k:>4} | {val:>8}{flag}")

    # --- MDE on the DiD as a function of k ---
    results = {}
    print("\n### per-SAMPLE interaction MDE (delta_large=0) @80% power, by k")
    print("    cell = smallest per-sample small-model gap; (g) = realized pass@k DiD gap")
    header = f"{'n':>5} {'s_f':>6} |" + "".join(f"{('k=%d' % k):>13}" for k in K_GRID)
    print(header)
    print("-" * len(header))
    for n in N_GRID:
        for s_f in S_F_GRID:
            row = f"{n:>5} {s_f:>6.2f} |"
            for k in K_GRID:
                delta, gap, pw = mde_did_passk(n, s_f, k, rng)
                results[(n, s_f, k)] = (delta, gap, pw)
                if delta is None:
                    row += f"{'>0.50':>13}"
                else:
                    row += f"{('+%.2f(%.2f)' % (delta, gap)):>13}"
            print(row)

    # --- best interior k per (n, s_f) ---
    print("\n### best (smallest-MDE) k per cell -- is the optimum INTERIOR?")
    print(f"{'n':>5} {'s_f':>6} | {'best k':>7} {'MDE(per-sample)':>16} {'k=1 baseline':>14}")
    print("-" * 52)
    for n in N_GRID:
        for s_f in S_F_GRID:
            best_k, best_delta = None, None
            for k in K_GRID:
                d = results[(n, s_f, k)][0]
                if d is not None and (best_delta is None or d < best_delta):
                    best_delta, best_k = d, k
            base = results[(n, s_f, 1)][0]
            base_s = ("+%.2f" % base) if base is not None else ">0.50"
            if best_delta is None:
                print(f"{n:>5} {s_f:>6.2f} | {'--':>7} {'>0.50':>16} {base_s:>14}")
            else:
                interior = "interior" if 1 < best_k < K_GRID[-1] else (
                    "boundary" if best_k in (1, K_GRID[-1]) else "")
                print(f"{n:>5} {s_f:>6.2f} | {best_k:>5}{interior[:2]:>2} "
                      f"{('+%.2f' % best_delta):>16} {base_s:>14}")

    # --- decision summary ---
    print("\n" + "=" * 78)
    print("DECISION SUMMARY -- does pass@k rescue the CAPSTONE interaction?")
    print("=" * 78)
    for n in (116, 200):
        # per-sample MDE at k=1 (interaction baseline ~ e-0041) vs best interior k
        k1 = [results[(n, s, 1)][0] for s in S_F_GRID]
        k1 = [x for x in k1 if x is not None]
        bests = []
        for s in S_F_GRID:
            cand = [results[(n, s, k)][0] for k in K_GRID]
            cand = [x for x in cand if x is not None]
            if cand:
                bests.append(min(cand))
        if k1 and bests:
            print(f"  n={n}: interaction per-sample MDE  k=1 {min(k1):.2f}-{max(k1):.2f}"
                  f"  ->  best-k {min(bests):.2f}-{max(bests):.2f}")
    print("\nINTERPRETATION:")
    print("  - This is the SMALLEST per-sample small-model rough/fine gap that a")
    print("    pass@k-scored paired eval can flag as a genuine gap-GROWS-as-model-")
    print("    shrinks INTERACTION at 80% power, against a zero large-model gap.")
    print("  - Compare k=1 (interaction baseline, ~ e-0041's DiD MDE) to the best")
    print("    interior k: that delta is how much pass@k rescues the HARDER target,")
    print("    completing the {single,interaction} x {pass@1,pass@k} matrix")
    print("    (e-0040 / e-0041 / e-0042 are the other three cells).")
    print("  - Saturation note: the large model sits LIFT above the small one, so")
    print("    its pass@k rate ceilings FIRST; with delta_large=0 that drives the")
    print("    large-arm difference to ~0 with low variance (helps), while the")
    print("    small arms' own saturation at high k eventually re-inflates the MDE.")


if __name__ == "__main__":
    main()
