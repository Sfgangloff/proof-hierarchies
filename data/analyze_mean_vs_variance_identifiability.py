"""Is a granularity benefit a MEAN lift or a VARIANCE/reliability reduction --
and can the planned eval even tell them apart? (q-0010)

q-0010 asks whether a rough->fine pass@k benefit (if any) is a UNIFORM lift in
per-problem solve probability (the MEAN moves) or a REDUCTION in run-to-run
variance at fixed mean (fewer wasted samples on near-hopeless problems -- the
RELIABILITY moves), and whether that mean-vs-variance split itself depends on
model size. The question notes it is "buildable as a per-sample-outcome
reanalysis of the planned q-0007 eval logs, no extra generations." Those logs do
not exist yet (blocked on Modal), so -- in the same design-stage spirit as the
e-0040..e-0055 power/budget/leakage chain -- this prices the IDENTIFIABILITY and
POWER of the two mechanisms BEFORE the spend, so the eval is instrumented to tell
them apart rather than discovering after the fact that it cannot.

THE KEY STRUCTURAL FACT. Per-problem solve probability p_i across the held-out
set has a distribution; the policy can change its MEAN or its SPREAD.

  pass@1 = E[p]                         (depends ONLY on the mean)
  pass@k = E[1 - (1-p)^k]               (concave in p for k>=1)

Because 1-(1-p)^k is CONCAVE in p, Jensen makes pass@k DECREASING in the spread
of p at fixed mean. So:

  * A MEAN mechanism (fine raises every p_i) lifts pass@1 AND pass@k.
  * A VARIANCE mechanism (fine compresses the spread of p_i at the SAME mean)
    leaves pass@1 EXACTLY unchanged but RAISES pass@k for every k>1, and the gap
    GROWS with k.

CONSEQUENCE for the staged design (e-0051). Stage 1 is a pass@1 screen. A pure
reliability benefit is INVISIBLE to pass@1 by construction -- the stage-1 screen
has power ~= alpha (false-positive only) against it. So a stage-1 NO-GO does NOT
rule out a real variance-mechanism granularity benefit; only a pass@k>1 score can
see it. This is the mean-vs-variance dual of e-0051's "necessary-not-sufficient"
finding for the size interaction.

WHAT THIS SCRIPT COMPUTES (pure stdlib; seed 0; no Lean, no Modal).
  (A) The pass@k SIGNATURE of each mechanism: expected (fine-rough) pass@k vs k,
      for a MEAN mechanism and a mean-matched VARIANCE mechanism -- showing the
      variance mechanism is 0 at k=1 and grows with k (the identifiability handle).
  (B) The POWER of a pass@1 screen vs a pass@k screen to DETECT each mechanism, at
      the within-deep effective n (106, e-0046), via a paired McNemar exact test
      on per-problem pass@k indicators (same machinery family as e-0040/e-0051).
  (C) A SIZE-interaction note: a pure variance mechanism's pass@k gap GROWS with
      the base rate (it is LARGER for the higher-mean / more-capable model), because
      pass@k is near-linear in p at floor rates so the Jensen concavity advantage of
      compressing spread nearly vanishes as p->0. So -- contrary to naive intuition --
      a reliability benefit at floor-level rates does NOT mimic "gap grows as model
      shrinks"; it points the OTHER way. The per-sample-outcome reanalysis (q-0010)
      is therefore diagnostic: a pass@1-invisible-but-pass@k-visible gap that grows as
      the model shrinks is hard to explain by floor-level reliability alone.

PAIRED MODEL. Each held-out problem i has a latent difficulty d_i ~ N(0,1). A
policy maps it to a solve probability p = sigmoid(intercept + slope * d_i); a
SMALLER |slope| = LESS spread in p (more reliable), a LARGER intercept = higher
mean. rough and fine share d_i (same problems -> paired/comonotonic), so the only
differences are the intercept (mean) and slope (spread). Intercepts are calibrated
by bisection so each arm hits its target mean p exactly, making the variance
mechanism EXACTLY mean-matched at pass@1.

HONEST SCOPE. Design-stage power/identifiability calc, NOT a measured outcome.
(1) Logit-normal per-problem difficulty is an assumption (a beta-binomial or a
real difficulty distribution would differ in the tails). (2) The k samples per
problem are i.i.d. Bernoulli(p_i) given p_i -- the standard pass@k model, no
shared-prompt degeneracy. (3) Mean and variance mechanism magnitudes are CHOSEN to
be mean-matched at pass@1, not estimated from data. (4) Projects power, not a
pass@k number the SFT'd models will hit. Pure stdlib; deterministic seed 0.
"""

