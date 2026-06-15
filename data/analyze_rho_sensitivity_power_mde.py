"""Rho-SENSITIVITY gate for the Stage-0.5 power/MDE quartet (q-0007, q-0001).

The four power gates e-0040 (single gap x pass@1), e-0041 (interaction x pass@1),
e-0042 (single gap x pass@k) and e-0043 (interaction x pass@k) all close the Modal
go/no-go on the SAME load-bearing constant: the per-problem outcome correlation
between the rough-SFT and fine-SFT models is fixed at rho=0.5 (a single value, never
swept). But for a PAIRED McNemar test rho is NOT a nuisance knob -- it is the lever
the whole "underpowered" verdict turns on. The expected discordant imbalance
E[b-c] = n*delta is INVARIANT to rho, but the discordant TOTAL E[b+c] shrinks as rho
rises, so the same systematic gap lands in a smaller, more extreme discordant set ->
the paired test gains power. Higher rho => SMALLER MDE.

Why this matters for THIS study: rough and fine are not two unrelated models. They are
(a) SFT variants of the SAME base prover, (b) trained from paired reconstructions of
the SAME 607/~442 source proofs, (c) evaluated on the SAME held-out theorems. Per-
problem solvability is dominated by intrinsic problem difficulty shared across both
arms, so the realistic rho is plausibly WELL ABOVE 0.5 (0.7-0.9). If so, the affordable
n=116 within-deep route may be adequately powered at k=1 after all -- flipping e-0040/
e-0041's "statistically invisible at affordable n" verdict. Conversely if rho is LOW
(<0.3, e.g. the two policies solve disjoint problem subsets) the design is even worse.
Either way the go/no-go cannot rest on a single unswept rho.

This script reuses e-0040's paired McNemar Gaussian-copula machinery UNCHANGED and
sweeps rho in {0.0, 0.3, 0.5, 0.7, 0.9} over the single-gap pass@1 MDE, reporting MDE
as a function of rho for each (n, p_lo). The k=1 single-gap cell is the cleanest place
to isolate the rho dependence; the conclusion (MDE monotone-decreasing in rho)
propagates to all four gates because they share this copula. Pure stdlib (random,
math); deterministic seed; no Lean, no Modal, no numpy.
"""

import math
import random

SEED = 0
M = 1200            # Monte-Carlo trials per (n, p_lo, delta, rho) cell
ALPHA = 0.05
TARGET_POWER = 0.80
N_GRID = [50, 63, 116, 200]
P_LO_GRID = [0.05, 0.10, 0.20]
RHO_GRID = [0.0, 0.3, 0.5, 0.7, 0.9]   # SWEEP -- the whole point of this gate
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
    tail = 0.0
    loghalf_n = -n * math.log(2.0)
    log_comb = 0.0  # log C(n,0)
    for i in range(0, k + 1):
        if i > 0:
            log_comb += math.log(n - i + 1) - math.log(i)
        tail += math.exp(log_comb + loghalf_n)
    return min(1.0, 2.0 * tail)


def simulate_power(n, p_lo, delta, rho, rng):
    """Power of paired McNemar test for rough(p_hi) vs fine(p_lo) over n problems."""
    p_hi = p_lo + delta
    if p_hi >= 1.0:
        return None
    thr_lo = inv_phi(p_lo)
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


def mde_for(n, p_lo, rho, rng):
    for delta in DELTA_GRID:
        pw = simulate_power(n, p_lo, delta, rho, rng)
        if pw is None:
            return None
        if pw >= TARGET_POWER:
            return delta
    return None


def main():
    rng = random.Random(SEED)
    print("=" * 80)
    print("RHO-SENSITIVITY of the single-gap pass@1 paired MDE (e-0040 machinery)")
    print(f"  McNemar exact, alpha={ALPHA}, target power={TARGET_POWER}, M={M} trials/cell")
    print(f"  rho swept over {RHO_GRID} (all four power gates fixed rho=0.5)")
    print("=" * 80)

    results = {}  # (n, p_lo, rho) -> MDE
    for n in N_GRID:
        for p_lo in P_LO_GRID:
            print(f"\n### n={n}, weaker-policy pass rate p_lo={p_lo:.2f}")
            print(f"{'rho':>6} | {'MDE (abs gap @80% power)':>26}")
            print("-" * 38)
            for rho in RHO_GRID:
                mde = mde_for(n, p_lo, rho, rng)
                results[(n, p_lo, rho)] = mde
                if mde is None:
                    print(f"{rho:>6.1f} | {'> 0.50 (unreachable)':>26}")
                else:
                    print(f"{rho:>6.1f} | {('+%.2f -> %.2f' % (mde, p_lo + mde)):>26}")

    # ---- decision summary ----
    print("\n" + "=" * 80)
    print("DECISION SUMMARY -- how much does the unswept rho=0.5 choice matter?")
    print("=" * 80)

    # 1) The supply-ample affordable route n=116: MDE vs rho
    print("\n[A] Affordable supply-ample route n=116 -- MDE by rho (avg over p_lo):")
    for rho in RHO_GRID:
        ms = [results[(116, p, rho)] for p in P_LO_GRID]
        clean = [m for m in ms if m is not None]
        if clean:
            print(f"    rho={rho:.1f}: MDE range {min(clean):.2f}-{max(clean):.2f} "
                  f"across p_lo in {P_LO_GRID}")
        else:
            print(f"    rho={rho:.1f}: unreachable at every p_lo")

    # 2) Multiplicative gain from rho=0.5 -> rho=0.9 (the realistic-same-proof case)
    print("\n[B] Power gain from the unswept rho assumption (rho=0.5 baseline):")
    for n in N_GRID:
        line = [f"  n={n:>3}:"]
        for p_lo in P_LO_GRID:
            base = results[(n, p_lo, 0.5)]
            hi = results[(n, p_lo, 0.9)]
            lo = results[(n, p_lo, 0.3)]
            def fmt(m):
                return f"{m:.2f}" if m is not None else ">.50"
            line.append(f"p_lo={p_lo:.2f}[rho.3/{ '%.2f'%base if base else '>.50'}/.9: "
                        f"{fmt(lo)}/{fmt(base)}/{fmt(hi)}]")
        print("  ".join(line))

    print("\nINTERPRETATION:")
    print("  - MDE is MONOTONE-DECREASING in rho: pairing two SFT variants of the same")
    print("    base on the same held-out theorems is the lever, not a nuisance.")
    print("  - If realistic rho ~0.8-0.9 (shared problem difficulty dominates), the")
    print("    affordable n=116 route is far better powered than the rho=0.5 verdict")
    print("    implied -- potentially resolving few-point gaps at k=1 with no pass@k")
    print("    gymnastics. If rho <0.3 (disjoint solve sets) the design is even worse.")
    print("  - CONSEQUENCE: the Modal go/no-go cannot rest on rho=0.5. The eval must")
    print("    LOG the realized discordant counts (b+c) to estimate rho empirically;")
    print("    a small pilot fixes rho before committing the full SFT+eval spend.")
    print("\nCAVEAT: design-stage power calc, not an outcome. rho is an assumed copula")
    print("  parameter; the realized rough/fine outcome correlation is unknown until a")
    print("  pilot eval. Gaussian-copula approximation to paired Bernoulli; single seed.")


if __name__ == "__main__":
    main()
