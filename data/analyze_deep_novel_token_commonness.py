"""CPU-only test of the load-bearing CAVEAT in a-0020 (q-0009).

e-0020 measured how much of the section frontier is GROUNDED in the parent
statement and found it only median ~37.5% (library-token grounding), with the
median wide-frontier decl introducing ~2 NOVEL library identifiers absent from
the goal. Its verdict was deliberately hedged -- "plausible but unproven" --
because of one caveat it flagged but never measured:

    "a NOVEL library token is not proof the target is unlearnable: a model has
     parametric Mathlib knowledge and can emit a common library name
     (mul_comm, Nat.succ) that is absent from the statement."

That caveat is load-bearing. If the novel library tokens the predictor must
"invent" are overwhelmingly COMMON Mathlib names (Finset, Continuous, le_trans
-- the kind a model trained on Mathlib has seen thousands of times), then the
novel-content burden is mostly recall of high-frequency vocabulary, and a-0020's
predictability gate reads much more favorably. If instead they are RARE /
specialised identifiers (appearing in one or a handful of decls), the predictor
must produce genuinely low-frequency content from its input, and the gate is a
real obstacle.

WHAT WE MEASURE. We reuse e-0020's tokenization and library/grounded/novel
classification verbatim. We additionally build a CORPUS DOCUMENT-FREQUENCY map
over ALL data/deep decls (not just the 633 wide-frontier ones): for each library
token component, df = the number of distinct decls whose statement OR any
have-tree node type contains it. df is a proxy for "how common is this name in
Mathlib" -- i.e. how likely a Mathlib-trained model already knows it. Then for
every NOVEL library token (frontier token absent from its own statement) we look
up its corpus df and report the distribution, contrasted against the df of the
GROUNDED tokens as a calibration baseline.

CAVEAT (honest, and the direction matters). data/deep (~1,261 decls) is a SAMPLE
of Mathlib, so corpus df UNDER-counts true Mathlib frequency: a token that is a
singleton here may still be common in full Mathlib. So a high observed-df share
is a LOWER bound on the truly-common share -- strong evidence the novel content
is recallable; a high singleton share is only WEAK evidence it is rare (it may
be common in the unsampled remainder). Same one-way shape as e-0018/e-0020. This
is a data-level frequency proxy, not a trained-predictor accuracy.
"""
import json
import glob
import re
import statistics as st
from collections import defaultdict

DEEP = "data/deep/*.json"
OUT = "data/corpus_v3/deep_novel_token_commonness.json"

IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_'.₀-₉]*")


def named(nd):
    return nd.get("name", "_") != "_" and (nd.get("type") or "").strip() != ""


def top_frontier(nodes):
    return [nd for nd in nodes if named(nd)]


def components(text):
    out = set()
    for tok in IDENT.findall(text or ""):
        out.add(tok)
        if "." in tok:
            for part in tok.split("."):
                if part:
                    out.add(part)
    return out


def is_library(tok):
    return any(c.isupper() for c in tok)


def all_type_vocab(d):
    """Library-token components appearing anywhere in a decl's content surface:
    its statement plus every have-tree node type. Used to build corpus df."""
    vocab = set(components(d.get("statement", "")))

    def walk(nodes):
        for nd in nodes:
            vocab.update(components(nd.get("type", "")))
            walk(nd.get("children", []) or [])

    walk(d.get("have_tree", []) or [])
    return {t for t in vocab if is_library(t)}


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
        "min": round(s[0], 4), "p10": round(q(0.10), 4), "p25": round(q(0.25), 4),
        "p50": round(q(0.50), 4), "p75": round(q(0.75), 4), "p90": round(q(0.90), 4),
        "max": round(s[-1], 4), "mean": round(sum(s) / len(s), 4),
    }


