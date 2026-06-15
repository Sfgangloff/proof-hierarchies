"""BASE-RATE BREAK-EVEN gate for the headline rough-vs-fine study (q-0007 / q-0001).

e-0059 (the JOINT feasibility frontier) REVERSED e-0041's pessimistic pass@1 verdict:
composing supply x power x budget, it found the gap-grows-as-model-shrinks INTERACTION
becomes resolvable (+0.047-0.068 MDE, ~34x baseline) on the supply-ample deep routes
WHEN the small-model per-sample pass rate sits near the e-0005 0/50 floor, because that
is where pass@k amplification is strongest. But that whole verdict rests on ONE unmeasured
parameter -- the post-SFT small-model per-sample rate p_lo -- and e-0059 swept it on a
COARSE 3-point grid {0.05, 0.10, 0.20} that hides a sharp cliff: feasible at 0.10,
DEAD at 0.20. e-0059's own load-bearing caveat says so: feasibility "would FAIL if SFT
lifts the base rate to ~0.20 with a still-small gap."

This gate converts that binary into a continuous frontier and pins the decision number
e-0059 left a 3-point hole around: the BREAK-EVEN base rate p* at which the interaction
MDE crosses each plausible effect band {+0.05,+0.10,+0.15} on the COMMITTED routes
(within-deep-binary n=116, on-domain-deep n=126). p* answers the operational go/no-go:
"the design is GO iff the realized post-SFT small-model per-sample pass rate stays below
p* -- and here is exactly how much margin above the 0/50 floor that leaves."

Reuses e-0040/e-0042/e-0059's McNemar Gaussian-copula machinery VERBATIM (same phi,
inv_phi, mcnemar_exact_two_sided, passk, simulate_power, best_k_mde). The only change is
a FINE p_lo grid (0.02..0.30 step 0.02) instead of the 3-point grid, plus a break-even
search per route x effect band.

HONEST SCOPE. Design-stage synthesis, identical assumptions to e-0059: supply n are the
chain's COUNT projections (not real round-trips); DiD interaction MDE = single-gap MDE x
e-0041's measured 1.35x surcharge (not a four-arm re-simulation); rho=0.5 (e-0040
assumed); k samples i.i.d. given p; single seed. Projects feasibility, not a measured
pass@k outcome. The true post-SFT small-model rate is Modal-blocked -- this prices WHERE
that rate must land, it does not measure it.
"""

import math
import random

SEED = 0
M = 1000
ALPHA = 0.05
TARGET_POWER = 0.80
RHO = 0.5
K_GRID = [1, 2, 4, 8]                 # interior best-k (e-0042); k=16 saturates at floor
DID_MULTIPLIER = 1.35                 # e-0041: interaction MDE ~1.35x single-gap MDE
EFFECT_BAND = [0.05, 0.10, 0.15]      # plausible absolute pass@k granularity gap
DELTA_GRID = [round(0.005 * k, 3) for k in range(1, 101)]  # per-sample gap 0.005..0.50

# Fine base-rate sweep -- the whole point of this gate (e-0059 used only 0.05/0.10/0.20).
P_LO_GRID = [round(0.02 * k, 2) for k in range(1, 16)]     # 0.02 .. 0.30 step 0.02

# Committed supply-ample construct-valid routes (e-0059's two GO routes; pi_mid and
# corpus_v3 dropped -- e-0059 ruled them most-expensive/dead respectively).
ROUTES = [
    ("within-deep-binary", 116, 34.0,
     "e-0046/e-0049/e-0055: ~116 verified depth>=1 carriers, module-disjoint holdout"),
    ("on-domain-deep",     126, 34.0,
     "e-0029: ~126 verified AND miniF2F-eval-relevant frontiers (on-domain slice)"),
]


