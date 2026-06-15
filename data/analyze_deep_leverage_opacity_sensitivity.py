#!/usr/bin/env python3
"""CPU-only OPACITY-SENSITIVITY gate for the q-0011 leverage construct.

Every q-0011 gate so far (e-0058 base rate, analyze_deep_leverage_effective_n's
eval-split D) carries the SAME unquantified caveat verbatim:

    "term-mode-only citation (48% of bodies opaque 'by') -> all counts are
     LOWER BOUNDS."

The detector (analyze_deep_have_reuse.is_term_body) only scans term-mode bodies
for identifier tokens; a citation that lives in raw tactic text inside a `by`
block is invisible. So the leverage base rate (12.2% citeable / 2.7% reused) and
the eval-split leverage carrier count D (cited>=1: 49, reused>=2: 8) are both
LOWER bounds. Nobody has asked the two questions that caveat begs:

  (1) RECALL: what fraction of citing-capable proof content is actually VISIBLE
      to the detector (term-mode), i.e. how big is the undercount? Refine the
      flat "48% opaque" figure by separating opaque-LEAF `by` (truly invisible)
      from opaque-BRANCH `by` (whose structured term-mode descendants the
      flatten()+scan ALREADY recovers), giving a conservative and an optimistic
      recall.

  (2) ROBUSTNESS: does the leverage POWER verdict survive the opacity? The
      eval-split McNemar floor needs D>=6 leverage carriers (e-0045). Opacity can
      only HIDE citations, never invent them, so the true D >= observed D. If the
      observed LOWER bound already clears D>=6, more hidden reuse only strengthens
      the verdict -> the power conclusion is robust by monotonicity, no model
      needed. We then bound the recall-corrected base rate so the eval's "did the
      model use the decomposition" read is interpretable.

Decision logic (monotone, not Monte-Carlo): observed counts are a floor; recall
gives the inflation range to the ceiling. Robust iff floor already passes.

CPU-only, pure stdlib, no Lean, no Modal. Reuses analyze_deep_have_reuse (e-0058
detector) and analyze_deep_leverage_effective_n (eval-split D) UNCHANGED.
"""
import json
import glob
import collections

import analyze_deep_have_reuse as hr
import analyze_deep_leverage_effective_n as lev

DEEP = sorted(glob.glob("data/deep/*.json"))


def body_class(n):
    """Classify a node's body for detector VISIBILITY.

    - empty       : no body (intro/obtain binder) -> cites nothing, not a body.
    - term        : term-mode body -> VISIBLE to the citation detector.
    - opaque_leaf : tactic-mode 'by' with NO children -> truly invisible; any
                    citation in its tactic text is permanently lost.
    - opaque_branch: tactic-mode 'by' WITH children -> the children's term-mode
                     bodies ARE scanned (flatten recovers them), so this node's
                     reuse is PARTIALLY visible.
    """
    b = (n.get("body") or "").strip()
    if not b:
        return "empty"
    if hr.is_term_body(b):
        return "term"
    return "opaque_branch" if n.get("children") else "opaque_leaf"


