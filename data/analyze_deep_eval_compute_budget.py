"""DEEP-ROUTE EVAL COMPUTE-BUDGET gate: does the statistically-recommended
headline design actually FIT the free-tier Modal envelope? (q-0007 / q-0001)

The Stage-0.5 power chain (e-0040..e-0047) priced the headline's statistical
RESOLVABILITY and converged on a recommendation: run the within-deep route at
effective n~106-115 (e-0046), score with a TUNED pass@k whose optimum is INTERIOR
(e-0047: best k=8-16 at floor rates, k=4 once the weaker policy saturates), across
>=2 model sizes (the interaction/DiD needs at least two), 2 policies (rough/fine).

That whole chain answered "is the effect resolvable?" and never once answered the
question CLAUDE.md makes a first-class constraint: "can we AFFORD to resolve it?"
The recommendation's load-bearing lever -- a large interior k -- is exactly the
multiplier that drives eval compute, because pass@k requires k generations AND k
Lean verifications PER (problem, model, policy). No gate multiplied the recommended
(n, k, sizes, policies) back out into a compute cost and compared it to what the
project has empirically shown it can afford.

There is exactly one such empirical anchor on disk: e-0006/a-0005 measured the
end-to-end T4 + Kimina-Lean-Server loop at ~56 minutes for 50 problems at pass@1
(k=1), one model, one policy, and reported it ran WITHIN free-tier limits. That is
the only eval run the project has PROVEN affordable: 50 problem-samples = 56 T4-min.
We price the recommended design as a MULTIPLE of that proven-affordable unit, which
avoids fabricating a credit-dollar figure the user has said is not auto-visible.

Cost model. The eval issues, for each (problem, model size, policy), k sampled
generations, each followed by one Lean verification:

    total_samples = n_problems * k * n_sizes * n_policies

Two regimes bound the wall-clock:
  * LINEAR (verification-bound, conservative): every sample costs the full anchor
    per-sample time t1 = 56/50 = 1.12 T4-min. wall = t1 * total_samples. This is
    the honest upper bound, and it is also near-truth because the k Lean compiles
    per problem are strictly serial-in-work and dominate.
  * GEN-BATCHED (optimistic lower bound): a 0.5B model batches its k generations
    on a T4 at near-constant GPU time, so only verification scales with k. Splitting
    t1 into a generation share g and a verification share (1-g), the batched wall is
    t1 * n * sizes * policies * (g + (1-g)*k). We report g=0.5 as a midpoint; the
    verification floor (1-g)*k makes even this large for big k.

Anchor-relative is the headline: cost_units = total_samples / 50, i.e. how many
proven-affordable e-0006 runs the design equals. The single run that was shown to
fit = 1.0 unit.

CAVEATS. t1=1.12 min/sample is from the PRE-SFT degenerate 0.5B model, which emits
short junk that Kimina rejects fast; SFT'd models emit longer, often near-valid
proofs that are SLOWER to generate AND slower to verify, so t1 -- and every number
here -- is a LOWER bound on the post-SFT eval cost. Training compute (e-0007 QLoRA,
2 policies x n_sizes adapters) is NOT included; this gate prices EVAL only. Free-tier
credit is finite and not auto-visible (CLAUDE.md), so we anchor to the one run proven
to fit rather than to an absolute budget. Pure stdlib; no Lean, no Modal.

  python3 -m data.analyze_deep_eval_compute_budget [--out path.json]
"""

from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEEP_INTERACTION_JSON = HERE / "corpus_v3" / "deep_interaction_passk_power.json"

# --- empirical anchor: the ONE eval run e-0006/a-0005 proved affordable ----------
ANCHOR_PROBLEMS = 50          # a-0005: 50 problems
ANCHOR_MINUTES = 56.0         # a-0005: ~56 T4-min, within free-tier limits
ANCHOR_K = 1                  # pass@1
ANCHOR_SAMPLES = ANCHOR_PROBLEMS * ANCHOR_K           # 50 problem-samples
T1_MIN_PER_SAMPLE = ANCHOR_MINUTES / ANCHOR_SAMPLES   # 1.12 T4-min / problem-sample

