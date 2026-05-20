/-
proof_terms — for each user theorem in the requested modules, emit the
pretty-printed proof TERM (ConstantInfo.value) alongside the type. Pairs
with the original tactic source (from full_proof_training_data) to give
the FINE (tactic) / ROUGH (term-mode) binary granularity per theorem.

Mirrors ntp-toolkit's declarations.lean: CoreM.withImportModules + MetaM.run'
+ env.constants.map₁ filtered by module ownership + withHammerPPOptions ppExpr.

  lake exe proof_terms Mathlib.Logic.Basic
-/
import Mathlib.Lean.CoreM
import Mathlib.Lean.Expr.Basic
import Batteries
import TrainingData.Utils.TheoremPrettyPrinting

open Lean Meta TheoremPrettyPrinting

/-- Pretty-print options chosen for ROUND-TRIP PARSEABILITY: print all
    implicit args + universe levels + full names so the resulting string
    is a valid Lean source term (no `⋯` ellipses, no notation-only forms).
    Verbose, but that's the price of guaranteed re-elaboration. -/
def withRoundTripPP {α} (x : MetaM α) : MetaM α :=
  withOptions (fun o =>
    o.setBool `pp.all true
      |>.setBool `pp.fullNames true
      |>.setBool `pp.universes true) x

/-- A "real" user theorem (matches declarations.lean's isHumanTheorem
    criterion, slightly stricter than just `.thmInfo`). -/
def isUserTheorem (cinfo : ConstantInfo) : CoreM Bool := do
  match cinfo with
  | .thmInfo _ =>
    let hasDeclRange := (← Lean.findDeclarationRanges? cinfo.name).isSome
    let notProjFn := !(← Lean.isProjectionFn cinfo.name)
    return hasDeclRange && notProjFn
  | _ => return false

def emitTermsForModules (moduleNames : Array Name) : MetaM Unit := do
  let env ← getEnv
  for (name, cinfo) in env.constants.map₁ do
    match cinfo with
    | .thmInfo val =>
      if let some moduleIdx := env.getModuleIdxFor? name then
        if let some moduleName := env.header.moduleNames[moduleIdx.toNat]? then
          if moduleNames.contains moduleName then
            if ← isUserTheorem cinfo then
              try
                let ppType ← withHammerPPOptions <| ppExpr val.type
                let ppTerm ← withRoundTripPP <| ppExpr val.value
                let j := Json.mkObj [
                  ("module",   Json.str moduleName.toString),
                  ("declName", Json.str name.toString),
                  ("type",     Json.str (toString ppType)),
                  ("term",     Json.str (toString ppTerm))
                ]
                IO.println j.compress
              catch _ =>
                IO.eprintln s!"warning: failed to pp term {name}"
    | _ => pure ()

def main (args : List String) : IO UInt32 := do
  let options := Options.empty.insert `maxHeartbeats (0 : Nat)
  let modules := match args with
    | [] => #[`Mathlib]
    | xs => xs.toArray.map (·.toName)
  unsafe enableInitializersExecution
  initSearchPath (← findSysroot)
  CoreM.withImportModules modules (options := options) do
    MetaM.run' (emitTermsForModules modules)
  return 0
