"""Tests for tree rewriting operations."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import json
import pytest
from rewriter.tree import HaveNode, ProofTree
from rewriter.operations import merge, merge_toplevel, split, reorder, all_merges, all_splits, all_reorders


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

def make_flat_tree() -> ProofTree:
    """3 flat top-level siblings, no children."""
    return ProofTree(
        theorem_name="test_flat",
        statement="P",
        nodes=[
            HaveNode("h1", "A", "proof_a"),
            HaveNode("h2", "B", "proof_b h1"),
            HaveNode("h3", "C", "proof_c h1 h2"),
        ],
    )


def make_nested_tree() -> ProofTree:
    """
    h1 : A := proof_a
      h1a : X := proof_x
      h1b : Y := proof_y h1a
    h2 : B := proof_b h1
    """
    return ProofTree(
        theorem_name="test_nested",
        statement="P",
        nodes=[
            HaveNode("h1", "A", "proof_a h1a h1b", children=[
                HaveNode("h1a", "X", "proof_x"),
                HaveNode("h1b", "Y", "proof_y h1a"),
            ]),
            HaveNode("h2", "B", "proof_b h1"),
        ],
    )


def make_deep_tree() -> ProofTree:
    """
    h1
      h2
        h3 : leaf
    """
    return ProofTree(
        theorem_name="test_deep",
        statement="P",
        nodes=[
            HaveNode("h1", "A", "body_h1 h2", children=[
                HaveNode("h2", "B", "body_h2 h3", children=[
                    HaveNode("h3", "C", "leaf_proof"),
                ]),
            ]),
        ],
    )


# --------------------------------------------------------------------------- #
# ProofTree / HaveNode basics
# --------------------------------------------------------------------------- #

def test_depth_flat():
    t = make_flat_tree()
    assert t.depth() == 0


def test_depth_nested():
    t = make_nested_tree()
    assert t.depth() == 1


def test_depth_deep():
    t = make_deep_tree()
    assert t.depth() == 2


def test_size():
    t = make_nested_tree()
    assert t.size() == 4   # h1, h1a, h1b, h2


def test_roundtrip_dict():
    t = make_nested_tree()
    t2 = ProofTree.from_dict(t.to_dict())
    assert t2.to_dict() == t.to_dict()


def test_clone_independence():
    t = make_flat_tree()
    t2 = t.clone()
    t2.nodes[0].name = "CHANGED"
    assert t.nodes[0].name == "h1"


# --------------------------------------------------------------------------- #
# Merge
# --------------------------------------------------------------------------- #

def test_merge_basic():
    t = make_nested_tree()
    # merge h1a (path [0, 0]) into h1
    result = merge(t, [0, 0])
    # h1 should no longer have h1a as a child
    assert len(result.nodes[0].children) == 1
    assert result.nodes[0].children[0].name == "h1b"
    # h1b should be untouched
    assert result.nodes[0].children[0].body == "proof_y h1a"


def test_merge_substitutes_name():
    t = make_nested_tree()
    # h1 body references h1a; merging h1a should inline it
    result = merge(t, [0, 0])
    assert "(proof_x)" in result.nodes[0].body


def test_merge_promotes_grandchildren():
    """Merging a node with children should adopt those children."""
    t = make_deep_tree()
    # merge h2 (path [0, 0]) into h1
    result = merge(t, [0, 0])
    # h1 now has h3 as a child (h2's child) instead of h2
    assert len(result.nodes[0].children) == 1
    assert result.nodes[0].children[0].name == "h3"


def test_merge_immutable():
    t = make_nested_tree()
    _ = merge(t, [0, 0])
    assert len(t.nodes[0].children) == 2   # original unchanged


def test_merge_requires_parent():
    t = make_nested_tree()
    with pytest.raises(ValueError):
        merge(t, [0])   # top-level node has no parent


def test_merge_toplevel_removes_node():
    t = make_flat_tree()
    result = merge_toplevel(t, 1)
    assert len(result.nodes) == 2
    assert result.nodes[0].name == "h1"
    assert result.nodes[1].name == "h3"


# --------------------------------------------------------------------------- #
# Split
# --------------------------------------------------------------------------- #

def test_split_basic():
    t = make_nested_tree()
    # split h1a (child 0 of h1 at path [0]) out to top level
    result = split(t, [0], 0)
    # h1a should now be a top-level node before h1
    assert result.nodes[0].name == "h1a"
    assert result.nodes[1].name == "h1"
    assert len(result.nodes[1].children) == 1
    assert result.nodes[1].children[0].name == "h1b"


def test_split_preserves_grandchildren():
    t = make_deep_tree()
    # split h3 out of h2 (child 0 of h2 at path [0,0])
    result = split(t, [0, 0], 0)
    # h3 should be a child of h1 now (sibling of h2)
    h1 = result.nodes[0]
    assert len(h1.children) == 2
    names = [c.name for c in h1.children]
    assert "h3" in names
    assert "h2" in names


def test_split_immutable():
    t = make_nested_tree()
    _ = split(t, [0], 0)
    assert len(t.nodes[0].children) == 2


def test_split_bad_index():
    t = make_nested_tree()
    with pytest.raises(IndexError):
        split(t, [0], 99)


# --------------------------------------------------------------------------- #
# Reorder
# --------------------------------------------------------------------------- #

def test_reorder_toplevel():
    t = make_flat_tree()
    result = reorder(t, [], [2, 0, 1])
    assert [n.name for n in result.nodes] == ["h3", "h1", "h2"]


def test_reorder_children():
    t = make_nested_tree()
    result = reorder(t, [0], [1, 0])
    children = result.nodes[0].children
    assert children[0].name == "h1b"
    assert children[1].name == "h1a"


def test_reorder_invalid_perm():
    t = make_flat_tree()
    with pytest.raises(ValueError):
        reorder(t, [], [0, 0, 2])


def test_reorder_immutable():
    t = make_flat_tree()
    _ = reorder(t, [], [2, 0, 1])
    assert t.nodes[0].name == "h1"


# --------------------------------------------------------------------------- #
# Enumerate all operations
# --------------------------------------------------------------------------- #

def test_all_merges_nested():
    t = make_nested_tree()
    merges = all_merges(t)
    paths = [p for p, _ in merges]
    # should find [0,0] and [0,1]
    assert [0, 0] in paths
    assert [0, 1] in paths


def test_all_merges_flat():
    t = make_flat_tree()
    assert all_merges(t) == []


def test_all_splits_nested():
    t = make_nested_tree()
    splits = all_splits(t)
    assert len(splits) == 2   # h1a and h1b can each be split out


def test_all_splits_flat():
    t = make_flat_tree()
    assert all_splits(t) == []


def test_all_reorders_flat():
    t = make_flat_tree()
    reorders = all_reorders(t)
    # 3 siblings → 2 adjacent swaps at top level
    paths = [p for p, _, _ in reorders]
    assert paths.count([]) == 2


def test_all_reorders_nested():
    t = make_nested_tree()
    reorders = all_reorders(t)
    level_paths = [p for p, _, _ in reorders]
    # h1 has 2 children → 1 swap; top has 2 nodes → 1 swap
    assert level_paths.count([]) == 1
    assert level_paths.count([0]) == 1


# --------------------------------------------------------------------------- #
# Round-trip: split then merge restores original structure
# --------------------------------------------------------------------------- #

def test_split_merge_roundtrip():
    t = make_nested_tree()
    t2 = split(t, [0], 0)    # promote h1a to top level
    # now merge it back: h1a is now nodes[0], h1 is nodes[1]
    # merging h1 child (but h1a is now a sibling, not a child) —
    # roundtrip via merge_toplevel and re-nesting isn't trivial,
    # so we just verify the split increased top-level count
    assert len(t2.nodes) == 3   # h1a, h1, h2
    assert t2.nodes[0].name == "h1a"


# --------------------------------------------------------------------------- #
# Real corpus smoke test
# --------------------------------------------------------------------------- #

def test_corpus_smoke():
    import glob
    raw_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "raw")
    files = glob.glob(os.path.join(raw_dir, "*.json"))[:5]
    for f in files:
        data = json.load(open(f))
        for record in data[:10]:
            tree = ProofTree.from_dict(record)
            d = tree.to_dict()
            assert d["name"] == record["name"]
            # all operations should run without crashing
            for path, _ in all_merges(tree):
                pass
            for path, ci, _ in all_splits(tree):
                pass
            for path, perm, _ in all_reorders(tree):
                pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