GEN_SHARE = 0.5   # midpoint split of t1 between generation (batches in k) and verify


def load_design():
    """Read the e-0047 recommendation: effective n and the powered best-k per s_f."""
    if not DEEP_INTERACTION_JSON.exists():
        subprocess.run(
            [sys.executable, "-m", "data.analyze_deep_interaction_passk_power"],
            cwd=str(HERE.parent), check=True,
        )
    d = json.loads(DEEP_INTERACTION_JSON.read_text())
    n_ge2 = d["deep_effective_n"]["ge2"]   # 106 -- the real >=2-frontier route
    n_ge1 = d["deep_effective_n"]["ge1"]   # 115
    # best k per weaker-policy rate s_f on the >=2-frontier route (the powered band)
    best_k = {sf: cell["best_k"] for sf, cell in d["cells"]["ge2"]["interaction"].items()}
    return n_ge1, n_ge2, best_k, d


def linear_wall_min(n, k, sizes, policies):
    return T1_MIN_PER_SAMPLE * n * k * sizes * policies


def batched_wall_min(n, k, sizes, policies, g=GEN_SHARE):
    # generation batches in k (near-constant), verification scales linearly in k
    per_problem = T1_MIN_PER_SAMPLE * (g + (1.0 - g) * k)
    return per_problem * n * sizes * policies


def cost_units(n, k, sizes, policies):
    return (n * k * sizes * policies) / ANCHOR_SAMPLES


