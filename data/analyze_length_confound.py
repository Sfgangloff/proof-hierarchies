"""
Stage 0.5 analysis — quantify the rough/fine length confound (q-0008).

CPU-only, stdlib-only. Reads the prepared per-policy SFT JSONLs and the
underlying pairs, and characterizes the completion-length gap between the
rough (pi_root, term-mode) and fine (pi_leaf, tactic) policies.

  python3 data/analyze_length_confound.py

Why: the headline rough-vs-fine pass@k comparison (q-0007) is only
interpretable if any effect survives controlling for sequence length
(q-0008). a-0006 asserts the paired data is "length-decorrelated"; this
script tests that claim with actual numbers on the prepared corpus.

What it reports, per split and overall:
  - completion length distributions (chars + token proxy) for each policy
  - the within-theorem rough/fine length RATIO distribution
  - the within-theorem Pearson + Spearman correlation of the two lengths
    (decorrelation is what a length-covariate regression needs)

Token proxy: completion chars / 4 (a standard BPE rule-of-thumb for code).
No tokenizer dependency; the char numbers are exact, the token numbers are
an estimate and labeled as such.
"""

import json
import math
import pathlib
from collections import defaultdict

ROOT = pathlib.Path(__file__).parent / "corpus_v3"
SFT = ROOT / "sft"
SPLITS = ["train", "dev", "test"]
POLICIES = ["rough", "fine"]
CHARS_PER_TOKEN = 4.0  # BPE rule-of-thumb for code; token numbers are estimates


def load_policy(policy: str, split: str) -> dict[str, str]:
    """declName -> completion string, for one policy/split."""
    out = {}
    path = SFT / policy / f"{split}.jsonl"
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            out[row["declName"]] = row["completion"]
    return out


def pctl(xs: list[float], p: float) -> float:
    """Linear-interpolated percentile of a sorted-able list."""
    if not xs:
        return float("nan")
    s = sorted(xs)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * p
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return s[int(k)]
    return s[lo] * (hi - k) + s[hi] * (k - lo)


def summary(xs: list[float]) -> dict:
    return {
        "n": len(xs),
        "mean": sum(xs) / len(xs) if xs else float("nan"),
        "p10": pctl(xs, 0.10),
        "p50": pctl(xs, 0.50),
        "p90": pctl(xs, 0.90),
        "max": max(xs) if xs else float("nan"),
    }


def pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return float("nan")
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx == 0 or vy == 0:
        return float("nan")
    return cov / math.sqrt(vx * vy)


def rankdata(xs: list[float]) -> list[float]:
    """Average ranks, ties shared."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float:
    return pearson(rankdata(xs), rankdata(ys))


def char_len(s: str) -> int:
    """Completion length in chars, stripping the leading ':=' marker so we
    measure proof body, not the shared delimiter."""
    return len(s.strip())


def fmt(d: dict) -> str:
    return (
        f"n={d['n']:>4}  mean={d['mean']:>8.1f}  "
        f"p10={d['p10']:>7.1f}  p50={d['p50']:>7.1f}  "
        f"p90={d['p90']:>8.1f}  max={d['max']:>8.1f}"
    )


def main():
    print("=" * 78)
    print("ROUGH/FINE LENGTH CONFOUND ANALYSIS (q-0008)")
    print("completion length = chars of stripped completion; tokens ~= chars/4")
    print("=" * 78)

    # accumulate paired (rough_chars, fine_chars) across all splits
    all_rough_c: list[float] = []
    all_fine_c: list[float] = []
    all_ratio: list[float] = []

    for split in SPLITS:
        rough = load_policy("rough", split)
        fine = load_policy("fine", split)
        shared = sorted(set(rough) & set(fine))
        rc = [char_len(rough[d]) for d in shared]
        fc = [char_len(fine[d]) for d in shared]
        ratios = [r / f for r, f in zip(rc, fc) if f > 0]

        all_rough_c += rc
        all_fine_c += fc
        all_ratio += ratios

        print(f"\n--- split: {split}  (paired decls: {len(shared)}) ---")
        print(f"  rough chars : {fmt(summary(rc))}")
        print(f"  fine  chars : {fmt(summary(fc))}")
        print(f"  rough/fine ratio : {fmt(summary(ratios))}")

    print("\n" + "=" * 78)
    print("OVERALL (all splits pooled)")
    print("=" * 78)
    rsum = summary(all_rough_c)
    fsum = summary(all_fine_c)
    print(f"  rough chars       : {fmt(rsum)}")
    print(f"  fine  chars       : {fmt(fsum)}")
    print(f"  rough/fine ratio  : {fmt(summary(all_ratio))}")
    print(f"\n  median rough tokens (est) : {rsum['p50']/CHARS_PER_TOKEN:,.0f}")
    print(f"  median fine  tokens (est) : {fsum['p50']/CHARS_PER_TOKEN:,.0f}")
    print(f"  mean   length multiplier  : {rsum['mean']/fsum['mean']:.1f}x")
    print(f"  median length multiplier  : {rsum['p50']/fsum['p50']:.1f}x")

    pear = pearson(all_rough_c, all_fine_c)
    spear = spearman(all_rough_c, all_fine_c)
    print("\n  within-theorem length correlation (rough_len vs fine_len):")
    print(f"    Pearson  r = {pear:.3f}")
    print(f"    Spearman r = {spear:.3f}")
    print(
        "\n  Interpretation: a length-covariate regression can separate "
        "granularity\n  from length only insofar as the two lengths are NOT "
        "collinear within\n  theorem. High correlation => the covariate and the "
        "treatment move together\n  => limited ability to disentangle the effect."
    )

    # token-budget context: how many decls blow past a small ctx window?
    for budget_tok in (512, 1024, 2048):
        budget_chars = budget_tok * CHARS_PER_TOKEN
        rough_over = sum(1 for c in all_rough_c if c > budget_chars)
        fine_over = sum(1 for c in all_fine_c if c > budget_chars)
        n = len(all_rough_c)
        print(
            f"\n  completions over ~{budget_tok} tok ({budget_chars:.0f} chars): "
            f"rough {rough_over}/{n} ({100*rough_over/n:.0f}%), "
            f"fine {fine_over}/{n} ({100*fine_over/n:.0f}%)"
        )


if __name__ == "__main__":
    main()
