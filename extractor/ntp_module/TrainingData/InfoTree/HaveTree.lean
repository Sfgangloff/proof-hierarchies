/-
HaveTree — extract the in-proof node tree with dependency edges, reusing
ntp-toolkit's TacticInvocation helpers.

A NODE is a hypothesis introduced *by a have-like tactic step*
(have/suffices/obtain/rcases/let/set) — detected by (a) a per-tactic
LocalContext diff (goalsBefore → goalsAfter of THAT tactic, so the theorem's
own binders, present before the first tactic, are excluded) and (b) a
have-like syntax-kind gate (so `intro`/`rintro` binder management is
excluded). Internal / hygienic names are dropped.

v1 dependency edges are TYPE-LEVEL (fvars/consts in the introduced
hypothesis' type); the subproof-term refinement is isolated in `typeDeps`
and marked TODO.
-/
import TrainingData.Frontend
import TrainingData.InfoTree.TacticInvocation.Basic
import Lean

open Lean Elab Meta

namespace HaveTree

structure HaveNode where
  userName   : String
  ppType     : String
  usesConsts : Array String
  usesHyps   : Array String
  line       : Nat
  deriving Inhabited

def toJson (n : HaveNode) : Json :=
  Json.mkObj [
    ("userName",   Json.str n.userName),
    ("ppType",     Json.str n.ppType),
    ("usesConsts", Json.arr (n.usesConsts.map Json.str)),
    ("usesHyps",   Json.arr (n.usesHyps.map Json.str)),
    ("line",       Json.num n.line)
  ]

/-- Substring test (no extra imports). -/
def hasInfix (s sub : String) : Bool := (s.splitOn sub).length > 1

/-- A user-written, non-machine hypothesis name we keep as a node. -/
def userMeaningful (n : Name) : Bool :=
  ¬ n.isInternal
  && ¬ n.hasMacroScopes
  && ¬ hasInfix n.toString "._@."
  && ¬ hasInfix n.toString "_hyg"
  && n != `_

/-- Is this tactic a have-like introduction (vs. intro/rintro/etc.)? -/
def isHaveLike (stx : Syntax) : Bool :=
  let k := stx.getKind.toString.toLower   -- e.g. "…tactichave_"
  hasInfix k "have" || hasInfix k "suffices" || hasInfix k "obtain"
    || hasInfix k "rcases" || hasInfix k "tacticlet"
    || hasInfix k "tacticset" || hasInfix k "mathlib.tactic.set"

def dedupNames (a : Array Name) : Array String :=
  (a.foldl (fun s n => s.insert n) ({} : NameSet)).toList.toArray.map (·.toString)

/-- All elaborated `TermInfo` expressions in this tactic's OWN subproof
    (`t.children`). Pure; mirrors ntp-toolkit's `findAllInfo` usage. The
    subproof's sub-term `TermInfo`s expose used hyps/lemmas as concrete
    `.fvar`/`.const`, so unioning over them yields true term-level deps
    without mvar-chasing. -/
def subproofExprs (t : TacticInvocation) : Array Expr := Id.run do
  let mut es : Array Expr := #[]
  for child in t.children do
    let infos := child.findAllInfo none fun i => match i with
      | .ofTermInfo _ => true
      | _ => false
    for p in infos do
      match p with
      | (.ofTermInfo ti, _, _) => es := es.push ti.expr
      | _ => pure ()
  return es

/-- TRUE dependency set for an introduced hyp `d`: constants and earlier-node
    fvars occurring in `d`'s TYPE or anywhere in the subproof term. -/
def nodeDeps (d : LocalDecl) (prior : Array LocalDecl) (subEs : Array Expr) :
    Array String × Array String :=
  let exprs := #[d.type] ++ subEs
  let consts := dedupNames (exprs.flatMap (·.getUsedConstants))
  let hyps := prior.filterMap (fun p =>
    if exprs.any (fun e => e.hasAnyFVar (· == p.fvarId))
    then some p.userName.toString else none)
  (consts, hyps)

/-- Visible (non-impl, user-meaningful) local decls of a goal. -/
def visibleDecls (mv : MVarId) : MetaM (Array LocalDecl) := do
  let lctx := (← mv.getDecl).lctx
  return lctx.decls.toArray.filterMap (fun o => o)
    |>.filter (fun d => ¬ d.isImplementationDetail && userMeaningful d.userName)

/-- Per-declaration have-node sequence: for each have-like tactic, the
    user-meaningful hypotheses it adds (goalsBefore → goalsAfter diff). -/
def nodesOfTactics (invs : List TacticInvocation) : IO (Array HaveNode) := do
  let mut out : Array HaveNode := #[]
  for t in invs do
    if ¬ isHaveLike t.info.stx then continue
    if t.info.goalsBefore.isEmpty || t.info.goalsAfter.isEmpty then continue
    let line := (t.range).1.line
    let subEs := subproofExprs t
    let beforeNames : NameSet ← t.runMetaMGoalsBefore (fun gs => do
      match gs.head? with
      | none => return {}
      | some g =>
        let ds ← visibleDecls g
        return ds.foldl (fun (s : NameSet) d => s.insert d.userName) {})
    let nodes ← t.runMetaMGoalsAfter (fun gs => do
      match gs.head? with
      | none => return (#[] : Array HaveNode)
      | some g =>
        let after ← visibleDecls g
        let prior := after.filter (fun d => beforeNames.contains d.userName)
        let mut acc : Array HaveNode := #[]
        for d in after do
          if ¬ beforeNames.contains d.userName then
            let (cs, hs) := nodeDeps d prior subEs
            let ppT := toString (← g.withContext (ppExpr d.type))
            acc := acc.push
              { userName := d.userName.toString, ppType := ppT,
                usesConsts := cs, usesHyps := hs, line := line }
        return acc)
    for n in nodes do
      out := out.push n
  return out

end HaveTree
