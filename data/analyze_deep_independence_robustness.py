"""CPU-only robustness test of e-0018's near-independence finding to its OWN
load-bearing caveat: the elided-body bound.

e-0018 concluded q-0009's wide frontiers are observably NEAR-INDEPENDENT (only
18.5% of decls show any inter-sibling proof-body coupling; max chain 2; ~94%
of subgoals "ready"). But it flagged one honest caveat that cuts one way: only
43.8% of frontier bodies were scannable (47.2% elided to bare `by`, 9.0%
empty), so every coupling number is a LOWER bound and every independence number
an UPPER bound. A skeptic's first objection is therefore: "your independence is
an artifact of not seeing half the proofs -- where bodies ARE visible, coupling
is high, and you just missed it elsewhere."

This script answers that objection directly, CPU-only, over the same 633
data/deep wide-frontier decls. The artifact hypothesis makes a sharp,
falsifiable prediction: if low coupling is driven by invisibility, then
coupling must RISE with body visibility -- decls whose frontier bodies are
fully scannable should be MORE coupled than partially-elided ones. We test it
two ways:

  1. STRATIFY by per-decl scannable fraction (NONE / PARTIAL / FULL) and report
     the coupled fraction, ready-fraction, and chain length in each stratum.
     The FULL stratum is the honest one: there every "observably independent"
     decl is ACTUALLY independent (no hidden body could hide an edge), so its
     coupled fraction is a real coupling rate, not a lower bound.

  2. CORRELATE per-decl scannable fraction against per-decl coupling (binary
     coupled, and edge density = edges / possible ordered pairs). A positive
     correlation supports the artifact hypothesis; a flat/negative one refutes
     it and shows e-0018's headline survives full visibility.

Reuses e-0018's citation logic verbatim (whole-identifier sibling reference)
so the only new thing is the visibility stratification.
"""
import json
import glob
import re
import statistics as st

DEEP = "data/deep/*.json"
OUT = "data/corpus_v3/deep_independence_robustness.json"

IDENT_PREV = "A-Za-z0-9_'.₀-₉"
IDENT_NEXT = "A-Za-z0-9_'₀-₉"


def named(nd):
    return nd.get("name", "_") != "_" and (nd.get("type") or "").strip() != ""


def top_frontier(nodes):
    return [nd for nd in nodes if named(nd)]


def cites(body, name):
    pat = r"(?<![" + IDENT_PREV + r"])" + re.escape(name) + r"(?![" + IDENT_NEXT + r"])"
    return re.search(pat, body) is not None


def scannable(nd):
    b = (nd.get("body") or "").strip()
    return b not in ("", "by")


def longest_chain(n, edges):
    adj = {i: [] for i in range(n)}
    for (j, i) in edges:
        adj[j].append(i)

    def depth(u, on_path):
        best = 0
        for v in adj[u]:
            if v in on_path:
                continue
            best = max(best, 1 + depth(v, on_path | {v}))
        return best

    return max((depth(u, {u}) for u in range(n)), default=0)


def quantiles(vals):
    s = sorted(vals)
    if not s:
        return {}

    def q(p):
        if len(s) == 1:
            return s[0]
        idx = p * (len(s) - 1)
        lo = int(idx)
        hi = min(lo + 1, len(s) - 1)
        return s[lo] + (s[hi] - s[lo]) * (idx - lo)

    return {"min": s[0], "p10": q(0.10), "p50": q(0.50),
            "p90": q(0.90), "max": s[-1], "mean": round(sum(s) / len(s), 3)}


def pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx == 0 or vy == 0:
        return None
    return round(cov / (vx ** 0.5 * vy ** 0.5), 4)


def analyze_decl(front):
    """Return (k, scannable_count, edges, coupled_bool, chain, ready_frac)."""
    names = [nd["name"] for nd in front]
    k = len(front)
    scan = [scannable(nd) for nd in front]
    edges = []
    for i, nd in enumerate(front):
        if not scan[i]:
            continue
        body = nd.get("body") or ""
        for j in range(k):
            if j != i and cites(body, names[j]):
                edges.append((j, i))
    edges = list(set(edges))
    coupled = len(edges) > 0
    chain = longest_chain(k, edges) if edges else 0
    blocked = {i for (_, i) in edges}
    ready = (k - len(blocked)) / k
    return k, sum(scan), edges, coupled, chain, ready


def stratum_summary(rows):
    """rows: list of (k, edges, coupled, chain, ready)."""
    n = len(rows)
    if n == 0:
        return {"n": 0}
    coupled = sum(1 for r in rows if r[2])
    edge_density = []
    for k, edges, _, _, _ in rows:
        pairs = k * (k - 1)  # ordered pairs i!=j
        edge_density.append(len(edges) / pairs if pairs else 0.0)
    return {
        "n": n,
        "coupled_decls": coupled,
        "coupled_frac": round(coupled / n, 4),
        "mean_ready_frac": round(st.mean(r[4] for r in rows), 4),
        "mean_edge_density": round(st.mean(edge_density), 5),
        "chain_quantiles": quantiles([r[3] for r in rows]),
        "chain_ge2_decls": sum(1 for r in rows if r[3] >= 2),
    }


def main():
    decls = []
    for f in sorted(glob.glob(DEEP)):
        for d in json.load(open(f)):
            front = top_frontier(d.get("have_tree", []))
            if len(front) >= 2:
                decls.append((d["name"], front))

    none_rows, partial_rows, full_rows = [], [], []
    scan_fracs, coupled_flags, edge_densities = [], [], []

    for name, front in decls:
        k, n_scan, edges, coupled, chain, ready = analyze_decl(front)
        sf = n_scan / k
        scan_fracs.append(sf)
        coupled_flags.append(1 if coupled else 0)
        pairs = k * (k - 1)
        edge_densities.append(len(edges) / pairs if pairs else 0.0)
        row = (k, edges, coupled, chain, ready)
        if n_scan == 0:
            none_rows.append(row)
        elif n_scan == k:
            full_rows.append(row)
        else:
            partial_rows.append(row)

    result = {
        "n_wide_decls": len(decls),
        "strata": {
            "NONE_scannable": stratum_summary(none_rows),
            "PARTIAL_scannable": stratum_summary(partial_rows),
            "FULL_scannable": stratum_summary(full_rows),
        },
        "visibility_vs_coupling": {
            "pearson_scanfrac_vs_coupled": pearson(scan_fracs, coupled_flags),
            "pearson_scanfrac_vs_edgedensity": pearson(scan_fracs, edge_densities),
            "note": ("artifact hypothesis predicts POSITIVE correlation "
                     "(more visible -> more coupling found). flat/negative "
                     "refutes the elision-artifact objection."),
        },
        "headline_e0018_coupled_frac": 0.185,
        "interpretation_key": {
            "FULL_scannable.coupled_frac": ("the HONEST coupling rate: no hidden "
                "body can hide an edge here, so it is a real rate, not a lower "
                "bound. compare to the 0.185 e-0018 headline."),
        },
    }
    json.dump(result, open(OUT, "w"), indent=2, ensure_ascii=False)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
