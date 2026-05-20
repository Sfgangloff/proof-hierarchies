"""
Stage 0b dev loop — sync our extractor module into the Volume's ntp-toolkit,
patch the lakefile, build `have_tree`, print diagnostics. Iterate.

  .venv/bin/modal run --detach modal/build_have_tree.py::build_ht
  .venv/bin/modal run --detach modal/build_have_tree.py::run_ht --module Mathlib.Logic.Basic

The Lean toolchain is baked into the image (one-time) so each dev container
starts fast instead of re-downloading v4.26.0.
"""

import pathlib
import modal

VOLUME_NAME = "proof-hierarchies-lean"
VOL_ROOT = "/lean"
NTP = f"{VOL_ROOT}/ntp-toolkit"
SRC_LOCAL = str(pathlib.Path(__file__).parent.parent / "extractor" / "ntp_module")

app = modal.App("proof-hierarchies-havetree")
vol = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git", "curl", "build-essential", "ca-certificates")
    .run_commands(
        "curl -fsSL https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh "
        "-o /tmp/elan-init.sh",
        "sh /tmp/elan-init.sh -y --default-toolchain none",
        # bake the frozen toolchain into the image → fast dev containers
        "/root/.elan/bin/elan toolchain install leanprover/lean4:v4.26.0",
        "/root/.elan/bin/elan default leanprover/lean4:v4.26.0",
    )
    .env({"PATH": "/root/.elan/bin:/usr/local/bin:/usr/bin:/bin"})
    .add_local_dir(SRC_LOCAL, remote_path="/src", copy=False)
)

LEAN_EXE_BLOCK = """
lean_exe have_tree where
  root := `scripts.have_tree
  supportInterpreter := true

lean_exe proof_terms where
  root := `scripts.proof_terms
  supportInterpreter := true
"""


def _sh(cmd: str, cwd: str | None = None, check: bool = True):
    import subprocess
    print(f"+ {cmd}", flush=True)
    return subprocess.run(cmd, shell=True, check=check, cwd=cwd,
                          executable="/bin/bash")


def _sync_sources():
    """Copy mounted /src into the ntp-toolkit checkout; patch lakefile."""
    import shutil, os
    pairs = [
        ("/src/TrainingData/InfoTree/HaveTree.lean",
         f"{NTP}/TrainingData/InfoTree/HaveTree.lean"),
        ("/src/scripts/have_tree.lean",
         f"{NTP}/scripts/have_tree.lean"),
        ("/src/scripts/proof_terms.lean",
         f"{NTP}/scripts/proof_terms.lean"),
        ("/src/TrainingData/HaveSelfTest.lean",
         f"{NTP}/TrainingData/HaveSelfTest.lean"),
    ]
    for s, d in pairs:
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copyfile(s, d)
        print(f"synced {s} -> {d}")
    lf = f"{NTP}/lakefile.lean"
    txt = open(lf).read()
    needed = "lean_exe proof_terms" not in txt
    if needed:
        # remove any prior partial patch then re-append the canonical block
        txt = "\n".join(l for l in txt.splitlines()
                       if not (l.startswith("lean_exe have_tree")
                               or l.startswith("  root := `scripts.have_tree")))
        open(lf, "w").write(txt.rstrip() + "\n" + LEAN_EXE_BLOCK)
        print("patched lakefile.lean (have_tree + proof_terms)")
    else:
        print("lakefile.lean already has both exes")


@app.function(image=image, volumes={VOL_ROOT: vol}, timeout=60 * 40)
def build_ht():
    assert "MATHLIB_COMMIT=2df2f0150c275ad53cb3c90f7c98ec15a56a1a67" \
        in open(f"{VOL_ROOT}/PIN.txt").read(), "pin mismatch — STOP"
    _sync_sources()
    r = _sh("lake build have_tree proof_terms", cwd=NTP, check=False)
    vol.commit()   # persist synced sources + patched lakefile + build artifacts
    if r.returncode != 0:
        print(f"\n=== BUILD FAILED (exit {r.returncode}) — fix and re-run ===")
    else:
        print("\n=== have_tree BUILT OK — running self-test ===")
        _sh("lake exe have_tree TrainingData.HaveSelfTest", cwd=NTP, check=False)


@app.function(image=image, volumes={VOL_ROOT: vol}, timeout=60 * 5)
def cat_src():
    """Print the known-good ntp-toolkit sources we model have_tree on
    (ground truth at the frozen SHA)."""
    for rel in ("scripts/declarations.lean",
                "scripts/full_proof_training_data.lean",
                "TrainingData/Frontend.lean"):
        p = f"{NTP}/{rel}"
        print(f"\n===== {rel} =====")
        print(open(p).read())


@app.function(image=image, volumes={VOL_ROOT: vol}, timeout=60 * 30)
def run_ht(module: str = "Mathlib.Logic.Basic"):
    _sh(f"lake exe have_tree {module} | head -c 4000 ; echo", cwd=NTP)


@app.function(image=image, volumes={VOL_ROOT: vol}, timeout=60 * 30)
def run_proof_terms(module: str = "Mathlib.Logic.Basic"):
    """Sanity-check the proof_terms extractor on one module."""
    _sh(f"lake exe proof_terms {module} | head -c 4000 ; echo", cwd=NTP)
