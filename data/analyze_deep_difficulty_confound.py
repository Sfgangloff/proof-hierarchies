"""CPU-only DIFFICULTY-CONFOUND gate for q-0008.

q-0008 asks whether any rough/fine pass@k effect survives controlling for
sequence LENGTH *and* PROBLEM DIFFICULTY. The length half is settled: e-0010/
e-0011/e-0027/a-0027 showed the 144x rough/fine length gap is a corpus_v3
term-vs-tactic SERIALIZATION artifact that the same-format data/deep route
dissolves to a median ~29-token granularity delta. The DIFFICULTY half has
never been analyzed. This gate closes it.

Two distinct difficulty threats live inside q-0008; the planned design treats
them very differently and prior work conflated them:

  (1) PAIRED-CONTRAST threat (the one the planned design already kills).
      Stage 3 is a WITHIN-THEOREM paired comparison: the SAME theorem is
      serialized rough and fine, so per-theorem difficulty is held constant by
      construction and CANNOT confound the paired (rough-fine) contrast. We
      verify this is the actual design and state why difficulty drops out.

  (2) SELECTION threat (unanalyzed, real). The granularity contrast only
      EXISTS on theorems that admit a fine decomposition -- the >=2-wide
      named-frontier "wide" targets (the canonical 633). If those are
      systematically HARDER (or easier) than the rest of data/deep, then
      (a) the result generalizes only to a difficulty-skewed sub-population,
      and (b) the post-SFT base rate p_lo -- the single Modal-blocked
      parameter the e-0059/e-0060 feasibility frontier turns on -- is the base
      rate OF THE SELECTED SET, not of Mathlib at large. So selection
      difficulty directly moves the break-even p* the GO rule is read against.

  (3) EFFECT-MODIFICATION threat (unanalyzed). Even within the paired design,
      if the granularity SIGNAL (the named-header length delta that is the only
      thing differing between arms) is concentrated on the hard or the easy
      tail, then any granularity benefit is difficulty-modified and pooling
      across difficulty dilutes the paired McNemar power. We measure the
      correlation between the granularity delta and difficulty.

Difficulty proxies (corpus-structural, CPU-only -- no Lean, no Modal, no
ground-truth pass rate available). For each decl we compute:
    stmt_chars   : statement length (goal-statement size)
    tree_nodes   : total have-tree nodes (recursive) -- proof-size proxy
    tree_depth   : max have-tree nesting depth -- structural-complexity proxy
    named_width  : top-level named-with-type have count (the granularity carrier)
These are the SAME crude proxies the rest of the chain uses (e-0017/e-0024).
A composite difficulty rank is the average of per-decl percentile ranks of
stmt_chars, tree_nodes, tree_depth (named_width excluded from the composite
because it DEFINES the selection, to avoid circularity).

Statistics, all rank-based and stdlib-only:
  - distribution summaries (median / IQR) of each proxy, wide vs non-wide;
  - Mann-Whitney U -> rank-biserial effect size r and AUC (P(wide > nonwide));
  - Cliff's delta;
  - Spearman rho between the granularity HEADER DELTA (e-0027 definition) and
    composite difficulty, over the wide targets (effect-modification);
  - difficulty-stratified count of wide targets (tertiles) to show how the
    paired n distributes across difficulty.

Deterministic, pure stdlib, seed-free. Reads data/deep/*.json. No pairs.
"""
import json
import glob
import math
import statistics as st

DEEP = "data/deep/*.json"
OUT = "data/corpus_v3/deep_difficulty_confound.json"

HEADER_OVERHEAD = 13  # "have " + " : " + " := " ~ 13 chars (e-0027 convention)


# ----- tree walkers -----
def named_nodes(nodes):
    """All named-with-type nodes (recursive), e-0012 notion."""
    out = []
    for nd in nodes:
        name = nd.get("name", "_")
        typ = (nd.get("type") or "").strip()
        if name != "_" and typ != "":
            out.append(nd)
        out.extend(named_nodes(nd.get("children") or []))
    return out


def top_named_width(nodes):
    return sum(
        1
        for nd in nodes
        if nd.get("name", "_") != "_" and (nd.get("type") or "").strip() != ""
    )


