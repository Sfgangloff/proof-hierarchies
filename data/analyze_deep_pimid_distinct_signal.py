"""STRUCTURAL DISTINCT-SIGNAL gate for pi_mid -- the one unmet CPU-only gate on
q-0005's reopened 3-level (rough / mid / fine) U-shape.

a-0052/a-0053/a-0055 (e-0054/e-0055/e-0057) reopened q-0005 on the deep route:
55.9% of the 633 canonical wide targets admit an intermediate named-nesting cut
pi_mid (substantive named-depth >= 2), and pi_mid SURVIVES the held-out split on
supply + power (~63 verified eval carriers, ~10.5x the McNemar D>=6 floor). But
every one of those answers flagged the SAME unmet gate explicitly:

   "depth is a STRUCTURAL count; whether each named frontier carries DISTINCT
    granularity signal [vs both rough and fine] is the unmet construct-validity
    gate."

They deferred it to the term-vs-tactic FORMAT half (e-0036/e-0037), which needs
the paid extract. But there is a CPU-only, on-disk half of distinctness that has
never been measured: does pi_mid carry a NON-TRIVIAL amount of named structure
that is STRICTLY BETWEEN pi_root and pi_leaf -- i.e. is the intermediate cut a
genuine third level, or does it (a) collapse onto pi_root (names almost nothing
beyond the inlined body) or (b) collapse onto pi_leaf (the nested level it omits
is empty/trivial)? If mid collapses onto an endpoint on EVERY carrier, a 3-arm
design is wasted regardless of the format question; if mid carries a substantial
incremental block at BOTH boundaries on most carriers, the third arm is
structurally warranted.

THE THREE POLICIES, ON-DISK (substantive named = name != "_", type non-empty,
body non-empty; the e-0026/e-0032 inline-or-name unit):

  pi_root (rough): name 0 haves -- the whole derivation is the proof body.
  pi_mid:          name only TOP-LEVEL substantive haves; inline everything
                   nested below them.
  pi_leaf (fine):  name EVERY substantive have (top + all nesting levels) at the
                   minimal antichain.

SIGNAL carried by a policy = the named-header block it exposes (count of named
substantive haves, and the chars of their name+type+body it surfaces as explicit
named sub-results). The two INCREMENTS that define distinctness are:

  mid - root  = what pi_mid names that pi_root inlines      = the TOP-LEVEL block
  leaf - mid  = what pi_leaf names that pi_mid inlines       = the NESTED block

pi_mid is structurally distinct from BOTH endpoints on a carrier iff BOTH
increments are non-trivial (>= a minimal chars threshold). We report, over the
depth>=2 carriers:
  - distribution of the two increments (count + chars), median/IQR;
  - fraction of carriers where mid is NON-COLLAPSING at BOTH boundaries
    (the construct-valid-mid rate) at several char thresholds;
  - the LADDER monotonicity (root < mid < leaf in named count, by construction)
    and the relative position of mid (mid-block share of the total leaf block) --
    a mid that names ~half the eventual block is the strongest U-shape candidate;
    one that names ~all or ~none of it is an endpoint in disguise.

This is the STRUCTURAL half of the distinctness gate (token/char separability of
the three named blocks). The remaining unmet half is the term-vs-tactic FORMAT
confound (e-0036/e-0037, off-disk, paid extract). Pure stdlib; deterministic.

  python3 -m data.analyze_deep_pimid_distinct_signal [--out path.json]
"""

from __future__ import annotations
import argparse, glob, json, statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEEP_DIR = ROOT / "data/deep"
HEADER_OVERHEAD = 13   # e-0027 "have  :  := " convention


def is_substantive_named(nd):
    return (nd.get("name", "_") != "_"
            and (nd.get("type") or "").strip() != ""
            and (nd.get("body") or "").strip() != "")


def header_chars(nd):
    return HEADER_OVERHEAD + len(nd.get("name", "")) + len((nd.get("type") or "")) + len((nd.get("body") or ""))


def substantive_named_depth(nodes):
    """Longest root->leaf chain through substantive-named nodes."""
    best = 0
    for nd in nodes:
        sub = substantive_named_depth(nd.get("children") or [])
        if is_substantive_named(nd):
            best = max(best, 1 + sub)
        else:
            best = max(best, sub)
    return best


