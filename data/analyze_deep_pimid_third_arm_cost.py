"""THIRD-ARM (pi_mid) COST gate for q-0005 -- prices the one unmet NON-format
gate on the reopened 3-level rough/mid/fine U-shape.

q-0005's reopening chain (a-0052/a-0053/a-0055 = e-0054/e-0055/e-0057) and the
new on-disk distinct-signal gate (e-0064/a-0062) cleared the 3-level contrast on
SUPPLY, EVAL POWER, SUBSTANTIVE construct depth, and DISTINCT named content.
a-0053/a-0054/a-0055 each named the SAME two remaining gates on actually adding a
3rd arm:
  (1) the off-disk term-vs-tactic FORMAT confound (e-0036/e-0037) -- genuinely
      Modal-blocked (e-0036: 0/633 residual bodies on disk), out of scope here;
  (2) "the ~1.5x compute of a 3rd adapter+eval arm that the 2-arm Stage-0.5 cost
      chain (e-0048 eval / e-0052 training) NEVER PRICED."

This gate prices (2): the INCREMENTAL eval+training compute of going from the
2-policy (rough,fine) design to the 3-policy (rough,mid,fine) design, in the same
proven-affordable units as e-0048, and reads it against e-0048's staged-eval
decision and the new structural warrant.

COST MODEL (e-0048, reused exactly). The eval issues, per (problem, size, policy),
k generations + k Lean verifications: total_samples = n * k * sizes * policies, and
cost_units = total_samples / 50 (the e-0006/a-0005 proven-affordable run). Adding
pi_mid is a THIRD policy, so for any fixed (n, k, sizes) the eval cost scales 3/2.
BUT the 3-level U-shape test runs on a SMALLER n: only the depth>=2 carriers admit
a pi_mid, so the eval n drops from the binary route's ~106-115 to e-0057's ~63
verified pi_mid carriers (the intersection where all three levels are distinct).
We price BOTH framings:
  - APPLES-TO-APPLES: same n, 3 policies vs 2 -> exactly 1.5x eval (the a-0054 quote);
  - U-SHAPE-AS-RUN: the 3-policy design on n_umid=63 vs the binary 2-policy on n=106
    -> the real marginal cost of ANSWERING the U-shape, which is LESS than 1.5x
    because the smaller carrier set partly offsets the extra arm.

TRAINING. QLoRA trains one adapter per (policy, size) (e-0007). The 3rd policy adds
n_sizes adapters: training scales 3/2 in adapter count too. We report the adapter
delta; the per-adapter wall is not on disk (e-0052 priced it only relatively), so
training is given as the 1.5x multiplier on the 2-arm training budget.

OUTPUT. For the e-0048 design grid (k x sizes), the 2-policy vs 3-policy eval cost
in proven-run units and the marginal delta; the U-shape-as-run cost at n_umid; and
a go/no-go that COMPOSES this cost with the now-cleared structural gates and the
staged-eval logic (the 3rd arm only matters AFTER a 2-arm single-size signal, so
its cost lands in stage 2, gated, not paid up front).

CAVEATS. PRE-SFT lower bounds (t1 from the degenerate model, e-0048); training wall
not absolutely priced; the FORMAT half of the 3rd-arm warrant is still Modal-blocked
(e-0036/e-0037), so this gate prices the arm's COST, not its construct-validity --
a GO here is "the 3rd arm is affordable AND structurally warranted on disk", still
conditional on the paid format extract. Pure stdlib; no Lean, no Modal.

  python3 -m data.analyze_deep_pimid_third_arm_cost [--out path.json]
"""

from __future__ import annotations
import argparse, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUDGET_JSON = HERE / "corpus_v3" / "deep_eval_compute_budget.json"
UMID_JSON = HERE / "corpus_v3" / "deep_umid_substantive_depth.json"

