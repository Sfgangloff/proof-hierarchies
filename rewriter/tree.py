"""
Core data structure for have-trees.

A HaveNode represents one `have h : T := body` in a Lean 4 proof.
Children are the have-nodes that appear inside `body` (nested haves).
The top-level proof is a list of HaveNodes (siblings before the final tactic).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import copy
import json


@dataclass
class HaveNode:
    name: str
    type: str        # goal type; may be "" if not captured
    body: str        # tactic / term proof of this goal
    children: list[HaveNode] = field(default_factory=list)

    def is_leaf(self) -> bool:
        return len(self.children) == 0

    def depth(self) -> int:
        if self.is_leaf():
            return 0
        return 1 + max(c.depth() for c in self.children)

    def size(self) -> int:
        return 1 + sum(c.size() for c in self.children)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type,
            "body": self.body,
            "children": [c.to_dict() for c in self.children],
        }

    @staticmethod
    def from_dict(d: dict) -> HaveNode:
        return HaveNode(
            name=d["name"],
            type=d.get("type", ""),
            body=d.get("body", ""),
            children=[HaveNode.from_dict(c) for c in d.get("children", [])],
        )

    def clone(self) -> HaveNode:
        return copy.deepcopy(self)

    def to_lean(self, indent: int = 0) -> str:
        """Render back to approximate Lean 4 syntax (best-effort, not verified)."""
        pad = "  " * indent
        lines = []
        for child in self.children:
            lines.append(child.to_lean(indent + 1))
        type_ann = f" : {self.type}" if self.type else ""
        if lines:
            inner = "\n".join(lines)
            lines_str = f"\n{inner}\n{pad}  "
        else:
            lines_str = ""
        name_part = f"have {self.name}{type_ann} := " if self.name != "_" else f"have{type_ann} := "
        if lines:
            return f"{pad}{name_part}{{\n{inner}\n{pad}  {self.body}\n{pad}}}"
        else:
            return f"{pad}{name_part}{self.body}"


@dataclass
class ProofTree:
    """A proof is a flat list of top-level have-nodes, followed by a closing tactic."""
    theorem_name: str
    statement: str
    nodes: list[HaveNode]         # ordered top-level haves
    module: str = ""

    def depth(self) -> int:
        if not self.nodes:
            return 0
        return max(n.depth() for n in self.nodes)

    def size(self) -> int:
        return sum(n.size() for n in self.nodes)

    def to_dict(self) -> dict:
        return {
            "module": self.module,
            "name": self.theorem_name,
            "statement": self.statement,
            "have_tree": [n.to_dict() for n in self.nodes],
        }

    @staticmethod
    def from_dict(d: dict) -> ProofTree:
        return ProofTree(
            theorem_name=d.get("name", ""),
            statement=d.get("statement", ""),
            module=d.get("module", ""),
            nodes=[HaveNode.from_dict(n) for n in d.get("have_tree", [])],
        )

    def clone(self) -> ProofTree:
        return copy.deepcopy(self)

    def to_lean(self) -> str:
        lines = [f"-- theorem {self.theorem_name}"]
        for node in self.nodes:
            lines.append(node.to_lean(indent=1))
        return "\n".join(lines)
