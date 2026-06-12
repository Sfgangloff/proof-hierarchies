"""CPU-only test of q-0009's LAST surviving premise: INDEPENDENT solvability.

The chain e-0012..e-0017 narrowed Variant B (section-predictor + solver) down
to one load-bearing assumption. Recap:

  - supply (e-0014/e-0015/e-0016): 633 deep decls expose a >=2-wide top-level
    named frontier -- enough to SFT a predictor;
  - emission economics (e-0016): naming a frontier costs ~20 tok median vs
    ~1,768 tok to emit a full rough proof -- an ~88x up-front reduction;
  - solver-side size (e-0017): decomposition does NOT reliably yield SMALLER
    subgoals (median largest subgoal ~90% of the parent; 45% of decls have a
    subgoal at least as large as the parent).

e-0017's verdict was explicit: "the planner's potential value must come from
INDEPENDENT solvability / search-space decomposition, not from smaller
subproblems." That independence was asserted as the only remaining
justification but never measured. This script measures it, CPU-only, over the
same 633 wide-frontier targets.

WHAT INDEPENDENCE MEANS HERE. A section is a maximal antichain in the
*dependency* poset, so the frontier subgoals do not depend on each other as
poset nodes. But the planner's "fewer LLM calls / parallel solve" payoff needs
something stronger at the PROOF level: each subgoal must be solvable WITHOUT
the proofs of its siblings in context. If subgoal_i's proof BODY references
sibling subgoal_j (by name), then a solver cannot attack them in parallel --
it must solve j first and thread j into i's context, which serializes the work
and reintroduces the very context-passing the planner was meant to avoid.

The have-tree records expose exactly this: each top-level named frontier node
carries a `body` (the reconstructed proof term / tactic block). We scan each
body for whole-identifier references to its SIBLING frontier names and build
the directed dependency graph over the frontier (edge j -> i iff body_i cites
name_j). From it:
  - observably-independent decls: frontier with ZERO inter-sibling body edges
    (a solver could attack every subgoal in parallel);
  - coupled decls: >=1 edge (solver must serialize part of the frontier);
  - longest observable dependency chain (how serial the frontier is);
  - fraction of frontier nodes that are "ready" (no sibling deps -> immediately
    solvable) -- the genuinely parallel mass.

CAVEAT (honest, and it cuts one way). 47.2% of frontier bodies are elided to a
bare "by" and 9.0% are empty (only 43.8% -- term + visible by-tactic -- carry a
scannable body). We can only see references in scannable bodies, so EVERY
coupling number here is a LOWER BOUND: a decl counted "observably independent"
may be coupled through an elided body. Thus a high observed-coupling rate is
strong evidence AGAINST clean factorization; a high observed-independence rate
is weak evidence FOR it (could be hidden). This is a data-level structural
bound like e-0010/e-0016/e-0017, not a pass@k claim.
"""
import json
import glob
import re
import statistics as st

DEEP = "data/deep/*.json"
OUT = "data/corpus_v3/deep_frontier_independence.json"


def named(nd):
    return nd.get("name", "_") != "_" and (nd.get("type") or "").strip() != ""


def top_frontier(nodes):
    return [nd for nd in nodes if named(nd)]


# A reference to `name` is an occurrence not glued to a longer Lean identifier.
# Lean identifier chars: letters, digits, _, ', subscripts, and '.' (field
# access). We forbid a preceding identifier char and a following identifier
# char, but ALLOW a trailing '.' (B_ineq.trans_lt' still references B_ineq).
IDENT_PREV = "A-Za-z0-9_'.₀-₉"
IDENT_NEXT = "A-Za-z0-9_'₀-₉"


def cites(body, name):
    pat = r"(?<![" + IDENT_PREV + r"])" + re.escape(name) + r"(?![" + IDENT_NEXT + r"])"
    return re.search(pat, body) is not None


