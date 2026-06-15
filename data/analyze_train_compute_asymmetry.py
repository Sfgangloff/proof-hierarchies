"""
Stage 0.5 analysis — TRAINING-compute asymmetry between the rough and fine
policies (the half of the headline budget e-0048 explicitly excluded).

CPU-only, stdlib-only. Reads the prepared per-policy SFT JSONLs and reports
the per-policy SUPERVISED-FINE-TUNING token volume (prompt + completion, the
unit a causal-LM QLoRA forward+backward actually processes), the rough/fine
ratio, and what it means for (a) the Modal budget e-0048 priced for EVAL only
and (b) the construct validity of the headline rough-vs-fine comparison.

  python3 data/analyze_train_compute_asymmetry.py

Why this gate exists
--------------------
The whole Stage-0.5 power/cost chain (e-0040..e-0051) priced the EVAL and the
e-0048 compute-budget gate states plainly that it "EXCLUDES e-0007 QLoRA
training (2 policies x sizes adapters)". But QLoRA training is a FIXED cost
paid BEFORE any eval, so the staged-eval logic (e-0051) — run the cheap
single-size screen first, escalate only on signal — cannot defer it: you must
train both policies (x sizes) up front regardless of whether the eval ever
escalates. And e-0010 already showed the rough (term-mode) and fine (tactic)
serializations differ ~144x in completion length on corpus_v3. If training
cost tracks token volume (it does, to first order: QLoRA FLOPs ~ 6 * N_params
* total_tokens * epochs), then the two ARMS of the comparison are not
compute-matched, which is both a budget item e-0048 omitted AND a confound:
a skeptic attributes any pass@k gap to "rough saw Nx more gradient tokens",
not to granularity.

This computes the actual N from the prepared corpus and connects it to the
e-0048 anchor and the e-0027 same-format escape hatch. No Lean, no Modal.

Token proxy: chars / 4 (the e-0010 convention; char numbers are exact,
token numbers are an estimate and labelled as such). The SFT training unit is
prompt + completion because a causal LM forward+backward-passes the whole
packed sequence even when the loss is masked to the completion.
"""

import json
import pathlib

ROOT = pathlib.Path(__file__).parent / "corpus_v3"
SFT = ROOT / "sft"
POLICIES = ["rough", "fine"]
CHARS_PER_TOKEN = 4.0  # e-0010 convention; token figures are estimates

# e-0048 anchor (a-0005 / e-0006): the one eval run proven to fit the free tier.
# 50 problems @ pass@1 = 50 samples in ~56 T4-min => t1 = 1.12 T4-min / sample.
T1_MIN_PER_SAMPLE = 56.0 / 50.0  # = 1.12

# e-0027 / a-0027: same-format (both tactic-mode) deep granularity-only length
# delta — the named-have headers fine keeps and rough inlines. Median ~117 char
# (~29 tok), p90 ~330 char (~82 tok); rough is the SHORTER side there.
DEEP_HEADER_DELTA_TOK_MEDIAN = 117.0 / CHARS_PER_TOKEN  # ~29 tok


def char_len(s: str) -> int:
    return len(s.strip())


def policy_train_volume(policy: str) -> dict:
    """Total SFT token volume (prompt + completion) over the TRAIN split."""
    path = SFT / policy / "train.jsonl"
    n = 0
    prompt_chars = 0
    compl_chars = 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            n += 1
            prompt_chars += char_len(row["prompt"])
            compl_chars += char_len(row["completion"])
    total_chars = prompt_chars + compl_chars
    return {
        "n": n,
        "prompt_tok": prompt_chars / CHARS_PER_TOKEN,
        "compl_tok": compl_chars / CHARS_PER_TOKEN,
        "total_tok": total_chars / CHARS_PER_TOKEN,
    }


