"""
Batch extraction of have-trees from Lean 4 source files.

Strategy (Phase 1 — syntactic):
  Parse .lean files to find theorem/lemma declarations and their have-statements.
  Build a tree from indentation nesting. This is a fast first pass;
  the Lean-side #extract_have command gives the accurate semantic version.

Output: data/raw/<module_name>.json  — list of ProofRecord objects.
"""

import re
import json
import sys
from pathlib import Path
from dataclasses import dataclass, asdict

ROOT = Path(__file__).parent.parent


@dataclass
class HaveNode:
    name: str
    type: str
    body: str
    indent: int   # used only during tree-building; stripped in output
    children: list


@dataclass
class ProofRecord:
    module: str
    name: str
    statement: str
    have_tree: list


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# Matches any `have` form with `:=`:
#   have name : type := body
#   have name := body           (no type annotation)
#   have : type := body         (anonymous, possibly type contains `=`)
#   have ⟨a, b⟩ := body        (destructuring)
#
# Uses lazy `.*?` for the header so it stops at the first `:=`.
HAVE_RE = re.compile(
    r'^(?P<indent>[ \t]*)'
    r'have\b'
    r'(?P<header>.*?)'
    r':=\s*(?P<body>.*)$'
)

# Matches `have name : type` ending with ` by` (proof body on next lines, no `:=`).
HAVE_BY_RE = re.compile(
    r'^(?P<indent>[ \t]*)'
    r'have\b'
    r'(?P<header>.*?)'
    r'\s+by\s*$'
)

# Simple word identifier (safe to use as a substitution target in merge).
_SIMPLE_NAME_RE = re.compile(r"^[\w']+$")


def _parse_header(header: str) -> tuple[str, str]:
    """Split a have-header into (name, type).

    Header is everything between `have` and `:=` / ` by`.
    Returns ('_', type) for anonymous or destructuring forms.
    """
    header = header.strip()
    # Find the first ':' that is NOT part of ':=' (i.e. not followed by '=')
    i = 0
    while i < len(header):
        if header[i] == ':':
            if i + 1 < len(header) and header[i + 1] == '=':
                # This is ':=' inside the header (shouldn't happen due to regex, but guard)
                i += 2
                continue
            # Found the type separator
            name_part = header[:i].strip()
            type_part = header[i + 1:].strip()
            name = name_part if _SIMPLE_NAME_RE.match(name_part) else '_'
            return name, type_part
        i += 1
    # No ':' found — the whole header is the name (or pattern)
    name = header if _SIMPLE_NAME_RE.match(header) else '_'
    return name, ''

# Top-level declaration keyword (handles attributes, modifiers on preceding lines)
TOPDECL_KW_RE = re.compile(
    r'^(?:(?:private|protected|noncomputable|@\[[\w\s,]*\])\s+)*'
    r'(?:theorem|lemma|def|abbrev|example)\s+'
    r'(?P<name>[\w\'\.]+)'
)

# `:= by` or `:=` ending a declaration header line
DECL_HEADER_END_RE = re.compile(r':=\s*(?:by)?\s*$')

# Lines that start a top-level block (used to detect end of a proof body)
TOPLEVEL_START_RE = re.compile(
    r'^(?:theorem|lemma|def|abbrev|example|class|instance|structure|inductive'
    r'|namespace|section|end|variable|open|private|protected|noncomputable'
    r'|@\[)'
)


# ---------------------------------------------------------------------------
# Declaration scanner
# ---------------------------------------------------------------------------

def scan_declarations(lines: list[str]) -> list[tuple[str, str, int, int]]:
    """
    Return list of (name, statement, body_start_line, body_end_line).
    body_start_line is the line AFTER the `:= by` header.
    body_end_line is exclusive.
    """
    results = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        m = TOPDECL_KW_RE.match(line.lstrip())
        if not m or line[0] == ' ':  # only truly top-level (no leading indent)
            i += 1
            continue

        decl_name = m.group('name')

        # Collect header lines until we see `:= by` or `:=`
        header_lines = [line]
        j = i + 1
        header_end = i  # line index of the line containing `:=`

        if DECL_HEADER_END_RE.search(line):
            header_end = i
        else:
            while j < n and j < i + 20:  # headers rarely exceed 20 lines
                header_lines.append(lines[j])
                if DECL_HEADER_END_RE.search(lines[j]):
                    header_end = j
                    break
                j += 1

        if header_end == i and not DECL_HEADER_END_RE.search(line):
            # Never found `:=`, skip
            i += 1
            continue

        # Extract the statement (everything between the name and `:=`)
        raw_header = ' '.join(l.strip() for l in header_lines)
        stmt_match = re.search(r':\s*(.+?)\s*:=', raw_header)
        statement = stmt_match.group(1).strip() if stmt_match else ''

        # Proof body starts after the header
        body_start = header_end + 1

        # Body ends at the next top-level declaration
        k = body_start
        while k < n:
            bl = lines[k]
            if bl.strip() == '':
                k += 1
                continue
            if not bl[0].isspace() and TOPLEVEL_START_RE.match(bl):
                break
            k += 1

        results.append((decl_name, statement, body_start, k))
        i = k  # continue scanning from end of this proof

    return results


# ---------------------------------------------------------------------------
# Have-tree builder
# ---------------------------------------------------------------------------

def parse_have_tree(lines: list[str]) -> list[HaveNode]:
    """Build a have-tree from proof body lines using indentation nesting."""
    stack: list[HaveNode] = []
    roots: list[HaveNode] = []

    for line in lines:
        m = HAVE_RE.match(line) or HAVE_BY_RE.match(line)
        if not m:
            continue
        ind = len(m.group('indent').expandtabs(4))
        name, typ = _parse_header(m.group('header'))
        body = (m.groupdict().get('body') or '').strip()

        node = HaveNode(name=name, type=typ, body=body, indent=ind, children=[])

        while stack and stack[-1].indent >= ind:
            stack.pop()

        if stack:
            stack[-1].children.append(node)
        else:
            roots.append(node)
        stack.append(node)

    return roots