def main():
    all_decls = []
    for f in sorted(glob.glob(DEEP)):
        for d in json.load(open(f)):
            all_decls.append(d)

    # ---- corpus document-frequency over ALL decls (commonness proxy) ----
    df = defaultdict(int)
    for d in all_decls:
        for t in all_type_vocab(d):
            df[t] += 1
    n_corpus = len(all_decls)

    # ---- wide-frontier decls (the e-0020 / q-0009 target set) ----
    wide = []
    for d in all_decls:
        front = top_frontier(d.get("have_tree", []))
        if len(front) >= 2:
            wide.append((d["name"], d.get("statement", ""), front))

    novel_dfs = []        # df of every novel library token (pooled)
    grounded_dfs = []     # df of every grounded library token (calibration)
    per_decl_common_frac = []   # per-decl: of novel lib tokens, frac with df>=COMMON
    rare_examples = []
    common_examples = defaultdict(int)

    COMMON = 25   # appears in >=25/1261 decls (~2%) -> unambiguously common Mathlib name
    RARE = 2      # appears in <=2 decls in this sample

    for name, stmt, front in wide:
        stmt_vocab = components(stmt)
        fr_vocab = set()
        for nd in front:
            fr_vocab |= components(nd["type"])
        lib = {t for t in fr_vocab if is_library(t)}
        if not lib:
            continue
        grounded = {t for t in lib if t in stmt_vocab}
        novel = lib - grounded
        for t in grounded:
            grounded_dfs.append(df.get(t, 0))
        if not novel:
            continue
        nd_dfs = [df.get(t, 0) for t in novel]
        novel_dfs.extend(nd_dfs)
        common = sum(1 for v in nd_dfs if v >= COMMON)
        per_decl_common_frac.append(common / len(novel))
        # collect a few genuinely-rare examples for inspection
        for t in sorted(novel):
            if df.get(t, 0) <= RARE and len(rare_examples) < 12:
                rare_examples.append({"decl": name, "token": t, "df": df.get(t, 0)})
            if df.get(t, 0) >= COMMON:
                common_examples[t] += 1

    def band(vals, lo, hi=None):
        if hi is None:
            return sum(1 for v in vals if v >= lo)
        return sum(1 for v in vals if lo <= v <= hi)

    n_novel = len(novel_dfs)
    bands = {
        "df==1 (corpus singleton)": band(novel_dfs, 1, 1),
        "df 2-4 (rare)": band(novel_dfs, 2, 4),
        "df 5-24 (uncommon)": band(novel_dfs, 5, 24),
        "df 25-99 (common, >=~2%)": band(novel_dfs, 25, 99),
        "df>=100 (very common)": band(novel_dfs, 100),
    }
    band_frac = {k: round(v / n_novel, 4) for k, v in bands.items()} if n_novel else {}

    top_common = sorted(common_examples.items(), key=lambda kv: -kv[1])[:12]

    result = {
        "n_corpus_decls": n_corpus,
        "n_wide_frontier_decls": len(wide),
        "n_novel_library_tokens_pooled": n_novel,
        "n_grounded_library_tokens_pooled": len(grounded_dfs),
        "COMMON_threshold_df": COMMON,
        "novel_token_df_distribution": quantiles([float(x) for x in novel_dfs]),
        "grounded_token_df_distribution_CALIBRATION": quantiles([float(x) for x in grounded_dfs]),
        "novel_token_df_bands": bands,
        "novel_token_df_bands_frac": band_frac,
        "per_decl_common_novel_fraction": quantiles(per_decl_common_frac),
        "share_novel_tokens_common_df_ge_25": round(band(novel_dfs, COMMON) / n_novel, 4) if n_novel else None,
        "share_novel_tokens_rare_df_le_2": round(band(novel_dfs, 1, 2) / n_novel, 4) if n_novel else None,
        "most_frequent_novel_tokens": [{"token": t, "n_decls_introducing_as_novel": c} for t, c in top_common],
        "rare_novel_examples": rare_examples,
        "caveat": (
            "Corpus df is computed over data/deep's ~1,261 decls, a SAMPLE of "
            "Mathlib, so it UNDER-counts true Mathlib frequency: a singleton here "
            "may be common in full Mathlib. A high common-df share is therefore a "
            "LOWER bound on the truly-recallable share (strong evidence the novel "
            "content is parametric-knowledge recall), while a high singleton share "
            "is only weak evidence of rarity. Data-level frequency proxy, not a "
            "trained-predictor accuracy."
        ),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    with open(OUT, "w") as fh:
        json.dump(result, fh, indent=2, ensure_ascii=False)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
