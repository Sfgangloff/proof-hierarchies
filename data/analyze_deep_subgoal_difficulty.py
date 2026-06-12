"""CPU-only test of the SOLVER-SIDE half of q-0009's 'fewer LLM calls' premise.

The chain e-0012..e-0016 established, for the data/deep wide-frontier corpus:
  - supply: 633 decls (50.2%) expose a >=2-wide top-level named frontier;
  - emission economics: naming a frontier costs ~20 tok median vs ~1,768 tok
    to emit a full rough proof (e-0016) -- an ~88x up-front reduction.

But e-0016 explicitly flagged the OTHER half as untested: "the per-decl
emission/solver-difficulty trade-off is a data-level proxy, not measured
pass@k." All five prior experiments measured how cheap it is to EMIT the
frontier; NONE asked whether the frontier actually makes the SOLVER's job
easier -- i.e. whether each subgoal is a SMALLER problem than the parent
theorem. A planner that splits a hard goal into subgoals each as hard as the
original buys nothing on the solver side, no matter how cheap the split is.

This script tests that, CPU-only, over the same wide-frontier targets:
  for each decl, compare the PARENT conclusion size against the TOP-LEVEL
  frontier subgoal sizes (chars + token proxy, the same crude difficulty
  proxy the whole chain uses). Key statistics:
    - ratio_max  = largest frontier subgoal / parent conclusion
                   (<1  => every subgoal is individually smaller than the parent)
    - ratio_sum  = sum of frontier subgoals / parent conclusion
                   (total subproblem mass vs the whole)
    - fraction of decls whose every subgoal is smaller than the parent.

The parent CONCLUSION is recovered by scanning the (left-truncated) statement
from the RIGHT for the last top-level ':' (depth 0 w.r.t. brackets), so left
truncation of the binder prefix does not corrupt it. Bare-proposition
statements with no top-level ':' are taken whole.

CAVEAT (honest): chars/tokens are a SIZE proxy for difficulty, not a search-
space measure; a short subgoal can still be hard. This bounds the premise at
the data level only, exactly as e-0010/e-0016 did -- not a pass@k claim.
"""
import json
import glob
import statistics as st

DEEP = "data/deep/*.json"
OUT = "data/corpus_v3/deep_subgoal_difficulty.json"

OPEN = "({[⟨"   # ( { [ ⟨
CLOSE = ")}]⟩"   # ) } ] ⟩


def named(nd):
    return nd.get("name", "_") != "_" and (nd.get("type") or "").strip() != ""


def top_frontier_types(nodes):
    return [(nd.get("type") or "").strip() for nd in nodes if named(nd)]


def conclusion(stmt):
    """Last top-level ':' splits binders from the conclusion. Scan from the
    right so left-truncation of the binder prefix is harmless. Depth counts
    closers (+1) and openers (-1) from the right; a ':' at depth 0 is top
    level. Returns the conclusion substring (whole string if none found)."""
    depth = 0
    s = stmt
    for i in range(len(s) - 1, -1, -1):
        ch = s[i]
        if ch in CLOSE:
            depth += 1
        elif ch in OPEN:
            depth -= 1
        elif ch == ":" and depth == 0:
            # ':=' or '::' are not statement separators; the elaborated
            # pretty-printed type never contains ':=', and '::' is inside a
            # term so it sits at depth>0 here only if bracketed -- accept ':'.
            return s[i + 1:].strip()
    return s.strip()


def quantiles(vals):
    s = sorted(vals)
    if not s:
        return {}

    def q(p):
        return round(s[min(len(s) - 1, int(p * len(s)))], 3)
    return {
        "min": round(s[0], 3), "p10": q(0.10), "p50": round(st.median(s), 3),
        "p90": q(0.90), "max": round(s[-1], 3), "mean": round(st.mean(s), 3),
    }


def main():
    n_decls = 0
    parent_concl_chars = []
    max_sub_chars = []
    ratio_max = []
    ratio_sum = []
    n_all_smaller = 0          # every subgoal < parent conclusion
    n_any_ge_parent = 0        # some subgoal >= parent conclusion
    n_wide = 0
    examples_hard = []         # decls where max subgoal ~ parent (ratio>=0.8)

    for f in glob.glob(DEEP):
        for e in json.load(open(f)):
            n_decls += 1
            ftypes = top_frontier_types(e.get("have_tree") or [])
            if len(ftypes) < 2:
                continue
            n_wide += 1
            concl = conclusion(e.get("statement") or "")
            pc = max(1, len(concl))            # guard div-by-zero
            subs = [len(t) for t in ftypes]
            mx = max(subs)
            parent_concl_chars.append(len(concl))
            max_sub_chars.append(mx)
            rmax = mx / pc
            rsum = sum(subs) / pc
            ratio_max.append(rmax)
            ratio_sum.append(rsum)
            if mx < len(concl):
                n_all_smaller += 1
            else:
                n_any_ge_parent += 1
            if rmax >= 0.8 and len(examples_hard) < 6:
                examples_hard.append({
                    "name": e["name"], "ratio_max": round(rmax, 2),
                    "parent_concl_chars": len(concl), "max_sub_chars": mx,
                })

    tok = lambda xs: [x / 4 for x in xs]   # noqa: E731  (4 chars/token, chain convention)

    report = {
        "source": "data/deep wide-frontier targets — q-0009 solver-side premise",
        "premise_tested": ("does the named frontier split the parent into "
                           "SMALLER (proxy: easier) subgoals? e-0016 measured "
                           "emission cost only; this measures the solver side."),
        "n_decls_total": n_decls,
        "n_wide_targets(top_frontier>=2)": n_wide,
        "PARENT_CONCLUSION_chars": quantiles(parent_concl_chars),
        "PARENT_CONCLUSION_tokens_est": quantiles(tok(parent_concl_chars)),
        "LARGEST_SUBGOAL_chars": quantiles(max_sub_chars),
        "RATIO_max_subgoal_over_parent": quantiles(ratio_max),
        "RATIO_sum_subgoals_over_parent": quantiles(ratio_sum),
        "decls_every_subgoal_smaller_than_parent": {
            "n": n_all_smaller,
            "pct": round(100 * n_all_smaller / n_wide, 1),
        },
        "decls_some_subgoal_ge_parent": {
            "n": n_any_ge_parent,
            "pct": round(100 * n_any_ge_parent / n_wide, 1),
        },
        "examples_subgoal_as_hard_as_parent(ratio_max>=0.8)": examples_hard,
        "CAVEAT": ("chars/tokens are a SIZE proxy for difficulty, not search "
                   "space; bounds the premise at the data level only, like "
                   "e-0010/e-0016 — not a pass@k measurement."),
    }
    json.dump(report, open(OUT, "w"), indent=2)
    print(json.dumps(report, indent=2))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
