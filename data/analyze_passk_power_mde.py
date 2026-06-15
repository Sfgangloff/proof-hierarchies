"""How much does pass@k (k>1) raise the power of the headline rough-vs-fine
comparison? -- the unquantified recommendation in e-0040/a-0038 and e-0041/a-0039.

Both prior power gates close with the SAME load-bearing advice for the Modal
go/no-go: a single-seed pass@1 eval is underpowered for any modest granularity
effect, so the design should "use pass@k>1 / continuous-margin outcomes (which
raise both pass rates and power)". Neither gate computes HOW MUCH pass@k helps,
nor whether the gain saturates. This experiment supplies that number, reusing the
e-0040 McNemar Gaussian-copula machinery unchanged -- the only change is that each
policy's per-problem outcome is now pass@k, with marginal

    P(k) = 1 - (1 - p)^k

for a per-SAMPLE pass rate p. The two competing forces this makes explicit:

  (+) AMPLIFICATION. A small per-sample gap is amplified in pass@k space when
      rates are low: with p_lo=0.05, delta=0.05 (p_hi=0.10), the pass@8 gap is
      (0.95)^8 - (0.90)^8 = 0.233 -- a 4.6x larger absolute gap to detect.
  (-) SATURATION. As k grows both policies' pass@k rates climb toward 1; the gap
      then COLLAPSES (both near-certain to solve) and binomial noise (variance
      maximal near 0.5) rises. So there is an OPTIMAL k beyond which power FALLS.

DESIGN. Per-sample weaker-policy rate p_lo in {0.05,0.10,0.20} (the e-0040 grid,
read as pass@1 sample rates near the e-0005 0/50 floor). For each k, per-sample
gap delta, map to pass@k marginals (P_lo, P_hi) = (1-(1-p_lo)^k, 1-(1-p_hi)^k),
feed those into the SAME paired McNemar exact copula simulation (rho=0.5, the
e-0040 assumed SFT-variant outcome correlation, now applied in pass@k-outcome
space), and find the smallest per-SAMPLE delta reaching 80% power. Report MDE on
the per-sample gap vs k, so the comparison to e-0040's pass@1 MDE is apples-to-
apples (same true quantity: the per-sample rough-vs-fine advantage).

HONEST SCOPE. Design-stage power calc, NOT a measured pass@k outcome. (1) The
k independent samples are assumed i.i.d. per problem (no shared per-problem
difficulty random effect collapsing them) -- a fuller model would DERIVE the
pass@k correlation from a difficulty random effect rather than fix it; here rho
is held at e-0040's 0.5 in pass@k space for comparability, an assumption (real
pass@k correlation likely exceeds pass@1's, which would RAISE power -- conservative
here). (2) Pure stdlib (random, math); deterministic seed; no Lean, no Modal, no
numpy. (3) Projects power, not a pass@k number the SFT'd models will actually hit.
"""

import math
import random

SEED = 0
M = 1200            # Monte-Carlo trials per cell (e-0040 used 1500; trimmed for the k-sweep)
ALPHA = 0.05
TARGET_POWER = 0.80
N_GRID = [50, 63, 116, 200]
P_LO_GRID = [0.05, 0.10, 0.20]      # per-SAMPLE (pass@1) weaker-policy rates
K_GRID = [1, 2, 4, 8, 16]
RHO = 0.5                            # pass@k-outcome correlation (e-0040 assumption)
DELTA_GRID = [round(0.01 * k, 2) for k in range(1, 51)]  # per-sample gap 0.01..0.50


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
    """pass@k marginal for per-sample rate p over k i.i.d. samples."""
    return 1.0 - (1.0 - p) ** k


def simulate_power_marginals(n, P_lo, P_hi, rho, rng):
    """Paired McNemar power for two correlated binary outcomes with the given
    marginals (already in pass@k space)."""
    if P_hi >= 1.0:
        P_hi = 1.0 - 1e-9
    thr_lo = inv_phi(P_lo)
    thr_hi = inv_phi(P_hi)
    a = rho
    bcoef = math.sqrt(max(0.0, 1.0 - rho * rho))
    rejects = 0
    for _ in range(M):
        b = c = 0
        for _ in range(n):
            z1 = rng.gauss(0.0, 1.0)
            z2 = a * z1 + bcoef * rng.gauss(0.0, 1.0)
            rough_pass = z1 < thr_hi
            fine_pass = z2 < thr_lo
            if rough_pass and not fine_pass:
                b += 1
            elif fine_pass and not rough_pass:
                c += 1
        if mcnemar_exact_two_sided(b, c) < ALPHA:
            rejects += 1
    return rejects / M


