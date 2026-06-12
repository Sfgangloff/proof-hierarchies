"""
Stage 0.5 analysis — how much of the rough/fine length gap is removable
pretty-printer scaffolding? (q-0008 follow-up to e-0010)

CPU-only, stdlib-only. e-0010 found rough (pi_root, term-mode) completions
are a median ~144x longer than fine (pi_leaf, tactic) with zero common
support, so a within-theorem length-covariate regression cannot identify
the granularity effect. The graph's stated unblock is "a terser rough
serialization or a length-matched subset before SFT."

This script asks the prerequisite question for the *terser serialization*
route: how much of the rough completion is pure elaboration scaffolding
that a different pretty-printer configuration would strip, and would
stripping it bring rough into length common support with fine?

  python3 data/analyze_rough_terseness.py

The rough completions are fully-explicit pretty-printed proof terms:
  - universe annotations:        @Eq.{u_3 + 1}, @Eq.trans.{1}, .{u_3, u_3, u_3}
  - explicit-application sigils:  @HMul.hMul, @of_eq_true
  - fully-qualified projection chains:
        DivisionMonoid.toDivInvOneMonoid.toInvOneClass.inv
  - pretty-printer indentation / line wrapping.
None of these change the *granularity* (the section cut); they are
serialization verbosity. A `pp.universes false` + `pp.explicit false`
+ short-name + single-line rendering would remove most of them.

We cannot re-run Lean's pretty-printer cheaply, so we estimate the
achievable length two ways, both as TEXT transforms over the real
completions, and report each clearly labelled:

  CONSERVATIVE (lower bound on reduction): strip universe annotations
    `.{...}`, drop the `@` explicit sigil, collapse all runs of
    whitespace (incl. newlines/indentation) to a single space. These are
    purely cosmetic — they never remove a subterm — so the result is a
    sound LOWER bound on how short a terser serialization can get.

  AGGRESSIVE (optimistic, upper bound on reduction): additionally shorten
    every dotted identifier chain to its final component
    (Foo.bar.baz -> baz), simulating short-name pretty-printing. This can
    in principle collapse distinct names, so it OVER-states reduction; it
    is the optimistic end of the range.

The honest answer lives between the two. Crucially, neither transform can
remove the explicit type/instance *arguments* that `pp.explicit false`
would hide (that needs real elaboration), so even the aggressive estimate
is itself a lower bound on what Lean's own terser pp could achieve — i.e.
if even the aggressive estimate stays far above fine, the gap is
structural; if it reaches common support, a terser serialization is a
viable unblock worth implementing on Modal.
"""

import json
import math
import pathlib
import re

ROOT = pathlib.Path(__file__).parent / "corpus_v3"
SFT = ROOT / "sft"
SPLITS = ["train", "dev", "test"]
CHARS_PER_TOKEN = 4.0  # BPE rule-of-thumb for code; token numbers are estimates

UNIVERSE_RE = re.compile(r"\.\{[^{}]*\}")        # .{u_3 + 1}, .{u_3, u_3, u_3}, .{1}
WS_RE = re.compile(r"\s+")
# dotted identifier chain: at least two components, last component kept.
# allow lean identifier chars incl. unicode greek/subscripts already in the data.
DOTTED_RE = re.compile(r"(?:[^\s().{}@,]+\.)+([^\s().{}@,]+)")


def load_completions(policy: str, split: str) -> dict[str, str]:
    out = {}
    with open(SFT / policy / f"{split}.jsonl") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            # strip the shared ':=' delimiter so we measure the proof body
            body = row["completion"].strip()
            if body.startswith(":="):
                body = body[2:]
            out[row["declName"]] = body.strip()
    return out


def conservative(s: str) -> str:
    s = UNIVERSE_RE.sub("", s)
    s = s.replace("@", "")
    s = WS_RE.sub(" ", s)
    return s.strip()


def aggressive(s: str) -> str:
    s = conservative(s)
    s = DOTTED_RE.sub(lambda m: m.group(1), s)
    return s


