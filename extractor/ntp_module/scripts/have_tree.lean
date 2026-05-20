/-
have_tree — per-declaration in-proof node tree extractor.

Mirrors ntp-toolkit's known-good `full_proof_training_data` structure:
namespace `Lean.Elab.IO` reached via `open Lean Elab IO`; per-command
`CompilationStep`s from `compileModule`; new theorem(s) of a step via the
built-in `CompilationStep.diff`; tactic invocations from `step.trees`.

  lake exe have_tree Mathlib.Logic.Basic   -- one JSON object per theorem
-/
import TrainingData.Frontend
import TrainingData.InfoTree.TacticInvocation.Basic
import TrainingData.InfoTree.HaveTree
import Mathlib.Lean.CoreM
import Cli

open Lean Elab IO Meta
open Cli

def haveTreeData (args : Cli.Parsed) : IO UInt32 := do
  initSearchPath (← findSysroot)
  let module : Name := (args.positionalArg! "module" |>.as! String).toName
  let steps ← compileModule module
  let mut out : Array Json := #[]
  for step in steps do
    let declNames := step.diff.filterMap (fun ci =>
      match ci with
      | .thmInfo _ => some ci.name
      | _ => none)
    if declNames.isEmpty then continue
    let invs := step.trees.flatMap (fun t => t.tactics)
    if invs.isEmpty then continue
    let nodes ← HaveTree.nodesOfTactics invs
    for declName in declNames do
      out := out.push <| Json.mkObj [
        ("module",     Json.str module.toString),
        ("declName",   Json.str declName.toString),
        ("have_nodes", Json.arr (nodes.map HaveTree.toJson))
      ]
  for j in out do
    IO.println j.compress
  return 0

def have_tree : Cli.Cmd := `[Cli|
  have_tree VIA haveTreeData; ["0.1.0"]
  "Extract the in-proof have/dependency node tree for each theorem in a module."
  ARGS:
    module : String; "Lean module name to compile and extract from."
]

def main (args : List String) : IO UInt32 :=
  have_tree.validate args