def tree_size(nodes):
    n = 0
    for nd in nodes:
        n += 1
        n += tree_size(nd.get("children") or [])
    return n


def tree_depth(nodes):
    if not nodes:
        return 0
    return 1 + max(tree_depth(nd.get("children") or []) for nd in nodes)


def granularity_delta_chars(nodes):
    """e-0027: inlining removes every named header; delta = sum over named
    nodes of HEADER_OVERHEAD + len(name) + len(type)."""
    d = 0
    for nd in named_nodes(nodes):
        d += HEADER_OVERHEAD + len(nd.get("name", "")) + len(nd.get("type") or "")
    return d


# ----- rank stats (stdlib) -----
def ranks(xs):
    """Average ranks (1-based), ties averaged."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def percentile_ranks(xs):
    """Percentile rank in [0,1] per element (fraction <= x, midrank)."""
    rk = ranks(xs)
    n = len(xs)
    return [(r - 0.5) / n for r in rk]


def mann_whitney(a, b):
    """U for group a vs b; return U_a, AUC=P(a>b)+0.5 P(tie), rank-biserial r,
    Cliff's delta, and a normal-approx z/p (two-sided)."""
    na, nb = len(a), len(b)
    allv = a + b
    rk = ranks(allv)
    Ra = sum(rk[:na])
    Ua = Ra - na * (na + 1) / 2.0
    auc = Ua / (na * nb)              # P(a>b) with tie=0.5
    cliff = 2 * auc - 1              # Cliff's delta = AUC*2-1
    rb = cliff                      # rank-biserial == Cliff's delta here
    # normal approx with tie correction
    n = na + nb
    # tie correction
    from collections import Counter
    tie_term = 0.0
    for c in Counter(allv).values():
        tie_term += c ** 3 - c
    mu = na * nb / 2.0
    sigma2 = (na * nb / 12.0) * ((n + 1) - tie_term / (n * (n - 1)))
    sigma = math.sqrt(sigma2) if sigma2 > 0 else 0.0
    if sigma > 0:
        z = (Ua - mu) / sigma
        # two-sided p via erfc
        p = math.erfc(abs(z) / math.sqrt(2))
    else:
        z, p = 0.0, 1.0
    return {
        "U_wide": round(Ua, 1),
        "AUC_P_wide_gt_nonwide": round(auc, 3),
        "cliffs_delta": round(cliff, 3),
        "rank_biserial_r": round(rb, 3),
        "z": round(z, 3),
        "p_two_sided": float(f"{p:.2e}"),
    }