def scannable(nd):
    b = (nd.get("body") or "").strip()
    return b not in ("", "by")


def longest_chain(n, edges):
    """Longest simple-path length (# edges) in the graph given by edges j->i
    (i depends on j). The text-citation graph CAN contain cycles (mutual
    references), unlike the true dependency poset, so we guard against
    revisiting a node already on the current DFS path. Frontiers are tiny
    (<=~22 nodes) so exhaustive simple-path search is trivial."""
    adj = {i: [] for i in range(n)}
    for (j, i) in edges:
        adj[j].append(i)

    def depth(u, on_path):
        best = 0
        for v in adj[u]:
            if v in on_path:
                continue  # cycle: don't extend along a revisited node
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

    return {
        "min": s[0], "p10": q(0.10), "p50": q(0.50),
        "p90": q(0.90), "max": s[-1],
        "mean": round(sum(s) / len(s), 3),
    }


def main():
    decls = []
    for f in sorted(glob.glob(DEEP)):
        for d in json.load(open(f)):
            front = top_frontier(d.get("have_tree", []))
            if len(front) >= 2:
                decls.append((d["name"], front))

    n_wide = len(decls)
    coupled = 0
    fully_indep = 0
    no_scannable = 0          # decls where NO frontier body is scannable
    edge_counts = []
    chain_lens = []
    ready_fracs = []          # fraction of frontier nodes with no sibling dep
    total_nodes = 0
    total_scannable = 0
    total_edges = 0
    examples_coupled = []
    examples_chain = []

    for name, front in decls:
        names = [nd["name"] for nd in front]
        k = len(front)
        total_nodes += k
        scan = [scannable(nd) for nd in front]
        total_scannable += sum(scan)
        # edges j -> i : body_i cites sibling name_j
        edges = []
        for i, nd in enumerate(front):
            if not scan[i]:
                continue
            body = (nd.get("body") or "")
            for j in range(k):
                if j == i:
                    continue
                if cites(body, names[j]):
                    edges.append((j, i))
        edges = list(set(edges))
        total_edges += len(edges)
        edge_counts.append(len(edges))

        if sum(scan) == 0:
            no_scannable += 1

        if edges:
            coupled += 1
            cl = longest_chain(k, edges)
            chain_lens.append(cl)
            if len(examples_coupled) < 8:
                examples_coupled.append({"decl": name, "frontier": k, "edges": len(edges)})
            if cl >= 3 and len(examples_chain) < 8:
                examples_chain.append({"decl": name, "frontier": k, "chain": cl})
        else:
            chain_lens.append(0)
            # observably independent (only meaningful if something was scannable)
            if sum(scan) > 0:
                fully_indep += 1

        # nodes with >=1 incoming sibling edge are "blocked"; rest are ready
        blocked = {i for (_, i) in edges}
        ready_fracs.append((k - len(blocked)) / k)

    observably_independent_strict = fully_indep  # had scannable body, zero edges
    result = {
        "n_wide_decls": n_wide,
        "frontier_nodes_total": total_nodes,
        "frontier_nodes_scannable": total_scannable,
        "scannable_frac": round(total_scannable / total_nodes, 4),
        "decls_no_scannable_body": no_scannable,
        "coupled_decls": coupled,
        "coupled_frac": round(coupled / n_wide, 4),
        "observably_independent_decls": observably_independent_strict,
        "observably_independent_frac": round(observably_independent_strict / n_wide, 4),
        "total_inter_sibling_edges": total_edges,
        "edge_count_quantiles": quantiles(edge_counts),
        "longest_chain_quantiles": quantiles(chain_lens),
        "ready_fraction_quantiles": quantiles(ready_fracs),
        "chain_len_ge3_decls": sum(1 for c in chain_lens if c >= 3),
        "examples_coupled": examples_coupled,
        "examples_long_chain": examples_chain,
    }

    json.dump(result, open(OUT, "w"), indent=2, ensure_ascii=False)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
