"""JOINT feasibility frontier for the headline rough-vs-fine study (q-0007 / q-0001).

The Stage-0.5 gate chain (e-0029..e-0058) priced every design axis IN ISOLATION:
  - SUPPLY  : verified construct-valid eval carriers per route
              (e-0029 on-domain ~126; e-0031/e-0046 within-deep ~116; e-0057 pi_mid ~63;
               e-0032 corpus_v3 construct-valid ~4.4% -> dead).
  - POWER   : paired-McNemar / pass@k / DiD MDE as a function of n and k
              (e-0040 single-gap pass@1; e-0042 interior best-k; e-0041 DiD ~1.35x single-gap;
               e-0056 variance mechanism blind to pass@1).
  - BUDGET  : compute multiples over the proven-affordable baseline
              (e-0048 single-size pass@1 = 8.5x, multi-size interaction = 34-204x;
               e-0052/e-0053 training collapses to ~1-2x under the same-format build).

No gate COMPOSED them. This experiment assembles the three axes into ONE decision
table: for each construct-valid eval ROUTE (its supply fixes n) and each study
DESIGN (single-size gap vs the headline size-INTERACTION), it computes the achievable
best-interior-k MDE (reusing e-0040/e-0042's McNemar Gaussian-copula machinery
verbatim) and attaches the compute multiple, then marks the cell RESOLVABLE iff its
MDE clears a stated plausible-effect band. Output: the minimal jointly-feasible design,
or a proof that the headline INTERACTION is unresolvable at any affordable route while
a single-size GAP is.

HONEST SCOPE. Design-stage synthesis. The supply numbers are the chain's established
projections (per-area COUNT projections, not real round-trips); the DiD MDE uses
e-0041's measured ~1.35x single-gap multiplier rather than re-simulating four arms;
base rate p_lo is swept over the chain's {0.05,0.10,0.20} grid because the true
within-deep small-model pass rate is unmeasured (Modal-blocked). Pure stdlib, seed 0,
no Lean, no Modal. Projects feasibility, not a measured pass@k outcome.
"""

import math
import random

SEED = 0
M = 1200
ALPHA = 0.05
TARGET_POWER = 0.80
P_LO_GRID = [0.05, 0.10, 0.20]      # per-sample weaker-policy rate; true rate unmeasured
K_GRID = [1, 2, 4, 8]               # interior best-k lives here (e-0042); k=16 saturates
RHO = 0.5                           # e-0040 assumed SFT-variant outcome correlation
DELTA_GRID = [round(0.005 * k, 3) for k in range(1, 101)]  # per-sample gap 0.005..0.50
DID_MULTIPLIER = 1.35               # e-0041: interaction MDE ~1.3-1.4x single-gap MDE

# Plausible absolute pass@k granularity-effect band against which a route is judged.
# The project never commits a point value; the literature framing is "a few points".
EFFECT_BAND = [0.05, 0.10, 0.15]

