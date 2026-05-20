# Proof-Decomposition Granularity for Small Theorem Provers — Experimental Protocol

> Status: living protocol. Supersedes `PLAN.md`. Target venue: **ICLR 2027**
> (abstract ≈ Sept 2026). Binding compute constraint: **one T4 16 GB GPU on
> free-tier Modal** → small models (≤ 1.5 B, QLoRA), CPU-side Lean verification,
> subsampled eval.

---

## 1. Research question and claim

> A *proof decomposition* is a choice of which intermediate results a proof is
> articulated through. We can generate, **for the same theorem**, two verified
> granularities — a *rough* form (in-proof haves inlined into the main proof
> body) and a *fine* form (haves kept as named intermediates) — using
> sections of its dependency poset. **Claim (calibrated 2026-05-20):** the
> rough/fine choice is a controllable training-data axis for small theorem
> provers — it materially shifts held-out `pass@k`, and the effect grows as
> the model shrinks.
>
> **Why binary rather than the original 'intermediate granularity is
> optimal' framing:** the 21-module Stage 0d gate signal shows real Mathlib
> proofs are 96% one-liners; among the 4% decomposable, dep-poset depth ≤ 3
> and policy variance is moderate (π_root vs π_leaf ≈ 22% size difference).
> A multi-level "U-shape" claim is not what the data supports; the binary
> rough/fine contrast is, and it remains a clean within-theorem ablation.

The independent variable is the **section-selection policy**, applied within
theorem (the same mathematical content, re-articulated). The dependent variable
is held-out `pass@k` of a small model SFT'd on the resulting corpus.

This subsumes the original `have`-tree idea: in-proof `have`/`suffices`/`calc`
steps are just one kind of node; lemma/theorem invocations are the dominant
structure.

---

## 2. Proof structure: DAG, internal nodes, bounded unfolding

### 2.1 The global proof DAG

Let the environment be the set `V` of named declarations (theorems, lemmas,
defs, instances). For a declaration `d`, its elaborated proof term references a
set of constants `C(d) ⊆ V` (Lean: `Expr` constant-occurrence collection — this
is exactly what premise-selection extractors already compute). Define edges
`d → e` for every `e ∈ C(d)`. Mathlib's proofs are well-founded, so
`G = (V, →)` is a **DAG**, not a tree.

### 2.2 Internal nodes

Within a single declaration's proof, the tactic block introduces *internal
nodes*: `have`, `suffices`, `show`, `refine ?g`, `calc` steps, `obtain`/`rcases`
witnesses. Each internal node `n` has a statement (its ascribed/elaborated
type, pretty-printed in its local context) and a justification that itself
references constants in `V` and/or earlier internal nodes. Internal nodes form
a tree hanging off `d`'s DAG node.

The full node set is `N = V ⊎ {internal nodes}`. The reachability order `≼`
("`m` is used in justifying `n`", transitively) is a partial order on `N`
(acyclic: a DAG plus internal trees).

### 2.3 Why "the proof tree" needs an expansion frontier (key reality)

Unfolding `G` from a root theorem into a tree duplicates every shared lemma's
entire subtree under each use → **super-exponential**, bottoming out only at
axioms and primitive recursors, which are not human-meaningful. A full tree is
not materializable.

We therefore define the tree **relative to an expansion frontier**
`F ⊆ V`: starting from root `t`, recurse into a child `e`'s own proof **iff
`e ∉ F`**; nodes in `F` (and primitives) are opaque leaves. `F` is itself a
coarse granularity dial:

- `F = V` (every named decl opaque) ⇒ the tree is just `t`'s own in-proof
  structure — this recovers the original `have`-tree as the special case.
- `F = ∅` ⇒ expand to primitives — intractable.

**Operational decision (see §11 Open Decisions, D2):** the corpus expands a
named declaration `e` only if `e` is itself in our extracted set *and* within a
bounded unfold depth `δ`. Default `δ = 1` for the pilot (expand one level of
named lemmas, plus all in-proof internal nodes of `t` and of those lemmas),
revisited at the §9 gate. This keeps trees finite, verifiable, and meaningful.

---

## 3. Sections (maximal antichains) and the decomposition they induce