def fmt_h(minutes):
    return f"{minutes/60:.1f}h"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "corpus_v3" / "deep_eval_compute_budget.json"))
    args = ap.parse_args()

    n_ge1, n_ge2, best_k, _ = load_design()
    n = n_ge2  # price the real >=2-frontier route

    print("=" * 78)
    print("DEEP-ROUTE EVAL COMPUTE-BUDGET: can the powered headline design be AFFORDED?")
    print(f"  anchor (e-0006/a-0005, proven within free tier): {ANCHOR_PROBLEMS} problems @ "
          f"pass@{ANCHOR_K} = {ANCHOR_SAMPLES} samples in {ANCHOR_MINUTES:.0f} T4-min")
    print(f"  => t1 = {T1_MIN_PER_SAMPLE:.3f} T4-min / problem-sample (PRE-SFT lower bound)")
    print(f"  route: within-deep effective n = {n} (>=2 frontier, e-0046); policies = 2")
    print(f"  e-0047 powered best-k per weaker-policy rate s_f: {best_k}")
    print("=" * 78)

    POLICIES = 2
    rows = []
    # the design grid: powered k band x model-size count
    K_GRID = [1, 4, 8, 16]
    SIZE_GRID = [2, 3]
    print(f"\n{'design':<34}{'samples':>9}{'units':>8}{'linear':>10}{'batched':>10}")
    print(f"{'(n=%d, 2 policies)' % n:<34}{'':>9}{'(/50)':>8}{'(T4)':>10}{'(T4,g=.5)':>10}")
    print("-" * 78)
    for sizes in SIZE_GRID:
        for k in K_GRID:
            samples = n * k * sizes * POLICIES
            u = cost_units(n, k, sizes, POLICIES)
            lin = linear_wall_min(n, k, sizes, POLICIES)
            bat = batched_wall_min(n, k, sizes, POLICIES)
            label = f"k={k:<2} x {sizes} sizes"
            print(f"{label:<34}{samples:>9}{u:>7.0f}x{fmt_h(lin):>10}{fmt_h(bat):>10}")
            rows.append(dict(k=k, sizes=sizes, policies=POLICIES, n=n, samples=samples,
                             units_of_proven_run=round(u, 1),
                             linear_T4_min=round(lin, 1), batched_T4_min=round(bat, 1)))
        print("-" * 78)

    # the two anchor designs for the verdict
    powered = next(r for r in rows if r["k"] == 16 and r["sizes"] == 3)   # full headline, k=16
    powered_k8 = next(r for r in rows if r["k"] == 8 and r["sizes"] == 2)  # leaner powered
    cheap = next(r for r in rows if r["k"] == 4 and r["sizes"] == 2)       # k=4 floor (best @ s_f=.20)
    single = next(r for r in rows if r["k"] == 1 and r["sizes"] == 2)      # single-size pass@1 fallback

    print("\nANCHOR-RELATIVE COST (multiples of the one eval run proven to fit free tier):")
    print(f"  full powered headline  (k=16, 3 sizes): {powered['units_of_proven_run']:>5.0f}x  "
          f"= {fmt_h(powered['linear_T4_min'])} linear / {fmt_h(powered['batched_T4_min'])} batched")
    print(f"  lean powered headline  (k=8,  2 sizes): {powered_k8['units_of_proven_run']:>5.0f}x  "
          f"= {fmt_h(powered_k8['linear_T4_min'])} / {fmt_h(powered_k8['batched_T4_min'])}")
    print(f"  cheap powered (k=4,    2 sizes):        {cheap['units_of_proven_run']:>5.0f}x  "
          f"= {fmt_h(cheap['linear_T4_min'])} / {fmt_h(cheap['batched_T4_min'])}")
    print(f"  single-size pass@1 fallback (k=1, 2 sz):{single['units_of_proven_run']:>5.0f}x  "
          f"= {fmt_h(single['linear_T4_min'])} / {fmt_h(single['batched_T4_min'])}")

    verdict = (
        f"The statistically-recommended headline design is COMPUTE-EXPENSIVE relative to the "
        f"only eval run the project has proven affordable. At the within-deep effective n={n} "
        f"(2 policies), the full powered interaction (k=16, 3 sizes) = "
        f"{powered['units_of_proven_run']:.0f}x the proven-affordable e-0006 run "
        f"({fmt_h(powered['linear_T4_min'])} T4 linear, {fmt_h(powered['batched_T4_min'])} gen-batched), "
        f"dominated by the irreducible n*k Lean verifications. The interior-k lever that e-0047 needs "
        f"to make the interaction resolvable is the SAME lever that drives this cost. Affordable-side "
        f"options: the k=4/2-size powered design = {cheap['units_of_proven_run']:.0f}x "
        f"({fmt_h(cheap['linear_T4_min'])}), and the single-size pass@1 gap (q-0007 only, NOT the "
        f"interaction) = {single['units_of_proven_run']:.0f}x ({fmt_h(single['linear_T4_min'])}). "
        f"All figures are PRE-SFT lower bounds (t1 from the degenerate model; SFT'd generation+"
        f"verification is slower) and EXCLUDE QLoRA training (e-0007). Decision: stage the eval -- "
        f"run the single-size pass@1 gap first ({single['units_of_proven_run']:.0f}x, resolves "
        f"+0.11-0.16), and only escalate to the multi-size interior-k interaction once a single-size "
        f"signal justifies the {powered_k8['units_of_proven_run']:.0f}-{powered['units_of_proven_run']:.0f}x spend."
    )
    print("\n" + "=" * 78)
    print("VERDICT:", verdict)
    print("=" * 78)

    out = dict(
        what="Eval compute-budget gate: prices the e-0047 statistically-recommended headline "
             "design (within-deep n, interior-k pass@k, multi-size DiD) as a multiple of the one "
             "eval run e-0006/a-0005 proved fits the free tier (50 samples / 56 T4-min). EVAL only; "
             "training (e-0007) excluded; PRE-SFT lower bounds.",
        anchor=dict(problems=ANCHOR_PROBLEMS, minutes=ANCHOR_MINUTES, k=ANCHOR_K,
                    samples=ANCHOR_SAMPLES, t1_min_per_sample=round(T1_MIN_PER_SAMPLE, 4)),
        route=dict(effective_n_ge1=n_ge1, effective_n_ge2=n_ge2, policies=POLICIES,
                   best_k_per_sf=best_k, gen_share=GEN_SHARE),
        grid=rows,
        verdict=verdict,
    )
    Path(args.out).write_text(json.dumps(out, indent=2))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
