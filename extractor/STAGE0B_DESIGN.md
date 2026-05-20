# Stage 0b — have-dependency extractor design

> Executable spec. The old `extractor/HaveExtractor/` prototype (regex /
> `letE` / surface-syntax) is **superseded** and will be removed once this
> lands. `letE`-based have detection is unreliable: with proof irrelevance /
> `Expr` erasure, `Prop` `have`s often don't survive as `letE` in the stored
> term — hence InfoTree-based extraction.

## Base (frozen — see EXPERIMENT.md §8)

Fork `cmu-l3/ntp-toolkit`; check out the **SHA**
`fbde6c4265eda8a83ab74112987f5e6c17d8858d` ("Update to v4.26.0", on the
`hammer` branch history — *not* a branch head, so pin to the SHA). Its
`lean-toolchain` = `leanprover/lean4:v4.26.0`; lakefile mathlib & doc-gen4
`@ "v4.26.0"`; manifest Mathlib rev = `2df2f0150c275ad53cb3c90f7c98ec15a56a1a67`
= **our frozen Mathlib** (zero skew). Build on Modal reusing the
`proof-hierarchies-lean` Volume's warm `lake` cache.

Non-blocking open check: does `fbde6c4` include `main`'s post-#9 commits
(#10 `declarations2`, #11 `proof_wanted` parsing)? If we need them,
cherry-pick onto the fork; otherwise ignore.

## Reuse (verified module facts)

- `scripts/full_proof_training_data.lean` (`lake exe full_proof_training_data`)
  → per-decl JSON: `file, module, declName, decl, proof, srcUpToDecl`.
  Gives (a) statement + proof.
- `scripts/premises.lean` (`lake exe premises`) → per-decl JSON:
  `name, dependents:[{name, explicit, direct}]`. Gives (b) the
  constant-dependency edge set; reuse its constant-collection logic for
  per-node justification edges.
- Lean support lib to build on: `TrainingData/Frontend.lean`,
  `TrainingData/InfoTree/Basic.lean`,
  `TrainingData/InfoTree/TacticInvocation/Basic.lean`,
  `TrainingData/InfoTree/ToJson.lean`,
  `TrainingData/Utils/TheoremPrettyPrinting.lean`.
- LeanDojo precedent (mirror, don't reinvent):
  `lean-dojo/LeanDojo` → `src/lean_dojo/data_extraction/ExtractData.lean`
  (`processFile`/`processAllFiles`; emits `*.ast.json` with tactic
  goal-states + `premises`).

## New module: `scripts/have_tree.lean` (+ `TrainingData/InfoTree/HaveTree.lean`)

Per declaration, emit the in-proof node tree: nodes =
`have / suffices / show / let / calc-step / obtain / rcases` introductions.
Each node:
`{ userName, ppType (type in its LocalContext), usesConsts (library
premises of THIS node's subproof), usesHyps (earlier node userNames its
subproof truly depends on), span }`. Tree edges = the `usesHyps` relation
(true term-level dependency), **not** indentation, **not** `letE`.

### API recipe (signatures to confirm at v4.26.0 — see fragile list)

1. Decl value/type: `Environment.find? : Name → Option ConstantInfo`;
   match `.thmInfo val` → `val.value : Expr`, `val.type : Expr`.
2. Walk elaboration `InfoTree` (from `TrainingData/Frontend.lean`):
   `InfoTree.foldInfo` / `visitM`; filter `Info.ofTacticInfo`. `TacticInfo`
   carries `stx`, `goalsBefore/After : List MVarId`, `mctxBefore/After`.
3. Identify node-introducing tactics by `TacticInfo.stx` kind
   (`Lean.Parser.Tactic.tacticHave_`, `tacticSuffices_`, `tacticShow_`,
   `calcTactic`, `obtain`, `rcases`, term `let`). Introduced fvar(s) =
   `LocalDecl`s present in `goalsAfter` main goal's `LocalContext` but
   absent in `goalsBefore` — read `userName`, `.type`.
4. TRUE dependency for an introduced hyp:
   a. find the metavar whose subproof solves the `have` (the synthetic goal
      mvar in the `goalsBefore`/`goalsAfter` diff);
   b. `instantiateMVars` its assignment (`mctxAfter`);
   c. on the instantiated proof `Expr`: `Expr.collectFVars` → fvarIds →
      map back to earlier-node `userName`s via the goal `LocalContext`;
      `Expr.getUsedConstants` → library-lemma edges.
5. Pretty-print types in context: `Meta.ppExpr` / `Meta.ppGoal` /
   `ContextInfo.runMetaM` (re-enter the captured `ContextInfo`).

### Skeleton (illustrative — fix signatures at v4.26.0)

```lean
import Lean
open Lean Elab Meta Tactic

structure HaveNode where
  userName   : Name
  ppType     : String
  usesConsts : Array Name      -- library premises of this node's subproof
  usesHyps   : Array Name      -- earlier node names it truly depends on

def collectHaveDeps (trees : List InfoTree) : MetaM (Array HaveNode) := do
  let mut out := #[]
  for t in trees do
    t.foldInfo (init := ()) fun ctx info _ => do
      match info with
      | .ofTacticInfo ti =>
        if isHaveLike ti.stx then
          ctx.runMetaM {} do
            let some gAfter := ti.goalsAfter.head? | pure ()
            let lctx := (← gAfter.getDecl).lctx
            for d in newDecls lctx ti.goalsBefore do      -- before/after diff
              let mv  ← findHaveProofMVar ti d
              let pf  ← instantiateMVars (.mvar mv)
              let cs  := pf.getUsedConstants
              let fvs := (pf.collectFVars {}).fvarIds
              let hyp := fvs.filterMap (lctx.find? · |>.map (·.userName))
              out := out.push
                { userName := d.userName
                  ppType := toString (← Meta.ppExpr d.type)
                  usesConsts := cs
                  usesHyps := hyp.filter (· != d.userName) }
      | _ => pure ()
  return out
```

## Output → corpus schema

Join per decl: `{module, declName, statement (=decl), proof,
premises (=dependents), have_nodes:[HaveNode], src}`. This is the input the
Stage 0c verified-rewrite harness and the section-policy code (`rewriter/`)
consume — replacing the regex `data/raw` corpus.

## Validated status (2026-05-19)

`have_tree` compiles against the frozen v4.26.0 Mathlib on Modal and passes
the deterministic self-test (`TrainingData/HaveSelfTest.lean`): node
detection is correct for have / suffices / obtain / rcases / let, including
**nested** haves (`inner` inside `step`'s `by`). Gotcha fixed: tactic kind
is `…tacticHave_` (capital H) — match the **lowercased** kind string.

**Open limitation (load-bearing):** `usesHyps`/`usesConsts` are v1
TYPE-LEVEL only (`typeDeps`). The self-test confirms the miss: `h2`'s proof
is `h1.symm` and `inner`'s is `key`, but neither `h1`∈`h2.usesHyps` nor
`key`∈`inner.usesHyps` because the dependency flows through the proof term,
not the type. Since a *section* is an antichain in the dependency order,
wrong (too-sparse) edges distort the central formalism — the term-level
refinement is required for a sound corpus, not optional.

Refinement recipe (next): for a have-like `TacticInvocation t`, take its
subproof from `t.children : PersistentArray InfoTree` (the `:= e` / `:= by …`
body); union the used constants and the fvars over the elaborated/
instantiated body term, mapping fvars back to earlier node names. The
self-test is the oracle (expect `h2.usesHyps ⊇ [h1]`, `inner.usesHyps ⊇
[key]` after the fix).

## Version-fragile APIs — confirm at v4.26.0 before relying

`Expr.getUsedConstants` vs `…AsSet`; `InfoTree.foldInfo`/`visitM` arg order
& whether `ContextInfo` is passed; `Expr.collectFVars` / `CollectFVars.State`
field names (`fvarIds`?); `Meta.ppGoal`/`ppExpr` module paths;
`MetavarContext` assignment accessors; tactic `Syntax` kind names
(`tacticHave_` etc. renamed across versions). Confirm via the Lean LSP MCP
(must be re-pinned to v4.26.0 first) / loogle / Mathlib docs.
