"""Constructive same-format serializer over REAL captured proof bodies (not skeletons).

Question this answers WITHOUT spending Modal credit:
  The whole e-0033..e-0036 chain established that the same-format (both-tactic-mode)
  build is well-defined and confound-free BY CONSTRUCTION, but EVERY figure in it
  (the header-only length delta e-0027/e-0033; the sibling-referenced substitution
  rate e-0034=12.8% "lower bound"; the compression-inversion rate a-0033=0.90%) was
  estimated from data/deep have_tree records whose proof BODIES are ELIDED to a bare
  `by` -- so the emitted serializations were explicitly "structural skeletons, not
  runnable Lean", and reference counts were sibling-only (residual unobservable).

  corpus_v3/full_proofs, by contrast, carries the FULL residual tactic body with
  multi-`have` blocks intact (a-0035). This script runs the same-format serializer
  (e-0033's scheme) over the corpus_v3 full_proofs that actually have >=2 top-level
  `have` steps -- REAL, non-elided bodies -- and measures, for the first time on
  real captured Lean:

    1. FORMAT delta = 0 by construction (both policies tactic-mode; they share the
       residual and differ only by the named-have headers pi_leaf keeps).
    2. The REALIZED header-only length delta pi_leaf adds over pi_root, from real
       bodies -- cross-check on e-0027 (~117 char) / e-0033 (~147 char) skeleton
       estimates.
    3. Reference counts including the RESIDUAL body (not just siblings): how many
       named haves are referenced 0 / 1 / >=2 times downstream. This tightens
       e-0034's sibling-only "12.8% lower bound" into a real estimate on this subset.
    4. COMPRESSION-INVERSION: how many haves are referenced >=2 times, so a sound
       pi_root inliner that duplicates the body makes pi_root LONGER than pi_leaf
       (inverting the "rough is shorter" assumption a-0010/q-0008/a-0033 rest on).

  HONEST SCOPE: corpus_v3 full_proofs are the FOUNDATIONAL modules (the granularity
  construct is rare here, e-0026), so only N=7 decls carry >=2 real top-level haves
  (an 8th, eq_one_of_inv_eq', is a term-mode `match` whose haves sit inside arms, not
  at the tactic top level, so it is excluded by the indentation parser). This is a
  small CONSTRUCTIVE demonstration on real bodies -- the first to escape the
  "bodies elided / skeleton / lower-bound" caveat threaded through a-0026..a-0035 --
  NOT a corpus-scale measurement. It validates the SCHEME end-to-end on real Lean and
  checks whether the skeleton-derived figures hold up; the corpus-scale figure still
  needs the Modal extract_full_proofs re-run over the 452 deep modules (e-0037).

  CAVEATS: heuristic text parsing of top-level `have` blocks by indentation (no Lean
  elaboration); anonymous `have :` are named `this`, shadowing approximated by cutting
  the downstream window at the next `have :` (correct for the dominant redefine-then-
  use pattern, may undercount an old `this` referenced inside the new have's own body);
  ref counts are TEXTUAL identifier occurrences, so an instance-providing have used via
  typeclass resolution shows 0 refs yet cannot be dropped; net-length uses a crude
  full-body-duplication-per-use-site model; N=7 over foundational modules; no round-trip
  / no Modal / not runnable Lean emitted.

Input (local, already on disk):
  data/corpus_v3/full_proofs/*.jsonl  -- {declName, module, proof} with full bodies

  python3 data/analyze_realbody_same_format.py [--out path.json] [--show]
"""
import argparse
import glob
import json
import re

FULL_PROOFS_GLOB = "data/corpus_v3/full_proofs/*.jsonl"
# Lean identifier continuation chars: alnum, _, ', and Unicode subscripts (h₁, x₀, …)
NAME_CONT = r"A-Za-z0-9_'₀-₉ₐ-ₜ"
NAME_RE = re.compile(r"[A-Za-z_][" + NAME_CONT + r"]*")
# anonymous-binder destructuring: have <pat> := ...  (introduces hyps, not an
# inline-able named sub-derivation)
HAVE_RE = re.compile(r"^have\b")