import math
import random

SEED = 0
M = 1500                 # Monte-Carlo trials per power cell
ALPHA = 0.05
N_DEEP = 106             # within-deep >=2-frontier effective n (e-0046)
K_GRID = [1, 2, 4, 8, 16]
CALIB_POOL = 200_000     # latent draws used to calibrate each arm's intercept to its target mean


def sigmoid(x):
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def calibrate_intercept(target_mean, slope, pool):
    """Find intercept b so that E[sigmoid(b + slope*d)] = target_mean, d~N(0,1)."""
    lo, hi = -20.0, 20.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        m = sum(sigmoid(mid + slope * d) for d in pool) / len(pool)
        if m < target_mean:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def passk_from_p(p, k):
    return 1.0 - (1.0 - p) ** k


def expected_passk(intercept, slope, k, pool):
    return sum(passk_from_p(sigmoid(intercept + slope * d), k) for d in pool) / len(pool)


def mcnemar_exact_p(b, c):
    """Two-sided exact McNemar p-value on discordant counts (b, c)."""
    n = b + c
    if n == 0:
        return 1.0
    x = min(b, c)
    # two-sided: 2 * P(X <= x) under Binom(n, 0.5), capped at 1
    cum = 0.0
    for i in range(0, x + 1):
        cum += math.comb(n, i)
    p = 2.0 * cum / (2.0 ** n)
    return min(1.0, p)


def power_paired_passk(rough_int, rough_slope, fine_int, fine_slope, n, k, rng, trials):
    """Power of a paired McNemar exact test on per-problem pass@k indicators."""
    sig = 0
    for _ in range(trials):
        b = c = 0  # b = fine solves & rough fails; c = rough solves & fine fails
        for _ in range(n):
            d = rng.gauss(0.0, 1.0)
            pr = sigmoid(rough_int + rough_slope * d)
            pf = sigmoid(fine_int + fine_slope * d)
            # k i.i.d. Bernoulli draws each; pass@k = any success
            rough_pass = any(rng.random() < pr for _ in range(k))
            fine_pass = any(rng.random() < pf for _ in range(k))
            if fine_pass and not rough_pass:
                b += 1
            elif rough_pass and not fine_pass:
                c += 1
        if mcnemar_exact_p(b, c) < ALPHA:
            sig += 1
    return sig / trials


