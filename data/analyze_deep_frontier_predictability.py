"""CPU-only test of q-0009's UNTOUCHED premise: is the frontier PREDICTABLE
from the theorem statement?

The chain e-0012..e-0019 cleared every data-level gate for Variant B (a
section-predictor + solver) EXCEPT the one that defines whether the predictor
can be trained at all. Recap of what is already established over the 633
data/deep wide-frontier decls:

  - supply (e-0014/15/16): 633 decls expose a >=2-wide top-level named frontier;
  - emission economics (e-0016): naming a frontier is ~88x cheaper than emitting
    the full proof;
  - subgoal size (e-0017): subgoals are NOT reliably smaller than the parent;
  - independence (e-0018/19): the frontier factorizes -- ~82% of decls show zero
    inter-sibling proof-body coupling, robust to body-visibility stratification.

But a section-predictor's INPUT is only the theorem statement (the goal). Its
OUTPUT is the frontier (the list of subgoal types). Every gate above measured
properties of the OUTPUT in isolation -- none asked whether the output is a
function the predictor can learn from the INPUT. If the frontier subgoals are
built largely from vocabulary already present in the statement, the target is a
structured RECOMBINATION of the input -- learnable. If they introduce many new
library identifiers absent from the statement, the predictor must INVENT
mathematical content it never saw in its input -- much harder for a small model,
and a genuine identifiability problem for the target.

WHAT WE MEASURE. For each wide-frontier decl we tokenize the parent `statement`
and each top-level frontier subgoal `type` into Lean identifier tokens (and
their dot-split components, so `g.TerminatedAt` contributes both `g` and
`TerminatedAt`). A subgoal token is GROUNDED if it occurs in the statement's
token set, NOVEL otherwise.

LOCAL vs LIBRARY. A novel single-letter `r`/`n`/`a` is just a fresh bound
variable -- its identity is arbitrary and a predictor emitting an
alpha-equivalent frontier is fine, so counting it as "invented content" would
overstate the difficulty. We therefore classify each token component:
  - LIBRARY (content): contains an uppercase letter OR a digit-free dotted
    projection head that is capitalized -- i.e. an unambiguous Mathlib
    type/structure/namespace/lemma reference by Mathlib's casing convention;
    concretely here: has any uppercase char. These are genuine mathematical
    content the predictor must produce.
  - LOCAL (lowercase, no uppercase): bound variables and a handful of lowercase
    library defs (le, dens). Their novelty is mostly harmless renaming.

The headline groundedness is computed over LIBRARY tokens -- the genuine-content
vocabulary -- with the raw all-token figure reported alongside.

CAVEAT (honest, and it cuts one way -- same shape as e-0018/e-0019). Lexical
novelty OVERSTATES unlearnability: a model has parametric Mathlib knowledge and
can emit a common library name (`mul_comm`, `Nat.succ`) that is absent from the
statement, so a NOVEL library token is not proof the target is unlearnable.
Conversely a GROUNDED token IS provably a verbatim function of the input. So a
high grounded fraction is STRONG positive evidence the target is learnable; a
high novel fraction is only WEAK negative evidence. This is a data-level
structural bound like e-0010/e-0016/e-0017, not a trained-predictor accuracy.
"""
import json
import glob
import re
import statistics as st

DEEP = "data/deep/*.json"
OUT = "data/corpus_v3/deep_frontier_predictability.json"

# Lean identifier: starts with a letter/_/greek-ish, may contain dots (field
# access), primes, digits, subscripts. We capture the whole dotted chain then
# split on '.' for component-level grounding.
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_'.₀-₉]*")


def named(nd):
    return nd.get("name", "_") != "_" and (nd.get("type") or "").strip() != ""


def top_frontier(nodes):
    return [nd for nd in nodes if named(nd)]


def components(text):
    """Identifier token components of a string: every dotted chain plus each of
    its dot-split parts. Returns a set."""
    out = set()
    for tok in IDENT.findall(text or ""):
        out.add(tok)
        if "." in tok:
            for part in tok.split("."):
                if part:
                    out.add(part)
    return out


