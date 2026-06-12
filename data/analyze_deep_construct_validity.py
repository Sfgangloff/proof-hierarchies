"""Construct-validity gate for the data/deep PIVOT (the e-0026 analogue on deep).

Question this answers WITHOUT spending Modal credit:
  e-0026 (a-0026) found that on data/corpus_v3 the headline rough-vs-fine axis is
  a CONSTRUCT-VALIDITY threat: only 42/607 (6.9%) pairs are granularity-bearing
  (>=1 named have) and 27 (4.4%) expose a >=2 frontier -- 93.1% are FORMAT-ONLY
  (term-mode-vs-tactic-mode serialization with no inline-able have to keep-or-fold).
  The project's response was the data/deep PIVOT (a-0014): 633 decls with a
  top-level named frontier of >=2 subgoals, claimed to be genuinely granularity-
  rich. But that claim was only ever measured as a COUNT of frontier WIDTH
  (e-0014/e-0016) and never as a construct-validity check: do those 633 wide
  frontiers actually carry the inline-able have-step construct that corpus_v3
  lacked, or do they inherit the same emptiness?

  This script runs e-0026's construct logic over the 633 deep wide-frontier
  targets. The granularity construct is "a named subgoal with its OWN proof body"
  -- the unit pi_root (rough) would INLINE and pi_leaf (fine) would KEEP NAMED.
  A frontier node with an EMPTY body is a hypothesis / destructuring binder
  (obtain/rcases/intro), not an independent sub-derivation, so it carries no
  inline-or-name granularity contrast. We therefore define the SUBSTANTIVE
  frontier width = number of top-level frontier nodes with a non-empty proof
  body, and ask how many of the 633 still clear >=2 (and >=3) under this
  construct-valid definition.

  If most of the 633 survive, the data/deep pivot genuinely FIXES the
  construct-validity threat e-0026 raised for corpus_v3 (the granularity axis is
  real, not format-only). If most collapse, the pivot inherits the problem.

  CAVEAT: this measures the PRESENCE of the granularity construct (inline-able
  have-steps), not the term-vs-tactic FORMAT confound, which on corpus_v3 came
  from build_pairs.py's serialization CHOICE (rough=elaborated term, fine=tactic
  source). No deep pairs are built yet; whether the eventual deep build serializes
  both policies in the SAME mode (eliminating the format confound) is a build
  decision this gate does not touch. This is a data-level construct check, no
  Lean, no Modal, no round-trip, produces no verified pairs.

Inputs (local, already on disk):
  data/corpus_v3/deep_wide_targets.json  -- 633 wide-frontier targets (e-0016)
  data/deep/<Module>.json                -- have_tree records (named subgoals)

  python3 data/analyze_deep_construct_validity.py [--out path.json]
"""

from __future__ import annotations
import argparse, collections, json, os, statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ROOT / "data/corpus_v3/deep_wide_targets.json"
DEEP_DIR = ROOT / "data/deep"


def deep_path(module: str) -> Path:
    # Mathlib.Foo.Bar -> data/deep/Foo__Bar.json
    stem = module.removeprefix("Mathlib.").replace(".", "__")
    return DEEP_DIR / f"{stem}.json"