def phi(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def inv_phi(p):
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
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = 0.0
    loghalf_n = -n * math.log(2.0)
    log_comb = 0.0
    for i in range(0, k + 1):
        if i > 0:
            log_comb += math.log(n - i + 1) - math.log(i)
        tail += math.exp(log_comb + loghalf_n)
    return min(1.0, 2.0 * tail)


def passk(p, k):
    return 1.0 - (1.0 - p) ** k


def simulate_power(n, P_lo, P_hi, rng):
    if P_hi >= 1.0:
        P_hi = 1.0 - 1e-9
    thr_lo = inv_phi(P_lo)
    thr_hi = inv_phi(P_hi)
    a = RHO
    bcoef = math.sqrt(max(0.0, 1.0 - RHO * RHO))
    rejects = 0
    for _ in range(M):
        b = c = 0
        for _ in range(n):
            z1 = rng.gauss(0.0, 1.0)
            z2 = a * z1 + bcoef * rng.gauss(0.0, 1.0)
            if (z1 < thr_hi) and not (z2 < thr_lo):
                b += 1
            elif (z2 < thr_lo) and not (z1 < thr_hi):
                c += 1
        if mcnemar_exact_two_sided(b, c) < ALPHA:
            rejects += 1
    return rejects / M


def best_k_mde(n, p_lo, rng):
    """Smallest per-sample gap at 80% power across k in K_GRID, and the best k."""
    best = (None, None)  # (mde, k)
    for k in K_GRID:
        for delta in DELTA_GRID:
            p_hi = p_lo + delta
            if p_hi >= 1.0:
                break
            pw = simulate_power(n, passk(p_lo, k), passk(p_hi, k), rng)
            if pw >= TARGET_POWER:
                if best[0] is None or delta < best[0]:
                    best = (delta, k)
                break
    return best


def main():
    rng = random.Random(SEED)
    print("=" * 96)
    print("BASE-RATE BREAK-EVEN -- WHERE must the post-SFT small-model pass rate land for the")
    print("headline interaction to stay resolvable? (sharpens e-0059's 3-point base-rate sweep)")
    print(f"  paired McNemar exact, alpha={ALPHA}, power={TARGET_POWER}, rho={RHO}, M={M}/cell, seed={SEED}")
    print("  single-gap MDE = smallest per-sample rough-fine gap at 80% power, best interior k")
    print(f"  interaction MDE = single-gap MDE x {DID_MULTIPLIER} (e-0041 measured DiD surcharge)")
    print("=" * 96)

    # single-gap best-k MDE on the FINE base-rate grid, per route
    table = {}  # (route, p_lo) -> (single_mde, best_k)
    for name, n, *_ in ROUTES:
        for p_lo in P_LO_GRID:
            table[(name, p_lo)] = best_k_mde(n, p_lo, rng)

    for name, n, c_inter, prov in ROUTES:
        print(f"\nROUTE {name} (n={n}, interaction compute ~{c_inter:.0f}x baseline)")
        print(f"  {prov}")
        print(f"  {'p_lo':>6} | {'single MDE':>12} | {'k*':>3} | {'inter MDE':>11} | "
              f"resolvable-interaction @ band")
        print("  " + "-" * 78)
        for p_lo in P_LO_GRID:
            mde, k = table[(name, p_lo)]
            if mde is None:
                print(f"  {p_lo:>6.2f} | {'>0.50':>12} | {'-':>3} | {'>0.68':>11} | none")
                continue
            inter = mde * DID_MULTIPLIER
            bands = " ".join(f"+{b:.2f}:{'Y' if inter <= b else 'n'}" for b in EFFECT_BAND)
            print(f"  {p_lo:>6.2f} | {'+%.3f' % mde:>12} | {k:>3} | "
                  f"{'+%.3f' % inter:>11} | {bands}")

    # ---- break-even base rate p* per route x effect band ----
    # MDE is monotone non-decreasing in p_lo over this floor->mid regime (less pass@k
    # amplification as the base rate rises), so the resolvable region is p_lo <= p*.
    # p* = largest grid base rate whose interaction MDE still clears the band (with the
    # next grid point failing); report as a half-open interval between grid points.
    print("\n" + "=" * 96)
    print("BREAK-EVEN BASE RATE p*  --  interaction is RESOLVABLE iff small-model p_lo <= p*")
    print("  (margin = headroom above the e-0005 0/50 pre-SFT floor before the design fails)")
    print("=" * 96)
    for name, n, c_inter, prov in ROUTES:
        print(f"\n  {name} (n={n}):")
        for thr in EFFECT_BAND:
            ok = [p for p in P_LO_GRID
                  if table[(name, p)][0] is not None
                  and table[(name, p)][0] * DID_MULTIPLIER <= thr]
            if not ok:
                print(f"    band +{thr:.2f}: NEVER resolvable -- interaction MDE > +{thr:.2f} "
                      f"at every base rate (incl. the 0/50 floor)")
                continue
            p_star = max(ok)
            nxt = [p for p in P_LO_GRID if p > p_star]
            if not nxt:
                print(f"    band +{thr:.2f}: p* >= {p_star:.2f} (resolvable across the ENTIRE "
                      f"swept range up to {max(P_LO_GRID):.2f})")
            else:
                print(f"    band +{thr:.2f}: p* in ({p_star:.2f}, {nxt[0]:.2f}] -- GO while the "
                      f"small-model per-sample rate stays <~{nxt[0]:.2f}")

    print("\n" + "=" * 96)
    print("BOTTOM LINE")
    print("=" * 96)
    # focus on the loosest committed band (+0.10) on the cheapest route
    thr = 0.10
    name, n = ROUTES[0][0], ROUTES[0][1]
    ok = [p for p in P_LO_GRID
          if table[(name, p)][0] is not None
          and table[(name, p)][0] * DID_MULTIPLIER <= thr]
    if ok:
        p_star = max(ok)
        nxt = [p for p in P_LO_GRID if p > p_star]
        edge = nxt[0] if nxt else max(P_LO_GRID)
        print(f"  On {name} at the +{thr:.2f} effect band, the headline interaction is")
        print(f"  resolvable while the post-SFT small-model per-sample pass rate stays")
        print(f"  below ~{edge:.2f} (break-even p* ~ {p_star:.2f}-{edge:.2f}). The e-0005")
        print(f"  pre-SFT floor is 0/50, so the design has ~{p_star:.2f} absolute headroom")
        print(f"  above the floor -- it survives a modest SFT lift but FAILS if SFT pushes")
        print(f"  the small model past ~{edge:.2f} pass@1 with a still-small granularity gap.")
        print(f"  This quantifies e-0059's binary cliff (feasible@0.10 / dead@0.20) as a")
        print(f"  continuous break-even, and confirms the floor assumption is load-bearing.")
    else:
        print(f"  Even at the 0/50 floor the interaction is unresolvable at +{thr:.2f} on "
              f"{name}.")
    print("\nCAVEATS: design-stage synthesis (identical assumptions to e-0059); supply n are")
    print("COUNT projections, not real round-trips; interaction MDE = e-0041's 1.35x")
    print("multiplier, not a four-arm re-simulation; rho=0.5 assumed; k samples i.i.d. given")
    print("p; single seed. The true post-SFT small-model rate is Modal-blocked -- this prices")
    print("WHERE it must land, it does not measure it. p* is read on a 0.02 grid.")


if __name__ == "__main__":
    main()