def pctl(xs, p):
    if not xs:
        return float("nan")
    s = sorted(xs)
    if len(s) == 1:
        return float(s[0])
    k = (len(s) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return float(s[int(k)])
    return s[lo] * (hi - k) + s[hi] * (k - lo)


def summ(xs):
    return {
        "n": len(xs),
        "mean": sum(xs) / len(xs) if xs else float("nan"),
        "p10": pctl(xs, 0.10),
        "p50": pctl(xs, 0.50),
        "p90": pctl(xs, 0.90),
        "max": max(xs) if xs else float("nan"),
    }


def fmt(d):
    return (f"n={d['n']:>4}  mean={d['mean']:>8.1f}  p10={d['p10']:>8.1f}  "
            f"p50={d['p50']:>8.1f}  p90={d['p90']:>8.1f}  max={d['max']:>8.1f}")


def main():
    # pool all splits; the confound is corpus-wide, splits share the policy.
    rough, fine = {}, {}
    for sp in SPLITS:
        rough.update(load_completions("rough", sp))
        fine.update(load_completions("fine", sp))
    decls = sorted(set(rough) & set(fine))
    print(f"paired decls (rough & fine): {len(decls)}\n")

    raw_len = [len(rough[d]) for d in decls]
    con_len = [len(conservative(rough[d])) for d in decls]
    agg_len = [len(aggressive(rough[d])) for d in decls]
    fine_len = [len(fine[d]) for d in decls]

    print("=== rough completion length (chars) under each serialization ===")
    print(f"  raw (current)     {fmt(summ(raw_len))}")
    print(f"  conservative-pp   {fmt(summ(con_len))}")
    print(f"  aggressive-pp     {fmt(summ(agg_len))}")
    print(f"  fine (tactic)     {fmt(summ(fine_len))}")
    print()

    # per-decl fraction of raw chars removed
    con_keep = [c / r for c, r in zip(con_len, raw_len) if r]
    agg_keep = [a / r for a, r in zip(agg_len, raw_len) if r]
    print("=== fraction of rough chars REMOVED by terser serialization ===")
    print(f"  conservative removes  p10={1-pctl(con_keep,0.9):.2%}  "
          f"p50={1-pctl(con_keep,0.5):.2%}  p90={1-pctl(con_keep,0.1):.2%}")
    print(f"  aggressive   removes  p10={1-pctl(agg_keep,0.9):.2%}  "
          f"p50={1-pctl(agg_keep,0.5):.2%}  p90={1-pctl(agg_keep,0.1):.2%}")
    print()

    # within-theorem rough/fine ratio under each serialization
    def ratios(rlen):
        return [r / f for r, f in zip(rlen, fine_len) if f]
    print("=== within-theorem rough/fine length RATIO ===")
    for name, rlen in [("raw", raw_len), ("conservative", con_len),
                       ("aggressive", agg_len)]:
        rs = ratios(rlen)
        print(f"  {name:>12}  p10={pctl(rs,0.1):>7.1f}x  p50={pctl(rs,0.5):>7.1f}x  "
              f"p90={pctl(rs,0.9):>7.1f}x  (frac with ratio<=2x: "
              f"{sum(1 for x in rs if x<=2)/len(rs):.1%})")
    print()

    # common-support test: does rough drop into the fine length range?
    fine_p90 = pctl(fine_len, 0.90)
    fine_max = max(fine_len)
    print(f"=== common-support test (fine p90={fine_p90:.0f} chars, "
          f"fine max={fine_max:.0f} chars) ===")
    for name, rlen in [("raw", raw_len), ("conservative", con_len),
                       ("aggressive", agg_len)]:
        below_p90 = sum(1 for x in rlen if x <= fine_p90) / len(rlen)
        below_max = sum(1 for x in rlen if x <= fine_max) / len(rlen)
        print(f"  {name:>12}  rough <= fine-p90: {below_p90:5.1%}   "
              f"rough <= fine-max: {below_max:5.1%}")
    print()

    # token-budget framing (the e-0010 512-tok budget)
    budget = 512
    print(f"=== fraction of rough completions over a {budget}-token budget "
          f"(~{int(budget*CHARS_PER_TOKEN)} chars) ===")
    thr = budget * CHARS_PER_TOKEN
    for name, rlen in [("raw", raw_len), ("conservative", con_len),
                       ("aggressive", agg_len)]:
        over = sum(1 for x in rlen if x > thr) / len(rlen)
        print(f"  {name:>12}  over budget: {over:5.1%}")
    fine_over = sum(1 for x in fine_len if x > thr) / len(fine_len)
    print(f"  {'fine':>12}  over budget: {fine_over:5.1%}")


if __name__ == "__main__":
    main()