def spearman(xs, ys):
    rx, ry = ranks(xs), ranks(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    dx = math.sqrt(sum((v - mx) ** 2 for v in rx))
    dy = math.sqrt(sum((v - my) ** 2 for v in ry))
    if dx == 0 or dy == 0:
        return {"rho": 0.0, "p_two_sided": 1.0, "n": n}
    rho = num / (dx * dy)
    # t approx
    if abs(rho) < 1.0 and n > 2:
        t = rho * math.sqrt((n - 2) / (1 - rho ** 2))
        # two-sided p via normal approx on t for moderate n
        p = math.erfc(abs(t) / math.sqrt(2))
    else:
        p = 0.0
    return {"rho": round(rho, 3), "p_two_sided": float(f"{p:.2e}"), "n": n}


def summ(xs):
    xs = sorted(xs)
    n = len(xs)

    def q(p):
        if n == 1:
            return xs[0]
        idx = p * (n - 1)
        lo = int(math.floor(idx))
        hi = min(lo + 1, n - 1)
        frac = idx - lo
        return xs[lo] * (1 - frac) + xs[hi] * frac

    return {
        "n": n,
        "median": round(q(0.5), 1),
        "q25": round(q(0.25), 1),
        "q75": round(q(0.75), 1),
        "mean": round(sum(xs) / n, 1),
    }


def main():
    files = [f for f in glob.glob(DEEP) if "/._" not in f and not f.split("/")[-1].startswith("._")]
    recs = []
    for f in files:
        for e in json.load(open(f)):
            ht = e.get("have_tree") or []
            recs.append(
                {
                    "module": e["module"],
                    "name": e["name"],
                    "stmt_chars": len(e.get("statement") or ""),
                    "tree_nodes": tree_size(ht),
                    "tree_depth": tree_depth(ht),
                    "named_width": top_named_width(ht),
                    "delta_chars": granularity_delta_chars(ht),
                }
            )

    n = len(recs)

    # composite difficulty = mean of percentile ranks of the 3 non-circular proxies
    pr_stmt = percentile_ranks([r["stmt_chars"] for r in recs])
    pr_nodes = percentile_ranks([r["tree_nodes"] for r in recs])
    pr_depth = percentile_ranks([r["tree_depth"] for r in recs])
    for i, r in enumerate(recs):
        r["difficulty"] = (pr_stmt[i] + pr_nodes[i] + pr_depth[i]) / 3.0

    # ---- selection: WIDE (>=2 top named) vs NON-WIDE ----
    wide = [r for r in recs if r["named_width"] >= 2]
    nonwide = [r for r in recs if r["named_width"] < 2]

    selection = {
        "n_wide": len(wide),
        "n_nonwide": len(nonwide),
        "pct_wide": round(100 * len(wide) / n, 1),
    }
    for proxy in ["stmt_chars", "tree_nodes", "tree_depth", "difficulty"]:
        a = [r[proxy] for r in wide]
        b = [r[proxy] for r in nonwide]
        selection[proxy] = {
            "wide": summ(a),
            "nonwide": summ(b),
            "test": mann_whitney(a, b),
        }

    # ---- effect-modification: granularity delta vs difficulty, over WIDE ----
    wd_delta = [r["delta_chars"] for r in wide]
    wd_diff = [r["difficulty"] for r in wide]
    wd_width = [r["named_width"] for r in wide]
    effect_mod = {
        "spearman_delta_vs_difficulty": spearman(wd_delta, wd_diff),
        "spearman_width_vs_difficulty": spearman(wd_width, wd_diff),
        "note": "delta = e-0027 named-header granularity length delta (chars); "
        "the ONLY thing differing between rough/fine arms in a same-format pair.",
    }

    # ---- difficulty-stratified paired-n distribution over WIDE ----
    # tertiles of composite difficulty computed on the FULL corpus so the cut
    # is population-anchored, not wide-internal.
    diffs_all = sorted(r["difficulty"] for r in recs)
    t1 = diffs_all[int(n / 3)]
    t2 = diffs_all[int(2 * n / 3)]

    def tertile(d):
        return "low" if d <= t1 else ("mid" if d <= t2 else "high")

    strat = {"low": 0, "mid": 0, "high": 0}
    strat_delta = {"low": [], "mid": [], "high": []}
    for r in wide:
        t = tertile(r["difficulty"])
        strat[t] += 1
        strat_delta[t].append(r["delta_chars"])
    stratified = {
        "wide_count_by_population_difficulty_tertile": strat,
        "median_granularity_delta_chars_by_tertile": {
            k: (round(st.median(v), 1) if v else None) for k, v in strat_delta.items()
        },
    }

    result = {
        "source": "data/deep/*.json",
        "n_decls": n,
        "paired_contrast_threat": {
            "design": "Stage 3 = WITHIN-THEOREM paired (same theorem, rough vs "
            "fine serialization); build_sft.py uses identical theorem indices "
            "across policies (e-0006).",
            "verdict": "Per-theorem difficulty is held CONSTANT by construction "
            "in the paired contrast, so it cannot confound the (rough-fine) "
            "difference. The length half (a-0027) is the remaining within-pair "
            "confound, already dissolved by the same-format deep route.",
        },
        "selection_threat": selection,
        "effect_modification_threat": effect_mod,
        "stratified": stratified,
        "difficulty_proxy_def": "composite = mean percentile-rank of "
        "{stmt_chars, tree_nodes, tree_depth}; named_width excluded (defines "
        "selection). CPU-structural proxy; no ground-truth pass rate (Modal-blocked).",
    }

    import os
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(result, open(OUT, "w"), indent=2, ensure_ascii=False)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