def load_multihave(min_haves=2):
    """Return [(declName, module, proof)] for proofs with >= min_haves top-level haves."""
    out = []
    for f in glob.glob(FULL_PROOFS_GLOB):
        for line in open(f):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if not isinstance(r, dict):
                continue
            p = r.get("proof", "") or ""
            blocks = top_level_haves(p)
            if len(blocks) >= min_haves:
                out.append((r.get("declName", ""), r.get("module", ""), p, blocks))
    return out


def proof_body_lines(proof):
    """Strip the leading ':=' / ':= by' and return (base_indent, [lines]) of the body."""
    # drop a leading ':=' or ':= by'
    txt = proof
    txt = re.sub(r"^\s*:=\s*by\b", "", txt, count=1)
    if txt == proof:  # no 'by': term-mode body after ':='
        txt = re.sub(r"^\s*:=", "", proof, count=1)
    lines = txt.split("\n")
    # base indent = min indent over non-empty lines
    indents = [len(l) - len(l.lstrip()) for l in lines if l.strip()]
    if not indents:
        return 0, []
    base = min(indents)
    return base, lines


def top_level_haves(proof):
    """Heuristically split the proof body into top-level statements and return the
    `have` ones as dicts {name, header_len, body_len, is_destructure, full}.
    A top-level statement starts at base indent; it extends until the next line at
    base indent (continuation lines are deeper-indented)."""
    base, lines = proof_body_lines(proof)
    # group lines into statements by base indent
    stmts = []
    cur = []
    for l in lines:
        if not l.strip():
            if cur:
                cur.append(l)
            continue
        indent = len(l) - len(l.lstrip())
        if indent <= base and l.lstrip().startswith(("have", "let", "intro", "refine",
                                                     "rw", "simp", "exact", "ext",
                                                     "obtain", "subst", "convert",
                                                     "classical", "apply", "grind",
                                                     "match", "calc", "{", "·", "|",
                                                     "_")):
            if cur:
                stmts.append(cur)
            cur = [l]
        else:
            if cur:
                cur.append(l)
            else:
                cur = [l]
    if cur:
        stmts.append(cur)

    haves = []
    for st in stmts:
        text = "\n".join(st)
        head = st[0].lstrip()
        if not HAVE_RE.match(head):
            continue
        # destructuring binder: have <...> := ...   (no inline-able name)
        m_destr = re.match(r"^have\s*[⟨\(]", head)
        # named: have NAME ... : TYPE := ...   or  have NAME := ...
        m_named = re.match(r"^have\s+([A-Za-z_][" + NAME_CONT + r"]*)", head)
        # anonymous: have : TYPE := ...   (named `this`)
        m_anon = re.match(r"^have\s*:", head)
        if m_destr and not m_named:
            name = None
            kind = "destructure"
        elif m_anon:
            name = "this"
            kind = "anon_this"
        elif m_named:
            name = m_named.group(1)
            kind = "named"
        else:
            name = None
            kind = "other"
        # header = text up to and including ' := ' (what pi_leaf adds; the body is shared)
        hm = re.search(r":=", text)
        header_len = (hm.end() if hm else len(text))
        body_len = len(text) - header_len
        haves.append({
            "name": name,
            "kind": kind,
            "header_len": header_len,
            "body_len": body_len,
            "full_len": len(text),
            "full": text,
        })
    return haves