def main():
    decls = []
    for f in DEEP:
        try:
            arr = json.load(open(f))
        except Exception:
            continue
        decls.extend(d for d in arr if "have_tree" in d)

    # ------------------------------------------------------------------ census
    # over ALL nodes and, separately, over the NAMED haves whose reuse we score.
    allc = collections.Counter()
    namedc = collections.Counter()
    for d in decls:
        for n in hr.flatten(d["have_tree"]):
            c = body_class(n)
            allc[c] += 1
            if hr.named(n):
                namedc[c] += 1

    def shares(counter):
        nonempty = sum(v for k, v in counter.items() if k != "empty")
        out = {k: counter[k] for k in ("empty", "term", "opaque_branch", "opaque_leaf")}
        out["nonempty_bodies"] = nonempty
        # recall = visible citing-capable content / all citing-capable content.
        # conservative: only term-mode bodies are visible.
        # optimistic: opaque_BRANCH bodies are partially recovered via their
        #   term-mode descendants, so only opaque_LEAF content is truly lost.
        out["recall_conservative"] = round(counter["term"] / nonempty, 3) if nonempty else None
        out["recall_optimistic"] = (
            round((nonempty - counter["opaque_leaf"]) / nonempty, 3) if nonempty else None
        )
        return out

    all_census = shares(allc)
    named_census = shares(namedc)

    # ------------------------------------------------- eval-split lower-bound D
    # reuse the leverage effective-n gate verbatim (e-0046 split x e-0058 detector)
    lev_out = lev.main()
    ev = lev_out["splits"]["eval"]
    D_cited1 = ev["cited1"]
    D_reused2 = ev["reused2"]
    FLOOR = 6  # e-0045: McNemar exact needs >=6 same-direction discordant pairs

    # recall used to inflate the observed FLOOR to a true-count CEILING range.
    # citing capacity lives in body content, so use the all-node census recall.
    r_cons = all_census["recall_conservative"]
    r_opt = all_census["recall_optimistic"]

    def ceiling_range(observed):
        """True count >= observed (monotone). Under uniform-citation, an observed
        count is a recall-thinned sample of the true count, so the point estimate
        of the true count is observed/recall; range spans optimistic..conservative
        recall. Reported as an interpretability band, NOT used for the verdict."""
        hi = round(observed / r_cons) if r_cons else None   # smallest recall -> largest ceiling
        lo = round(observed / r_opt) if r_opt else None     # largest recall  -> smallest ceiling
        return {"floor_observed": observed, "ceiling_est_lo": lo, "ceiling_est_hi": hi}

    # base rates (whole population) for interpretability, with the same band.
    nh = lev  # noop alias to keep import used in linters
    base = hr.analyze() if hasattr(hr, "analyze") else None
    base_citeable = base["named_haves"]["citeable_ge1_pct"] if base else None
    base_reused = base["named_haves"]["reused_ge2_pct"] if base else None

    verdict_robust = D_reused2 >= FLOOR  # cleanest fingerprint already clears floor?
    verdict_cited_robust = D_cited1 >= FLOOR

    out = {
        "source": "q-0011 leverage OPACITY-SENSITIVITY: quantify the '48% opaque -> lower bound' caveat",
        "reuses": {
            "detector": "e-0058 analyze_deep_have_reuse.is_term_body (unchanged)",
            "eval_split_D": "analyze_deep_leverage_effective_n (e-0046 x e-0058, unchanged)",
            "floor": "e-0045 McNemar combinatorial: D<6 -> power exactly 0 at alpha=0.05",
        },
        "body_census_all_nodes": all_census,
        "body_census_named_haves": named_census,
        "detector_recall": {
            "conservative_term_only": all_census["recall_conservative"],
            "optimistic_excl_opaque_leaf": all_census["recall_optimistic"],
            "interpretation": (
                "Detector sees ~%s-%s of citing-capable body content; opaque-BRANCH "
                "reuse is partly recovered via term-mode descendants, only opaque-LEAF "
                "`by` is permanently invisible." % (
                    all_census["recall_conservative"], all_census["recall_optimistic"])
            ),
        },
        "eval_leverage_carriers": {
            "cited_ge1": ceiling_range(D_cited1),
            "reused_ge2_cleanest": ceiling_range(D_reused2),
        },
        "base_rate_recall_corrected_pct": {
            "citeable_ge1_observed": base_citeable,
            "reused_ge2_observed": base_reused,
            "note": "true rate in [observed, observed/recall]; lower bound is what e-0058 reported.",
        },
        "ROBUSTNESS_VERDICT": {
            "monotone_argument": "opacity HIDES citations, never adds them => true D >= observed D; "
            "if the observed lower bound already clears the D>=6 floor, more hidden reuse only "
            "strengthens power.",
            "cited_ge1_clears_floor_at_lower_bound": verdict_cited_robust,
            "reused_ge2_clears_floor_at_lower_bound": verdict_robust,
            "leverage_power_robust_to_opacity": verdict_robust,
            "caveat_now_bounded": (
                "Power verdict robust by monotonicity; opacity affects only the MAGNITUDE of the "
                "interpretable base rate, bounded by detector recall above, not the go/no-go."
            ),
        },
    }
    return out


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, ensure_ascii=False))
