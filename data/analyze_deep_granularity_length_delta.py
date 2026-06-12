"""CPU-only test: is the rough/fine LENGTH confound that blocks q-0008 a property
of GRANULARITY, or of the term-vs-tactic SERIALIZATION choice baked into
corpus_v3?

Background. e-0010 found the corpus_v3 rough (pi_root, elaborated proof TERM) vs
fine (pi_leaf, tactic SOURCE) completions differ by a median 144x in length
(rough ~7,074 chars / ~1,768 tok vs fine ~49 chars / ~12 tok), with ZERO common
support -- so q-0008's length-covariate regression has no overlap region.
e-0011 showed cosmetic re-serialization cannot close it: the gap "is structural
to term-vs-tactic serialization ... it lives in the explicit elaborated
type/instance arguments". e-0026 separately found corpus_v3's rough/fine axis is
93% FORMAT-only (term-vs-tactic), not granularity. Both point at the SAME root
cause -- corpus_v3 set rough = the ELABORATED TERM and fine = the TACTIC SOURCE,
so the rough/fine contrast conflates serialization format with granularity, and
the 144x gap is the format difference, not the granularity difference.

The untested question. If you instead hold serialization FORMAT fixed (both
sides tactic-mode source) and vary ONLY granularity -- rough = the frontier
haves INLINED, fine = the frontier haves NAMED -- how large is the length gap?
If e-0010/e-0011's "it's the serialization, not the granularity" reading is
right, this same-format granularity delta should be SMALL and bounded, and a
same-format contrast cannot reproduce the zero-overlap pathology (because rough
and fine then SHARE all their tactic body content and differ only by the named
have headers). data/deep, which a-0014/a-0026 propose as the granularity corpus,
lets us measure this delta at the data level from the named have-tree.

What is measurable, and what is not. The have-tree gives each named have-node's
NAME and TYPE reliably; bodies are mostly elided ("by"), so full proof length is
NOT recoverable. But the length DELTA between a fully-named (fine) and a
fully-inlined (rough) serialization of the SAME proof is, to first order,
exactly the named have HEADERS that inlining removes:

    fine  = ...; have <name_i> : <type_i> := <body_i>; ... ; <goal using name_i>
    rough = ...; <body_i inlined at its single frontier use site>; ...

The shared content is the bodies; the granularity-specific delta is
sum_i ( len("have ") + len(name_i) + len(" : ") + len(type_i) + len(" := ") ).
We compute that delta per decl (header overhead ~13 chars/node) over ALL named
nodes (inlining removes every named header, not just the top-level frontier),
and contrast its magnitude with corpus_v3's measured serialization delta (e-0010).

This is a DATA-LEVEL bound, the q-0008 analogue of e-0010: it bounds the length
difference attributable to granularity alone, and shows whether a same-format
deep contrast escapes the zero-overlap regime. It does NOT measure pass@k.
"""
import json
import glob
import statistics as st

DEEP = "data/deep/*.json"
OUT = "data/corpus_v3/deep_granularity_length_delta.json"

# corpus_v3 rough/fine serialization gap, as published by e-0010 (chars / tok).
CV3_ROUGH_MED_CHARS = 7074
CV3_FINE_MED_CHARS = 49
CV3_ROUGH_MED_TOK = 1768
CV3_FINE_MED_TOK = 12

HEADER_OVERHEAD = 13  # "have " (5) + " : " (3) + " := " (4) + slack ~ len of `have _ :  := `


def named(nd):
    return nd.get("name", "_") != "_" and (nd.get("type") or "").strip() != ""


def walk(nodes):
    for nd in nodes:
        yield nd
        yield from walk(nd.get("children") or [])


def header_chars(nd):
    """Chars the FINE (named) serialization spends naming this have that the
    ROUGH (inlined) serialization omits: the `have <name> : <type> :=` header."""
    return len(nd["name"]) + len((nd.get("type") or "")) + HEADER_OVERHEAD


def q(vals, i):
    return round(st.quantiles(vals, n=10)[i], 2)