def _to_dict(node: HaveNode) -> dict:
    return {
        'name':     node.name,
        'type':     node.type,
        'body':     node.body,
        'children': [_to_dict(c) for c in node.children],
    }


# ---------------------------------------------------------------------------
# Non-triviality filter
# ---------------------------------------------------------------------------

# Single-word tactics that are always trivial on their own.
_TRIVIAL_WORDS = {
    'rfl', 'simp', 'ring', 'ring_nf', 'trivial', 'decide', 'tauto',
    'omega', 'norm_num', 'aesop', 'assumption', 'contradiction',
    'done', 'rfl.', 'constructor', 'intro', 'exact',
}


def _body_nontrivial(body: str) -> bool:
    """
    Return True if a single-node proof body is interesting enough to keep.

    Rules (any one is sufficient):
      - Contains a tactic sequencer (;  <;>  ·) → multi-step, keep.
      - Body spans multiple non-empty lines → multi-step, keep.
      - Body is at least MIN_BODY_CHARS characters → complex single call, keep.
    """
    MIN_BODY_CHARS = 25

    # Multi-line body (the lines were passed separately; check joined body)
    # Sequencing operators
    if re.search(r'(?:;|<;>|\n\s*·)', body):
        return True

    inner = re.sub(r'^by\s+', '', body.strip())

    # Pure single-word trivial tactic
    if re.match(r'^\w+$', inner) and inner in _TRIVIAL_WORDS:
        return False

    # "exact <one_identifier>" or "apply <one_identifier>" with no spaces in arg
    if re.match(r'^(?:exact|apply)\s+\S+$', inner) and len(inner) < MIN_BODY_CHARS:
        return False

    return len(inner) >= MIN_BODY_CHARS


def _tree_depth(nodes: list[dict]) -> int:
    def nd(n: dict) -> int:
        return 0 if not n['children'] else 1 + max(nd(c) for c in n['children'])
    return max(nd(n) for n in nodes) if nodes else 0


def is_nontrivial(tree: list[dict], min_depth: int = 0) -> bool:
    """Return True if the proof tree is worth keeping in the corpus.

    min_depth=0  — original behaviour (any have-tree with a non-trivial body)
    min_depth=1  — require at least one nested have (genuine hierarchy)
    """
    if min_depth > 0:
        # Synth-roots (name=='_') are never genuinely hierarchical
        if len(tree) == 1 and tree[0]['name'] == '_':
            return False
        return _tree_depth(tree) >= min_depth

    if len(tree) > 1:
        return True
    node = tree[0]
    if node['children']:
        return True
    # Single flat node — apply body filter
    return _body_nontrivial(node['body'])


# ---------------------------------------------------------------------------
# File-level extraction
# ---------------------------------------------------------------------------

def extract_from_file(path: Path, min_depth: int = 0) -> list[ProofRecord]:
    text  = path.read_text(encoding='utf-8', errors='replace')
    lines = text.splitlines()
    records: list[ProofRecord] = []

    for name, stmt, bstart, bend in scan_declarations(lines):
        body_lines = lines[bstart:bend]
        tree = parse_have_tree(body_lines)

        if not tree:
            if min_depth > 0:
                # No have statements → depth 0; skip if min_depth requires nesting
                continue
            # No `have` statements — synthesize a single root node from
            # the full proof body so the proof is still represented.
            non_empty = [l.strip() for l in body_lines if l.strip()]
            if not non_empty:
                continue
            if len(non_empty) > 1:
                body_text = '\n'.join(non_empty)
            else:
                body_text = non_empty[0]
            tree = [{'name': '_', 'type': '', 'body': body_text, 'children': []}]

        tree_dicts = [_to_dict(n) for n in tree] if isinstance(tree[0], HaveNode) else tree
        if is_nontrivial(tree_dicts, min_depth=min_depth):
            records.append(ProofRecord(
                module=path.stem,
                name=name,
                statement=stmt,
                have_tree=tree_dicts,
            ))

    return records


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def process_directory(src: Path, out: Path, min_depth: int = 0) -> None:
    out.mkdir(parents=True, exist_ok=True)
    files = sorted(src.rglob('*.lean'))
    print(f"Found {len(files)} .lean files under {src}")
    if min_depth:
        print(f"Keeping only trees with depth >= {min_depth}")
    total = 0
    for i, f in enumerate(files):
        records = extract_from_file(f, min_depth=min_depth)
        if records:
            rel = f.relative_to(src)
            dest = out / (str(rel).replace('/', '__').replace('.lean', '.json'))
            dest.write_text(json.dumps([asdict(r) for r in records], indent=2))
            total += len(records)
        if (i + 1) % 500 == 0:
            print(f"  {i+1}/{len(files)} files, {total} proofs so far…")
    print(f"Extracted {total} proofs → {out}")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(
        description="Extract have-trees from Lean 4 source files."
    )
    parser.add_argument("src", help="Path to Lean source directory")
    parser.add_argument("out", nargs="?", help="Output directory (default: data/deep/)")
    parser.add_argument("--min-depth", type=int, default=1,
                        help="Minimum have-tree depth to keep (default: 1)")
    args = parser.parse_args()

    src_dir = Path(args.src)
    out_dir = Path(args.out) if args.out else ROOT / 'data' / 'deep'
    process_directory(src_dir, out_dir, min_depth=args.min_depth)
