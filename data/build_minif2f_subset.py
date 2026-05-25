"""
Stage 0.5 pilot — pick a deterministic miniF2F_v2 subset for the gate eval.

Input:  data/eval/miniF2F_v2s.jsonl   (downloaded from roozbeh-yz/miniF2F_v2)
Output: data/eval/minif2f_v2_subset.json
        { "source": "miniF2F_v2s",
          "split": "test",
          "n": 50,
          "seed": 0,
          "names": [...] }

Choice of v2s (simplified) over v2c (competition): the pilot is a yield gate, not
a final benchmark. v2s drops multiple-choice plumbing, giving 0.5B a fair shot
at producing *any* pass@1 signal. v2c reserved for Stage 3.

Run:
    python3 data/build_minif2f_subset.py
"""

import json
import random
from pathlib import Path

ROOT = Path(__file__).parent / "eval"
SRC = ROOT / "miniF2F_v2s.jsonl"
OUT = ROOT / "minif2f_v2_subset.json"

N = 50
SEED = 0


def main() -> None:
    rows = [json.loads(line) for line in SRC.read_text().splitlines() if line.strip()]
    test = sorted(
        (r for r in rows if r["split"] == "test"),
        key=lambda r: r["name"],
    )
    rng = random.Random(SEED)
    picked = rng.sample(test, N)
    names = sorted(r["name"] for r in picked)
    OUT.write_text(
        json.dumps(
            {
                "source": "miniF2F_v2s",
                "split": "test",
                "n": N,
                "seed": SEED,
                "names": names,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"wrote {OUT} — {len(names)} names")


if __name__ == "__main__":
    main()