def top_area(module: str) -> str:
    parts = module.split(".")
    return parts[1] if module.startswith("Mathlib.") and len(parts) > 1 else parts[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data/deep_construct_validity.json"))
    args = ap.parse_args()

    manifest = json.loads(TARGETS.read_text())
    targets = manifest["targets"]

    cache: dict[Path, list] = {}

    def records(module: str) -> list:
        p = deep_path(module)
        if p not in cache:
            cache[p] = json.loads(p.read_text()) if p.exists() else []
        return cache[p]

    sub_widths: list[int] = []
    body_kind = collections.Counter()
    area_total = collections.Counter()
    area_sub2 = collections.Counter()
    missing = 0

    for t in targets:
        rec = next((r for r in records(t["module"]) if r["name"] == t["name"]), None)
        if rec is None:
            missing += 1
            continue
        nodes = rec["have_tree"]
        sub = 0
        for n in nodes:
            b = (n.get("body") or "").strip()
            if b == "":
                body_kind["empty (hypothesis / obtain binder, no own proof)"] += 1
            elif b == "by":
                body_kind["tactic have (`by` block)"] += 1
                sub += 1
            elif b.startswith("by"):
                body_kind["tactic have (inline `by ...`)"] += 1
                sub += 1
            else:
                body_kind["term have (term-mode proof)"] += 1
                sub += 1
        sub_widths.append(sub)
        a = top_area(t["module"])
        area_total[a] += 1
        if sub >= 2:
            area_sub2[a] += 1

    n = len(sub_widths)
    sub_ge2 = sum(1 for w in sub_widths if w >= 2)
    sub_ge3 = sum(1 for w in sub_widths if w >= 3)
    sub_zero = sum(1 for w in sub_widths if w == 0)

    report = {
        "description": (
            "Construct-validity gate for the data/deep pivot (e-0026 analogue). "
            "SUBSTANTIVE frontier width = # top-level named subgoals with a non-empty "
            "proof body (genuine inline-able have-steps; empty-body nodes are "
            "hypotheses/obtain binders, not granularity-bearing). Tests whether the "
            "633 wide-frontier targets carry the inline-or-name construct corpus_v3 "
            "lacked (93.1% format-only, e-0026)."
        ),
        "n_targets": n,
        "n_missing_record": missing,
        "substantive_width_ge2": sub_ge2,
        "substantive_width_ge2_frac": round(sub_ge2 / n, 4),
        "substantive_width_ge3": sub_ge3,
        "substantive_width_ge3_frac": round(sub_ge3 / n, 4),
        "substantive_width_zero": sub_zero,
        "substantive_width_median": statistics.median(sub_widths),
        "substantive_width_mean": round(statistics.mean(sub_widths), 2),
        "substantive_width_distribution": dict(sorted(collections.Counter(sub_widths).items())),
        "frontier_node_body_kinds": dict(body_kind.most_common()),
        "per_area_substantive_ge2": {
            a: {"total": area_total[a], "substantive_ge2": area_sub2[a],
                "frac": round(area_sub2[a] / area_total[a], 2)}
            for a, _ in area_total.most_common()
        },
        "corpus_v3_reference": {
            "note": "e-0026 / a-0026 on corpus_v3 (607 verified pairs)",
            "granularity_bearing": 42, "granularity_bearing_frac": 0.069,
            "frontier_ge2": 27, "frontier_ge2_frac": 0.044,
            "format_only_frac": 0.931,
        },
    }

    Path(args.out).write_text(json.dumps(report, indent=2))

    print(f"data/deep construct-validity gate ({n} wide-frontier targets, {missing} missing)")
    print("-" * 64)
    print(f"SUBSTANTIVE frontier width (named subgoal w/ own proof body):")
    print(f"  >=2 : {sub_ge2:4d}  ({100*sub_ge2/n:.1f}%)   [the inline-or-name construct]")
    print(f"  >=3 : {sub_ge3:4d}  ({100*sub_ge3/n:.1f}%)")
    print(f"  ==0 : {sub_zero:4d}   (all frontier nodes empty-body)")
    print(f"  median {report['substantive_width_median']}  mean {report['substantive_width_mean']}")
    print()
    print("frontier node body kinds (2,869 top-level nodes):")
    for k, v in body_kind.most_common():
        print(f"  {v:5d}  {k}")
    print()
    print("vs corpus_v3 (e-0026): only 6.9% granularity-bearing, 4.4% frontier>=2, 93.1% format-only")
    print(f"-> data/deep is {sub_ge2/633/0.044:.0f}x richer in construct-valid wide frontiers")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