### 3.1 Definition

Fix a root `t` and frontier `F`; let `T = T(t, F)` be the resulting finite
proof tree with order `≼`. A **section** `S ⊆ T` is:

1. an **antichain**: no two `s, s' ∈ S` are `≼`-comparable
   (neither is an ancestor of the other); and
2. **maximal / a cutset**: every node `v ∈ T` is `≼`-comparable to some
   `s ∈ S` (every node is an ancestor or a descendant of a section node).

Equivalently: every root-to-leaf path of `T` meets `S` in exactly one node. In
order-theory terms `S` is a *maximal antichain*; in tree terms a *frontier
cut*. This is the precise reading of the informal definition; the
"parent/child" relation is taken transitively (comparability), confirmed as
working definition pending §11 D1.

`S` partitions `T` into:

- **Upper part** `U(S)` = strict ancestors of `S` (the proof of `t` that
  remains to be produced, using the statements of `S` as named lemmas /
  hypotheses);
- **Lower parts** = the subtrees rooted at each `s ∈ S` (each `s` becomes a
  black box, *or* is recursively decomposed in a separate training example).

The two extremes:

- **Coarsest section** `S = {t}` (cut at the root): no decomposition — the flat
  proof. (Pure `have`-tree-flat baseline.)
- **Finest section** `S = leaves(T)`: maximal decomposition at the chosen `F`.

### 3.2 Induced decomposition as verifiable Lean

Given `(t, F, S)`, the **decomposed proof** is reconstructed as a single Lean
artifact:

```
theorem t … := by
  have s₁ : ⟦stmt s₁⟧ := ⟦proof of s₁ confined to its subtree⟧
  …
  have sₖ : ⟦stmt sₖ⟧ := ⟦…⟧
  ⟦proof of t using s₁ … sₖ⟧          -- = U(S)
```

(`have` for in-proof nodes; for a named-lemma section node either cite the
existing lemma or extract it as a local `have`.) **Semantics preservation is
not assumed — it is verified** (§5): the reconstructed artifact must compile to
a proof of `t`'s *original* statement with `#print axioms` showing no `sorry`
and no axiom set beyond the original's. Rewrites that fail verification are
discarded. This is the load-bearing methodological claim of the paper.

---

## 4. Section-selection policies (the comparative experiment)

The number of maximal antichains is exponential; we do **not** enumerate. We
compare a fixed family of *policies* `π : (t, F) ↦ S`. Each policy yields a
corpus; we SFT a small model per corpus and compare held-out `pass@k`.

**Calibrated to binary granularity** given the §9 corpus signal (depth ≤ 3 in
real Mathlib). The primary contrast is two policies:

- **π_root** — maximal antichain near the theorem (in-proof haves inlined
  into the main proof body; library lemmas cited directly). The "rough"
  decomposition. Rendered by source-level inlining of `have h : T := body`
  into the proof tail.
- **π_leaf** — minimal antichain at the bottom (haves kept named; lemma
  invocations kept as intermediate references). The "fine" decomposition.
  Rendered as the (verified) original proof structure.

Interior policies (`π_depth`, `π_size`, `π_premise`, `π_balanced`, `π_named`,
`π_learned`) remain implemented in `rewriter/sections.py` for ablation /
follow-on work, but are not the primary axis of comparison given the data.

---

## 5. Verification & semantics preservation

Every reconstructed decomposed proof is checked by the **Kimina Lean Server**
(MIT) at the frozen toolchain pin (§8), CPU-side, separate from the GPU:

1. compiles against the *original* theorem statement;
2. `#print axioms` ⊆ original's axiom set (no `sorry`, no `native_decide`
   smuggling);
3. (sanity) the section-node statements elaborate in the reconstructed context.

Non-verifying decompositions are dropped and counted (a reported yield metric).
A policy's effective corpus = its verified decompositions only.

---

## 6. The learning task

**Variant A — policy-as-data-serialization (PRIMARY; tractable on free tier).**
For policy `π`: build corpus `D_π = { (statement_of_t → serialized decomposed
proof under π) }`. Fix a serialization (whole-proof, deterministic node order,
identical surface syntax across policies). SFT a small model on each `D_π`
separately at a **fixed token budget** (§7). Evaluate held-out `pass@k`.
Compare policies. This is the locked Stage 1–3.