def main():
    rng = random.Random(SEED)
    pool = [rng.gauss(0.0, 1.0) for _ in range(CALIB_POOL)]

    # --- Mechanism definitions (per-sample per-problem solve probability) -----
    # Baseline (rough) arm: floor-level mean, substantial spread.
    BASE_MEAN = 0.10
    BASE_SLOPE = 1.5            # dispersion of per-problem difficulty in logit space
    rough_int = calibrate_intercept(BASE_MEAN, BASE_SLOPE, pool)

    # MEAN mechanism: fine lifts the mean by +0.04 at the SAME spread (slope).
    MEAN_LIFT = 0.04
    meanmech_slope = BASE_SLOPE
    meanmech_int = calibrate_intercept(BASE_MEAN + MEAN_LIFT, meanmech_slope, pool)

    # VARIANCE mechanism: fine compresses the spread (slope 1.5 -> 0.6) at the
    # SAME mean -> pass@1 identical by construction, pass@k raised for k>1.
    varmech_slope = 0.6
    varmech_int = calibrate_intercept(BASE_MEAN, varmech_slope, pool)

    print("=" * 78)
    print("q-0010: MEAN vs VARIANCE mechanism -- identifiability & detectability")
    print("=" * 78)
    print(f"seed={SEED}  M={M}  alpha={ALPHA}  n_deep={N_DEEP} (e-0046)  pool={CALIB_POOL}")
    print(f"rough (baseline): mean={BASE_MEAN:.3f} slope={BASE_SLOPE} intercept={rough_int:.3f}")
    print(f"MEAN mech (fine): mean={BASE_MEAN+MEAN_LIFT:.3f} slope={meanmech_slope} "
          f"(+{MEAN_LIFT:.2f} mean lift, same spread)")
    print(f"VAR  mech (fine): mean={BASE_MEAN:.3f} slope={varmech_slope} "
          f"(mean-matched, spread 1.5->0.6)")

    # --- (A) pass@k SIGNATURE -------------------------------------------------
    print("\n--- (A) Expected pass@k gap (fine - rough) by mechanism ---")
    print(f"{'k':>3} | {'rough':>8} | {'MEAN fine':>9} {'gap':>7} | {'VAR fine':>9} {'gap':>7}")
    sig_rows = {}
    for k in K_GRID:
        r = expected_passk(rough_int, BASE_SLOPE, k, pool)
        fm = expected_passk(meanmech_int, meanmech_slope, k, pool)
        fv = expected_passk(varmech_int, varmech_slope, k, pool)
        sig_rows[k] = {"rough": r, "mean_fine": fm, "mean_gap": fm - r,
                       "var_fine": fv, "var_gap": fv - r}
        print(f"{k:>3} | {r:>8.4f} | {fm:>9.4f} {fm-r:>+7.4f} | {fv:>9.4f} {fv-r:>+7.4f}")
    print("  -> MEAN mechanism: gap present already at k=1.")
    print("  -> VAR  mechanism: gap ~0 at k=1 (mean-matched), GROWS with k -- the")
    print("     identifiability handle. A pass@1-only score cannot see it at all.")

    # --- (B) DETECTION POWER at n_deep ---------------------------------------
    print(f"\n--- (B) Power to DETECT each mechanism at n={N_DEEP} (paired McNemar exact) ---")
    print(f"{'k':>3} | {'MEAN mech':>9} | {'VAR mech':>9}")
    pow_rows = {}
    for k in K_GRID:
        pm = power_paired_passk(rough_int, BASE_SLOPE, meanmech_int, meanmech_slope,
                                N_DEEP, k, random.Random(SEED + k), M)
        pv = power_paired_passk(rough_int, BASE_SLOPE, varmech_int, varmech_slope,
                                N_DEEP, k, random.Random(SEED + 100 + k), M)
        pow_rows[k] = {"mean_mech": pm, "var_mech": pv}
        print(f"{k:>3} | {pm:>9.3f} | {pv:>9.3f}")
    print("  -> VAR mechanism power at k=1 collapses to ~alpha (structurally blind);")
    print("     it only becomes detectable as k grows. A pass@1 staged screen (e-0051)")
    print("     would MISS a pure reliability benefit -- NO-GO at k=1 is not no-effect.")

    # --- (C) SIZE-interaction note: smaller model nearer the floor -----------
    # If the small model sits LOWER (mean 0.05 vs 0.10) at the same logit spread,
    # the SAME variance-compression yields a SMALLER pass@k gap (pass@k ~ linear
    # in p at floor rates -> the Jensen concavity advantage nearly vanishes), so a
    # reliability benefit at floor rates does NOT mimic "gap grows as model shrinks".
    SMALL_MEAN = 0.05
    small_rough_int = calibrate_intercept(SMALL_MEAN, BASE_SLOPE, pool)
    small_var_int = calibrate_intercept(SMALL_MEAN, varmech_slope, pool)
    print("\n--- (C) Variance-mechanism pass@k gap: small (mean .05) vs large (mean .10) ---")
    print(f"{'k':>3} | {'small gap':>9} | {'large gap':>9}")
    size_rows = {}
    for k in K_GRID:
        sg = (expected_passk(small_var_int, varmech_slope, k, pool)
              - expected_passk(small_rough_int, BASE_SLOPE, k, pool))
        lg = sig_rows[k]["var_gap"]
        size_rows[k] = {"small_gap": sg, "large_gap": lg}
        print(f"{k:>3} | {sg:>+9.4f} | {lg:>+9.4f}")
    print("  -> the VAR-mechanism gap is SMALLER for the small (lower-mean) model:")
    print("     at floor rates pass@k ~ linear in p, so compressing spread barely")
    print("     helps. A pure reliability benefit thus points OPPOSITE to 'gap grows")
    print("     as model shrinks' -- so a pass@1-invisible / pass@k-visible gap that")
    print("     DOES grow as the model shrinks is hard to explain by reliability alone.")

    out = {
        "seed": SEED, "M": M, "alpha": ALPHA, "n_deep": N_DEEP,
        "rough": {"mean": BASE_MEAN, "slope": BASE_SLOPE, "intercept": rough_int},
        "mean_mech": {"mean": BASE_MEAN + MEAN_LIFT, "slope": meanmech_slope,
                      "intercept": meanmech_int, "lift": MEAN_LIFT},
        "var_mech": {"mean": BASE_MEAN, "slope": varmech_slope, "intercept": varmech_int},
        "signature": sig_rows, "power": pow_rows, "size_interaction": size_rows,
    }
    import json
    with open("data/mean_vs_variance_identifiability.json", "w") as f:
        json.dump(out, f, indent=2)
    print("\nwrote data/mean_vs_variance_identifiability.json")


if __name__ == "__main__":
    main()
