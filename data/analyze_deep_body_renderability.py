"""Body-renderability gate for the data/deep same-format build (e-0033/a-0032 follow-up).

Question this answers WITHOUT spending Modal credit:
  e-0033 (a-0032) showed the same-format (both-tactic-mode) build is well-defined
  and confound-free, and that pi_root inlining is a simple DROP for 87.2% of named
  haves. But it flagged a load-bearing caveat -- repeated as "structural skeletons,
  not runnable Lean" -- because data/deep have_tree bodies are mostly ELIDED to the
  literal string "by" (the tactic block content is not captured). e-0033/e-0034
  never quantified HOW MUCH of the build is already renderable from disk vs how
  much the eventual (mandatory) Modal re-extraction must recover.

  This gate measures the BODY-CAPTURE profile of the named substantive frontier
  haves over the same 633 wide-frontier targets, then scopes renderability for
  EACH policy:

    pi_leaf (fine) keeps `have <name> : <type> := <body>` for every named have.
      It therefore needs the BODY of every named have. A bare-`by` have has no
      captured body -> pi_leaf cannot render a runnable proof for it. A target is
      FULLY pi_leaf-renderable from data/deep iff ALL its named haves have a
      captured body.

    pi_root (rough) inlines each named have. For an INDEPENDENT have (name not
      referenced by a sibling) inlining is a header DROP -- NO body is needed, so
      it is renderable regardless of body elision. Only SIBLING-REFERENCED haves
      (e-0034's 12.8% substitution-required subset) need the body substituted, so
      pi_root is render-blocked ONLY by sibling-referenced haves whose body is
      elided.

  The point: pi_root is far more renderable from the elided records than pi_leaf,
  because dropping an independent header needs no body. This sharpens e-0033's
  "skeletons not runnable Lean" caveat into a per-policy number and scopes the
  body-recovery half of the Modal re-extraction.

  HARD CAVEAT (does NOT make either policy runnable from disk alone): the
  have_tree records contain ONLY the named have nodes, not the RESIDUAL main proof
  body that surrounds them. So even a target whose every have body is captured is
  not runnable Lean from data/deep -- the residual tactic block is absent for all
  633. The Modal re-extraction must recover (a) the residual for every target AND
  (b) the elided have bodies this gate counts. This gate scopes (b) only; (a) is a
  full re-extraction regardless. Data-level only: no Lean, no Modal, no round-trip,
  no verified pairs. "Captured" = body string present and non-empty and not the
  elided `by` / `by ...` placeholder; "elided" = bare `by` (tactic block dropped).

Inputs (local, already on disk):
  data/corpus_v3/deep_wide_targets.json  -- 633 wide-frontier targets (e-0016)
  data/deep/<Module>.json                -- have_tree records (named subgoals)

  python3 data/analyze_deep_body_renderability.py [--out path.json]
"""

from __future__ import annotations
import argparse, collections, json, re, statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ROOT / "data/corpus_v3/deep_wide_targets.json"
DEEP_DIR = ROOT / "data/deep"


def deep_path(module: str) -> Path:
    stem = module.removeprefix("Mathlib.").replace(".", "__")
    return DEEP_DIR / f"{stem}.json"


def top_area(module: str) -> str:
    parts = module.split(".")
    return parts[1] if module.startswith("Mathlib.") and len(parts) > 1 else parts[0]


def substantive(node: dict) -> bool:
    """Named frontier node with its own proof body (e-0032/e-0033 definition)."""
    return (node.get("body") or "").strip() != ""


