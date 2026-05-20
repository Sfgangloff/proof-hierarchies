"""
Sections (maximal antichains / cuts) over a proof's dependency poset, plus
a family of section-selection policies.

Per EXPERIMENT.md §2: nodes are in-proof haves UNION the named library
lemmas the proof invokes (frontier δ=1, lemma nodes opaque). Edges:
  have_a → have_b   if b ∈ a.usesHyps        (in-proof term-level dep)
  have_a → lemma_L  if L ∈ a.usesConsts      (lemma-invocation)
δ=1 lemmas are leaves of the poset.

Replaces the unsound string-substitution operations in `rewriter/operations.py`.
The empirical v1 single-proof have-only model was flat (depth ≤ 1 on the
sample) — see `data/corpus_v1` analysis. Adding lemma-invocation edges
restores the dependency structure the formalism requires.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from functools import cached_property
from typing import Iterable, Callable
import json


_NOISE_LEMMA_PREFIXES = ("_private.", "inst", "Lean.", "Bool.")
_NOISE_LEMMA_NAMES = {
    "_", "[anonymous]", "sorryAx", "Eq", "And", "Or", "Iff", "Not", "Ne",
    "True", "False", "Nat", "Bool", "Int", "Prop", "Sort", "Type", "HEq",
    "Decidable", "OfNat.ofNat", "Eq.mp", "Eq.mpr", "Eq.refl", "Eq.symm",
    "Eq.trans", "congrArg", "id", "rfl", "this",
}


def _is_user_lemma(name: str) -> bool:
    """Drop obvious non-lemma noise: private aux, instance synthesis,
    hygienic temps, Lean metaprogramming, type/constructor names. v1
    heuristic — refine as the corpus tells us to."""
    if any(name.startswith(p) for p in _NOISE_LEMMA_PREFIXES): return False
    if "._@." in name or "_hyg" in name: return False
    if name in _NOISE_LEMMA_NAMES: return False
    return True


def is_user_decl(decl_name: str) -> bool:
    """A `real' theorem (not auto-generated). Drops simp/proof variants,
    private aux, and the `._eq_*` equation lemmas the elaborator emits."""
    bad_segs = ("._simp_", "._proof_", "._eq_", "._fun_",
                "._cstage", "._unsafe_rec")
    if any(seg in decl_name for seg in bad_segs): return False
    if decl_name.startswith("_private."): return False
    if "._@." in decl_name: return False
    return True


@dataclass(frozen=True)
class HaveNode:
    user_name: str
    pp_type: str
    uses_consts: tuple[str, ...]
    uses_hyps: tuple[str, ...]   # raw: includes binders + earlier haves
    line: int

    @staticmethod
    def from_json(d: dict) -> "HaveNode":
        return HaveNode(
            user_name=d["userName"],
            pp_type=d["ppType"],
            uses_consts=tuple(d.get("usesConsts", [])),
            uses_hyps=tuple(d.get("usesHyps", [])),
            line=int(d.get("line", 0)),
        )


@dataclass(frozen=True)
class LemmaNode:
    """A named library lemma invoked by the proof, opaque at frontier δ=1."""
    name: str
    kind: str = "lemma"


@dataclass
class ProofTree:
    module: str
    decl_name: str
    nodes: list[HaveNode]                       # in-proof have-nodes
    lemma_nodes: list[LemmaNode] = field(default_factory=list)
    # premises used directly by the *outer* proof body (not inside any have)
    outer_premises: list[str] = field(default_factory=list)

    @staticmethod
    def from_json(d: dict) -> "ProofTree":
        return ProofTree(
            module=d["module"],
            decl_name=d["declName"],
            nodes=[HaveNode.from_json(n) for n in d.get("have_nodes", [])],
        )

    @staticmethod
    def join_with_premises(have_record: dict, all_premises: set[str],
                           keep_only_user_lemmas: bool = True) -> "ProofTree":
        """Build a δ=1 tree by joining a have_tree record with the proof's
        named premise set. `all_premises` = the set of named constants used
        anywhere in the proof (from ntp-toolkit's `premises` exe).
        `keep_only_user_lemmas` drops `_private` / `instOfNat`-style noise."""
        t = ProofTree.from_json(have_record)
        invoked_in_haves: set[str] = set()
        for n in t.nodes:
            invoked_in_haves.update(n.uses_consts)
        # Lemma nodes = ALL premises actually invoked.
        candidates = (set(all_premises)) if all_premises else invoked_in_haves
        if keep_only_user_lemmas:
            candidates = {c for c in candidates if _is_user_lemma(c)}
        t.lemma_nodes = sorted([LemmaNode(name=c) for c in candidates],
                               key=lambda x: x.name)
        # Outer premises = premises invoked outside any have (proof tail).
        t.outer_premises = sorted(c for c in candidates if c not in invoked_in_haves)
        return t

    # ------------------------------------------------------------------ #
    # Dependency relation (the proof poset)
    # ------------------------------------------------------------------ #

    @cached_property
    def by_name(self) -> dict[str, HaveNode | LemmaNode]:
        d: dict[str, HaveNode | LemmaNode] = {n.user_name: n for n in self.nodes}
        for l in self.lemma_nodes:
            d.setdefault(l.name, l)
        return d

    @cached_property
    def deps(self) -> dict[str, set[str]]:
        """Direct deps over the unified node set:
          have h → other haves (h.usesHyps ∩ have-names)
          have h → lemma L     (h.usesConsts ∩ lemma-names)
          lemma  → ∅           (opaque at δ=1)"""
        have_names = {n.user_name for n in self.nodes}
        lemma_names = {l.name for l in self.lemma_nodes}
        d: dict[str, set[str]] = {}
        for h in self.nodes:
            d[h.user_name] = (
                {x for x in h.uses_hyps if x in have_names and x != h.user_name}
                | {x for x in h.uses_consts if x in lemma_names}
            )
        for l in self.lemma_nodes:
            d[l.name] = set()
        return d

    @cached_property
    def prereqs(self) -> dict[str, set[str]]:
        """Transitive closure of `deps`: prereqs[n] = everything n recursively
        depends on (BELOW n in the dep poset)."""
        p: dict[str, set[str]] = {n: set() for n in self.by_name}
        changed = True
        while changed:
            changed = False
            for n in self.by_name:
                new = set(self.deps[n])
                for d in self.deps[n]:
                    new |= p[d]
                if new != p[n]:
                    p[n] = new; changed = True
        return p

    @cached_property
    def consumers(self) -> dict[str, set[str]]:
        """consumers[n] = nodes that recursively depend on n (ABOVE n)."""
        c: dict[str, set[str]] = {n: set() for n in self.by_name}
        for n, ps in self.prereqs.items():
            for p in ps:
                c[p].add(n)
        return c

    # Back-compat aliases (descendants in tree-of-deps terms = prereqs).
    @property
    def ancestors(self): return self.prereqs        # noqa: D401  kept for tests
    @property
    def descendants(self): return self.consumers

    def comparable(self, a: str, b: str) -> bool:
        if a == b: return True
        return b in self.prereqs[a] or b in self.consumers[a]

    def depth_of(self, n: str) -> int:
        """Longest dep chain ending at n (roots have depth 0)."""
        if not self.deps[n]:
            return 0
        return 1 + max(self.depth_of(d) for d in self.deps[n])

    # ------------------------------------------------------------------ #
    # Sections
    # ------------------------------------------------------------------ #

    def is_antichain(self, S: Iterable[str]) -> bool:
        S = list(S)
        return all(not self.comparable(a, b) for i, a in enumerate(S) for b in S[i+1:])

    def is_maximal_antichain(self, S: set[str]) -> bool:
        """S is a section iff antichain AND every node is comparable to some s in S."""
        if not self.is_antichain(S):
            return False
        return all(any(self.comparable(n, s) for s in S) for n in self.by_name)


# ---------------------------------------------------------------------- #
# Section-selection policies  (see EXPERIMENT.md §4)
# ---------------------------------------------------------------------- #

Policy = Callable[[ProofTree], set[str]]


def pi_root(tree: ProofTree) -> set[str]:
    """Section nearest the theorem: poset-MAXIMAL nodes (nothing depends on
    them — the proxies for {t} when we don't carry a literal theorem node).
    Per EXPERIMENT.md §3, the 'flat / no in-proof decomposition' cut."""
    return {n for n in tree.by_name if not tree.descendants[n]}


def pi_leaf(tree: ProofTree) -> set[str]:
    """Section at the bottom: poset-MINIMAL nodes (no deps) — δ=1 lemmas and
    leaf haves. The 'maximal decomposition at frontier F' cut."""
    return {n for n, ds in tree.deps.items() if not ds}


def pi_depth(k: int) -> Policy:
    """Cut at depth k: include nodes at depth k, plus all nodes that have no
    descendant at depth ≥ k (so the result remains a maximal antichain)."""
    def policy(tree: ProofTree) -> set[str]:
        if not tree.nodes:
            return set()
        depth = {n: tree.depth_of(n) for n in tree.by_name}
        S = {n for n, d in depth.items() if d == k}
        # Fill: any node with no descendant at depth k joins S.
        for n in tree.by_name:
            if any(depth[d] >= k for d in tree.descendants[n]):
                continue
            if all(not (depth[a] >= k) for a in tree.ancestors[n]):
                # leaf of the "below depth k" region; include if depth < k
                if depth[n] < k and n not in S:
                    S.add(n)
        return S
    return policy


def pi_size(tau: int) -> Policy:
    """Size-bounded cut: promote nodes whose *prereq-subtree* (things below
    them, transitively) has size ≤ τ, picking the maximally-up such cut.
    Greedy from leaves upward: include n if size[n] ≤ τ and no chosen node
    is already below n (we keep going up until the budget is exceeded)."""
    def policy(tree: ProofTree) -> set[str]:
        if not tree.by_name:
            return set()
        size = {n: 1 + len(tree.prereqs[n]) for n in tree.by_name}
        # Topo order: leaves first, then up toward consumers.
        order = sorted(tree.by_name, key=lambda n: tree.depth_of(n))
        S: set[str] = set()
        covered: set[str] = set()         # nodes below the current frontier
        for n in order:
            if size[n] <= tau and not (tree.prereqs[n] & S):
                # remove any prior-chosen prereq from S — n subsumes it
                S -= tree.prereqs[n]
                S.add(n)
                covered |= {n} | tree.prereqs[n]
        return S
    return policy


POLICIES: dict[str, Policy] = {
    "root": pi_root,
    "leaf": pi_leaf,
    "depth1": pi_depth(1),
    "depth2": pi_depth(2),
    "size4": pi_size(4),
}


# ---------------------------------------------------------------------- #
# Corpus loader
# ---------------------------------------------------------------------- #

def load_jsonl(path: str) -> list[ProofTree]:
    out: list[ProofTree] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            out.append(ProofTree.from_json(json.loads(line)))
    return out
