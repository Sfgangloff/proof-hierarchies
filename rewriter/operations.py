"""
Rewriting operations on ProofTree / HaveNode structures.

Operations
----------
merge(tree, path)   -- inline the node at `path` into its parent
split(tree, path)   -- promote a child of `path` up to the parent's sibling list
reorder(tree, path, perm) -- permute siblings at a given level

All operations return a NEW ProofTree (immutable-style). The originals are unchanged.

Paths
-----
A path is a list of ints: [i, j, k, ...] meaning
  tree.nodes[i].children[j].children[k] ...
An empty path [] refers to the top-level node list itself (used by reorder only).
A single-element path [i] refers to tree.nodes[i].
"""

from __future__ import annotations
from typing import Sequence
from .tree import HaveNode, ProofTree


# --------------------------------------------------------------------------- #
# Path helpers
# --------------------------------------------------------------------------- #

def _get_parent_list_and_index(tree: ProofTree, path: list[int]) -> tuple[list[HaveNode], int]:
    """Return (sibling_list, index_within_list) for the node at `path`."""
    if not path:
        raise ValueError("path must be non-empty")
    siblings = tree.nodes
    for step in path[:-1]:
        siblings = siblings[step].children
    return siblings, path[-1]


def _get_node(tree: ProofTree, path: list[int]) -> HaveNode:
    siblings, idx = _get_parent_list_and_index(tree, path)
    return siblings[idx]


# --------------------------------------------------------------------------- #
# Merge: inline a child have into its parent
# --------------------------------------------------------------------------- #

def merge(tree: ProofTree, path: list[int]) -> ProofTree:
    """
    Inline the node at `path` into its parent, removing one level of nesting.

    The node's children are adopted by the grandparent (inserted in the same
    position), and the node's body is substituted into the parent's body
    wherever the node's name appears — using a simple text substitution.

    Requires: len(path) >= 2 (can't merge a top-level node into the tree root;
    use merge_toplevel for that).
    """
    if len(path) < 2:
        raise ValueError("merge needs a node that has a parent (path length >= 2)")
    result = tree.clone()
    parent_path = path[:-1]
    parent = _get_node(result, parent_path)
    child_idx = path[-1]
    child = parent.children[child_idx]

    # Replace parent's body: substitute child.name with child.body (inline)
    if child.name and child.name != "_":
        new_body = parent.body.replace(child.name, f"({child.body})")
    else:
        new_body = parent.body

    # Splice: remove child from parent's children, promote child's children
    new_children = (
        parent.children[:child_idx]
        + child.children
        + parent.children[child_idx + 1:]
    )
    parent.body = new_body
    parent.children = new_children
    return result


def merge_toplevel(tree: ProofTree, index: int) -> ProofTree:
    """
    Remove a top-level have node by inlining it. Since there is no Lean parent
    node, we just drop it from the list (its body is already used by downstream
    nodes at the same level — this is a structural removal, not a textual one).

    Use this to flatten the top-level list by dropping a named intermediate step.
    The resulting tree may not be Lean-valid without further editing, but it is
    structurally valid for analysis.
    """
    result = tree.clone()
    result.nodes = result.nodes[:index] + result.nodes[index + 1:]
    return result


# --------------------------------------------------------------------------- #
# Split: promote a grandchild to become a sibling of its grandparent
# --------------------------------------------------------------------------- #

def split(tree: ProofTree, path: list[int], child_index: int) -> ProofTree:
    """
    Promote child_index-th child of the node at `path` to be a sibling,
    inserted just before `path[-1]` in the parent list.

    Before:  [..., parent(children=[..., child, ...]), ...]
    After:   [..., child, parent(children=[...without child...]), ...]

    The child retains its own children. The parent's body is unchanged
    (it already referenced the child by name; in the new flat structure,
    the child now appears earlier as a sibling, which is valid Lean ordering).
    """
    result = tree.clone()
    node = _get_node(result, path)
    if child_index >= len(node.children):
        raise IndexError(f"child_index {child_index} out of range (node has {len(node.children)} children)")

    child = node.children.pop(child_index)

    # Insert child just before the node in the parent sibling list
    if len(path) == 1:
        insertion_point = path[0]
        result.nodes.insert(insertion_point, child)
    else:
        parent_siblings, node_idx = _get_parent_list_and_index(result, path)
        parent_siblings.insert(node_idx, child)

    return result


# --------------------------------------------------------------------------- #
# Reorder: permute siblings
# --------------------------------------------------------------------------- #

def reorder(tree: ProofTree, path: list[int], perm: Sequence[int]) -> ProofTree:
    """
    Permute the siblings at the level given by `path`.

    path=[]          → reorder top-level nodes
    path=[i]         → reorder children of tree.nodes[i]
    path=[i,j]       → reorder children of tree.nodes[i].children[j]

    `perm` must be a permutation of range(n) where n is the sibling count.
    """
    result = tree.clone()
    if not path:
        siblings = result.nodes
        n = len(siblings)
        if sorted(perm) != list(range(n)):
            raise ValueError(f"perm {perm} is not a valid permutation of 0..{n-1}")
        result.nodes = [siblings[i] for i in perm]
    else:
        node = _get_node(result, path)
        siblings = node.children
        n = len(siblings)
        if sorted(perm) != list(range(n)):
            raise ValueError(f"perm {perm} is not a valid permutation of 0..{n-1}")
        node.children = [siblings[i] for i in perm]
    return result


# --------------------------------------------------------------------------- #
# Enumerate all valid single-step operations on a tree
# --------------------------------------------------------------------------- #

def all_merges(tree: ProofTree) -> list[tuple[list[int], ProofTree]]:
    """Return (path, result) for every valid merge (nodes with a parent)."""
    results = []

    def visit(nodes: list[HaveNode], prefix: list[int]):
        for i, node in enumerate(nodes):
            for j in range(len(node.children)):
                path = prefix + [i, j]
                try:
                    results.append((path, merge(tree, path)))
                except Exception:
                    pass
                visit(node.children, prefix + [i])

    visit(tree.nodes, [])
    return results


def all_splits(tree: ProofTree) -> list[tuple[list[int], int, ProofTree]]:
    """Return (path, child_index, result) for every valid split."""
    results = []

    def visit(nodes: list[HaveNode], prefix: list[int]):
        for i, node in enumerate(nodes):
            for j in range(len(node.children)):
                path = prefix + [i]
                try:
                    results.append((path, j, split(tree, path, j)))
                except Exception:
                    pass
            visit(node.children, prefix + [i])

    visit(tree.nodes, [])
    return results


def all_reorders(tree: ProofTree) -> list[tuple[list[int], list[int], ProofTree]]:
    """
    Return (path, perm, result) for all non-trivial reorderings (adjacent swaps only,
    to keep the count manageable).
    """
    import itertools
    results = []

    def adjacent_swaps(n: int) -> list[list[int]]:
        base = list(range(n))
        swaps = []
        for i in range(n - 1):
            p = base[:]
            p[i], p[i + 1] = p[i + 1], p[i]
            swaps.append(p)
        return swaps

    def visit_level(siblings: list[HaveNode], path: list[int]):
        n = len(siblings)
        if n >= 2:
            for perm in adjacent_swaps(n):
                try:
                    results.append((path[:], perm, reorder(tree, path, perm)))
                except Exception:
                    pass
        for i, node in enumerate(siblings):
            visit_level(node.children, path + [i])

    visit_level(tree.nodes, [])
    return results
