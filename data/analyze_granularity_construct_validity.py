"""Construct-validity gate for q-0007 (the headline rough-vs-fine SFT claim).

Question this answers WITHOUT spending Modal credit:
  q-0007 asks whether SFT on the ROUGH corpus vs the FINE corpus produces a
  held-out pass@k gap that we may read as a *decomposition-granularity* effect.
  But on data/corpus_v3 the two policies are built (data/build_pairs.py) as:
      rough = the verified ELABORATED PROOF TERM   (term-mode, `fun ... => ...`)
      fine  = the ORIGINAL TACTIC SOURCE           (tactic-mode, `:= by ...`)
  So the rough/fine axis conflates TWO things:
      (1) SERIALIZATION FORMAT   term-mode vs tactic-mode
      (2) DECOMPOSITION GRANULARITY   haves inlined vs haves kept as named steps
  These two only separate where the proof actually CONTAINS named have-steps.
  For a FLAT proof (zero named haves) there is nothing to inline-or-keep, so the
  rough/fine pair differs by FORMAT ALONE -- a granularity contrast in name only.

  This script quantifies, per pair, whether the contrast carries any genuine
  decomposition signal (>=1 named have) or is format-only, and looks at the
  fine completions directly (do they even contain a `have`?). If almost all
  pairs are format-only, then a measured rough/fine pass@k gap on corpus_v3
  would chiefly validate a *format* effect (term vs tactic), NOT a granularity
  effect -- a construct-validity threat the eventual Modal SFT must confront,
  separate from the length confound (a-0010) and the supply ceiling (e-0012).

Inputs (local, already on disk):
  data/corpus_v3/pairs.jsonl       -- 607 verified pairs (declName, rough, fine)
  data/corpus_v2/corpus/*.jsonl    -- have-tree records (have_nodes[])

  python3 -m data.analyze_granularity_construct_validity [--out path.json]
"""

from __future__ import annotations
import argparse, glob, json, re
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[1]
PAIRS = ROOT / "data/corpus_v3/pairs.jsonl"
HAVE_TREES_DIR = ROOT / "data/corpus_v2/corpus"

# whole-word `have` in a tactic block (the textual decomposition marker a
# model would learn to emit). Lean tactic haves are `have name : T := ...`.
HAVE_RE = re.compile(r"(?<![A-Za-z0-9_.])have(?![A-Za-z0-9_])")


def load_pairs() -> list[dict]:
    out = []
    for line in open(PAIRS):
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        if d.get("declName"):
            out.append(d)
    return out


def load_have_index() -> dict[str, list[dict]]:
    idx: dict[str, list[dict]] = {}
    for path in sorted(glob.glob(str(HAVE_TREES_DIR / "*.jsonl"))):
        for line in open(path):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "declName" in d:
                idx[d["declName"]] = d.get("have_nodes", []) or []
    return idx


def named_have_count(nodes: list[dict]) -> int:
    """count have-nodes that carry a real user name + a type (the frontier a
    granularity contrast could actually expose). Mirrors e-0012/e-0014."""
    n = 0
    for hn in nodes:
        name = (hn.get("userName") or hn.get("name") or "").strip()
        ptype = (hn.get("ppType") or hn.get("type") or "").strip()
        if name and name != "_" and ptype:
            n += 1
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data/corpus_v3/granularity_construct_validity.json"))
    args = ap.parse_args()

    pairs = load_pairs()
    have_idx = load_have_index()
    n = len(pairs)

    format_only = 0          # zero named haves -> rough/fine differ by format alone
    granularity_bearing = 0  # >=1 named have -> contrast carries decomposition signal
    nontrivial = 0           # >=2 named haves -> a real >=2 frontier
    fine_has_have_text = 0   # fine completion literally contains a tactic `have`
    rough_has_have_text = 0  # rough (term) completion literally contains `have`
    missing_havetree = 0

    # cross-check: of the format-only pairs, how many fine completions are
    # genuinely flat one-liners (no `have` in text) -- the contrast there is
    # unambiguously serialization-only.
    format_only_and_flat_fine = 0

    examples_granularity = []
    for d in pairs:
        name = d["declName"]
        rough = d.get("rough", "") or ""
        fine = d.get("fine", "") or ""
        nodes = have_idx.get(name)
        if nodes is None:
            missing_havetree += 1
            nodes = []
        nh = named_have_count(nodes)

        f_have = bool(HAVE_RE.search(fine))
        r_have = bool(HAVE_RE.search(rough))
        if f_have:
            fine_has_have_text += 1
        if r_have:
            rough_has_have_text += 1

        if nh >= 1:
            granularity_bearing += 1
            if nh >= 2:
                nontrivial += 1
            if len(examples_granularity) < 8:
                examples_granularity.append({"decl": name, "named_haves": nh,
                                             "fine_has_have": f_have})
        else:
            format_only += 1
            if not f_have:
                format_only_and_flat_fine += 1

    summary = {
        "n_pairs": n,
        "missing_havetree": missing_havetree,
        "rough_is_termmode": "rough = elaborated proof term; fine = original tactic source (build_pairs.py)",
        "format_only_pairs": format_only,
        "format_only_frac": round(format_only / n, 4),
        "granularity_bearing_pairs": granularity_bearing,
        "granularity_bearing_frac": round(granularity_bearing / n, 4),
        "nontrivial_frontier_pairs_ge2": nontrivial,
        "nontrivial_frontier_frac": round(nontrivial / n, 4),
        "fine_completion_contains_have": fine_has_have_text,
        "fine_completion_contains_have_frac": round(fine_has_have_text / n, 4),
        "rough_completion_contains_have": rough_has_have_text,
        "format_only_AND_flat_fine_text": format_only_and_flat_fine,
        "format_only_AND_flat_fine_frac": round(format_only_and_flat_fine / n, 4),
        "examples_granularity_bearing": examples_granularity,
        "interpretation": (
            "On corpus_v3 the rough/fine SFT axis confounds serialization "
            "format (term vs tactic) with decomposition granularity; the two "
            "separate only on the granularity-bearing pairs. The format-only "
            "fraction is the share of the contrast that carries NO decomposition "
            "signal -- there a measured pass@k gap is a format effect, not a "
            "granularity effect."
        ),
    }

    print(json.dumps(summary, indent=2))
    Path(args.out).write_text(json.dumps(summary, indent=2))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
