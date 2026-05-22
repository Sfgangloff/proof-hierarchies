"""
Stage 0.5 data prep — split corpus_v3/pairs.jsonl into per-policy
train/dev/test JSONLs for QLoRA SFT.

  python data/build_sft.py

Split: 80/10/10 stratified by module (so per-module proportions are
preserved across all three splits). Same theorem indices used for both
policies — paired comparison at eval requires identical splits.

Output:
  data/corpus_v3/sft/rough/{train,dev,test}.jsonl
  data/corpus_v3/sft/fine/{train,dev,test}.jsonl
  data/corpus_v3/sft/split_index.json   -- declName→split, for reproducibility

Row schema: {declName, module, prompt, completion}
  prompt     = "theorem <declName> : <type> "
  completion = <fine ':= by …'>  OR  <rough ':= <term>'>
"""

import json
import pathlib
import random
from collections import defaultdict

ROOT = pathlib.Path(__file__).parent / "corpus_v3"
PAIRS = ROOT / "pairs.jsonl"
SFT = ROOT / "sft"
SEED = 42
TRAIN_FRAC, DEV_FRAC = 0.8, 0.1  # test = remainder


def split_module(names: list[str], rng: random.Random) -> dict[str, str]:
    """Deterministic 80/10/10 split of one module's declNames."""
    shuffled = names[:]
    rng.shuffle(shuffled)
    n = len(shuffled)
    n_train = int(round(n * TRAIN_FRAC))
    n_dev = int(round(n * DEV_FRAC))
    out = {}
    for i, name in enumerate(shuffled):
        if i < n_train:
            out[name] = "train"
        elif i < n_train + n_dev:
            out[name] = "dev"
        else:
            out[name] = "test"
    return out


def main():
    pairs = [json.loads(l) for l in PAIRS.read_text().splitlines() if l.strip()]
    print(f"loaded {len(pairs)} pairs")

    by_module: dict[str, list[dict]] = defaultdict(list)
    for p in pairs:
        by_module[p["module"]].append(p)

    rng = random.Random(SEED)
    split_index: dict[str, str] = {}
    for mod in sorted(by_module):
        names = [p["declName"] for p in by_module[mod]]
        mod_split = split_module(names, rng)
        split_index.update(mod_split)

    # Materialise per-policy/split JSONLs.
    SFT.mkdir(exist_ok=True)
    for policy in ("rough", "fine"):
        (SFT / policy).mkdir(exist_ok=True)
        per_split = defaultdict(list)
        for p in pairs:
            split = split_index[p["declName"]]
            # prompt is the theorem signature; completion is the proof body
            # (`:= by …` for fine, `:= <term>` for rough). Keep `:=` in the
            # completion so the model learns where the proof starts.
            prompt = f"theorem {p['declName']} : {p['type']} "
            if policy == "fine":
                completion = p["fine"]                  # already starts with ':= by'
            else:
                completion = f":= {p['rough']}"
            per_split[split].append({
                "declName":   p["declName"],
                "module":     p["module"],
                "prompt":     prompt,
                "completion": completion,
            })
        for split, rows in per_split.items():
            out = SFT / policy / f"{split}.jsonl"
            with open(out, "w") as f:
                for r in rows:
                    f.write(json.dumps(r) + "\n")
            print(f"  {policy}/{split}.jsonl: {len(rows)}")

    (SFT / "split_index.json").write_text(json.dumps(split_index, indent=2))

    # Stratification report.
    tally = defaultdict(lambda: defaultdict(int))
    for name, split in split_index.items():
        for p in pairs:
            if p["declName"] == name:
                tally[p["module"]][split] += 1
                break
    print("\nstratification (per-module split sizes):")
    for mod in sorted(tally):
        t = tally[mod]
        n = sum(t.values())
        print(f"  {mod:55s}  train={t['train']:3d}  dev={t['dev']:2d}  test={t['test']:2d}  (n={n})")


if __name__ == "__main__":
    main()