def mde_per_sample_gap(n, p_lo, k, rng):
    """Smallest per-SAMPLE gap delta reaching 80% power under a pass@k eval.
    Returns (delta, passk_gap, power) or (None, None, None)."""
    for delta in DELTA_GRID:
        p_hi = p_lo + delta
        if p_hi >= 1.0:
            break
        P_lo, P_hi = passk(p_lo, k), passk(p_hi, k)
        pw = simulate_power_marginals(n, P_lo, P_hi, RHO, rng)
        if pw >= TARGET_POWER:
            return delta, P_hi - P_lo, pw
    return None, None, None


def main():
    rng = random.Random(SEED)
    print("=" * 86)
    print("PASS@K POWER / MDE -- how much does k>1 raise power of paired rough-vs-fine?")
    print(f"  McNemar exact, alpha={ALPHA}, target power={TARGET_POWER}, rho={RHO}, M={M}/cell")
    print("  MDE = smallest PER-SAMPLE rough-fine gap reaching 80% power under a pass@k eval")
    print("=" * 86)

    results = {}  # (n, p_lo, k) -> (delta, passk_gap)
    for p_lo in P_LO_GRID:
        print(f"\n### per-sample weaker-policy rate p_lo = {p_lo:.2f}  "
              f"(pass@k rate of weaker policy in brackets)")
        header = f"{'n':>5} | " + " | ".join(f"k={k:<2}".rjust(16) for k in K_GRID)
        print(header)
        print("-" * len(header))
        for n in N_GRID:
            cells = []
            for k in K_GRID:
                delta, gap, pw = mde_per_sample_gap(n, p_lo, k, rng)
                results[(n, p_lo, k)] = (delta, gap)
                if delta is None:
                    cells.append(f"{'>0.50':>16}")
                else:
                    Plo = passk(p_lo, k)
                    cells.append(f"{('+%.2f [%.2f]' % (delta, Plo)):>16}")
            print(f"{n:>5} | " + " | ".join(cells))

    # ---- decision summary ----
    print("\n" + "=" * 86)
    print("DECISION SUMMARY -- per-sample MDE vs k (best k in *stars*), p_lo averaged")
    print("=" * 86)
    print("  For each n, the smallest per-sample gap detectable at 80% power, by k:")
    for n in N_GRID:
        line = f"  n={n:>3}: "
        best_k, best_mde = None, 9.9
        parts = []
        for k in K_GRID:
            vals = [results[(n, p, k)][0] for p in P_LO_GRID]
            clean = [v for v in vals if v is not None]
            if clean:
                avg = sum(clean) / len(clean)
                parts.append((k, avg))
                if avg < best_mde:
                    best_mde, best_k = avg, k
        rendered = []
        for k, avg in parts:
            tag = f"*k{k}:{avg:.2f}*" if k == best_k else f"k{k}:{avg:.2f}"
            rendered.append(tag)
        print(line + "  ".join(rendered))

    print("\nINTERPRETATION:")
    print("  - Each entry is the per-SAMPLE rough-fine gap an n-problem paired eval can")
    print("    detect at 80% power when scored by pass@k. Lower = more sensitive.")
    print("  - k>1 AMPLIFIES a small per-sample gap (low rates) -> MDE drops; but as")
    print("    pass@k rates saturate toward 1 the gap collapses -> MDE rises again, so")
    print("    the best k is interior. Compare to e-0040's pass@1 (k=1) column.")
    print("  - CAVEAT: design-stage calc; k samples i.i.d. per problem; rho fixed at")
    print("    e-0040's 0.5 in pass@k space (real pass@k corr likely higher -> more power,")
    print("    so conservative); projects power, not a measured pass@k outcome.")


if __name__ == "__main__":
    main()