def body_captured(node: dict) -> bool:
    """Body string is present in the record (renderable), not the elided `by` placeholder.

    term-mode bodies (e.g. `pow_ne_zero _ h.1.2.1`) and inline `by norm_cast` are
    captured in full; a bare `by` means the tactic block was elided at extraction.
    """
    b = (node.get("body") or "").strip()
    return bool(b) and b != "by"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data/deep_body_renderability.json"))
    args = ap.parse_args()

    targets = json.loads(TARGETS.read_text())["targets"]

    cache: dict[Path, list] = {}

    def records(module: str) -> list:
        p = deep_path(module)
        if p not in cache:
            cache[p] = json.loads(p.read_text()) if p.exists() else []
        return cache[p]

    missing = 0
    named_total = 0                          # named substantive haves (cf e-0033: 2225)
    captured = 0                             # body present in record (term / inline by)
    elided = 0                              # bare `by` -> body dropped at extraction

    # per-target pi_leaf renderability (every named have needs a captured body):
    leaf_full = leaf_partial = leaf_none = 0
    leaf_capture_fracs: list[float] = []

    # pi_root renderability: only sibling-referenced haves need a body.
    ref_total = 0                           # sibling-referenced named haves (subst-required)
    ref_elided = 0                          # ...with elided body -> genuine pi_root blocker
    indep_total = 0                         # independent named haves (header drop, no body)
    root_full = 0                           # targets with NO elided sibling-referenced have

    area_named = collections.Counter()
    area_captured = collections.Counter()

    for t in targets:
        rec = next((r for r in records(t["module"]) if r["name"] == t["name"]), None)
        if rec is None:
            missing += 1
            continue
        nodes = rec["have_tree"]
        names = [(n.get("name") or "").strip() for n in nodes]
        area = top_area(t["module"])

        named_idx = [i for i, n in enumerate(nodes)
                     if substantive(n) and names[i] not in ("", "_")]
        if not named_idx:
            continue

        t_named = t_cap = 0
        t_ref_elided = 0
        for i in named_idx:
            n = nodes[i]
            t_named += 1
            named_total += 1
            area_named[area] += 1
            cap = body_captured(n)
            if cap:
                captured += 1
                t_cap += 1
                area_captured[area] += 1
            else:
                elided += 1

            # sibling-reference test (e-0034 logic): is this name used by a sibling?
            nm = names[i]
            pat = re.compile(r"(?<![\w.])" + re.escape(nm) + r"(?![\w])")
            n_occ = 0
            for j, m2 in enumerate(nodes):
                if j == i:
                    continue
                txt = (m2.get("body") or "") + " " + (m2.get("type") or "")
                n_occ += len(pat.findall(txt))
            if n_occ > 0:
                ref_total += 1
                if not cap:
                    ref_elided += 1
                    t_ref_elided += 1
            else:
                indep_total += 1

        # pi_leaf needs a captured body for every named have in the target
        leaf_capture_fracs.append(t_cap / t_named)
        if t_cap == t_named:
            leaf_full += 1
        elif t_cap == 0:
            leaf_none += 1
        else:
            leaf_partial += 1
        # pi_root is renderable for a target iff no sibling-referenced have is elided
        if t_ref_elided == 0:
            root_full += 1

    n_t = len(leaf_capture_fracs)
    report = {
        "description": (
            "Body-renderability gate for the data/deep same-format build "
            "(e-0033/a-0032 follow-up). Quantifies how much of the same-format "
            "rough/fine build is already renderable from data/deep vs needs the "
            "mandatory Modal re-extraction to recover elided tactic bodies. "
            "'captured' = have body present in the record; 'elided' = bare `by` "
            "(tactic block dropped at extraction). Top-level named substantive "
            "frontier haves over the 633 wide-frontier targets."
        ),
        "n_targets_with_named_haves": n_t,
        "n_missing_record": missing,
        "named_substantive_haves": named_total,
        "body_capture": {
            "captured": captured,
            "captured_frac": round(captured / named_total, 4) if named_total else None,
            "elided_bare_by": elided,
            "elided_frac": round(elided / named_total, 4) if named_total else None,
        },
        "pi_leaf_fine_renderability": {
            "note": "pi_leaf keeps `have name : type := body` -> needs a captured body for EVERY named have",
            "targets_fully_renderable": leaf_full,
            "targets_fully_renderable_frac": round(leaf_full / n_t, 4) if n_t else None,
            "targets_partial": leaf_partial,
            "targets_none_renderable": leaf_none,
            "mean_per_target_capture_frac": round(statistics.mean(leaf_capture_fracs), 4) if leaf_capture_fracs else None,
            "median_per_target_capture_frac": round(statistics.median(leaf_capture_fracs), 4) if leaf_capture_fracs else None,
        },
        "pi_root_rough_renderability": {
            "note": ("pi_root inlines: INDEPENDENT haves drop the header (no body needed, "
                     "renderable regardless of elision); only SIBLING-REFERENCED haves need "
                     "the body substituted, so pi_root is blocked ONLY by sibling-referenced "
                     "haves whose body is elided"),
            "independent_haves_header_drop": indep_total,
            "independent_haves_frac": round(indep_total / named_total, 4) if named_total else None,
            "sibling_referenced_haves": ref_total,
            "sibling_referenced_with_elided_body": ref_elided,
            "pi_root_blocked_haves_frac_of_named": round(ref_elided / named_total, 4) if named_total else None,
            "targets_fully_renderable": root_full,
            "targets_fully_renderable_frac": round(root_full / n_t, 4) if n_t else None,
        },
        "per_area_body_capture": {
            a: {"named": area_named[a], "captured": area_captured[a],
                "frac": round(area_captured[a] / area_named[a], 2)}
            for a, _ in area_named.most_common()
        },
        "caveats": (
            "have_tree records contain ONLY the named have nodes, NOT the residual "
            "main proof body around them; so even a fully-body-captured target is "
            "not runnable Lean from data/deep -- the residual tactic block is absent "
            "for ALL 633. The Modal re-extraction must recover (a) the residual for "
            "every target AND (b) the elided have bodies counted here; this gate "
            "scopes (b) only. Sibling-reference detection sees sibling bodies+types "
            "only (residual->have refs unobservable), so sibling_referenced and "
            "pi_root blockers are LOWER bounds. Data-level only; no Lean/Modal/"
            "round-trip; no verified pairs."
        ),
    }

    out = Path(args.out)
    out.write_text(json.dumps(report, indent=2))

    bc = report["body_capture"]
    pl = report["pi_leaf_fine_renderability"]
    pr = report["pi_root_rough_renderability"]
    print(f"named substantive frontier haves: {named_total} over {n_t} targets")
    print(f"  body CAPTURED: {captured} ({bc['captured_frac']:.1%})  "
          f"ELIDED bare-by: {elided} ({bc['elided_frac']:.1%})")
    print(f"pi_leaf (fine): fully-renderable targets {leaf_full}/{n_t} "
          f"({pl['targets_fully_renderable_frac']:.1%}); partial {leaf_partial}; none {leaf_none}; "
          f"mean per-target capture {pl['mean_per_target_capture_frac']:.1%}")
    print(f"pi_root (rough): independent header-drops {indep_total} ({pr['independent_haves_frac']:.1%}); "
          f"sibling-ref {ref_total}, of which elided (blockers) {ref_elided} "
          f"({pr['pi_root_blocked_haves_frac_of_named']:.1%} of named); "
          f"fully-renderable targets {root_full}/{n_t} ({pr['targets_fully_renderable_frac']:.1%})")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
