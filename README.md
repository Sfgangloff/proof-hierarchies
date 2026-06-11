# proof-hierarchies

Experiment code for **Proof-decomposition granularity as a controllable
training-data axis for small theorem provers** — re-articulating the *same
verified* Lean/Mathlib proofs at **rough** (`π_root`) vs **fine** (`π_leaf`)
granularity (cuts of the proof dependency DAG) and asking whether that changes
what a small prover learns.

> **The research reasoning lives elsewhere.** Questions, hypotheses, findings,
> and status are maintained as a structured reasoning graph in the
> **research-compiler** database, stream **`proof-hierarchies`**. To read it,
> open the research-compiler web app or run
> `rc export paper --stream proof-hierarchies`. Each analysis below is the node
> `e-00NN`. The active development protocol stays in `EXPERIMENT.md`.

## Status

Established (through Stage 0.5): a frozen Lean/Mathlib toolchain, a tested
section engine, a machine-**verified** 607-pair `(rough, fine)` corpus (84.7%
round-trip), the decomposability signal (~4% of Mathlib proofs decomposable,
depth ≤ 3 → a binary rough/fine contrast), and a 0/50 pre-SFT pilot floor. **Not
yet run:** Stage 2 QLoRA SFT (rough vs fine) and the Stage 3 headline eval
(pass@k × model size) — blocked on Modal credit.

## Experiment index

| Node | Stage / what | Code | Status |
| --- | --- | --- | --- |
| `e-0001` | 0a — frozen Lean/Mathlib toolchain | `modal/build_env.py` | done |
| `e-0002` | section formalism + policy engine (π_root/π_leaf) | `rewriter/sections.py` | done |
| `e-0003` | 0b/0c — extractor + verified reconstruction → 607 pairs | `modal/verify_corpus.py`, `extractor/ntp_module/`, `data/build_pairs.py` | done |
| `e-0004` | 0d — decomposability signal | `rewriter/dryrun_f_size.py` | done |
| `e-0005` | 0.5 — pilot baseline (T4 + Kimina) | `modal/eval_pilot.py` | done |
| `e-0006` | SFT data prep (rough/fine splits) | `data/build_sft.py` | done |
| `e-0007` | Stage 2 — QLoRA SFT (rough vs fine) | see `EXPERIMENT.md` | planned |
| `e-0008` | Stage 3 — main eval (pass@k × size) | see `EXPERIMENT.md` | planned |
| `e-0009` | Variant B — section-predictor / planner | see `EXPERIMENT.md` | planned |

## Layout

```
rewriter/      section engine (sections.py) + the superseded regex rewriter
extractor/     Lean InfoTree extractor (ntp_module/) + superseded prototypes
modal/         Modal cloud apps (env build, extract, verify, pilot eval)
data/          corpora (corpus_v3/), SFT splits, results
EXPERIMENT.md  active development protocol (Stages 0a–4)   ·   PLAN.md (superseded)
paper/         the living ICLR draft
```

## Branches

`iclr-foundation` is the work branch; `main` is preserved.
