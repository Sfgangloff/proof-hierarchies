#!/usr/bin/env python3
"""Stage 0.5 analysis (e-0053): measure the SAME-FORMAT deep training-token
overhead on the 633 real deep wide-frontier targets, grounding a-0050's
projected "~29 tok median header / ~1-2x ratio collapse" in on-disk data.

Context. a-0050/e-0052 measured corpus_v3's rough(term)-vs-fine(tactic)
training-token ratio at ~53x full-sequence / ~197x completion-only and argued
the asymmetry is a FORMAT confound (rough is fully-elaborated term-mode), which
the same-format deep build (pi_root/pi_leaf both in tactic mode, sharing the
residual body) collapses to "~1-2x". That ~1-2x rested on a PROJECTED ~29-tok
median named-have header, never measured on the 633 deep targets themselves.

This script:
  (1) re-confirms the corpus_v3 completion-only format asymmetry, and
  (2) MEASURES, from data/corpus_v3/deep_wide_targets.json (on-disk frontier
      widths + chars for all 633 targets), the additive fine-minus-rough
      header overhead the named antichain contributes in a same-format build,
      and the shared-body threshold above which the ratio stays <=2x / <=1.5x.

Same-format token model (both tactic mode, residual body B shared):
  fine  body = B + sum_i header_i + final-with-refs
  rough body = B + final-with-inlined-proofs
  fine - rough ~= sum_i header_i, where per frontier subgoal i the header is
      "have " + name + " : " + type + " := by"
  ~= type_chars + ~18 structural/name chars.  (frontier_chars = sum type_chars)
Hence ratio fine/rough = 1 + overhead/B; ratio<=2x  <=>  B >= overhead.

Pure-stdlib, CPU-only. Token proxy = chars/4 (consistent with e-0052).
"""
import json
import statistics as st

ROOT = "data/corpus_v3"
STRUCT_CHARS = 18  # "have "(5)+name(~4)+" : "(3)+" := by"(6)
TOK = 4.0          # chars per token proxy


def tok(s):
    return len(s) / TOK


def corpus_v3_format_asymmetry():
    rough, fine = [], []
    for line in open(f"{ROOT}/pairs.jsonl"):
        o = json.loads(line)
        rough.append(tok(o["rough"]))
        fine.append(tok(o["fine"]))
    return {
        "n": len(rough),
        "rough_median": round(st.median(rough), 1),
        "fine_median": round(st.median(fine), 1),
        "rough_sum": round(sum(rough)),
        "fine_sum": round(sum(fine)),
        "completion_ratio": round(sum(rough) / sum(fine), 1),
    }


def deep_sameformat_overhead():
    T = json.load(open(f"{ROOT}/deep_wide_targets.json"))["targets"]
    ov = [(t["frontier_chars"] + STRUCT_CHARS * t["frontier_width"]) / TOK for t in T]
    ov.sort()
    med = st.median(ov)
    out = {
        "n": len(T),
        "overhead_tok_median": round(med, 1),
        "overhead_tok_mean": round(st.mean(ov), 1),
        "overhead_tok_p90": round(ov[int(0.9 * len(ov))], 1),
        "overhead_tok_max": round(ov[-1], 1),
        "body_for_ratio_le_2x": round(med),
        "body_for_ratio_le_1_5x": round(2 * med),
        "ratio_at_body": {},
    }
    for B in (100, 200, 500, 1000):
        rs = sorted(1 + o / B for o in ov)
        out["ratio_at_body"][f"B={B}"] = {
            "median": round(st.median(rs), 2),
            "p90": round(rs[int(0.9 * len(rs))], 2),
        }
    return out


if __name__ == "__main__":
    res = {
        "corpus_v3_format_asymmetry": corpus_v3_format_asymmetry(),
        "deep_sameformat_overhead": deep_sameformat_overhead(),
    }
    print(json.dumps(res, indent=2))
