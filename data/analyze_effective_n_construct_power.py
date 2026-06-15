"""EFFECTIVE-n gate: fuse the construct-validity bottleneck (a-0026/e-0026) with
the eval power/MDE machinery (a-0038/e-0040) for q-0007/q-0001.

Two separate Stage-0.5 threads have never been multiplied together:

  (1) CONSTRUCT VALIDITY (e-0026/a-0026). On corpus_v3 the rough/fine axis is
      rough = elaborated proof TERM, fine = original tactic SOURCE, so it
      conflates serialization FORMAT (term vs tactic) with decomposition
      GRANULARITY (haves inlined vs named). The two only SEPARATE on the
      granularity-bearing pairs (>=1 named have-node). Only ~6.9% of the 607
      pairs carry that signal.

  (2) POWER / MDE (e-0040..e-0044). The paired rough-vs-fine eval is McNemar's
      exact test on n held-out problems; the quartet computes the minimum
      detectable gap at n in {50, 63, 116, 200}, all assuming every held-out
      problem can express the effect.

The unasked dual question: how many problems IN THE ACTUAL HELD-OUT TEST SPLIT
can express a *granularity* (not format) effect? A format-only pair (zero named
haves) differs by serialization alone, so rough-SFT and fine-SFT have nothing to
disagree about on the granularity axis -- it is CONCORDANT w.r.t. granularity and
contributes nothing to McNemar's discordant count for a granularity effect. So
the EFFECTIVE sample size for the headline granularity claim is not n=63 but the
number of granularity-bearing pairs in the test split.

This script joins the SAME three on-disk artifacts the power gates and the
construct gate each used -- the SFT split index, the verified pairs, the have-tree
records -- counts granularity-bearing pairs PER SPLIT, and feeds the effective
test-split n back through e-0040's own McNemar/Gaussian-copula power machinery
(imported unchanged) to get the effective MDE.

A combinatorial floor falls out of McNemar's exact two-sided test that no Monte
Carlo is needed to see: with at most D discordant pairs, the smallest achievable
two-sided p-value is 2*(0.5)^D (all D flips in one direction). For D=5 that is
0.0625 > 0.05 -- so a test split with <=5 granularity-bearing problems CANNOT
reject at alpha=0.05 under ANY effect size: power is exactly 0, not merely low.

Pure stdlib; no Lean, no Modal. Reuses data.analyze_eval_power_mde unchanged.

  python3 -m data.analyze_effective_n_construct_power [--out path.json]
"""

from __future__ import annotations
import argparse, glob, json, math
from collections import Counter
from pathlib import Path

# reuse the e-0040 paired-McNemar Gaussian-copula machinery UNCHANGED
from data.analyze_eval_power_mde import simulate_power, ALPHA, TARGET_POWER, M

ROOT = Path(__file__).resolve().parents[1]
PAIRS = ROOT / "data/corpus_v3/pairs.jsonl"
SPLIT = ROOT / "data/corpus_v3/sft/split_index.json"
HAVE_TREES_DIR = ROOT / "data/corpus_v2/corpus"

# grids mirror e-0040 so the effective-n MDE is comparable to the nominal one
P_LO_GRID = [0.05, 0.10, 0.20]
DELTA_GRID = [round(0.01 * i, 2) for i in range(1, 51)]  # +0.01 .. +0.50
RHO = 0.5  # e-0040's central assumption
SEED = 0


def named_have_count(nodes: list[dict]) -> int:
    """count have-nodes carrying a real user name + a type (mirrors e-0012/e-0026)."""
    n = 0
    for hn in nodes:
        name = (hn.get("userName") or hn.get("name") or "").strip()
        ptype = (hn.get("ppType") or hn.get("type") or "").strip()
        if name and name != "_" and ptype:
            n += 1
    return n


def load_have_index() -> dict[str, list[dict]]:
    idx: dict[str, list[dict]] = {}
    for path in sorted(glob.glob(str(HAVE_TREES_DIR / "*.jsonl"))):
        for line in open(path):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "declName" in d:
                idx[d["declName"]] = d.get("have_nodes", []) or []
    return idx


def mcnemar_min_two_sided_p(d: int) -> float:
    """Smallest achievable two-sided McNemar exact p with d discordant pairs
    (all d in one direction): 2*(0.5)^d, capped at 1."""
    if d <= 0:
        return 1.0
    return min(1.0, 2.0 * (0.5 ** d))


def min_discordant_for_significance(alpha: float) -> int:
    """smallest D such that 2*(0.5)^D < alpha (most extreme split rejects)."""
    d = 1
    while mcnemar_min_two_sided_p(d) >= alpha:
        d += 1
        if d > 100:
            break
    return d