def main():
    print("=" * 78)
    print("TRAINING-COMPUTE ASYMMETRY (rough vs fine) — the e-0048 omission")
    print("SFT token volume = prompt + completion (chars/4); train split only")
    print("=" * 78)

    vols = {p: policy_train_volume(p) for p in POLICIES}
    for p in POLICIES:
        v = vols[p]
        print(
            f"\n  {p:>5}: n={v['n']}  prompt={v['prompt_tok']:>10,.0f} tok  "
            f"completion={v['compl_tok']:>12,.0f} tok  "
            f"TOTAL={v['total_tok']:>12,.0f} tok"
        )

    r, f = vols["rough"], vols["fine"]
    seq_ratio = r["total_tok"] / f["total_tok"]
    compl_ratio = r["compl_tok"] / f["compl_tok"]
    print("\n" + "-" * 78)
    print("  ASYMMETRY (corpus_v3, the prepared headline corpus)")
    print("-" * 78)
    print(f"    full-sequence (prompt+completion) token ratio rough/fine = {seq_ratio:.1f}x")
    print(f"    completion-only token ratio rough/fine                  = {compl_ratio:.1f}x")
    print(
        "    => at matched epochs and model size, QLoRA FLOPs ~ 6*N*tokens*epochs,\n"
        f"       so the ROUGH adapter costs ~{seq_ratio:.0f}x the training compute of the\n"
        "       FINE adapter. The two arms of the comparison are NOT compute-matched."
    )

    # Express the absolute extra training token volume as eval-anchor multiples,
    # so the omitted training cost sits on the SAME scale e-0048 used for eval.
    # One proven-affordable eval run = 50 samples. We cannot convert tokens to
    # T4-min without a training-throughput anchor (none exists pre-SFT), so we
    # report the asymmetry as a RATIO and a per-size, per-epoch multiplier — the
    # decision-relevant facts that do not need a throughput constant.
    print("\n" + "-" * 78)
    print("  WHY THIS MATTERS FOR THE MODAL GO/NO-GO")
    print("-" * 78)
    print(
        "  (1) FIXED, NON-DEFERRABLE. e-0051's staged eval defers the EXPENSIVE\n"
        "      multi-size interaction behind a cheap single-size screen, but BOTH\n"
        "      adapters must be trained up front regardless. Training is paid even\n"
        "      if the screen says stop — e-0048 priced none of it.\n"
        f"  (2) UNMATCHED COMPUTE CONFOUND. Rough trains on {r['total_tok']:,.0f} tok vs\n"
        f"      fine {f['total_tok']:,.0f} tok ({seq_ratio:.0f}x). A pass@k gap is then\n"
        "      attributable to 'rough saw far more gradient tokens', not to\n"
        "      granularity — a confound DISTINCT from the length confound (e-0010,\n"
        "      which is about the EVAL-time sequence) and the construct-validity\n"
        "      confound (e-0026, which is about WHAT differs per example)."
    )

    print("\n" + "-" * 78)
    print("  THE SAME-FORMAT DEEP BUILD (e-0027/e-0033) COLLAPSES IT")
    print("-" * 78)
    print(
        "  On a same-format (both-tactic-mode) deep build, rough and fine SHARE\n"
        "  the residual body and statement and differ ONLY by the named-have\n"
        f"  headers — median granularity delta ~{DEEP_HEADER_DELTA_TOK_MEDIAN:.0f} tok/decl (e-0027), and\n"
        "  there FINE is the (slightly) longer side, not rough. So the training\n"
        "  token ratio there is ~1.0-2.0x, not "
        f"{seq_ratio:.0f}x: the same pivot that fixes\n"
        "  q-0007's construct validity (a-0026) and q-0008's length confound\n"
        "  (a-0027) ALSO compute-matches the two training arms. corpus_v3 cannot\n"
        "  be compute-matched without re-serializing rough in tactic mode."
    )

    print("\n" + "=" * 78)
    print("  BOTTOM LINE")
    print("=" * 78)
    print(
        f"  e-0048 priced EVAL and excluded training; the excluded half is\n"
        f"  {seq_ratio:.0f}x ASYMMETRIC on corpus_v3 (rough {r['total_tok']:,.0f} vs fine\n"
        f"  {f['total_tok']:,.0f} tok over {r['n']} train examples). This is a fixed,\n"
        f"  non-deferrable cost AND an unmatched-compute confound on the headline\n"
        f"  comparison; the same-format deep build (e-0027) collapses it to ~1-2x.\n"
        f"  CAVEAT: token proxy chars/4; FLOPs~tokens holds at matched epochs/size;\n"
        f"  no absolute T4-min (no pre-SFT training-throughput anchor exists)."
    )

    # Machine-readable summary for downstream gates.
    out = {
        "corpus": "corpus_v3",
        "n_train": r["n"],
        "rough_total_tok": round(r["total_tok"]),
        "fine_total_tok": round(f["total_tok"]),
        "seq_token_ratio": round(seq_ratio, 2),
        "completion_token_ratio": round(compl_ratio, 2),
        "deep_same_format_header_delta_tok_median": round(DEEP_HEADER_DELTA_TOK_MEDIAN, 1),
        "chars_per_token": CHARS_PER_TOKEN,
    }
    out_path = pathlib.Path(__file__).parent / "train_compute_asymmetry.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\n  wrote {out_path.relative_to(pathlib.Path(__file__).parent.parent)}")


if __name__ == "__main__":
    main()