def is_library(tok):
    """Genuine-content token by Mathlib casing convention: any uppercase char.
    Lowercase-only tokens are treated as local (bound vars / minor lowercase
    defs)."""
    return any(c.isupper() for c in tok)


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
        "min": round(s[0], 4), "p10": round(q(0.10), 4), "p50": round(q(0.50), 4),
        "p90": round(q(0.90), 4), "max": round(s[-1], 4),
        "mean": round(sum(s) / len(s), 4),
    }


def main():
    decls = []
    for f in sorted(glob.glob(DEEP)):
        for d in json.load(open(f)):
            front = top_frontier(d.get("have_tree", []))
            if len(front) >= 2:
                decls.append((d["name"], d.get("statement", ""), front))

    n_wide = len(decls)

    # per-decl grounded fractions
    grounded_all = []        # over ALL frontier tokens
    grounded_lib = []        # over LIBRARY frontier tokens only (the headline)
    novel_lib_counts = []    # # distinct novel library tokens the predictor must invent
    lib_token_counts = []    # # distinct library tokens in the frontier
    fully_grounded_lib = 0   # decls whose entire library frontier vocab is in the statement
    no_lib_tokens = 0        # decls whose frontier has no library token at all
    examples_grounded = []
    examples_novel = []

    for name, stmt, front in decls:
        stmt_vocab = components(stmt)
        # union of all frontier subgoal token components
        fr_vocab = set()
        for nd in front:
            fr_vocab |= components(nd["type"])
        if not fr_vocab:
            continue

        # ALL-token grounding
        g_all = sum(1 for t in fr_vocab if t in stmt_vocab) / len(fr_vocab)
        grounded_all.append(g_all)

        # LIBRARY-token grounding
        lib = {t for t in fr_vocab if is_library(t)}
        lib_token_counts.append(len(lib))
        if not lib:
            no_lib_tokens += 1
            continue
        grounded = {t for t in lib if t in stmt_vocab}
        novel = lib - grounded
        g_lib = len(grounded) / len(lib)
        grounded_lib.append(g_lib)
        novel_lib_counts.append(len(novel))
        if not novel:
            fully_grounded_lib += 1
            if len(examples_grounded) < 6:
                examples_grounded.append({"decl": name, "lib_tokens": sorted(lib)[:8]})
        elif g_lib < 0.25 and len(examples_novel) < 6:
            examples_novel.append({
                "decl": name,
                "novel_lib_tokens": sorted(novel)[:10],
                "stmt": stmt[:90],
            })

    n_lib_decls = len(grounded_lib)
    result = {
        "n_wide_decls": n_wide,
        "n_decls_with_library_frontier_tokens": n_lib_decls,
        "n_decls_no_library_frontier_tokens": no_lib_tokens,
        # headline: how grounded is the genuine-content frontier vocabulary?
        "grounded_fraction_LIBRARY_tokens": quantiles(grounded_lib),
        "grounded_fraction_ALL_tokens": quantiles(grounded_all),
        "novel_library_tokens_per_decl": quantiles([float(x) for x in novel_lib_counts]),
        "library_tokens_per_decl": quantiles([float(x) for x in lib_token_counts]),
        "decls_fully_grounded_library_frontier": fully_grounded_lib,
        "decls_fully_grounded_frac": round(fully_grounded_lib / n_lib_decls, 4) if n_lib_decls else None,
        "examples_fully_grounded": examples_grounded,
        "examples_low_grounding": examples_novel,
        "caveat": (
            "Lexical grounding is a data-level proxy. A GROUNDED token is provably "
            "a function of the statement input (strong positive evidence the target "
            "is learnable). A NOVEL library token is only weak negative evidence: a "
            "model can emit common Mathlib names from parametric knowledge. Lowercase "
            "library defs are counted as LOCAL, so the library-token grounding "
            "slightly excludes some content. Not a trained-predictor accuracy."
        ),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    with open(OUT, "w") as fh:
        json.dump(result, fh, indent=2, ensure_ascii=False)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
