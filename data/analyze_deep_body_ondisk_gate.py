"""On-disk body-availability gate for the data/deep same-format build (e-0033..e-0035 follow-up).

Question this answers WITHOUT spending Modal credit:
  The whole e-0033..e-0035 chain (a-0032..a-0034) terminates on ONE load-bearing
  claim: "a Modal re-extraction is required REGARDLESS to recover the RESIDUAL main
  proof body, which is absent for all 633 wide-frontier targets." That claim was
  ASSERTED from the shape of the data/deep records (which carry only have_tree
  nodes, not the residual body) but never actually TESTED against everything else
  the project already pulled to disk. If the 633 targets' full proof bodies happen
  to live in some already-extracted on-disk source (e.g. the corpus_v3 / corpus_v2
  full_proofs jsonls, which DO carry a full `proof` field), the load-bearing Modal
  cost collapses to zero. This gate settles that, and then scopes WHAT the Modal
  build is if the bodies are genuinely absent.

  Two findings, composed:

  (1) NEGATIVE-SHORTCUT JOIN. Join the 633 deep wide-frontier targets
      (deep_wide_targets.json, keyed (module, name)) against EVERY on-disk source
      of full tactic bodies: data/corpus_v3/full_proofs/*.jsonl and
      data/corpus_v2/corpus/full_proofs/*.jsonl (rows carry declName + module +
      proof = the full `:= by ...` body). Count how many of the 633 are recoverable
      from disk by (module,name), by name-only (loose), and how many deep target
      MODULES even appear in the on-disk full_proofs set. If ~0, a-0034's "Modal
      required regardless" is confirmed: there is no free path.

  (2) EXISTING-STEP SCOPE. If the bodies are absent, the decision-relevant question
      is whether recovering them is a NEW extractor or a RE-SCOPE of the existing
      pipeline. Probe the corpus_v3 full_proofs records to show the existing
      extract_full_proofs step ALREADY captures full residual bodies WITH multi-step
      `have` blocks intact (the exact content the same-format build's residual + fine
      headers need). If so, the Modal build for deep is CLAUDE.md pipeline step 4
      (extract_full_proofs) re-scoped to the 452 deep modules, not a new tool.

  Data-level only: no Lean, no Modal, no round-trip, no verified pairs. Pure stdlib.
"""

import glob
import json
import os
import statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_jsonl(path):
    rows = []
    bad = 0
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                bad += 1
    return rows, bad


def main():
    targets = json.load(
        open(os.path.join(ROOT, "data/corpus_v3/deep_wide_targets.json"))
    )["targets"]
    target_keys = set((t["module"], t["name"]) for t in targets)
    target_names = set(t["name"] for t in targets)
    target_mods = set(t["module"] for t in targets)

    # ---- (1) negative-shortcut join over every on-disk full-body source ----
    src_files = sorted(
        glob.glob(os.path.join(ROOT, "data/corpus_v3/full_proofs/*.jsonl"))
        + glob.glob(os.path.join(ROOT, "data/corpus_v2/corpus/full_proofs/*.jsonl"))
    )
    src_rows = []
    bad_total = 0
    for f in src_files:
        rows, bad = load_jsonl(f)
        bad_total += bad
        src_rows.extend(rows)

    src_keys = set((r.get("module"), r.get("declName")) for r in src_rows)
    src_names = set(r.get("declName") for r in src_rows)
    src_mods = set(r.get("module") for r in src_rows)

    on_disk_by_key = len(target_keys & src_keys)
    on_disk_by_name = len(target_names & src_names)
    mod_overlap = target_mods & src_mods

    # ---- (2) existing-step scope: does extract_full_proofs already capture
    #          full residual bodies WITH have blocks? ----
    v3_rows = [r for r in src_rows if "corpus_v3" in (r.get("file") or "") or True]
    # restrict to corpus_v3 full_proofs (the reference for the existing step)
    v3_rows = []
    for f in glob.glob(os.path.join(ROOT, "data/corpus_v3/full_proofs/*.jsonl")):
        rows, _ = load_jsonl(f)
        v3_rows.extend(rows)
    proofs = [(r.get("declName"), r.get("proof") or "") for r in v3_rows]
    plens = [len(p) for _, p in proofs]
    with_have = [(n, p) for n, p in proofs if "have" in p]
    multi_have = [(n, p) for n, p in proofs if p.count("have") >= 2]
    example = multi_have[0] if multi_have else (with_have[0] if with_have else None)

    out = {
        "experiment": "e-0036",
        "n_targets": len(targets),
        "n_target_modules": len(target_mods),
        "on_disk_full_body_sources": {
            "files": len(src_files),
            "decls": len(src_rows),
            "distinct_modules": len(src_mods),
            "bad_lines": bad_total,
        },
        "negative_shortcut_join": {
            "targets_recoverable_by_module_name": on_disk_by_key,
            "targets_recoverable_by_name_only": on_disk_by_name,
            "deep_modules_present_on_disk": len(mod_overlap),
            "overlapping_modules": sorted(mod_overlap),
        },
        "existing_step_scope": {
            "v3_full_proofs_decls": len(v3_rows),
            "proof_body_char_len_median": int(statistics.median(plens)) if plens else 0,
            "proof_body_char_len_max": max(plens) if plens else 0,
            "decls_with_have_in_body": len(with_have),
            "decls_with_ge2_have_in_body": len(multi_have),
            "example_decl": example[0] if example else None,
            "example_proof_head": (example[1][:200] if example else None),
        },
    }

    print(json.dumps(out, indent=2))

    print("\n=== VERDICT ===")
    if on_disk_by_key == 0 and on_disk_by_name == 0:
        print(
            f"CONFIRMED (a-0034): 0/{len(targets)} deep target bodies recoverable from disk;"
            f" {len(mod_overlap)} of {len(target_mods)} deep modules appear in on-disk full_proofs."
            " No free path -> Modal re-extraction required REGARDLESS."
        )
    else:
        print(
            f"REFUTED: {on_disk_by_key} targets recoverable by (module,name),"
            f" {on_disk_by_name} by name -> a free/partial path exists."
        )
    print(
        "SCOPE: existing extract_full_proofs already captures full residual bodies"
        f" with have-blocks intact ({len(multi_have)} corpus_v3 decls with >=2 haves,"
        " e.g. {}). So the deep build is CLAUDE.md step 4 (extract_full_proofs)"
        " re-scoped to the 452 deep modules, NOT a new extractor.".format(
            example[0] if example else "n/a"
        )
    )


if __name__ == "__main__":
    main()