def count_downstream_refs(proof, blocks):
    """For each named/this have, count downstream identifier references (siblings +
    residual). For `this`, count only until the next `have :` redefinition (Lean
    shadowing)."""
    base, lines = proof_body_lines(proof)
    full_text = "\n".join(lines)
    results = []
    # build a flat token stream with positions to find 'after definition' uses
    for b in blocks:
        nm = b["name"]
        if nm is None:
            results.append({**b, "refs": None})
            continue
        # locate the defining occurrence (first 'have <nm>' or 'have :' for this)
        # downstream text = everything in the proof AFTER this block's full text
        idx = full_text.find(b["full"])
        after = full_text[idx + len(b["full"]):] if idx >= 0 else ""
        if nm == "this":
            # cut at next anonymous 'have :' (redefinition of `this`)
            mcut = re.search(r"\n\s*have\s*:", after)
            if mcut:
                after = after[:mcut.start()]
        bnd = r"[" + NAME_CONT + r"]"
        refs = len(re.findall(r"(?<!" + bnd + r")" + re.escape(nm) + r"(?!" + bnd + r")", after))
        results.append({**b, "refs": refs})
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/realbody_same_format.json")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()

    decls = load_multihave(min_haves=2)
    per_decl = []
    all_haves = []
    for name, module, proof, blocks in decls:
        scored = count_downstream_refs(proof, blocks)
        per_decl.append({"decl": name, "module": module,
                         "n_haves": len(blocks), "haves": scored})
        all_haves.extend(scored)

    # aggregate over inline-able named haves (named + anon_this; destructure binders
    # are hypotheses, not inline-able sub-derivations -- excluded, matching e-0032)
    inlineable = [h for h in all_haves if h["kind"] in ("named", "anon_this")]
    destruct = [h for h in all_haves if h["kind"] == "destructure"]

    ref_dist = {"0": 0, "1": 0, "2+": 0}
    header_deltas = []  # header_len pi_leaf keeps that pi_root drops (granularity unit)
    invert = 0          # referenced >=2 -> sound pi_root duplicates body -> longer
    net_deltas = []     # pi_root_len - pi_leaf_len per have (negative => root shorter)
    for h in inlineable:
        r = h["refs"]
        if r is None:
            continue
        if r == 0:
            ref_dist["0"] += 1
        elif r == 1:
            ref_dist["1"] += 1
        else:
            ref_dist["2+"] += 1
        header_deltas.append(h["header_len"])
        # pi_leaf has: header + body (the have line).  pi_root inlines the body at
        # each of r use sites and drops the header+name.  Approximate:
        #   pi_leaf cost for this unit = header_len + body_len (the have block)
        #   pi_root cost              = r * body_len  (body duplicated at use sites)
        # net = pi_root - pi_leaf
        net = r * h["body_len"] - (h["header_len"] + h["body_len"])
        net_deltas.append(net)
        if r >= 2:
            invert += 1

    def med(xs):
        if not xs:
            return None
        s = sorted(xs)
        n = len(s)
        return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2

    summary = {
        "n_decls_with_ge2_haves": len(decls),
        "n_top_level_haves": len(all_haves),
        "n_inlineable_named_haves": len(inlineable),
        "n_destructure_binders": len(destruct),
        "format_delta": "0 by construction (both policies tactic-mode; shared residual)",
        "downstream_ref_distribution_over_inlineable": ref_dist,
        "header_len_delta_pi_leaf_over_pi_root": {
            "median": med(header_deltas),
            "max": max(header_deltas) if header_deltas else None,
            "all": sorted(header_deltas, reverse=True),
        },
        "net_len_pi_root_minus_pi_leaf": {
            "median": med(net_deltas),
            "min": min(net_deltas) if net_deltas else None,
            "max": max(net_deltas) if net_deltas else None,
        },
        "compression_inversions_root_longer": invert,
        "compression_inversion_rate": (invert / len(inlineable)) if inlineable else None,
    }

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if args.show:
        for d in per_decl:
            print(f"\n### {d['decl']}  ({d['module']})  n_haves={d['n_haves']}")
            for h in d["haves"]:
                print(f"  [{h['kind']:11s}] name={str(h['name']):10s} "
                      f"hdr={h['header_len']:3d} body={h['body_len']:4d} refs={h['refs']}")

    out = {"summary": summary, "per_decl": per_decl}
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
