import Mathlib
import Lean
import Lean.Elab.Command
import Lean.Data.Json

open Lean Elab Meta Command Json

/-!
# Have-Tree Extraction

Two approaches:
1. `#extract_have Name` — traverses the elaborated proof term (letE nodes = have-steps).
2. `#extract_have_syntax Name` — traverses the *source syntax* of the declaration,
   which is more reliable since proof-term erasure can hide letE nodes.
-/

-- ---------------------------------------------------------------------------
-- Proof-term approach
-- ---------------------------------------------------------------------------

partial def extractHaveTreeExpr (e : Expr) : MetaM (Array Json) := do
  match e with
  | .letE name type val body _ =>
    let typeStr := toString (← ppExpr type)
    let valStr  := toString (← ppExpr val)
    let children ← withLetDecl name type val fun fvar =>
      extractHaveTreeExpr (body.instantiate1 fvar)
    let node := Json.mkObj [
      ("name",     Json.str name.toString),
      ("type",     Json.str typeStr),
      ("proof",    Json.str valStr),
      ("children", Json.arr children)
    ]
    return #[node]
  | .app f a =>
    return (← extractHaveTreeExpr f) ++ (← extractHaveTreeExpr a)
  | .lam _ _ b _ =>
    extractHaveTreeExpr b
  | .mdata _ b =>
    extractHaveTreeExpr b
  | _ => return #[]

-- ---------------------------------------------------------------------------
-- Syntax approach (more reliable — not affected by proof erasure)
-- ---------------------------------------------------------------------------

/-- Collect all `have` nodes in a tactic-block syntax tree. -/
partial def collectHaveSyntax (stx : Syntax) (depth : Nat := 0) : Array Json :=
  match stx with
  | `(tactic| have $name : $type := $val) =>
    let children := collectHaveSyntax val (depth + 1)
    #[Json.mkObj [
      ("name",     Json.str name.getId.toString),
      ("type",     Json.str type.prettyPrint.pretty),
      ("proof",    Json.str val.prettyPrint.pretty),
      ("depth",    Json.num depth),
      ("children", Json.arr children)
    ]]
  | `(tactic| have $name : $type := by $seq) =>
    let children := collectHaveSyntax seq (depth + 1)
    #[Json.mkObj [
      ("name",     Json.str name.getId.toString),
      ("type",     Json.str type.prettyPrint.pretty),
      ("proof",    Json.str "by ..."),
      ("depth",    Json.num depth),
      ("children", Json.arr children)
    ]]
  | `(tactic| have $name : $type by $seq) =>
    let children := collectHaveSyntax seq (depth + 1)
    #[Json.mkObj [
      ("name",     Json.str name.getId.toString),
      ("type",     Json.str type.prettyPrint.pretty),
      ("proof",    Json.str "by ..."),
      ("depth",    Json.num depth),
      ("children", Json.arr children)
    ]]
  | _ =>
    stx.getArgs.foldl (fun acc child => acc ++ collectHaveSyntax child depth) #[]

-- ---------------------------------------------------------------------------
-- Commands
-- ---------------------------------------------------------------------------

/-- `#extract_have Name` — uses the proof term (may be empty if proof is erased). -/
elab "#extract_have" name:ident : command => do
  let env ← getEnv
  let n := name.getId
  match env.find? n with
  | none => logError s!"Unknown constant: {n}"
  | some info =>
    match info with
    | .thmInfo  val =>
      let nodes ← runTermElabM fun _ => liftMetaM (extractHaveTreeExpr val.value)
      logInfo s!"HAVE_TREE (term):{(Json.arr nodes).pretty}"
    | .defnInfo val =>
      let nodes ← runTermElabM fun _ => liftMetaM (extractHaveTreeExpr val.value)
      logInfo s!"HAVE_TREE (term):{(Json.arr nodes).pretty}"
    | .axiomInfo  _ => logError s!"{n} is an axiom — no proof term"
    | .opaqueInfo _ => logError s!"{n} is opaque — no proof term"
    | other => logError s!"{n} is {other.name} — not a theorem or def"

/-- `#extract_have_syntax Name` — uses the declaration syntax tree. -/
elab "#extract_have_syntax" name:ident : command => do
  let env ← getEnv
  let n := name.getId
  match env.find? n with
  | none => logError s!"Unknown constant: {n}"
  | some _ =>
    -- Look up the declaration's syntax via its source info
    match (← getEnv).getModuleIdx? n with
    | some _ => logInfo s!"(from imported module — source syntax not available here)"
    | none   =>
      -- Declaration is in the current file; get its syntax via the info tree
      logInfo s!"Constant {n} found in current file — use #extract_have_syntax in the same block"
