"""Substitution-severity gate for the same-format pi_root inliner (q-0007, q-0008).

Question this answers WITHOUT spending Modal credit:
  e-0033/a-0032 split the 2,225 named substantive frontier haves of the deep
  corpus into 1,941 (87.2%) SIMPLE-DROP (independent) and 284 (12.8%)
  SUBSTITUTION-REQUIRED (referenced by a sibling) -- "the one real difficulty"
  hiding behind the same-format build. But a-0032 only counted WHICH haves need
  substitution; it never quantified how BAD substitution is. Two things were
  silently assumed by the whole same-format chain:

    (i)  the e-0033 reference serializer models pi_root as "drop header, keep the
         body ONCE" (rough_lines.append("  " + body)). That is correct ONLY for
         the independent subset. For a sibling-referenced have, a SOUND inliner
         must SUBSTITUTE the body at every use site -- so if the name is used K
         times, pi_root carries K copies of the body, not one.

    (ii) every length argument (e-0027 header delta, e-0033 +173-char mean "fine
         adds over rough", and the q-0008 length-covariate design) rests on
         "pi_root is the MORE COMPRESSED policy" -- pi_leaf only ADDS the named
         headers. For substitution-required haves that direction can INVERT:
         duplicating a long body across >=2 sites can make pi_root LONGER than
         pi_leaf, flipping the sign of the length confound on exactly the subset
         the header-delta estimate ignores.

  This script measures the SEVERITY of substitution, over the SAME 633 deep
  wide-frontier targets:

    1. REFERENCE MULTIPLICITY. For each sibling-referenced named have, count the
       number of occurrences of its name across sibling bodies+types (use sites
       a sound inliner must rewrite). 1 site vs >=2 sites is the line between
       "roughly length-neutral substitution" and "genuine body duplication".

    2. LENGTH DIRECTION. For the subset whose body is OBSERVABLE (term-mode, not
       elided to `by`), compute the per-have net char delta of a SOUND inliner:

         delta_root_minus_leaf =
             n_occ * (len(body) + 2 - len(name))     # each use site: (body) replaces name
             - header_len                            # pi_leaf's `have name : T := body` removed

       delta > 0  => pi_root LONGER than pi_leaf for that have (compression INVERTS).
       Report how many of the observable substitution-required haves invert, and
       the realized net delta distribution -- the correction e-0033's drop-only
       serializer omits.

  If multiplicity is ~1 and inversions are rare, the +173-char "rough is shorter"
  framing survives substitution and the same-format build stays well-defined and
  cheap (a-0032 holds with a small correction). If >=2-site duplication is common
  and many haves invert, the length confound has a SECOND, opposite-sign
  component on the 12.8% subset that the q-0008 covariate design must model.

  CAVEATS: data-level only -- no Lean/Modal/round-trip/verified pairs. Sibling-to-
  sibling references only (residual->have refs unobservable: deep main bodies are
  elided), so multiplicity and the substitution count are LOWER bounds (same
  ceiling as e-0033). Length direction is computed only on the OBSERVABLE-body
  subset (term-mode); `by`-elided bodies have unknown length and are reported
  separately as unquantifiable. Char proxy for tokens (4 char/tok), as e-0010/27.

Inputs (local, already on disk):
  data/corpus_v3/deep_wide_targets.json  -- 633 wide-frontier targets (e-0016)
  data/deep/<Module>.json                -- have_tree records (named subgoals)

  python3 data/analyze_deep_substitution_severity.py [--out path.json]
"""

from __future__ import annotations
import argparse, collections, json, re, statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ROOT / "data/corpus_v3/deep_wide_targets.json"
DEEP_DIR = ROOT / "data/deep"
CHARS_PER_TOK = 4.0


def deep_path(module: str) -> Path:
    stem = module.removeprefix("Mathlib.").replace(".", "__")
    return DEEP_DIR / f"{stem}.json"


def top_area(module: str) -> str:
    parts = module.split(".")
    return parts[1] if module.startswith("Mathlib.") and len(parts) > 1 else parts[0]


