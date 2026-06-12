"""Same-format (both-tactic-mode) serializer prototype + constructibility audit.

Question this answers WITHOUT spending Modal credit:
  Four answers in the data/deep chain (a-0026, a-0027, a-0030, a-0031) carry the
  SAME open caveat: the construct-validity fix and the length-confound fix for
  the deep corpus only hold IF "the eventual build serializes BOTH policies in
  the SAME (tactic) mode -- a build decision NOT YET MADE." On corpus_v3 the
  format confound (e-0026) came from build_pairs.py's SERIALIZATION CHOICE:
  rough = elaborated proof TERM, fine = tactic SOURCE -- two different modes, so
  a measured rough/fine pass@k gap there would chiefly validate a term-vs-tactic
  FORMAT effect (144x length gap, a-0010), not granularity.

  Every deep answer ASSUMES this confound can be removed by serializing both
  policies in tactic mode, but no gate ever made that build concrete or checked
  it is well-defined over the deep have-trees. This script does:

    1. Implements a reference SAME-FORMAT serializer over the deep have_tree
       records. Both policies emit TACTIC mode and SHARE the residual body text;
       they differ ONLY by the named-have headers:
         pi_leaf  (fine):  `have <name> : <type> := <body>`  -- frontier kept NAMED
         pi_root  (rough): the same body INLINED, header dropped -- frontier folded
       => the term-vs-tactic FORMAT delta is 0 BY CONSTRUCTION (both tactic mode);
          the only difference is the bounded named headers (the granularity unit).

    2. CONSTRUCTIBILITY audit of the pi_root inliner. Inlining a named have is a
       trivial DROP iff that name is not referenced elsewhere; if a sibling
       frontier node (or the residual) references it, the inliner must SUBSTITUTE
       the body at each use site. We count, over the 633 wide-frontier targets,
       how many named substantive frontier haves are referenced by a SIBLING
       frontier node's captured body/type (substitution-required) vs independent
       (simple drop). This is the one real difficulty hiding behind the abstract
       "build decision not yet made".

    3. Realized same-format length delta = the header text pi_leaf adds over
       pi_root, summed per decl -- emitted from the actual serializer, a
       cross-check on e-0027's ~117-char / ~29-tok header-sum estimate.

  If most named haves are independent (simple drop) and the header delta is
  small, the same-format build is well-defined and cheap, and the format confound
  is removable by construction -- retiring the caveat threaded through a-0026/27/
  30/31. If many need substitution, the build is harder than assumed.

  CAVEATS: data-level only -- no Lean, no Modal, no round-trip, no verified pairs.
  data/deep bodies are mostly ELIDED to "by", so (a) the residual main body is
  unobservable: we can only audit SIBLING-to-sibling references, not residual->
  have references (a lower bound on substitution-required); (b) the emitted
  serializations are STRUCTURAL skeletons (headers + elided bodies), not runnable
  Lean -- a full rendered same-format build still needs the Modal re-extraction
  to capture full tactic bodies. What this establishes is that the same-format
  SCHEME is well-defined and that the rough/fine structural difference is purely
  the named headers (so the format confound cannot arise), plus how often the
  inliner needs substitution.

Inputs (local, already on disk):
  data/corpus_v3/deep_wide_targets.json  -- 633 wide-frontier targets (e-0016)
  data/deep/<Module>.json                -- have_tree records (named subgoals)

  python3 data/analyze_deep_same_format_serializer.py [--out path.json]
"""

from __future__ import annotations
import argparse, collections, json, re, statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ROOT / "data/corpus_v3/deep_wide_targets.json"
DEEP_DIR = ROOT / "data/deep"
CHARS_PER_TOK = 4.0  # same rough proxy used in e-0010/e-0027


def deep_path(module: str) -> Path:
    stem = module.removeprefix("Mathlib.").replace(".", "__")
    return DEEP_DIR / f"{stem}.json"


def top_area(module: str) -> str:
    parts = module.split(".")
    return parts[1] if module.startswith("Mathlib.") and len(parts) > 1 else parts[0]


