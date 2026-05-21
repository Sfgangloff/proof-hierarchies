"""
Stage 0c output — join verified term-mode proofs with original tactic
source to produce the binary-granularity (rough, fine) corpus.

  python data/build_pairs.py

For each declName that appears in all three sources, where:
  - verify/<M>.json[declName] == "pass"  (round-trip elaborates)
  - full_proofs/<M>.jsonl `proof` starts with ':= by'  (real tactic block)

emit {module, declName, type, fine, rough, levels} to
data/corpus_v3/pairs.jsonl, plus a per-module + overall summary.
"""

import json
import pathlib
from collections import defaultdict

ROOT = pathlib.Path(__file__).parent / "corpus_v3"
OUT = ROOT / "pairs.jsonl"
SUMMARY = ROOT / "pairs_summary.json"


def load_jsonl(path):
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def main():
    pt_dir = ROOT / "proof_terms"
    fp_dir = ROOT / "full_proofs"
    vf_dir = ROOT / "verify"

    pt_modules = {p.stem for p in pt_dir.glob("Mathlib.*.jsonl")}
    fp_modules = {p.stem for p in fp_dir.glob("Mathlib.*.jsonl")}
    vf_modules = {p.stem for p in vf_dir.glob("Mathlib.*.json")}
    modules = sorted(pt_modules & fp_modules & vf_modules)

    print(f"proof_terms modules: {len(pt_modules)}")
    print(f"full_proofs modules: {len(fp_modules)}")
    print(f"verify modules:      {len(vf_modules)}")
    print(f"  intersection:      {len(modules)}")
    print(f"  pt-only:           {sorted(pt_modules - fp_modules - vf_modules)}")
    print(f"  fp-only:           {sorted(fp_modules - pt_modules)}")

    per_module = []
    total_pairs = 0
    with open(OUT, "w") as fout:
        for mod in modules:
            verify = json.loads((vf_dir / f"{mod}.json").read_text())["results"]
            rough = {r["declName"]: r for r in load_jsonl(pt_dir / f"{mod}.jsonl")}
            fine = {r["declName"]: r for r in load_jsonl(fp_dir / f"{mod}.jsonl")}

            n_verified = sum(1 for v in verify.values() if v == "pass")
            n_tactic_fp = sum(1 for r in fine.values()
                              if r.get("proof", "").lstrip().startswith(":= by"))

            kept = 0
            for name, status in verify.items():
                if status != "pass":
                    continue
                pt = rough.get(name)
                fp = fine.get(name)
                if pt is None or fp is None:
                    continue
                proof = fp.get("proof", "").lstrip()
                if not proof.startswith(":= by"):
                    continue
                fout.write(json.dumps({
                    "module":   mod,
                    "declName": name,
                    "type":     pt.get("type", ""),
                    "levels":   pt.get("levels", []),
                    "fine":     proof,
                    "rough":    pt.get("term", ""),
                }) + "\n")
                kept += 1
            total_pairs += kept
            per_module.append({
                "module": mod,
                "verified_rough": n_verified,
                "tactic_fine": n_tactic_fp,
                "pairs": kept,
            })
            print(f"  {mod}: verified={n_verified}  tactic_fp={n_tactic_fp}  pairs={kept}")

    summary = {"total_pairs": total_pairs, "per_module": per_module}
    SUMMARY.write_text(json.dumps(summary, indent=2))
    print(f"\nTOTAL PAIRS: {total_pairs}  →  {OUT.relative_to(pathlib.Path.cwd())}")


if __name__ == "__main__":
    main()