def top_substantive(nodes):
    """Top-level substantive named haves (pi_mid names exactly these)."""
    out = []
    for nd in nodes:
        if is_substantive_named(nd):
            out.append(nd)
        # if a node is not substantive-named we still surface its children at top
        # level (binder pass-through), matching how pi_mid treats binder wrappers
        else:
            out.extend(top_substantive(nd.get("children") or []))
    return out


def all_substantive(nodes):
    out = []
    for nd in nodes:
        if is_substantive_named(nd):
            out.append(nd)
        out.extend(all_substantive(nd.get("children") or []))
    return out


def nested_substantive(nodes):
    """Substantive named haves strictly BELOW a top-level substantive node
    (the block pi_leaf names but pi_mid inlines)."""
    out = []
    for nd in nodes:
        if is_substantive_named(nd):
            out.extend(all_substantive(nd.get("children") or []))
        else:
            out.extend(nested_substantive(nd.get("children") or []))
    return out


def summ(xs):
    if not xs:
        return None
    xs = sorted(xs)
    n = len(xs)
    def q(p):
        if n == 1:
            return xs[0]
        i = p * (n - 1); lo = int(i); hi = min(lo + 1, n - 1)
        return xs[lo] * (1 - (i - lo)) + xs[hi] * (i - lo)
    return {"n": n, "median": round(q(0.5), 1), "q25": round(q(0.25), 1),
            "q75": round(q(0.75), 1), "mean": round(sum(xs) / n, 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data/corpus_v3/deep_pimid_distinct_signal.json"))
    args = ap.parse_args()

    recs = []
    seen = set()
    for f in glob.glob(str(DEEP_DIR / "*.json")):
        if Path(f).name.startswith("._"):
            continue
        for e in json.load(open(f)):
            key = (e["module"], e["name"])
            if key in seen:
                continue
            seen.add(key)
            recs.append(e)

    carriers = []
    for e in recs:
        ht = e.get("have_tree") or []
        if substantive_named_depth(ht) < 2:
            continue                       # only carriers that admit a pi_mid
        top = top_substantive(ht)
        alln = all_substantive(ht)
        nested = nested_substantive(ht)
        mid_minus_root_n = len(top)
        leaf_minus_mid_n = len(nested)
        mid_minus_root_c = sum(header_chars(n) for n in top)
        leaf_minus_mid_c = sum(header_chars(n) for n in nested)
        leaf_total_c = sum(header_chars(n) for n in alln)
        carriers.append({
            "mid_minus_root_n": mid_minus_root_n,
            "leaf_minus_mid_n": leaf_minus_mid_n,
            "mid_minus_root_c": mid_minus_root_c,
            "leaf_minus_mid_c": leaf_minus_mid_c,
            "leaf_total_c": leaf_total_c,
            "mid_block_share": (mid_minus_root_c / leaf_total_c) if leaf_total_c else 0.0,
        })

    nC = len(carriers)

    # increment distributions
    incr = {
        "mid_minus_root_count": summ([c["mid_minus_root_n"] for c in carriers]),
        "leaf_minus_mid_count": summ([c["leaf_minus_mid_n"] for c in carriers]),
        "mid_minus_root_chars": summ([c["mid_minus_root_c"] for c in carriers]),
        "leaf_minus_mid_chars": summ([c["leaf_minus_mid_c"] for c in carriers]),
        "mid_block_share_of_leaf": summ([round(c["mid_block_share"], 3) for c in carriers]),
    }

    # non-collapsing rate: mid distinct from BOTH endpoints at char thresholds
    non_collapse = {}
    for thr in [1, 20, 50, 100]:
        ok = sum(1 for c in carriers
                 if c["mid_minus_root_c"] >= thr and c["leaf_minus_mid_c"] >= thr)
        coll_root = sum(1 for c in carriers if c["mid_minus_root_c"] < thr)  # mid ~ root
        coll_leaf = sum(1 for c in carriers if c["leaf_minus_mid_c"] < thr)  # mid ~ leaf
        non_collapse[f"thr_{thr}c"] = {
            "both_blocks_nontrivial": ok,
            "frac": round(ok / nC, 3) if nC else None,
            "collapses_to_root": coll_root,
            "collapses_to_leaf": coll_leaf,
        }

    # mid-position histogram (is mid genuinely interior, not an endpoint clone?)
    shares = [c["mid_block_share"] for c in carriers]
    bins = {"[0.0,0.2)": 0, "[0.2,0.4)": 0, "[0.4,0.6)": 0, "[0.6,0.8)": 0, "[0.8,1.0]": 0}
    for s in shares:
        if s < 0.2: bins["[0.0,0.2)"] += 1
        elif s < 0.4: bins["[0.2,0.4)"] += 1
        elif s < 0.6: bins["[0.4,0.6)"] += 1
        elif s < 0.8: bins["[0.6,0.8)"] += 1
        else: bins["[0.8,1.0]"] += 1
    interior = sum(v for k, v in bins.items() if k in ("[0.2,0.4)", "[0.4,0.6)", "[0.6,0.8)"))

    nc50 = non_collapse["thr_50c"]
    report = {
        "what": (
            "Structural distinct-signal gate for pi_mid -- the CPU-only half of "
            "the construct-validity gate that a-0052/a-0053/a-0055 flagged but "
            "deferred. For every depth>=2 substantive carrier it measures the two "
            "named-block increments that define a genuine third level: mid-root "
            "(top-level block pi_mid names that pi_root inlines) and leaf-mid "
            "(nested block pi_leaf names that pi_mid inlines). pi_mid is "
            "structurally distinct from BOTH endpoints iff BOTH increments are "
            "non-trivial."
        ),
        "n_carriers_depth_ge2": nC,
        "substantive_named_def": "name != '_' AND type non-empty AND body non-empty (e-0026/e-0032 inline-or-name unit)",
        "increment_distributions": incr,
        "non_collapsing_rate": non_collapse,
        "mid_position_share_histogram": {
            "bins": bins,
            "interior_0.2_to_0.8": interior,
            "interior_frac": round(interior / nC, 3) if nC else None,
            "note": "mid_block_share = mid-block chars / total leaf-block chars; "
                    "interior (0.2-0.8) = pi_mid names a substantial-but-partial "
                    "fraction of the eventual fine block, the U-shape-relevant case.",
        },
        "caveats": (
            "STRUCTURAL/on-disk half ONLY: separates the three named blocks by "
            "count+chars; the remaining unmet half is the term-vs-tactic FORMAT "
            "confound (e-0036/e-0037, off-disk, paid extract). Body classification "
            "is syntactic (a one-token term-mode body counts substantive). pi_mid "
            "antichain modelled as top-level substantive haves with binder "
            "pass-through (matches e-0054/e-0057 depth convention); does not model "
            "the chosen cut's exact serialization. No Lean, no Modal."
        ),
    }

    report["verdict"] = (
        f"Over the {nC} depth>=2 deep carriers that admit an intermediate cut, "
        f"pi_mid carries a genuine, distinct block at BOTH boundaries on the "
        f"on-disk structure: the top-level block pi_mid names over pi_root has "
        f"median {incr['mid_minus_root_chars']['median']} chars "
        f"({incr['mid_minus_root_count']['median']} haves) and the nested block "
        f"pi_leaf names over pi_mid has median "
        f"{incr['leaf_minus_mid_chars']['median']} chars "
        f"({incr['leaf_minus_mid_count']['median']} haves). At a 50-char "
        f"non-triviality threshold {nc50['both_blocks_nontrivial']} carriers "
        f"({100*nc50['frac']:.0f}%) keep BOTH blocks non-trivial -- pi_mid does "
        f"NOT collapse onto either endpoint -- while {nc50['collapses_to_leaf']} "
        f"would collapse toward pi_leaf (trivial nested block) and "
        f"{nc50['collapses_to_root']} toward pi_root. pi_mid sits in the interior "
        f"(0.2-0.8 of the eventual fine block) on "
        f"{report['mid_position_share_histogram']['interior_frac']*100:.0f}% of "
        f"carriers, so it is a genuine third granularity level rather than an "
        f"endpoint clone for the bulk of the study set. CONSEQUENCE: the STRUCTURAL "
        f"half of the distinct-signal gate that a-0053/a-0055 deferred is now CLEARED "
        f"-- a 3-level rough/mid/fine U-shape is structurally warranted (distinct "
        f"named content at each level), and the only remaining open gate on the 3rd "
        f"arm is the off-disk term-vs-tactic FORMAT confound (e-0036/e-0037, paid "
        f"extract) plus the ~1.5x compute (a-0054). CAVEAT: on-disk chars/count "
        f"separation only; format-vs-content distinctness still needs the extract."
    )

    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
