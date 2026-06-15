"""Statistical power / minimum-detectable-effect (MDE) gate for the headline
rough-vs-fine pass@k comparison (q-0007, q-0001) -- a NEW kind of go/no-go.

Every prior data-level gate (supply e-0014/16, construct-validity e-0026/e-0032,
yield e-0028, on-domain composition e-0029, train/eval split e-0031, length
confound e-0010..e-0039) asks whether the TRAINING SIGNAL exists. None asks the
dual question: given the eval set sizes the project can actually afford, can the
planned comparison even RESOLVE a rough/fine pass@k gap? If small-model pass@1 is
near the 0/50 floor (e-0005), the binomial noise on ~50-200 held-out problems may
be wide enough that no plausible granularity gap is statistically distinguishable
-- in which case the paid Modal SFT+eval cannot answer the headline regardless of
how clean the corpus is.

DESIGN. The headline comparison is PAIRED: the same held-out theorems are
attempted by the rough-SFT model and the fine-SFT model, each scored pass/fail.
The correct test for two paired binary outcomes is McNemar's exact test on the
discordant pairs (b = rough-pass & fine-fail, c = rough-fail & fine-pass); under
H0 (no difference), b ~ Binomial(b+c, 0.5). Power is driven by the discordant
total b+c and the marginal gap, and -- crucially -- by the POSITIVE correlation
between the two models' per-problem outcomes (both are SFT variants of the same
base on the same problems), which a paired test exploits.

GENERATIVE MODEL (Gaussian copula, pure stdlib via simulation). For target
marginals p_lo (weaker policy pass rate) and p_hi = p_lo + delta, and outcome
correlation rho, draw two correlated latent normals per problem and threshold
each at its marginal to produce (rough_pass, fine_pass). Count discordant cells,
run McNemar's two-sided exact test at alpha=0.05, repeat M trials, report the
rejection fraction = power. For each (n, p_lo, rho) the MDE is the smallest delta
reaching 80% power.

EVAL SIZES probed (all real anchors in the stream):
  50  -- the e-0005 pilot subset
  63  -- the corpus_v3 held-out test split (e-0006)
  116 -- the within-deep verified eval frontiers (e-0031, the supply-ample route)
  200 -- an aspirational larger held-out set

HONEST SCOPE: this is a DESIGN-stage power calc, not an outcome. It assumes the
marginals/rho the user must still pick; it reports MDE across a plausible grid so
the dependence is explicit. The headline is actually a gap x model-SIZE
INTERACTION (does the gap GROW as the model shrinks): a difference-in-differences
across sizes is STRICTLY harder to power than the single-comparison MDE here, so
these MDEs are a LOWER bound on what the full interaction claim needs. Pure
stdlib (random, math); deterministic seed; no Lean, no Modal, no numpy.
"""

import math
import random

SEED = 0
M = 1500            # Monte-Carlo trials per (n, p_lo, delta, rho) cell
ALPHA = 0.05
TARGET_POWER = 0.80
N_GRID = [50, 63, 116, 200]
P_LO_GRID = [0.05, 0.10, 0.20]
RHO_GRID = [0.5]                  # realistic positive correlation for two SFT variants
DELTA_GRID = [round(0.01 * k, 2) for k in range(1, 51)]  # 0.01 .. 0.50


def phi(x):
    """Standard normal CDF via erf."""
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


def mcnemar_exact_two_sided(b, c):
    """Two-sided McNemar exact p-value: 2 * tail of Binomial(b+c, 0.5)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    # P(X <= k) for X ~ Binom(n, 0.5)
    tail = 0.0
    loghalf_n = -n * math.log(2.0)
    # cumulative via log-comb to stay exact for n up to ~200
    log_comb = 0.0  # log C(n,0)
    for i in range(0, k + 1):
        if i > 0:
            log_comb += math.log(n - i + 1) - math.log(i)
        tail += math.exp(log_comb + loghalf_n)
    p = 2.0 * tail
    return min(1.0, p)


def simulate_power(n, p_lo, delta, rho, rng):
    """Power of paired McNemar test for rough(p_hi) vs fine(p_lo) over n problems."""
    p_hi = p_lo + delta
    if p_hi >= 1.0:
        return None
    thr_lo = inv_phi(p_lo)   # pass if latent < thr  => P(pass)=p
    thr_hi = inv_phi(p_hi)
    a = rho
    bcoef = math.sqrt(max(0.0, 1.0 - rho * rho))
    rejects = 0
    for _ in range(M):
        b = c = 0
        for _ in range(n):
            z1 = rng.gauss(0.0, 1.0)
            z2 = a * z1 + bcoef * rng.gauss(0.0, 1.0)
            rough_pass = z1 < thr_hi   # rough = stronger policy (p_hi)
            fine_pass = z2 < thr_lo    # fine  = weaker policy (p_lo)
            if rough_pass and not fine_pass:
                b += 1
            elif fine_pass and not rough_pass:
                c += 1
        if mcnemar_exact_two_sided(b, c) < ALPHA:
            rejects += 1
    return rejects / M


def main():
    rng = random.Random(SEED)
    print("=" * 78)
    print("EVAL POWER / MINIMUM-DETECTABLE-EFFECT for paired rough-vs-fine pass@k")
    print(f"  McNemar exact, alpha={ALPHA}, target power={TARGET_POWER}, M={M} trials/cell")
    print("=" * 78)

    results = {}
    for rho in RHO_GRID:
        print(f"\n### outcome correlation rho = {rho}")
        print(f"{'n':>5} {'p_lo':>6} | {'MDE (abs gap @80% power)':>26} | {'rel. gap':>9}")
        print("-" * 56)
        for n in N_GRID:
            for p_lo in P_LO_GRID:
                mde = None
                mde_power = None
                for delta in DELTA_GRID:
                    pw = simulate_power(n, p_lo, delta, rho, rng)
                    if pw is None:
                        break
                    if pw >= TARGET_POWER:
                        mde = delta
                        mde_power = pw
                        break
                results[(rho, n, p_lo)] = mde
                if mde is None:
                    print(f"{n:>5} {p_lo:>6.2f} | {'> 0.50 (unreachable)':>26} | {'--':>9}")
                else:
                    rel = mde / p_lo
                    print(f"{n:>5} {p_lo:>6.2f} | "
                          f"{('+%.2f -> %.2f (pow %.2f)' % (mde, p_lo + mde, mde_power)):>26} | "
                          f"{rel:>8.1f}x")

    # ---- decision summary ----
    print("\n" + "=" * 78)
    print("DECISION SUMMARY")
    print("=" * 78)
    rho = RHO_GRID[0]
    for n in N_GRID:
        mdes = [results[(rho, n, p)] for p in P_LO_GRID]
        clean = [m for m in mdes if m is not None]
        if clean:
            lo, hi = min(clean), max(clean)
            print(f"  n={n:>3}: detectable absolute gap (80% power) ranges "
                  f"{lo:.2f}-{hi:.2f} across p_lo in {P_LO_GRID}")
        else:
            print(f"  n={n:>3}: NO gap <=0.50 reaches 80% power at any p_lo")
    print("\nINTERPRETATION:")
    print("  - MDE is the SMALLEST absolute rough-fine pass@1 gap an n-problem")
    print("    paired eval can detect at 80% power. Gaps below MDE are invisible to")
    print("    the planned comparison no matter how clean the corpus.")
    print("  - The headline claim is a gap x model-size INTERACTION (gap GROWS as")
    print("    the model shrinks): a difference-in-differences across sizes needs")
    print("    MORE power than this single-comparison MDE, so these are a floor.")


if __name__ == "__main__":
    main()