def mde_at(n: int) -> dict:
    """smallest absolute gap reaching TARGET_POWER at this n, per p_lo (e-0040)."""
    import random
    rng = random.Random(SEED)
    out = {}
    for p_lo in P_LO_GRID:
        mde = None
        for delta in DELTA_GRID:
            pw = simulate_power(n, p_lo, delta, RHO, rng)
            if pw is None:
                break
            if pw >= TARGET_POWER:
                mde = delta
                break
        out[p_lo] = mde
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data/corpus_v3/effective_n_construct_power.json"))
    args = ap.parse_args()

    split = json.load(open(SPLIT))
    have_idx = load_have_index()
    pairs = [json.loads(l) for l in open(PAIRS) if l.strip()]

    tot, gb, nt = Counter(), Counter(), Counter()
    for d in pairs:
        nm = d.get("declName")
        if not nm:
            continue
        s = split.get(nm, "UNSPLIT")
        tot[s] += 1
        nh = named_have_count(have_idx.get(nm, []))
        if nh >= 1:
            gb[s] += 1
        if nh >= 2:
            nt[s] += 1

    splits = {}
    for s in ["train", "dev", "test"]:
        splits[s] = {
            "n_pairs": tot[s],
            "granularity_bearing_ge1": gb[s],
            "granularity_bearing_frac": round(gb[s] / tot[s], 4) if tot[s] else None,
            "nontrivial_frontier_ge2": nt[s],
        }

    n_test_nominal = tot["test"]
    n_eff_ge1 = gb["test"]      # effective n for ANY granularity signal
    n_eff_ge2 = nt["test"]      # effective n for a real >=2 frontier

    d_needed = min_discordant_for_significance(ALPHA)

    # ---- the combinatorial floor (exact, no simulation) ----
    floor = {
        "min_discordant_pairs_for_alpha_0.05": d_needed,
        "min_two_sided_p_at_n_eff_ge1": round(mcnemar_min_two_sided_p(n_eff_ge1), 4),
        "min_two_sided_p_at_n_eff_ge2": round(mcnemar_min_two_sided_p(n_eff_ge2), 4),
        # power is EXACTLY 0 whenever the discordant ceiling (= n_eff) < d_needed
        "test_ge1_can_ever_reject": n_eff_ge1 >= d_needed,
        "test_ge2_can_ever_reject": n_eff_ge2 >= d_needed,
    }

    # ---- effective-n MDE via e-0040 machinery (will be unreachable when n_eff tiny) ----
    mde_nominal = mde_at(n_test_nominal)        # the FORMAT axis (e-0040 n=63 column)
    mde_eff_ge1 = mde_at(n_eff_ge1) if n_eff_ge1 > 0 else {p: None for p in P_LO_GRID}

    def fmt_mde(m):
        return {str(p): (v if v is not None else ">0.50/unreachable") for p, v in m.items()}

    summary = {
        "what": ("Effective-n gate: granularity-bearing pairs PER SPLIT x e-0040 "
                 "McNemar power. Only granularity-bearing test pairs can express a "
                 "granularity (not format) effect, so they -- not n=63 -- set the "
                 "effective sample size for the headline q-0007/q-0001 claim."),
        "splits": splits,
        "test_split": {
            "n_nominal": n_test_nominal,
            "n_effective_granularity_ge1": n_eff_ge1,
            "n_effective_granularity_ge2": n_eff_ge2,
        },
        "mcnemar_combinatorial_floor": floor,
        "mde": {
            "nominal_n_test_FORMAT_axis": fmt_mde(mde_nominal),
            "effective_n_GRANULARITY_axis_ge1": fmt_mde(mde_eff_ge1),
            "note": ("nominal column = the term-vs-tactic FORMAT effect e-0040 "
                     "priced at n=63; effective column = the GRANULARITY effect, "
                     "the project's actual headline, at n_eff."),
        },
        "rho": RHO, "alpha": ALPHA, "target_power": TARGET_POWER, "M": M, "seed": SEED,
        "interpretation": (
            f"The held-out test split has {n_test_nominal} pairs but only "
            f"{n_eff_ge1} are granularity-bearing ({n_eff_ge2} with a >=2 frontier). "
            f"McNemar's exact two-sided test needs >={d_needed} same-direction "
            f"discordant pairs to reach alpha={ALPHA}; with at most {n_eff_ge1} "
            f"granularity-bearing problems the discordant ceiling is {n_eff_ge1} < "
            f"{d_needed}, so the test CANNOT reject under ANY effect size -- power is "
            f"exactly 0, not merely low. The n=63 MDE the power quartet reported "
            f"prices the term-vs-tactic FORMAT effect, not the granularity effect "
            f"the paper claims. To make the granularity effect even POSSIBLE to "
            f"resolve, the eval must draw its held-out set from granularity-bearing "
            f"decls (the data/deep route) -- corpus_v3's split cannot do it."
        ),
    }

    print(json.dumps(summary, indent=2))
    Path(args.out).write_text(json.dumps(summary, indent=2))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