def substantive(node: dict) -> bool:
    """Frontier node with its own proof body (e-0032/e-0033 definition)."""
    return (node.get("body") or "").strip() != ""


def body_observable(node: dict) -> bool:
    """Term-mode body whose length is meaningful; elided `by...` bodies are not."""
    b = (node.get("body") or "").strip()
    return bool(b) and b != "by" and not b.startswith("by ")


def header_len(name: str, typ: str, body: str) -> int:
    """`have <name> : <type> := <body>` text length pi_leaf carries, pi_root drops."""
    return len("have ") + len(name) + (len(" : ") + len(typ) if typ else 0) + len(" := ") + len(body)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data/deep_substitution_severity.json"))
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
    named_total = 0                # named substantive haves (matches e-0033: 2225)
    referenced = 0                 # sibling-referenced (matches e-0033: 284, lower bound)
    multiplicity = []              # n_occ per referenced have (>=1)
    mult_hist = collections.Counter()
    # length-direction, observable-body subset of the referenced haves:
    obs_ref = 0
    obs_inverts = 0                # pi_root LONGER (delta_root_minus_leaf > 0)
    net_deltas = []                # sound-inliner net char delta, per observable referenced have
    elided_ref = 0                 # referenced but body elided -> length unquantifiable
    area_ref = collections.Counter()
    area_invert = collections.Counter()
    sample = []

    for t in targets:
        rec = next((r for r in records(t["module"]) if r["name"] == t["name"]), None)
        if rec is None:
            missing += 1
            continue
        nodes = rec["have_tree"]
        names = [(n.get("name") or "").strip() for n in nodes]
        area = top_area(t["module"])

        for i, n in enumerate(nodes):
            if not substantive(n):
                continue
            nm = names[i]
            if nm in ("", "_"):
                continue
            named_total += 1
            pat = re.compile(r"(?<![\w.])" + re.escape(nm) + r"(?![\w])")
            n_occ = 0
            for j, m2 in enumerate(nodes):
                if j == i:
                    continue
                txt = (m2.get("body") or "") + " " + (m2.get("type") or "")
                n_occ += len(pat.findall(txt))
            if n_occ == 0:
                continue
            # sibling-referenced -> substitution-required
            referenced += 1
            area_ref[area] += 1
            multiplicity.append(n_occ)
            mult_hist[min(n_occ, 5)] += 1  # bucket 5+ together

            body = (n.get("body") or "").strip()
            typ = (n.get("type") or "").strip()
            if body_observable(n):
                obs_ref += 1
                hlen = header_len(nm, typ, body)
                delta = n_occ * (len(body) + 2 - len(nm)) - hlen
                net_deltas.append(delta)
                if delta > 0:
                    obs_inverts += 1
                    area_invert[area] += 1
                    if len(sample) < 4:
                        sample.append({
                            "decl": t["name"], "module": t["module"], "have": nm,
                            "n_ref_sites": n_occ, "body_len": len(body),
                            "header_len": hlen, "net_delta_root_minus_leaf": delta,
                        })
            else:
                elided_ref += 1

    n_t = named_total
    ref_frac = referenced / n_t if n_t else 0.0
    multi_ge2 = sum(1 for m in multiplicity if m >= 2)
    invert_frac_obs = obs_inverts / obs_ref if obs_ref else 0.0
    # share of ALL named haves that demonstrably invert compression direction
    invert_frac_all = obs_inverts / n_t if n_t else 0.0

    report = {
        "description": (
            "Substitution-severity gate refining e-0033/a-0032 over the 633 deep "
            "wide-frontier targets. Quantifies how bad the 12.8% substitution-"
            "required subset is: reference multiplicity (use sites a sound inliner "
            "must rewrite) and the per-have net char delta of a SOUND pi_root "
            "inliner (body duplicated at each site), revealing where pi_root "
            "becomes LONGER than pi_leaf -- the opposite-sign length component the "
            "e-0033 drop-only serializer and the +173-char header-delta omit."
        ),
        "n_named_substantive_haves": n_t,
        "n_substitution_required": referenced,
        "substitution_required_frac": round(ref_frac, 4),
        "reference_multiplicity": {
            "note": "occurrences of the have-name across sibling bodies+types (sound-inliner rewrite sites); lower bound",
            "median": round(statistics.median(multiplicity), 1) if multiplicity else None,
            "mean": round(statistics.mean(multiplicity), 2) if multiplicity else None,
            "max": max(multiplicity) if multiplicity else None,
            "n_with_ge2_sites": multi_ge2,
            "frac_of_referenced_ge2_sites": round(multi_ge2 / referenced, 4) if referenced else None,
            "histogram_n_sites": {str(k) + ("+" if k == 5 else ""): mult_hist[k] for k in sorted(mult_hist)},
        },
        "length_direction_observable_body": {
            "note": ("sound-inliner net char delta = n_occ*(len(body)+2-len(name)) - header_len; "
                     ">0 means pi_root LONGER than pi_leaf (compression INVERTS). Observable "
                     "(term-mode) bodies only; elided `by` bodies unquantifiable."),
            "n_observable_referenced": obs_ref,
            "n_elided_referenced_unquantifiable": elided_ref,
            "n_invert_root_longer": obs_inverts,
            "invert_frac_of_observable_referenced": round(invert_frac_obs, 4),
            "invert_frac_of_all_named_haves": round(invert_frac_all, 4),
            "net_delta_chars": {
                "median": round(statistics.median(net_deltas), 1) if net_deltas else None,
                "mean": round(statistics.mean(net_deltas), 1) if net_deltas else None,
                "p90": round(sorted(net_deltas)[int(0.9 * (len(net_deltas) - 1))], 1) if net_deltas else None,
                "max": max(net_deltas) if net_deltas else None,
                "min": min(net_deltas) if net_deltas else None,
            },
        },
        "per_area_substitution": {
            a: {"substitution_required": area_ref[a], "inverts": area_invert[a]}
            for a, _ in area_ref.most_common()
        },
        "sample_inversions": sample,
        "caveats": (
            "Data-level only; no Lean/Modal/round-trip. Sibling-to-sibling refs "
            "only (residual->have refs unobservable: deep main bodies elided), so "
            "multiplicity and the substitution count are LOWER bounds. Length "
            "direction computed only on the observable (term-mode) body subset; "
            "elided `by` bodies reported separately as unquantifiable. Char/4 token "
            "proxy. A sound rendered build still needs Modal re-extraction."
        ),
    }

    Path(args.out).write_text(json.dumps(report, indent=2))

    print(f"substitution-severity gate ({n_t} named substantive haves, {missing} missing records)")
    print("-" * 70)
    print(f"substitution-required (sibling-referenced): {referenced}  ({100*ref_frac:.1f}%)  [lower bound]")
    rm = report["reference_multiplicity"]
    print(f"reference multiplicity: median {rm['median']}, mean {rm['mean']}, max {rm['max']}")
    print(f"  >=2 rewrite sites: {multi_ge2}/{referenced}  ({100*multi_ge2/referenced:.1f}% of referenced)" if referenced else "")
    print(f"  histogram n_sites: {rm['histogram_n_sites']}")
    print()
    ld = report["length_direction_observable_body"]
    print(f"length direction (observable-body referenced haves: {obs_ref}; elided unquantifiable: {elided_ref})")
    print(f"  pi_root LONGER than pi_leaf (compression INVERTS): {obs_inverts}/{obs_ref}"
          f"  ({100*invert_frac_obs:.1f}% of observable referenced; {100*invert_frac_all:.2f}% of all named haves)")
    print(f"  net delta (root-leaf) chars: median {ld['net_delta_chars']['median']}, "
          f"mean {ld['net_delta_chars']['mean']}, p90 {ld['net_delta_chars']['p90']}, max {ld['net_delta_chars']['max']}")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