ANCHOR_SAMPLES = 50          # e-0006/a-0005 proven-affordable unit
T1 = 56.0 / 50.0             # T4-min per problem-sample (e-0048)
GEN_SHARE = 0.5

K_GRID = [1, 4, 8, 16]
SIZE_GRID = [2, 3]


def units(n, k, sizes, policies):
    return (n * k * sizes * policies) / ANCHOR_SAMPLES


def linear_min(n, k, sizes, policies):
    return T1 * n * k * sizes * policies


def batched_min(n, k, sizes, policies, g=GEN_SHARE):
    return T1 * (g + (1 - g) * k) * n * sizes * policies


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "corpus_v3" / "deep_pimid_third_arm_cost.json"))
    args = ap.parse_args()

    # binary route n (e-0046/e-0048) and pi_mid carrier n (e-0057, substantive)
    n_binary = 106
    n_umid = 63
    if BUDGET_JSON.exists():
        b = json.loads(BUDGET_JSON.read_text())
        n_binary = b["route"].get("effective_n_ge2", n_binary)
    if UMID_JSON.exists():
        try:
            u = json.loads(UMID_JSON.read_text())
            # pull the SUBSTANTIVE pi_mid (depth>=2) eval-verified count from e-0057
            cell = u.get("contrasts", {}).get("umid_depth_ge2_SUBSTANTIVE")
            if cell and cell.get("eval_verified"):
                n_umid = int(round(cell["eval_verified"]))
        except Exception:
            pass

    grid = []
    for sizes in SIZE_GRID:
        for k in K_GRID:
            two = units(n_binary, k, sizes, 2)
            three_same_n = units(n_binary, k, sizes, 3)
            three_umid = units(n_umid, k, sizes, 3)
            grid.append({
                "k": k, "sizes": sizes,
                "two_policy_n%d" % n_binary: round(two, 1),
                "three_policy_same_n%d" % n_binary: round(three_same_n, 1),
                "marginal_3rd_arm_same_n": round(three_same_n - two, 1),
                "marginal_ratio_same_n": round(three_same_n / two, 3),
                "ushape_as_run_3policy_n%d" % n_umid: round(three_umid, 1),
                "ushape_vs_binary_ratio": round(three_umid / two, 3),
            })

    # anchor designs
    def cell(k, sizes):
        return next(r for r in grid if r["k"] == k and r["sizes"] == sizes)

    single = cell(1, 2)         # stage-1 single-size pass@1 screen (e-0048 fallback)
    cheap = cell(4, 2)          # cheap powered (e-0048)
    lean = cell(8, 2)
    full = cell(16, 3)          # full headline

    k2 = "two_policy_n%d" % n_binary
    k3s = "three_policy_same_n%d" % n_binary
    k3u = "ushape_as_run_3policy_n%d" % n_umid

    report = {
        "what": (
            "Third-arm (pi_mid) cost gate for q-0005: prices the incremental "
            "eval+training compute of the 3-policy rough/mid/fine U-shape design vs "
            "the 2-policy binary design, in e-0048 proven-affordable units, and "
            "reads it against the staged-eval decision and the now-cleared structural "
            "gates (e-0054/e-0055/e-0057/e-0064)."
        ),
        "n_binary_route": n_binary,
        "n_umid_carriers": n_umid,
        "n_umid_note": "e-0057 substantive pi_mid eval-verified carriers (depth>=2 "
                       "intersection where all three levels are distinct).",
        "cost_grid_units_of_proven_run": grid,
        "anchor_designs": {
            "stage1_single_size_pass1": {
                "two_policy": single[k2], "three_policy_same_n": single[k3s],
                "marginal_3rd_arm": round(single[k3s] - single[k2], 1),
                "ushape_as_run": single[k3u],
            },
            "cheap_powered_k4_2size": {
                "two_policy": cheap[k2], "three_policy_same_n": cheap[k3s],
                "marginal_3rd_arm": round(cheap[k3s] - cheap[k2], 1),
                "ushape_as_run": cheap[k3u],
            },
            "lean_powered_k8_2size": {
                "two_policy": lean[k2], "three_policy_same_n": lean[k3s],
                "marginal_3rd_arm": round(lean[k3s] - lean[k2], 1),
                "ushape_as_run": lean[k3u],
            },
            "full_headline_k16_3size": {
                "two_policy": full[k2], "three_policy_same_n": full[k3s],
                "marginal_3rd_arm": round(full[k3s] - full[k2], 1),
                "ushape_as_run": full[k3u],
            },
        },
        "training": {
            "adapters_2policy": "2 policies x n_sizes",
            "adapters_3policy": "3 policies x n_sizes",
            "adapter_count_ratio": 1.5,
            "note": "QLoRA trains one adapter per (policy,size) (e-0007); the 3rd "
                    "policy adds n_sizes adapters -> 1.5x training; per-adapter wall "
                    "not absolutely priced (e-0052 relative only).",
        },
        "caveats": (
            "PRE-SFT lower bounds (e-0048 t1). Training wall not absolutely priced "
            "(1.5x adapter-count multiplier only). The FORMAT half of the 3rd-arm "
            "warrant is still Modal-blocked (e-0036: 0/633 residual bodies on disk; "
            "e-0037 paid extract), so a GO here = 'affordable AND structurally "
            "warranted on disk', still conditional on the paid format extract. "
            "n_umid is the e-0057 per-area COUNT projection, not a real round-trip."
        ),
    }

    report["verdict"] = (
        f"The 2-arm Stage-0.5 cost chain (e-0048/e-0052) never priced the 3rd "
        f"(pi_mid) arm; this gate does. APPLES-TO-APPLES at fixed n, the 3rd policy "
        f"is exactly +50% eval compute (a-0054's quote confirmed): e.g. the full "
        f"headline (k=16, 3 sizes) goes {full[k2]:.0f}x -> {full[k3s]:.0f}x of the "
        f"proven-affordable run (+{full[k3s]-full[k2]:.0f}x), and the cheap powered "
        f"design (k=4, 2 sizes) {cheap[k2]:.0f}x -> {cheap[k3s]:.0f}x "
        f"(+{cheap[k3s]-cheap[k2]:.0f}x); training adds n_sizes adapters (1.5x). BUT "
        f"the U-shape actually RUNS on the smaller pi_mid carrier set (n_umid="
        f"{n_umid}, e-0057), so the marginal cost of ANSWERING the U-shape is LESS "
        f"than 1.5x: the full 3-policy U-shape at n_umid is {full[k3u]:.0f}x vs the "
        f"binary {full[k2]:.0f}x (ratio {full['ushape_vs_binary_ratio']:.2f}), and "
        f"the stage-1 single-size pass@1 3-level screen is only {single[k3u]:.0f}x. "
        f"COMPOSED with e-0064 (pi_mid carries distinct on-disk content on 72-83% of "
        f"carriers) and the staged-eval decision (e-0048): the 3rd arm's cost lands "
        f"in STAGE 2, gated behind a cheap 2-arm single-size signal, NOT paid up "
        f"front; and because the U-shape carrier set is smaller, the stage-2 3-level "
        f"escalation costs ~{full['ushape_vs_binary_ratio']:.2f}x the binary stage-2, "
        f"not 1.5x. VERDICT for q-0005: the 3-level U-shape is now cleared on supply, "
        f"power, substantive depth, distinct content (e-0064) AND cost (this gate, "
        f"affordable as a gated stage-2 add-on); the SOLE remaining open gate is the "
        f"off-disk term-vs-tactic FORMAT confound (e-0036/e-0037), which needs the "
        f"paid extract -- so binary-vs-3-level is decidable the moment that extract "
        f"runs, with every CPU-side prerequisite now met."
    )

    Path(args.out).write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
