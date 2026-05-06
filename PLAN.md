# Hierarchical Rewriting of Proofs — Research Plan

## Core Idea

In Lean 4 proofs, `have` statements create a natural tree structure: each `have h : T := proof` is a node with type `T`, a sub-proof, and children that are the `have`-dependencies used within it. The leaves are atomic tactic invocations (`simp`, `ring`, `exact`, `linarith`, etc.).

A single theorem can be written as many different such trees by choosing which intermediate results to name explicitly. The central question is: **do some tree representations make proofs easier to learn from, plan, or informalize?**

---

## Phase 1 — Proof Tree Extraction

Build a pipeline that takes a Lean 4 proof (Mathlib is the natural corpus) and extracts its `have`-tree structure.

- **Tooling**: Use the Lean REPL or `lean4-checker` to introspect proofs. Each `have` gives a named node with type and sub-proof.
- **Output**: A labeled tree where each node is `(goal_statement, tactic_proof_of_goal)` and children are the `have`-dependencies.
- **Challenge**: Proofs without explicit `have` statements need a canonical expansion — decide whether to extract implicit intermediate goals from tactic blocks (`refine`, `apply`, multi-step `calc`).

---

## Phase 2 — Defining the Rewriting Space

The rewriting operations on a proof tree are:

- **Splitting**: Replace an atomic tactic step with a `have` that names an intermediate goal → deeper tree.
- **Merging**: Inline a `have` into its parent → flatter tree.
- **Reordering**: Change the order of independent `have` statements.

This gives a combinatorial space of representations for a fixed proof. Quality metrics:

- *Depth*: max depth of the tree
- *Fanout*: max number of children per node
- *Leaf complexity*: proxy'd by tactic diversity and goal length
- *Readability*: goal statement length / type complexity (or LLM-judged)

Phases 1 and 2 are shared infrastructure that unlocks all three experiments below.

---

## Motivation 1 — Training Small Theorem Provers

**Hypothesis**: Small models fine-tuned on proofs at an appropriate hierarchical granularity generalize better than models trained on flat or overly deep proofs.

**Plan**:
1. Take a Mathlib slice (50k–200k theorems).
2. For each proof, generate several tree representations (flat, medium, deep) using the rewriting operations above.
3. Serialize each representation into a training format (linearized proof or tree-structured generation).
4. Fine-tune a small base model (Llama 3.1 8B or Deepseek-Math 7B) separately on each corpus variant.
5. Evaluate on **miniF2F** or **ProofNet** using `pass@k` for `k ∈ {1, 8, 32}`.
6. Ablate: does granularity matter uniformly, or only for certain theorem types (algebra vs. topology)?

**Key open question**: what serialization format to use — whole-proof vs. step-by-step REPL interaction changes the training setup significantly.

---

## Motivation 2 — Proof Planning

**Hypothesis**: Separating *plan generation* (the skeleton of `have` statements with their types) from *gap filling* (proving each `have`) improves efficiency and interpretability.

**Plan**:
1. Define a "plan" as the top-level `have`-skeleton: the sequence of intermediate statements without their proofs.
2. Train or prompt a model in two stages:
   - **Stage A**: Given the theorem statement, generate the plan.
   - **Stage B**: Given the theorem + plan, fill in each step.
3. Compare against a single-stage baseline (end-to-end proof generation).
4. Evaluate: success rate, number of LLM calls, proof length.
5. Study how plan quality correlates with success — does a balanced tree with readable intermediate goals lead to higher fill-in success?

**Connection to existing work**: Related to *Draft, Sketch, and Prove* (Jiang et al., 2023) and *LEGO-Prover*. The novel angle here is a systematic study of *what makes a good sketch* via the tree structure.

---

## Motivation 3 — Informalization

**Hypothesis**: A proof written in a specific hierarchical form maps naturally to a paragraph-structured mathematical explanation, making informalization (formal → natural language) easier and more controllable.

**Plan**:
1. Choose a target tree representation (e.g. moderate depth, fanout ≤ 3, readable intermediate types).
2. Build a template-based or LLM-based informalization that maps:
   - Each `have h : T` → "We claim that [NL(T)]."
   - Each leaf tactic block → "This follows because..."
   - Tree structure → paragraph/sentence flow
3. Compare informalization quality across different tree representations of the same proof.
4. Metrics: human readability judgment — can a mathematician understand the argument from the informalized output?
5. Stretch goal: train a small informalization model on paired (hierarchical Lean proof, NL proof) data.

**Why the tree helps**: flat proofs force the informalization model to invent intermediate structure; the `have`-tree provides it for free.

---

## Decisions

1. **Lean 4 / Mathlib4** as the proof corpus throughout.
2. **Rewriting existing proofs only** — no tactic oracle needed. The pipeline extracts and rewrites proofs that already exist in Mathlib4.
3. **Fine-tuning infrastructure is in scope** — setting up GPU training, training scripts, and evaluation harness is part of the work, not a prerequisite.
4. **Informalization evaluated qualitatively** — no reference texts needed for now. The criterion is human readability: can we understand the proof from the informalized output?
