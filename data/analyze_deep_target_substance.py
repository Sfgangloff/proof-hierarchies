"""CPU-only PRE-MODAL feasibility gate for q-0009's section-predictor on data/deep.

The recent chain (e-0012..e-0015) converges on ONE prescription: a Modal
round-trip verification (e-0003-style) over the ~633 wide-frontier data/deep
decls to give q-0009's section-predictor (Variant B) real training signal.
Before that paid spend, this script runs the gate that was NOT yet run —
analogous to how e-0010 gated q-0008 on the length confound before SFT.

Two things, both pure stdlib over the local have-tree JSON:

1. RESOLVE THE COLLISION CAVEAT (flagged by e-0014 AND e-0015). The stored
   `module` field is the last path component only, so e-0014's "646 distinct
   modules" is an undercount. The FILENAME encodes the full dotted path
   (Algebra__AffineMonoid__Irreducible.json -> Mathlib.Algebra.AffineMonoid.
   Irreducible), so we recover true full modules and emit a precisely-scoped
   target manifest for the Modal re-extraction — turning the vague "the 633
   wide-frontier decls" into an actionable, deduplicated target list.

2. SUBSTANCE OF THE EMISSION TARGET. A section-predictor must EMIT the named
   top-level frontier — the list of subgoal types (ppType). "Wide supply"
   (e-0015: 633 decls with top-width>=2) is only real training signal if those
   types are SUBSTANTIVE subgoals, not degenerate one-token rewrites, and if
   emitting the frontier is actually CHEAPER than emitting the whole proof
   (the "fewer LLM calls" premise of q-0009). We measure the frontier-type
   length distribution, the degenerate fraction, and the per-decl total
   emission burden (sum of frontier-type chars + token proxy).

"named node" = have_tree node with name != "_" and non-empty type — the same
definition used by e-0012/e-0014/e-0015. Frontier = TOP-LEVEL named nodes
(the one-shot antichain a predictor emits), matching e-0015's top_width.
"""
import json
import glob
import os
import statistics as st

DEEP = "data/deep/*.json"
OUT_REPORT = "data/corpus_v3/deep_target_substance.json"
OUT_MANIFEST = "data/corpus_v3/deep_wide_targets.json"

# A frontier subgoal type this short is almost certainly a degenerate rewrite
# (e.g. "0 < n", "p", "a = b") rather than a substantive subgoal worth a
# separate solver call. A conservative threshold; reported, not load-bearing.
DEGENERATE_CHARS = 8


def named(nd):
    return nd.get("name", "_") != "_" and (nd.get("type") or "").strip() != ""


def top_frontier_types(nodes):
    """ppTypes of the TOP-LEVEL named nodes — the predictor's emission target."""
    return [(nd.get("type") or "").strip() for nd in nodes if named(nd)]


def full_module(path):
    return "Mathlib." + os.path.basename(path)[:-5].replace("__", ".")


def pct(vals, thr, n):
    c = sum(1 for v in vals if v >= thr)
    return {"n": c, "pct": round(100 * c / n, 1)}


def quantiles(vals):
    s = sorted(vals)
    if not s:
        return {}
    def q(p):
        return s[min(len(s) - 1, int(p * len(s)))]
    return {
        "min": s[0], "p10": q(0.10), "p50": st.median(s),
        "p90": q(0.90), "max": s[-1], "mean": round(st.mean(s), 1),
    }


def main():
    n_decls = 0
    wide = []          # (full_module, name, top_width, frontier_type_chars[list])
    per_node_chars = []   # chars of every frontier subgoal type (wide decls only)
    degenerate = 0
    decl_burden_chars = []   # per-wide-decl total frontier emission chars

    for f in glob.glob(DEEP):
        mod = full_module(f)
        for e in json.load(open(f)):
            n_decls += 1
            ftypes = top_frontier_types(e.get("have_tree") or [])
            if len(ftypes) >= 2:                       # wide target (e-0015 def)
                chars = [len(t) for t in ftypes]
                wide.append((mod, e["name"], len(ftypes), chars))
                per_node_chars.extend(chars)
                degenerate += sum(1 for c in chars if c <= DEGENERATE_CHARS)
                decl_burden_chars.append(sum(chars))

    n_wide = len(wide)
    distinct_modules = len({m for m, *_ in wide})

    # token proxy: ~4 chars/token, matching e-0010/e-0011 convention
    node_tok = [c / 4 for c in per_node_chars]
    burden_tok = [c / 4 for c in decl_burden_chars]

    report = {
        "source": "data/deep — pre-Modal feasibility gate for q-0009 (Variant B)",
        "n_decls_total": n_decls,
        "n_wide_targets(top_frontier>=2)": n_wide,
        "wide_pct": round(100 * n_wide / n_decls, 1),
        "COLLISION_CAVEAT_RESOLVED": {
            "distinct_full_modules_from_filename": len(
                {full_module(f) for f in glob.glob(DEEP)}),
            "distinct_modules_among_wide_targets": distinct_modules,
            "e0014_last_component_count": 646,
            "note": ("filename encodes full dotted path; e-0014's 646 was a "
                     "last-component undercount. Wide targets span "
                     f"{distinct_modules} full modules."),
        },
        "EMISSION_SUBSTANCE (per frontier subgoal type, wide decls)": {
            "n_frontier_subgoals": len(per_node_chars),
            "chars": quantiles(per_node_chars),
            "tokens_est": quantiles(node_tok),
            "degenerate_le_%d_chars" % DEGENERATE_CHARS: {
                "n": degenerate,
                "pct_of_subgoals": round(100 * degenerate / len(per_node_chars), 1),
            },
        },
        "EMISSION_BURDEN (per wide decl, total frontier chars)": {
            "chars": quantiles(decl_burden_chars),
            "tokens_est": quantiles(burden_tok),
            "note": ("the predictor emits this much to name the whole frontier; "
                     "compare to a full rough term-mode proof (e-0010 median "
                     "~7074 chars / ~1768 tok) to judge the 'fewer LLM calls' "
                     "premise of q-0009"),
        },
        "manifest": OUT_MANIFEST,
    }

    # Precisely-scoped, deduplicated target manifest for the Modal re-extraction.
    manifest = {
        "description": ("q-0009 section-predictor training targets: data/deep "
                        "decls with a top-level named frontier of >=2 subgoals. "
                        "Full module paths recovered from filenames. NOT yet "
                        "verified (no round-trip); e-0003's ~84.7% yield applies."),
        "n_targets": n_wide,
        "n_modules": distinct_modules,
        "modules": sorted({m for m, *_ in wide}),
        "targets": [
            {"module": m, "name": nm, "frontier_width": w,
             "frontier_chars": sum(chars)}
            for m, nm, w, chars in sorted(wide, key=lambda x: -x[2])
        ],
    }

    json.dump(report, open(OUT_REPORT, "w"), indent=2)
    json.dump(manifest, open(OUT_MANIFEST, "w"), indent=2)
    print(json.dumps(report, indent=2))
    print(f"\nwrote {OUT_REPORT}")
    print(f"wrote {OUT_MANIFEST} ({n_wide} targets, {distinct_modules} modules)")


if __name__ == "__main__":
    main()
