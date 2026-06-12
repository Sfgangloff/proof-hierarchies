"""CPU-only learnability gate for q-0009: is the section frontier's CARDINALITY
(top-level WIDTH = how many subgoals the predictor must emit) predictable from
the theorem statement?

The e-0012..e-0023 chain cleared every data-level gate for the Variant B
section-predictor EXCEPT one slice of learnability: e-0020/e-0021 measured how
much of the frontier's *vocabulary* is grounded in / recombinable from the
statement, but NONE asked whether the frontier's STRUCTURE is predictable from
the input. Before a predictor can emit the right subgoal types it must emit the
right NUMBER of them; if frontier width is uncorrelated with any cheap feature
of the statement, the model cannot even guess its output cardinality from the
goal, which is a real, untested concern.

This script measures, over ALL data/deep decls (not just the >=2-wide selection
— conditioning on width>=2 would hide the predictability question), the
Spearman rank correlation between cheap statement features (char length, #
identifier tokens, # distinct library tokens, # logical/relational operators)
and the top-level named frontier width, plus the MAE of a length-tercile
predictor vs an always-predict-the-median baseline.

A "named node" = have_tree node with name != "_" and non-empty type (the e-0012
section-predictor target), matching e-0012/e-0014/e-0015. Top-level named nodes
= the one-shot antichain the predictor emits. Pure stdlib, no Modal, not
verified — a learnability estimate over the supply, the same role e-0014..e-0020
played.

CAVEAT (per e-0017): data/deep statements are LEFT-TRUNCATED (binder/hypothesis
prefix cut), so the surface features here are themselves partial; a learned model
could exploit structure these proxies miss, so a low correlation here is a
flag/lower-bound on learnability, not proof of unlearnability.
"""
import json
import glob
import re
import statistics as st

DEEP = "data/deep/*.json"
OUT = "data/corpus_v3/deep_width_predictability.json"

# logical / relational operators as a statement-complexity proxy
OPS = ["∀", "∃", "→", "↔", "∧", "∨", "¬", "=", "≤", "<", "≥", ">", "∈", "⊆", "∑", "∏"]
TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_']*")


def named(nd):
    return nd.get("name", "_") != "_" and (nd.get("type") or "").strip() != ""


def top_width(nodes):
    return sum(1 for nd in nodes if named(nd))


def stmt_features(stmt):
    stmt = stmt or ""
    toks = TOKEN_RE.findall(stmt)
    # library token: dotted-chain component with an uppercase char (Mathlib casing)
    libs = set()
    for raw in re.split(r"[^A-Za-z0-9_'.]", stmt):
        for comp in raw.split("."):
            if comp and any(c.isupper() for c in comp):
                libs.add(comp)
    nops = sum(stmt.count(op) for op in OPS)
    return {
        "chars": len(stmt),
        "tokens": len(toks),
        "lib_tokens": len(libs),
        "ops": nops,
    }


def rank(xs):
    """Average-tie ranks."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def pearson(a, b):
    n = len(a)
    if n < 2:
        return 0.0
    ma, mb = st.mean(a), st.mean(b)
    num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    da = sum((x - ma) ** 2 for x in a) ** 0.5
    db = sum((x - mb) ** 2 for x in b) ** 0.5
    if da == 0 or db == 0:
        return 0.0
    return num / (da * db)


def spearman(a, b):
    return pearson(rank(a), rank(b))


def main():
    widths = []
    feats = {"chars": [], "tokens": [], "lib_tokens": [], "ops": []}

    for f in glob.glob(DEEP):
        for e in json.load(open(f)):
            ht = e.get("have_tree") or []
            widths.append(top_width(ht))
            ff = stmt_features(e.get("statement"))
            for k in feats:
                feats[k].append(ff[k])

    n = len(widths)

    # Spearman of each feature vs frontier width, over ALL decls.
    corr_all = {k: round(spearman(feats[k], widths), 3) for k in feats}

    # Same, restricted to the >=2-wide predictor-target slice (the 633): even
    # among decls that HAVE a wide frontier, is the exact width predictable?
    idx_wide = [i for i in range(n) if widths[i] >= 2]
    w_wide = [widths[i] for i in idx_wide]
    corr_wide = {
        k: round(spearman([feats[k][i] for i in idx_wide], w_wide), 3) for k in feats
    }

    # Predictive value: length-tercile mean width vs constant-median baseline.
    chars = feats["chars"]
    order = sorted(range(n), key=lambda i: chars[i])
    t = n // 3
    terciles = {
        "short": [order[i] for i in range(0, t)],
        "mid": [order[i] for i in range(t, 2 * t)],
        "long": [order[i] for i in range(2 * t, n)],
    }
    tercile_mean_width = {
        name: round(st.mean([widths[i] for i in idxs]), 3)
        for name, idxs in terciles.items()
    }
    med = st.median(widths)
    mae_const = round(st.mean([abs(w - med) for w in widths]), 3)
    # tercile predictor: predict each tercile's own mean width (rounded)
    tercile_pred = {name: round(st.mean([widths[i] for i in idxs]))
                    for name, idxs in terciles.items()}
    mae_tercile = round(st.mean(
        [abs(widths[i] - tercile_pred[name])
         for name, idxs in terciles.items() for i in idxs]), 3)

    def dist(vals, cap=7):
        out = {}
        for v in vals:
            kk = str(v) if v <= cap else f"{cap+1}+"
            out[kk] = out.get(kk, 0) + 1
        return dict(sorted(out.items()))

    result = {
        "source": "data/deep — learnability gate (frontier WIDTH predictability) for q-0009",
        "n_decls": n,
        "caveat": "statements are LEFT-TRUNCATED (e-0017); surface features are partial, "
                  "so low correlation is a lower-bound flag on learnability, not proof.",
        "width_distribution_all": dist(widths),
        "median_width": med,
        "mean_width": round(st.mean(widths), 3),
        "spearman_feature_vs_width_ALL_decls": corr_all,
        "spearman_feature_vs_width_WIDE_slice_only": {
            "n": len(idx_wide), **corr_wide,
        },
        "length_tercile_mean_width": tercile_mean_width,
        "predictive_MAE": {
            "always_predict_median": mae_const,
            "length_tercile_predictor": mae_tercile,
            "improvement_abs": round(mae_const - mae_tercile, 3),
            "improvement_pct": round(100 * (mae_const - mae_tercile) / mae_const, 1)
            if mae_const else 0.0,
        },
    }

    with open(OUT, "w") as fh:
        json.dump(result, fh, indent=2, ensure_ascii=False)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