**Variant B — section predictor / planner (EXTENSION).** Train a model that,
given a goal, predicts a section `S` (the subgoal frontier); a separate solver
fills `U(S)` and each `s`. Evaluate end-to-end `pass@k` and #LLM-calls vs. a
single-stage baseline. This is the literal "train a model to predict this";
it's the Motivation-2/planning angle and a strong second result if compute
allows. Deferred until Variant A shows signal.

---

## 7. Confound control (decorrelation — non-negotiable)

A reviewer will attribute any effect to sequence length or example difficulty
unless we preempt it:

- **Matched token budget**: every policy's corpus is truncated/sampled to the
  *same* total training-token count and the same per-example length
  distribution where feasible; report the achieved distributions.
- **Length as covariate**: report `pass@k` controlling for serialized proof
  length (regression with length term); the policy effect must survive.
- **Same theorems across policies**: strictly within-theorem paired design — the
  *set* of root theorems is identical across all `D_π`; only articulation
  differs. Held-out theorem split is fixed once, shared by all policies.
- **Difficulty stratification**: report effects within difficulty strata
  (proof length / premise count / Mathlib area).
- `π_size` exists specifically as a length-controlled interior policy.

---

## 8. Frozen stack (do not allow version skew)

The single biggest de-risking rule: **one (Lean toolchain, Mathlib commit)
frozen across extraction, rewriting, verification, eval.**

- **Toolchain pin (FROZEN — Stage 0a complete 2026-05-19):**
  - Lean: `leanprover/lean4:v4.26.0`
  - Mathlib4: **`2df2f0150c275ad53cb3c90f7c98ec15a56a1a67`**
  - `repl`: **`a9a6f5bac483d65d08f6226e0ed653f03c479fb7`** (ref `v4.26.0`)
  - Built + captured on the `proof-hierarchies-lean` Modal Volume
    (`PIN.txt` = single source of truth).
  - **Zero-skew confirmed:** the Mathlib commit our env resolved to is
    *byte-identical* to the Mathlib rev pinned by the verified v4.26.0
    ntp-toolkit state (`cmu-l3/ntp-toolkit` @ commit
    `fbde6c4265eda8a83ab74112987f5e6c17d8858d`, the "Update to v4.26.0"
    commit on the `hammer` branch). Extractor and verifier therefore share
    one Mathlib — the dominant failure mode of this literature is removed.
  - **Stage 0b base:** fork `cmu-l3/ntp-toolkit`, check out the *SHA*
    `fbde6c4265eda8a83ab74112987f5e6c17d8858d` (not a branch head — pin to
    the SHA). No manual re-pinning needed. Open check (non-blocking): whether
    that commit includes `main`'s post-#9 work (#10 declarations2, #11
    `proof_wanted` parsing); cherry-pick if needed.
- **Extractor**: fork `cmu-l3/ntp-toolkit`, pinned to that tag; add a Lean
  module emitting, per declaration: statement, proof, `C(d)`, internal-node
  tree with pretty-printed typed statements and **term-level fvar/constant
  dependency** children (not surface syntax, not indentation).
- **Verifier / eval harness**: Kimina Lean Server, same pin. ≈ 8 GB RAM per
  warm worker; CPU/RAM-bound; runs on CPU Modal jobs.
- **Base models**: primary **Kimina-Prover-Preview-Distill-1.5B** (Apache-2.0,
  only credible sub-1.5 B Lean prior, 32 K ctx); controls
  **Qwen2.5-Math-1.5B-Instruct** (its base; 4 K ctx — a real risk for long
  decompositions) and **Qwen2.5-0.5B** (scaling-down control for the
  size-interaction claim).
- **Benchmarks**: ProofNet = `rahul3613/ProofNet-lean4`; miniF2F = the Lean 4
  test set from the chosen baseline-prover repo **and** additionally
  `roozbeh-yz/miniF2F_v2` (v1 has > 50 % misaligned statements — reporting v2
  is itself a credibility signal). Report all commits in the paper.

---

## 9. Corpus build and decision gates

