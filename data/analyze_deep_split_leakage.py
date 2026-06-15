"""TRAIN/EVAL LEAKAGE gate for the DATA/DEEP within-deep eval route (q-0007/q-0001).

The Stage-0.5 power chain (e-0040..e-0048) converged on the within-deep route as
the ONLY construct-valid AND adequately-powered home for the headline rough-vs-fine
pass@k gap, pricing its effective n (e-0046: ~106 granularity-bearing-and-verified)
and its compute cost (e-0048). Every one of those gates inherits ONE caveat from
e-0031 and never quantifies it:

    "module-disjoint is the standard but NOT AIRTIGHT leakage control."

If an eval-split theorem is duplicated in a train-split module, or is CITED BY NAME
inside train-split proof bodies (i.e. the eval lemma is itself a dependency the
model trains on), then a measured rough-vs-fine pass@k gap on that target is
partly MEMORIZATION, not generalization -- and the construct-valid effective n must
be DISCOUNTED by the leakage rate before the headline can be read off it. No prior
gate measured this. This one does, CPU-only over local data/deep/*.json, reusing
the EXACT e-0046 area-stratified every-5th-module split so the numbers compose.

Two leakage modes, both measured on the SAME split:

  (A) STATEMENT DUPLICATION (zero false positives): an eval target whose normalized
      `statement` string is identical to a TRAIN target's statement -- the same
      theorem proved in two modules. Pure memorization channel.

  (B) NAME-CITATION leakage (the prover-relevant one): an eval target whose declared
      NAME appears as an identifier token inside ANY train-split have_tree body --
      the eval theorem is used as a named lemma in training proofs, so the model is
      conditioned on it. Reported raw and at name-length thresholds (long, specific
      names are unambiguous; short generic names like `aux`/`of` can collide), and
      restricted to the GRANULARITY-BEARING eval targets (substantive_width>=1) that
      actually set the headline's effective n.

CAVEATS: name-citation is a TOKEN-level proxy for dependency (a verbatim name in a
train body is strong evidence of citation but not a resolved import graph); the deep
rec `name` is the local declaration name, matched against both full and last-`.`-
component train tokens; statement strings are compared after whitespace-normalization
only (alpha-equivalent restatements not caught). Counts not pass@k. Pure stdlib; no
Lean, no Modal; reuses the e-0031/e-0032 split+construct logic via the e-0046 module.

  python3 -m data.analyze_deep_split_leakage [--out path.json]
"""

from __future__ import annotations
import argparse, collections, json, re
from pathlib import Path

# reuse the e-0046 split + construct machinery UNCHANGED so the route composes
from data.analyze_deep_effective_n_power import (
    MANIFEST, deep_path, top_area, substantive_width, HOLDOUT_EVERY,
)

ROOT = Path(__file__).resolve().parents[1]

# identifier-with-dots token (Lean constant references inside proof bodies)
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.'!?₀-₉]*")
NAME_LEN_THRESHOLDS = (1, 6, 10, 16)  # report leakage at increasing specificity