def main():
    rows = []
    for f in sorted(glob.glob(DEEP)):
        for d in json.load(open(f)):
            ht = d.get("have_tree") or []
            nn = [nd for nd in walk(ht) if named(nd)]
            rows.append({
                "name": d.get("name", "?"),
                "stmt_chars": len((d.get("statement") or "")),
                "n_named": len(nn),
                "delta_chars": sum(header_chars(nd) for nd in nn),
            })

    total = len(rows)
    # granularity-bearing decls (a fine-vs-rough contrast exists only with >=1 named have)
    gran = [r for r in rows if r["n_named"] >= 1]
    wide = [r for r in rows if r["n_named"] >= 2]

    def summarize(rs, label):
        deltas = [r["delta_chars"] for r in rs]
        toks = [d / 4 for d in deltas]
        # within-decl fine/rough ratio LOWER bound: fine = rough + delta, and a
        # sound lower bound on rough is the statement itself (the goal the proof
        # must restate) -> ratio_ub = 1 + delta/stmt is an UPPER bound on the
        # ratio (overstates the gap, since true rough >> stmt). Report it as a
        # conservative ceiling: even this ceiling is nowhere near corpus_v3's 144x.
        ratio_ub = [1 + r["delta_chars"] / max(1, r["stmt_chars"]) for r in rs]
        return {
            "label": label,
            "n": len(rs),
            "delta_chars_p10_p50_p90": [q(deltas, 0), q(deltas, 4), q(deltas, 8)],
            "delta_chars_mean": round(st.mean(deltas), 1),
            "delta_chars_max": max(deltas),
            "delta_tok_proxy_p10_p50_p90": [q(toks, 0), q(toks, 4), q(toks, 8)],
            "ratio_ceiling_1plus_delta_over_stmt_p50_p90": [q(ratio_ub, 4), q(ratio_ub, 8)],
            "frac_delta_exceeds_cv3_rough_median": round(
                sum(1 for d in deltas if d >= CV3_ROUGH_MED_CHARS) / len(rs), 4),
        }

    out = {
        "n_decls_total": total,
        "n_granularity_bearing_ge1_named": len(gran),
        "n_wide_ge2_named": len(wide),
        "granularity_delta__ge1_named": summarize(gran, ">=1 named have"),
        "granularity_delta__ge2_named": summarize(wide, ">=2 named have (wide)"),
        "corpus_v3_serialization_gap_e0010": {
            "rough_median_chars": CV3_ROUGH_MED_CHARS,
            "fine_median_chars": CV3_FINE_MED_CHARS,
            "delta_median_chars": CV3_ROUGH_MED_CHARS - CV3_FINE_MED_CHARS,
            "rough_median_tok": CV3_ROUGH_MED_TOK,
            "fine_median_tok": CV3_FINE_MED_TOK,
            "within_theorem_ratio_median": "142.5x (p10 26.9, p90 850.4); 0% overlap",
        },
    }

    g = out["granularity_delta__ge1_named"]
    cv3_delta = CV3_ROUGH_MED_CHARS - CV3_FINE_MED_CHARS
    out["headline"] = {
        "deep_granularity_delta_median_chars": g["delta_chars_p10_p50_p90"][1],
        "deep_granularity_delta_median_tok": g["delta_tok_proxy_p10_p50_p90"][1],
        "cv3_serialization_delta_median_chars": cv3_delta,
        "shrink_factor_vs_cv3": round(cv3_delta / max(1, g["delta_chars_p10_p50_p90"][1]), 1),
    }

    json.dump(out, open(OUT, "w"), indent=2)

    h = out["headline"]
    print(f"data/deep decls: {total}; >=1 named (granularity-bearing): {len(gran)}; >=2 named: {len(wide)}")
    print()
    print("GRANULARITY-ONLY length delta (same-format, tactic-mode; named headers inlining removes):")
    print(f"  >=1 named: delta chars p10/p50/p90 = {g['delta_chars_p10_p50_p90']} "
          f"(~{g['delta_tok_proxy_p10_p50_p90']} tok); max {g['delta_chars_max']}")
    print(f"  ceiling ratio 1+delta/stmt: p50/p90 = {g['ratio_ceiling_1plus_delta_over_stmt_p50_p90']}")
    print(f"  frac with delta >= cv3 rough median (7074 ch): {g['frac_delta_exceeds_cv3_rough_median']}")
    print()
    print("CONTRAST vs corpus_v3 term-vs-tactic SERIALIZATION delta (e-0010):")
    print(f"  cv3 rough-fine delta median: {h['cv3_serialization_delta_median_chars']} chars "
          f"(~{CV3_ROUGH_MED_TOK - CV3_FINE_MED_TOK} tok), within-theorem ratio 142.5x, 0% overlap")
    print(f"  deep granularity delta median: {h['deep_granularity_delta_median_chars']} chars "
          f"(~{h['deep_granularity_delta_median_tok']} tok)")
    print(f"  => granularity delta is ~{h['shrink_factor_vs_cv3']}x SMALLER than the serialization delta")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