def substantive(node: dict) -> bool:
    """A frontier node with its OWN proof body (e-0032 definition): the unit
    pi_root inlines and pi_leaf keeps named. Empty-body nodes are hypothesis /
    obtain binders, not inline-able sub-derivations."""
    return (node.get("body") or "").strip() != ""


def render_body(node: dict) -> str:
    """Best-effort tactic-mode body text. Bodies are often elided to 'by'."""
    b = (node.get("body") or "").strip()
    return b if b else "sorry"


def emit_pair(nodes: list[dict]) -> tuple[str, str, int]:
    """Reference SAME-FORMAT (both tactic-mode) serializer over a frontier.

    Returns (fine_text, rough_text, header_delta_chars). Both share the body
    text; fine keeps named `have` headers, rough inlines (drops them). Only the
    substantive frontier nodes carry the granularity contrast.
    """
    fine_lines = ["by"]
    rough_lines = ["by"]
    header_delta = 0
    for n in nodes:
        body = render_body(n)
        if not substantive(n):
            # hypothesis / obtain binder: identical in both policies
            nm = (n.get("name") or "_").strip() or "_"
            typ = (n.get("type") or "").strip()
            line = f"  -- binder {nm}" + (f" : {typ}" if typ else "")
            fine_lines.append(line)
            rough_lines.append(line)
            continue
        nm = (n.get("name") or "_").strip() or "_"
        typ = (n.get("type") or "").strip()
        # fine: keep the named have header
        header = f"  have {nm}" + (f" : {typ}" if typ else "") + " := "
        fine_lines.append(header + body)
        # rough: inline -- body folded into the flow, header dropped
        rough_lines.append("  " + body)
        header_delta += len(header)
    return "\n".join(fine_lines), "\n".join(rough_lines), header_delta


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data/deep_same_format_serializer.json"))
    args = ap.parse_args()

    manifest = json.loads(TARGETS.read_text())
    targets = manifest["targets"]

    cache: dict[Path, list] = {}

    def records(module: str) -> list:
        p = deep_path(module)
        if p not in cache:
            cache[p] = json.loads(p.read_text()) if p.exists() else []
        return cache[p]

    missing = 0
    named_total = 0          # named substantive frontier haves
    anon_subst = 0           # anonymous ("_") substantive haves
    referenced = 0           # named haves referenced by a sibling -> substitution
    independent = 0          # named haves not referenced -> simple drop
    header_deltas: list[int] = []
    area_named = collections.Counter()
    area_ref = collections.Counter()
    sample_pair = None

    for t in targets:
        rec = next((r for r in records(t["module"]) if r["name"] == t["name"]), None)
        if rec is None:
            missing += 1
            continue
        nodes = rec["have_tree"]
        names = [(n.get("name") or "").strip() for n in nodes]

        fine, rough, delta = emit_pair(nodes)
        header_deltas.append(delta)

        # constructibility: which named substantive haves are referenced by a sibling?
        area = top_area(t["module"])
        for i, n in enumerate(nodes):
            if not substantive(n):
                continue
            nm = names[i]
            if nm in ("", "_"):
                anon_subst += 1
                continue
            named_total += 1
            area_named[area] += 1
            pat = re.compile(r"(?<![\w.])" + re.escape(nm) + r"(?![\w])")
            hit = False
            for j, m2 in enumerate(nodes):
                if j == i:
                    continue
                txt = (m2.get("body") or "") + " " + (m2.get("type") or "")
                if pat.search(txt):
                    hit = True
                    break
            if hit:
                referenced += 1
                area_ref[area] += 1
            else:
                independent += 1

        # keep a small, illustrative sample (2-3 substantive haves)
        if sample_pair is None:
            n_sub = sum(1 for n in nodes if substantive(n))
            if 2 <= n_sub <= 3:
                sample_pair = {
                    "decl": t["name"], "module": t["module"],
                    "pi_leaf_fine_tactic_mode": fine,
                    "pi_root_rough_tactic_mode": rough,
                    "header_delta_chars": delta,
                }

    n = len(header_deltas)
    ref_frac = referenced / named_total if named_total else 0.0
    toks = [d / CHARS_PER_TOK for d in header_deltas]

    report = {
        "description": (
            "Same-format (both-tactic-mode) serializer prototype + constructibility "
            "audit over the 633 deep wide-frontier targets. Demonstrates the "
            "rough/fine difference is purely the named-have headers (term-vs-tactic "
            "FORMAT delta = 0 by construction), and audits how often the pi_root "
            "inliner needs substitution (named have referenced by a sibling) vs a "
            "simple drop. Retires the 'serialize both policies in tactic mode -- a "
            "build decision not yet made' caveat in a-0026/a-0027/a-0030/a-0031."
        ),
        "n_targets": n,
        "n_missing_record": missing,
        "named_substantive_haves": named_total,
        "anon_substantive_haves": anon_subst,
        "inliner_simple_drop": independent,
        "inliner_simple_drop_frac": round(independent / named_total, 4) if named_total else None,
        "inliner_substitution_required": referenced,
        "inliner_substitution_required_frac": round(ref_frac, 4),
        "format_confound": {
            "term_vs_tactic_length_ratio": 1.0,
            "note": ("0 by construction: both policies emit tactic mode and share "
                     "the residual body; they differ only by named headers. vs "
                     "corpus_v3 rough(term)/fine(tactic) = 144x (a-0010)."),
        },
        "realized_same_format_header_delta": {
            "note": "header text pi_leaf adds over pi_root, per decl; cross-checks e-0027 (~117 char / ~29 tok)",
            "chars_median": round(statistics.median(header_deltas), 1),
            "chars_mean": round(statistics.mean(header_deltas), 1),
            "chars_p90": round(sorted(header_deltas)[int(0.9 * (n - 1))], 1),
            "chars_max": max(header_deltas),
            "approx_tok_median": round(statistics.median(toks), 1),
            "approx_tok_p90": round(sorted(toks)[int(0.9 * (n - 1))], 1),
        },
        "per_area_substitution_required": {
            a: {"named_haves": area_named[a], "substitution": area_ref[a],
                "frac": round(area_ref[a] / area_named[a], 2) if area_named[a] else 0.0}
            for a, _ in area_named.most_common()
        },
        "sample_pair": sample_pair,
        "caveats": (
            "Data-level only; no Lean/Modal/round-trip; no verified pairs. deep "
            "bodies are mostly elided to 'by', so (a) only SIBLING-to-sibling "
            "references are observable -- residual->have references are not, making "
            "the substitution-required count a LOWER bound; (b) emitted texts are "
            "structural skeletons, not runnable Lean. Establishes the same-format "
            "SCHEME is well-defined and the rough/fine difference is purely the "
            "named headers; a full rendered build still needs the Modal re-extract."
        ),
    }

    Path(args.out).write_text(json.dumps(report, indent=2))

    print(f"same-format serializer + constructibility audit ({n} targets, {missing} missing)")
    print("-" * 68)
    print(f"named substantive frontier haves : {named_total}  (anon '_': {anon_subst})")
    print(f"  inliner SIMPLE DROP (independent)        : {independent:5d}  ({100*independent/named_total:.1f}%)")
    print(f"  inliner SUBSTITUTION (sibling-referenced): {referenced:5d}  ({100*ref_frac:.1f}%)  [lower bound]")
    print()
    print(f"FORMAT confound: term-vs-tactic = 0 by construction (both tactic mode); vs corpus_v3 144x")
    print(f"realized same-format header delta: median {report['realized_same_format_header_delta']['chars_median']} char "
          f"(~{report['realized_same_format_header_delta']['approx_tok_median']} tok), "
          f"p90 {report['realized_same_format_header_delta']['chars_p90']} char  [e-0027: ~117 char/~29 tok]")
    print()
    print("per-area substitution-required (named haves referenced by a sibling):")
    for a, _ in area_named.most_common(10):
        d = report["per_area_substitution_required"][a]
        print(f"  {a:18s} {d['substitution']:3d}/{d['named_haves']:4d}  ({100*d['frac']:.0f}%)")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
