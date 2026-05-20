"""Unit tests for `sections.py` — proof-poset properties and policy outputs."""

from rewriter.sections import (
    HaveNode, ProofTree, pi_root, pi_leaf, pi_depth, pi_size,
)


def _tree(*specs: tuple[str, list[str]]) -> ProofTree:
    nodes = [HaveNode(user_name=n, pp_type="T", uses_consts=(),
                      uses_hyps=tuple(deps), line=0)
             for n, deps in specs]
    return ProofTree(module="m", decl_name="t", nodes=nodes)


def test_empty_tree_policies_are_empty():
    t = _tree()
    assert pi_root(t) == set()
    assert pi_leaf(t) == set()
    assert pi_depth(1)(t) == set()


def test_linear_chain_deps_and_closure():
    # a → b → c → d  (d depends on c, c on b, b on a)
    t = _tree(("a", []), ("b", ["a"]), ("c", ["b"]), ("d", ["c"]))
    assert t.deps["d"] == {"c"}
    assert t.ancestors["d"] == {"a", "b", "c"}
    assert t.descendants["a"] == {"b", "c", "d"}
    assert t.depth_of("d") == 3
    assert t.is_antichain({"a", "b"}) is False
    assert t.is_antichain({"b"}) is True


def test_linear_chain_root_and_leaf_sections():
    # d → c → b → a (d depends on c, …, a is the base/leaf).
    t = _tree(("a", []), ("b", ["a"]), ("c", ["b"]), ("d", ["c"]))
    assert pi_root(t) == {"d"}      # MAXIMAL: nothing depends on d
    assert pi_leaf(t) == {"a"}      # MINIMAL: a has no deps
    for S in (pi_root(t), pi_leaf(t)):
        assert t.is_maximal_antichain(S)


def test_diamond_sections_are_maximal_antichains():
    # d → b → a, d → c → a   (a is the base, d is the top)
    t = _tree(("a", []), ("b", ["a"]), ("c", ["a"]), ("d", ["b", "c"]))
    assert pi_root(t) == {"d"}
    assert pi_leaf(t) == {"a"}
    # depth(1) should give {b, c} — the antichain at distance 1 from roots.
    S = pi_depth(1)(t)
    assert S == {"b", "c"}
    assert t.is_maximal_antichain(S)


def test_size_policy_respects_bound():
    t = _tree(("a", []), ("b", ["a"]), ("c", ["a"]), ("d", ["b", "c"]))
    # prereq sizes: a=1, b=2, c=2, d=4. With τ=1 only `a` qualifies.
    assert pi_size(1)(t) == {"a"}


def test_uses_hyps_filters_binders():
    # `α` is a theorem binder, not a node — must be filtered from deps.
    t = _tree(("h", ["α"]), ("k", ["h", "n"]))
    assert t.deps["h"] == set()
    assert t.deps["k"] == {"h"}
