#!/usr/bin/env python3
"""Stage 0.5 design-stage gate for q-0011: do FINE-granularity named sub-results
carry detectable LEVERAGE structure -- i.e. are the named haves actually CITED
by other steps in the same proof (reuse), so that a future eval can attribute a
rough->fine pass@k gap to the model USING the decomposition rather than to
length/format?

The planned q-0007 eval logs (generated proofs) are Modal-blocked, so -- in the
exact design-stage spirit of the e-0040..e-0056 power/identifiability chain --
this does the two things the eval will need BEFORE the spend:

  (1) BUILD + validate the citation detector: parse each term-mode have body for
      identifier tokens and match them against the set of NAMED haves introduced
      earlier in the same proof (pre-order position). This is the exact tool the
      eval would run over generated proof text to measure "named-have reuse".

  (2) MEASURE the base rate of citeable / reusable named structure in the real
      deep FINE targets, so the eval's "did the model use the decomposition" read
      is interpretable and properly scoped:
        - how many named haves are cited >=1 time elsewhere (citeable),
        - how many are cited >=2 times (genuinely REUSED -- pi_root cannot inline
          a multiply-cited subgoal without duplicating it, so cited>=2 is exactly
          where rough and fine DIVERGE and where leverage must be learned),
        - what fraction of proofs expose at least one such reused named have.

CPU-only, pure stdlib, no Lean, no Modal. Operates on data/deep/*.json (the 633
wide-frontier decls; 834 files on disk, one decl each).

LIMITATION (lower bound): tactic-mode have bodies are stored opaquely as 'by'
(their internal structure is the children), so explicit name references that live
inside un-expanded tactic blocks are NOT visible. Measured citation rates are
therefore a LOWER BOUND on true within-proof reuse.
"""
import json
import glob
import re
from collections import Counter

DEEP = sorted(glob.glob("data/deep/*.json"))
TOK = re.compile(r"[A-Za-z_][\w']*")


def flatten(nodes):
    """Pre-order list of all nodes in a have_tree forest."""
    out = []

    def walk(n):
        out.append(n)
        for c in n.get("children", []):
            walk(c)

    for n in nodes:
        walk(n)
    return out


def is_term_body(b):
    """A leaf-ish term-mode body whose identifier tokens are real citations.
    Tactic-mode ('by' / 'by ...') and empty bodies expose no parseable refs."""
    if not b:
        return False
    if b == "by" or b.startswith("by") or b.startswith("by\n") or b.startswith("by "):
        return False
    return True


def named(n):
    nm = n.get("name")
    return bool(nm) and nm != "_"


def substantive_width(decl):
    """e-0032 construct-valid width: top-level named subgoals with their OWN
    non-empty proof body (the unit pi_root inlines / pi_leaf keeps named)."""
    w = 0
    for n in decl["have_tree"]:
        if named(n) and (n.get("body") or "").strip():
            w += 1
    return w


def analyze():
    decls = []
    for f in DEEP:
        try:
            arr = json.load(open(f))
        except Exception:
            continue
        for d in arr:
            if "have_tree" in d:
                decls.append(d)

    n_decls = len(decls)
    # per-decl tallies
    proofs_with_named = 0
    proofs_with_cited1 = 0  # >=1 named have cited elsewhere
    proofs_with_cited2 = 0  # >=1 named have cited >=2 (genuinely reused)
    # per-named-have citation distribution
    cite_counts = Counter()  # citation_count -> #named haves
    total_named = 0
    total_term_bodies = 0

    # restricted to construct-valid population (substantive width >=2)
    cv_decls = 0
    cv_with_cited1 = 0
    cv_with_cited2 = 0

    for d in decls:
        nodes = flatten(d["have_tree"])
        named_nodes = [n for n in nodes if named(n)]
        if named_nodes:
            proofs_with_named += 1
        total_named += len(named_nodes)

        # build set of names introduced (with pre-order index)
        name_first_idx = {}
        for i, n in enumerate(nodes):
            if named(n) and n["name"] not in name_first_idx:
                name_first_idx[n["name"]] = i

        # tokenize each term-mode body; record which earlier-introduced names it cites
        # citation_count[name] = # of OTHER bodies (at a later or different node)
        # that contain the name as a token
        cited = Counter()
        for i, n in enumerate(nodes):
            b = n.get("body") or ""
            if not is_term_body(b):
                continue
            total_term_bodies += 1
            toks = set(TOK.findall(b))
            for nm, first_i in name_first_idx.items():
                # a citation: the token appears, and it is not the node's own name
                # being (re)declared; count cross-step references
                if nm in toks and n.get("name") != nm:
                    cited[nm] += 1

        # tally distribution over named haves of this proof
        any1 = any2 = False
        for n in named_nodes:
            c = cited.get(n["name"], 0)
            cite_counts[c] += 1
            if c >= 1:
                any1 = True
            if c >= 2:
                any2 = True
        if any1:
            proofs_with_cited1 += 1
        if any2:
            proofs_with_cited2 += 1

        # construct-valid subset
        if substantive_width(d) >= 2:
            cv_decls += 1
            if any1:
                cv_with_cited1 += 1
            if any2:
                cv_with_cited2 += 1

    # fraction of named haves at each citation level
    citeable = sum(v for k, v in cite_counts.items() if k >= 1)
    reused = sum(v for k, v in cite_counts.items() if k >= 2)

    def pct(a, b):
        return round(100.0 * a / b, 1) if b else 0.0

    result = {
        "n_decls": n_decls,
        "total_named_haves": total_named,
        "total_term_mode_bodies_parsed": total_term_bodies,
        "named_have_citation_distribution": {str(k): cite_counts[k] for k in sorted(cite_counts)},
        "named_haves": {
            "total": total_named,
            "citeable_ge1": citeable,
            "citeable_ge1_pct": pct(citeable, total_named),
            "reused_ge2": reused,
            "reused_ge2_pct": pct(reused, total_named),
        },
        "proofs": {
            "total": n_decls,
            "with_any_named_have": proofs_with_named,
            "with_a_cited_named_have_ge1": proofs_with_cited1,
            "with_a_cited_named_have_ge1_pct": pct(proofs_with_cited1, n_decls),
            "with_a_reused_named_have_ge2": proofs_with_cited2,
            "with_a_reused_named_have_ge2_pct": pct(proofs_with_cited2, n_decls),
        },
        "construct_valid_subset_substantive_width_ge2": {
            "n_decls": cv_decls,
            "with_a_cited_named_have_ge1": cv_with_cited1,
            "with_a_cited_named_have_ge1_pct": pct(cv_with_cited1, cv_decls),
            "with_a_reused_named_have_ge2": cv_with_cited2,
            "with_a_reused_named_have_ge2_pct": pct(cv_with_cited2, cv_decls),
        },
    }
    return result


if __name__ == "__main__":
    r = analyze()
    print(json.dumps(r, indent=2, ensure_ascii=False))
