"""Decl-level net-length of the same-format build over REAL captured bodies.

Refines e-0038/a-0036 WITHOUT spending Modal credit.

  e-0038 ran the e-0033 same-format serializer over the 7 corpus_v3 full_proofs
  with >=2 real (non-elided) top-level haves and reported a per-HAVE compression-
  inversion rate of 4/13 = 30.8% (a sound pi_root that duplicates a >=2x-referenced
  body becomes LONGER than pi_leaf for that have). That is the right unit for
  reasoning about the inliner, but it is NOT the unit q-0008's length covariate or
  a-0010's "rough serialization is shorter" assumption actually see: the SFT
  training example is the WHOLE decl serialization, so what matters is whether
  pi_root is shorter than pi_leaf summed OVER the decl, and how concentrated the
  inversion is.

  This script reuses e-0038's parser (top_level_haves / count_downstream_refs)
  and aggregates the per-have net (pi_root_len - pi_leaf_len) to the DECL level:

    decl_net = sum over inline-able named haves of [ refs*body_len - (header_len + body_len) ]

  and reports, per decl and in aggregate:
    1. how many decls are pi_root-LONGER at the decl level (decl-level inversion),
    2. the decl-level net distribution (median / min / max),
    3. how concentrated each decl's net is in its single worst (most-inverting) have
       -- i.e. whether decl-level inversion is driven by one large multiply-
       referenced body or is diffuse.

  This is the decl-level (training-example) analogue of e-0038's per-have rate.

  HONEST SCOPE: same N=7 foundational-module corpus_v3 full_proofs as e-0038 (the
  only on-disk source of real, non-elided multi-have bodies; corpus_v2 full_proofs
  are byte-identical, 0 incremental decls); same heuristic indentation parse, no
  Lean elaboration, textual ref counts, crude full-body-duplication net model.
  Decl-level over 6 inline-able decls is an even smaller sample than the 13 haves
  -- this ANCHORS the unit/direction, it is not a corpus-scale estimate. The
  corpus-scale figure still needs e-0037's Modal extract_full_proofs re-run.

  python3 data/analyze_realbody_decl_level.py [--out path.json] [--show]
"""
import argparse
import json

from analyze_realbody_same_format import load_multihave, count_downstream_refs


def have_net(h):
    """pi_root_len - pi_leaf_len for one inline-able named have (e-0038 model)."""
    r = h["refs"]
    return r * h["body_len"] - (h["header_len"] + h["body_len"])


def med(xs):
    if not xs:
        return None
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/realbody_decl_level.json")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()

    decls = load_multihave(min_haves=2)
    per_decl = []
    for name, module, proof, blocks in decls:
        scored = count_downstream_refs(proof, blocks)
        inlineable = [h for h in scored
                      if h["kind"] in ("named", "anon_this") and h["refs"] is not None]
        if not inlineable:
            # all haves are destructuring binders -> no granularity unit, net 0
            per_decl.append({"decl": name, "module": module, "n_inlineable": 0,
                             "decl_net": 0, "worst_have_net": 0,
                             "n_inverting_haves": 0})
            continue
        nets = [have_net(h) for h in inlineable]
        decl_net = sum(nets)
        worst = max(nets)  # most positive = most pi_root-longer
        per_decl.append({
            "decl": name, "module": module,
            "n_inlineable": len(inlineable),
            "decl_net": decl_net,
            "worst_have_net": worst,
            # fraction of a positive decl_net explained by its single worst have
            "worst_share": (worst / decl_net) if decl_net > 0 else None,
            "n_inverting_haves": sum(1 for h in inlineable if h["refs"] >= 2),
        })

    with_units = [d for d in per_decl if d["n_inlineable"] > 0]
    decl_nets = [d["decl_net"] for d in with_units]
    root_longer = [d for d in with_units if d["decl_net"] > 0]
    # decls pi_root-longer whose inversion is concentrated in ONE have
    concentrated = [d for d in root_longer
                    if d["worst_share"] is not None and d["worst_share"] >= 0.9]

    summary = {
        "n_decls_total": len(per_decl),
        "n_decls_with_inlineable_haves": len(with_units),
        "decl_level_net_pi_root_minus_pi_leaf": {
            "median": med(decl_nets),
            "min": min(decl_nets) if decl_nets else None,
            "max": max(decl_nets) if decl_nets else None,
            "all_sorted": sorted(decl_nets),
        },
        "n_decls_pi_root_longer": len(root_longer),
        "decl_level_inversion_rate": (len(root_longer) / len(with_units)) if with_units else None,
        "n_root_longer_decls_concentrated_in_one_have": len(concentrated),
        "per_have_inversion_rate_e0038": "4/13 = 0.308 (for cross-reference)",
    }

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if args.show:
        for d in sorted(per_decl, key=lambda x: -x["decl_net"]):
            print(f"  net={d['decl_net']:+5d}  worst_have={d['worst_have_net']:+4d}  "
                  f"n_inl={d['n_inlineable']}  inv_haves={d['n_inverting_haves']}  {d['decl']}")

    out = {"summary": summary, "per_decl": per_decl}
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