- **Stage 0a** — ✅ COMPLETE (2026-05-19). Lean v4.26.0 + Mathlib
  `2df2f015…` + repl `a9a6f5ba…` built and frozen on the Modal Volume;
  verified byte-identical to ntp-toolkit's v4.26.0 Mathlib pin (zero skew).
- **Stage 0b** — extractor fork emits the DAG + internal trees JSONL.
- **Stage 0c** — verified reconstruction harness (§5) generalized from the
  current string-substitution `rewriter/operations.py` (which is unsound and
  will be replaced).
- **Stage 0.5 PILOT GATE** — a few hundred theorems, frontier `δ = 1`, two
  policies (`π_root`, one interior), QLoRA Qwen2.5-0.5B, `pass@1` on a miniF2F
  subset. **Proceed only if**: (i) verified-reconstruction yield ≥ ~50 %;
  (ii) any measurable `pass@1` gap between policies; (iii) the Modal T4 + Kimina
  loop runs end-to-end within free-tier limits.
- **Stage 0d GATE — early signal (2026-05-20):** 21-module broader sample
  (1,715 real user theorems) shows **4% decomposable** (≥ 2 in-proof
  nodes), **max depth 3**, π_root vs π_leaf ≈ 22% size variation. Extrapolated
  to full Mathlib (~200k decls): ~8k decomposable — **barely clears the
  5–10k threshold** but suffices for a calibrated binary-granularity pilot.
  Proceed under the calibrated (§1) framing; the full-Mathlib gate is met
  empirically once Stage 0c reconstruction yields verified pairs at scale.

---

## 10. Training, evaluation, analysis

- **Training (Stage 2)**: QLoRA, equal token budget per policy, identical
  hyperparameters; primary at 1.5 B, replicate the *direction* of the effect at
  0.5 B for the size-interaction claim. No extra seeds until signal is seen
  (free-tier caps).
- **Eval (Stage 3)**: `pass@1` and `pass@8` on miniF2F-test (+ miniF2F_v2) and
  ProofNet, subsampled if free-tier-bound; all proofs checked by the §8 Kimina
  harness; exact commits reported. `pass@8` over miniF2F-test ≈ 1 952 Lean
  checks (~15–60 min/warm-worker — cost is generation, not checking).
- **Analysis (Stage 4)**: within-theorem paired tests across policies;
  length-controlled regression; granularity × model-size interaction;
  per-Mathlib-area ablation. Primary figure: held-out `pass@k` vs.
  section-policy granularity, per model size.

---

## 11. Open decisions (need confirmation — embedded here rather than blocking)

- **D1.** "Parent or child" ⇒ taken as transitive ancestor/descendant
  (comparability), making a section a *maximal antichain / cut*. Working
  definition; confirm this matches intent. *(Recommended: yes.)*
- **D2.** Expansion frontier: expand named lemmas only if extracted and within
  unfold depth `δ` (default `δ = 1`, revisit at gate). *(Recommended: yes,
  start `δ = 1`.)*
- **D3.** Primary learning task = Variant A (policy-as-data), Variant B
  (section predictor) as a deferred second result. *(Recommended: yes.)*
- **D4.** Lower parts below a section: treat as **cited/given** (shorter
  sequences, cleaner length control) vs. **recursively inlined** (longer,
  reintroduces the length confound). *(Recommended: cited/given for the
  primary; inlining as an ablation only.)*

---

## 12. Risks

| Risk | Mitigation |
|---|---|
| Version skew corpus/verifier/eval | One frozen pin (§8); single biggest rule |
| DAG unfolding blowup | Bounded expansion frontier `δ` (§2.3) |
| Reconstructed proofs don't compile | Generate-then-verify; yield is a reported metric; drop failures (§5) |
| Effect is just sequence length | §7 decorrelation, `π_size`, length-covariate regression |
| Free-tier compute exhausted | Pilot gate first; tiny models; subsampled eval; no premature seeds |
| Novelty challenged vs ProofAug (ICML 2025) | Frame as *training-data representation for SFT*, not inference-time search; controlled within-theorem design is the contribution |
| Not enough hierarchical verifiable data | Stage 0d gate → explicit pivot trigger |
