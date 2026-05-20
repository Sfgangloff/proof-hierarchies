/-
Deterministic ground-truth for the have_tree extractor. Compiled from
source by `have_tree`'s `compileModule`; resolved via the project src
search path (no lib registration needed).

Expected nodes (per declName):
  selftest_basic   : h1, h2          (h2's proof uses h1 — TYPE-level edge
                                       will MISS this; demonstrates the v1
                                       limitation to be refined)
  selftest_obtain  : w, hw           (obtain destructuring)
  selftest_nested  : key, step, inner (inner is a have inside step's `by`)
  selftest_let     : t               (let-bound)
-/
import Mathlib.Logic.Basic

theorem selftest_basic (n : Nat) : n + 0 = n := by
  have h1 : n + 0 = n := Nat.add_zero n
  have h2 : n = n + 0 := h1.symm
  exact h1

theorem selftest_obtain (p : Nat → Prop) (h : ∃ x, p x) : True := by
  obtain ⟨w, hw⟩ := h
  trivial

theorem selftest_nested (a b : Nat) (hab : a = b) : b = a := by
  have key : a = b := hab
  have step : b = a := by
    have inner : a = b := key
    exact inner.symm
  exact step

theorem selftest_let (n : Nat) : n = n := by
  let t : Nat := n + 1
  have ht : t = n + 1 := rfl
  rfl