# ---- ROUTES: supply (verified construct-valid eval carriers) with provenance ----
# n is the per-SIZE held-out carrier count the paired McNemar test runs over.
ROUTES = [
    # name, supply n, compute-mult single-size, compute-mult interaction, provenance
    ("corpus_v3-test",        3,   8.5,  34.0,
     "e-0032: ~4.4% of ~63 test decls are >=2 construct-valid -> ~3 carriers (DEAD)"),
    ("within-deep-binary",  116,   8.5,  34.0,
     "e-0046/e-0049/e-0055: ~116 verified depth>=1 carriers, module-disjoint holdout"),
    ("within-deep-pi_mid",   63,  12.8,  51.0,   # 3-arm: ~1.5x compute (a-0054)
     "e-0057: ~63 verified depth>=2 substantive carriers (3rd pi_mid arm, ~1.5x cost)"),
    ("on-domain-deep",      126,   8.5,  34.0,
     "e-0029: ~126 verified AND miniF2F-eval-relevant frontiers (the on-domain slice)"),
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
    print("=" * 92)
    print("JOINT FEASIBILITY FRONTIER -- supply x power x budget, composed into one go/no-go")
    print(f"  paired McNemar exact, alpha={ALPHA}, power={TARGET_POWER}, rho={RHO}, M={M}/cell")
    print("  MDE = smallest PER-SAMPLE rough-fine gap resolvable at 80% power, best interior k")
    print("  interaction MDE = single-gap MDE x %.2f (e-0041 measured DiD surcharge)" % DID_MULTIPLIER)
    print("=" * 92)

    # single-gap best-k MDE per (route, p_lo)
    table = {}  # (route, p_lo) -> (single_mde, best_k)
    for name, n, *_ in ROUTES:
        for p_lo in P_LO_GRID:
            table[(name, p_lo)] = best_k_mde(n, p_lo, rng)

    print("\nSINGLE-SIZE GAP -- per-sample MDE [best k] by route x base rate")
    hdr = f"{'route':>20} {'n':>4} | " + " | ".join(f"p_lo={p:.2f}".rjust(14) for p in P_LO_GRID)
    print(hdr)
    print("-" * len(hdr))
    for name, n, *_ in ROUTES:
        cells = []
        for p_lo in P_LO_GRID:
            mde, k = table[(name, p_lo)]
            cells.append((f"+{mde:.3f} [k{k}]" if mde is not None else ">0.50").rjust(14))
        print(f"{name:>20} {n:>4} | " + " | ".join(cells))

    print("\nINTERACTION (gap-grows-as-model-shrinks) -- single-gap MDE x %.2f" % DID_MULTIPLIER)
    print(hdr)
    print("-" * len(hdr))
    for name, n, *_ in ROUTES:
        cells = []
        for p_lo in P_LO_GRID:
            mde, k = table[(name, p_lo)]
            v = f"+{mde * DID_MULTIPLIER:.3f} [k{k}]" if mde is not None else ">0.68"
            cells.append(v.rjust(14))
        print(f"{name:>20} {n:>4} | " + " | ".join(cells))

    # ---- joint feasibility against the effect band ----
    print("\n" + "=" * 92)
    print("JOINT FEASIBILITY -- a cell is RESOLVABLE iff best-k MDE <= effect threshold")
    print("  (MDE taken at the MOST FAVOURABLE base rate per route; compute mult from e-0048)")
    print("=" * 92)
    for thr in EFFECT_BAND:
        print(f"\n  plausible effect threshold = +{thr:.2f} absolute pass@k gap")
        for name, n, c_single, c_inter, prov in ROUTES:
            mdes = [table[(name, p)][0] for p in P_LO_GRID if table[(name, p)][0] is not None]
            if not mdes:
                print(f"    {name:>20} (n={n:>3}): single NO  inter NO   -- no powered cell at any k")
                continue
            best_single = min(mdes)
            best_inter = best_single * DID_MULTIPLIER
            s_ok = best_single <= thr
            i_ok = best_inter <= thr
            print(f"    {name:>20} (n={n:>3}): "
                  f"single {'YES' if s_ok else 'NO ':3} (MDE +{best_single:.3f}, {c_single:.0f}x)  "
                  f"inter {'YES' if i_ok else 'NO ':3} (MDE +{best_inter:.3f}, {c_inter:.0f}x)")

    print("\n" + "=" * 92)
    print("BOTTOM LINE")
    print("=" * 92)
    # cheapest route that resolves the SINGLE gap at the loosest plausible effect (+0.10)
    thr = 0.10
    single_ok, inter_ok = [], []
    for name, n, c_single, c_inter, prov in ROUTES:
        mdes = [table[(name, p)][0] for p in P_LO_GRID if table[(name, p)][0] is not None]
        if not mdes:
            continue
        bs = min(mdes)
        if bs <= thr:
            single_ok.append((c_single, name, bs))
        if bs * DID_MULTIPLIER <= thr:
            inter_ok.append((c_inter, name, bs * DID_MULTIPLIER))
    single_ok.sort()
    inter_ok.sort()
    print(f"  At a +{thr:.2f} plausible effect (favourable base rate, best interior k):")
    if single_ok:
        c, nm, mde = single_ok[0]
        print(f"  - SINGLE-SIZE GAP is RESOLVABLE. Cheapest viable route: {nm} "
              f"(MDE +{mde:.3f}, ~{c:.0f}x baseline).")
    else:
        print("  - SINGLE-SIZE GAP is UNRESOLVABLE at any route for +%.2f." % thr)
    if inter_ok:
        c, nm, mde = inter_ok[0]
        print(f"  - HEADLINE INTERACTION is RESOLVABLE. Cheapest route: {nm} "
              f"(MDE +{mde:.3f}, ~{c:.0f}x baseline).")
    else:
        print("  - HEADLINE INTERACTION is UNRESOLVABLE at every affordable route for "
              f"+{thr:.2f}: the gap-grows-as-model-shrinks claim needs n beyond any")
        print("    construct-valid supply the project can build, OR a larger true effect,")
        print("    OR a continuous-margin outcome. Restrict the paper to a single-size gap.")
    print("\nCAVEATS: design-stage synthesis; supply = chain's COUNT projections (not real")
    print("round-trips); DiD MDE = e-0041's 1.35x multiplier, not a re-simulation; base rate")
    print("swept (true within-deep small-model rate is Modal-blocked); single seed.")


if __name__ == "__main__":
    main()