def norm_stmt(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def collect_bodies(rec: dict) -> list[str]:
    """flatten every have_tree node body string in a record."""
    out: list[str] = []
    stack = list(rec.get("have_tree", []) or [])
    while stack:
        n = stack.pop()
        b = n.get("body")
        if b:
            out.append(b)
        stack.extend(n.get("children", []) or [])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data/corpus_v3/deep_split_leakage.json"))
    args = ap.parse_args()

    targets = json.loads(MANIFEST.read_text())["targets"]

    # ---- e-0046 area-stratified, module-disjoint every-5th-module eval holdout ----
    mods_by_area: dict[str, set] = collections.defaultdict(set)
    for t in targets:
        mods_by_area[top_area(t["module"])].add(t["module"])
    eval_modules = set()
    for area, mods in mods_by_area.items():
        for i, m in enumerate(sorted(mods)):
            if i % HOLDOUT_EVERY == HOLDOUT_EVERY - 1:
                eval_modules.add(m)

    eval_t = [t for t in targets if t["module"] in eval_modules]
    train_t = [t for t in targets if t["module"] not in eval_modules]

    # per-module deep record cache (name -> rec)
    cache: dict[Path, dict] = {}

    def rec_for(t: dict):
        p = deep_path(t["module"])
        if p not in cache:
            recs = json.loads(p.read_text()) if p.exists() else []
            cache[p] = {r["name"]: r for r in recs}
        return cache[p].get(t["name"])

    # ---- (A) statement duplication: train statement set ----
    train_stmts: dict[str, list] = collections.defaultdict(list)
    for t in train_t:
        r = rec_for(t)
        if r is not None:
            train_stmts[norm_stmt(r.get("statement", ""))].append((t["module"], t["name"]))

    # ---- (B) name-citation: identifier tokens over ALL bodies in train MODULES ----
    # Conservative net: every deep record in a train-split module (not just the
    # manifest target), since training proofs cite beyond the headline targets.
    train_modules = {t["module"] for t in train_t}
    n_train_recs_scanned = 0
    train_tokens: set[str] = set()
    for mod in train_modules:
        p = deep_path(mod)
        recs = json.loads(p.read_text()) if p.exists() else []
        for r in recs:
            n_train_recs_scanned += 1
            for body in collect_bodies(r):
                for tok in IDENT_RE.findall(body):
                    train_tokens.add(tok)
                    if "." in tok:
                        train_tokens.add(tok.rsplit(".", 1)[-1])  # last component

    # ---- score eval targets ----
    n_eval = 0
    missing = 0
    gb1 = 0                                   # granularity-bearing eval (sw>=1)
    stmt_dup = 0                              # (A) any-length statement duplicate
    stmt_dup_examples = []
    cited_by_len = {th: 0 for th in NAME_LEN_THRESHOLDS}            # (B) over ALL eval
    cited_gb_by_len = {th: 0 for th in NAME_LEN_THRESHOLDS}        # (B) over GB eval
    leaked_either_gb = 0                     # GB eval leaked by A OR B(len>=10)
    cited_examples = []

    for t in eval_t:
        r = rec_for(t)
        if r is None:
            missing += 1
            continue
        n_eval += 1
        name = t["name"]
        last = name.rsplit(".", 1)[-1]
        sw = substantive_width(r)
        is_gb = sw >= 1
        if is_gb:
            gb1 += 1

        dup = norm_stmt(r.get("statement", "")) in train_stmts
        if dup:
            stmt_dup += 1
            if len(stmt_dup_examples) < 12:
                stmt_dup_examples.append({"module": t["module"], "name": name,
                                          "train_loc": train_stmts[norm_stmt(r.get("statement", ""))][:2]})

        cited = (name in train_tokens) or (last in train_tokens)
        if cited:
            for th in NAME_LEN_THRESHOLDS:
                if len(last) >= th:
                    cited_by_len[th] += 1
                    if is_gb:
                        cited_gb_by_len[th] += 1
        if is_gb and (dup or (cited and len(last) >= 10)):
            leaked_either_gb += 1
            if len(cited_examples) < 12:
                cited_examples.append({"module": t["module"], "name": name,
                                       "stmt_dup": dup, "cited": cited, "name_len": len(last)})

    def pct(a, b):
        return round(100.0 * a / b, 1) if b else 0.0

    # headline: discount the e-0046 GB effective n by the conservative leakage rate
    leak_rate_gb = leaked_either_gb / gb1 if gb1 else 0.0
    report = {
        "experiment": "e-0049",
        "route": "within-deep every-5th-module holdout (e-0046 split, reused unchanged)",
        "split": {
            "eval_modules": len(eval_modules),
            "eval_targets": len(eval_t),
            "eval_targets_with_deep_rec": n_eval,
            "eval_missing_rec": missing,
            "train_targets": len(train_t),
            "granularity_bearing_eval_targets": gb1,
            "train_records_scanned_all_in_train_modules": n_train_recs_scanned,
            "train_body_identifier_tokens": len(train_tokens),
        },
        "A_statement_duplication": {
            "eval_targets_duplicated_in_train": stmt_dup,
            "rate_pct_of_eval": pct(stmt_dup, n_eval),
            "examples": stmt_dup_examples,
        },
        "B_name_citation_in_train_bodies": {
            "note": "eval target name appears as identifier token in a train-split body",
            "over_all_eval": {str(th): cited_by_len[th] for th in NAME_LEN_THRESHOLDS},
            "over_all_eval_pct": {str(th): pct(cited_by_len[th], n_eval) for th in NAME_LEN_THRESHOLDS},
            "over_granularity_bearing_eval": {str(th): cited_gb_by_len[th] for th in NAME_LEN_THRESHOLDS},
            "over_granularity_bearing_eval_pct": {str(th): pct(cited_gb_by_len[th], gb1) for th in NAME_LEN_THRESHOLDS},
        },
        "headline_leakage_discount": {
            "definition": "GB eval target leaked := statement-duplicated OR cited-by-name with last-component length>=10",
            "leaked_gb_targets": leaked_either_gb,
            "leak_rate_pct_of_gb": pct(leaked_either_gb, gb1),
            "clean_gb_fraction": round(1.0 - leak_rate_gb, 3),
            "e0046_effective_n_ge1_before_discount": 116,
            "effective_n_ge1_after_leak_discount": int(round(116 * (1.0 - leak_rate_gb))),
            "examples": cited_examples,
        },
    }

    Path(args.out).write_text(json.dumps(report, indent=2))

    print(f"=== e-0049 within-deep train/eval LEAKAGE gate ===")
    print(f"split: {len(eval_t)} eval targets ({gb1} granularity-bearing) vs {len(train_t)} train")
    print(f"(A) statement-duplicated eval targets: {stmt_dup} ({pct(stmt_dup, n_eval)}% of eval)")
    print(f"(B) eval name cited in train bodies (len>=10): {cited_by_len[10]} "
          f"({pct(cited_by_len[10], n_eval)}% of eval); over GB: {cited_gb_by_len[10]} "
          f"({pct(cited_gb_by_len[10], gb1)}% of GB)")
    print(f"HEADLINE: {leaked_either_gb}/{gb1} GB eval targets leaked "
          f"({pct(leaked_either_gb, gb1)}%) -> effective n_ge1 discounts "
          f"~116 -> ~{int(round(116 * (1.0 - leak_rate_gb)))}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
