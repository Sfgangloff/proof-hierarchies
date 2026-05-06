import HaveExtractor
import Mathlib.Algebra.BigOperators.Group.Finset.Basic

/-!
  Demo: extract the have-tree from a small theorem that uses have-steps.
  Run with `lake exe haveextractor`.
-/

-- A toy proof with explicit have-steps so the tree is non-trivial.
theorem demo_have_tree (n : ℕ) (h : n > 0) : n * 2 > 0 := by
  have h1 : n ≥ 1 := h
  have h2 : n * 2 ≥ 1 * 2 := Nat.mul_le_mul_right 2 h1
  linarith

#extract_have demo_have_tree

def main : IO Unit := do
  IO.println "Have-tree extractor loaded. Use #extract_have <TheoremName> in any Lean file."
