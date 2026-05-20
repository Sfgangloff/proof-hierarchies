"""
Stage 0a (physical) — build the FROZEN Lean/Mathlib environment onto a
persistent Modal Volume, and capture + record the exact Mathlib commit.

Pin (see EXPERIMENT.md §8): Lean v4.26.0, Mathlib at the tip of the
`v4.26.0` ref, repl @ branch `v4.26.0`. The Kimina Lean Server does NOT
freeze the Mathlib commit, so the whole point of this script is to resolve
it ONCE, write it to the Volume as the single source of truth, and never
let it move again.

Architecture rationale:
  - The image carries only the toolchain bootstrap (elan, git, build deps).
  - The heavy, mutable ~5-15 GB (Mathlib clone + `lake exe cache get`
    oleans + repl build) lives on a *Volume*, not in image layers — image
    builds have time limits and are not meant for large mutable data.

Usage (after `modal setup`):
  modal run modal/build_env.py::build          # one-time, slow (cache get)
  modal run modal/build_env.py::show_pin       # print the captured commit
  modal run modal/build_env.py::sanity         # compile a trivial Mathlib proof

NOTE: written against the modern Modal API (App/Image/Volume). If the
installed `modal` version differs, adjust the few decorated calls; the
shell logic is what matters and is version-independent.
"""

import modal

LEAN_VERSION = "v4.26.0"          # frozen project-wide pin
MATHLIB_REF = "v4.26.0"           # branch/tag we resolve to a commit
REPL_REF = "v4.26.0"

VOLUME_NAME = "proof-hierarchies-lean"
VOL_ROOT = "/lean"                 # mount point for the persistent volume

app = modal.App("proof-hierarchies-env")
vol = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)

# Minimal bootstrap image: elan installs the exact Lean toolchain on demand
# from each repo's `lean-toolchain`. No Lean baked into the image.
image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git", "curl", "build-essential", "ca-certificates")
    .run_commands(
        "curl -fsSL https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh "
        "-o /tmp/elan-init.sh",
        "sh /tmp/elan-init.sh -y --default-toolchain none",
    )
    .env({"PATH": "/root/.elan/bin:/usr/local/bin:/usr/bin:/bin"})
)


def _sh(cmd: str) -> None:
    """Run a shell command, raising on non-zero exit."""
    import subprocess
    print(f"+ {cmd}", flush=True)
    subprocess.run(cmd, shell=True, check=True, executable="/bin/bash")


@app.function(image=image, volumes={VOL_ROOT: vol}, timeout=60 * 60 * 3)
def build():
    """One-time: populate the Volume with the pinned Mathlib + repl, then
    freeze the resolved Mathlib commit to ${VOL_ROOT}/PIN.txt."""
    import os, subprocess, textwrap

    os.chdir(VOL_ROOT)

    # --- Mathlib at the v4.26.0 ref (shallow; we re-freeze via PIN.txt) ---
    if not os.path.isdir(f"{VOL_ROOT}/mathlib4/.git"):
        _sh(
            f"git clone --branch {MATHLIB_REF} --single-branch --depth 1 "
            f"https://github.com/leanprover-community/mathlib4.git "
            f"{VOL_ROOT}/mathlib4"
        )
    os.chdir(f"{VOL_ROOT}/mathlib4")
    # elan auto-installs the toolchain named in mathlib4/lean-toolchain
    _sh("elan show || true")
    _sh("lake exe cache get")          # download prebuilt oleans (~5-15 GB)
    _sh("lake build")                  # near-no-op once cache is warm

    mathlib_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip()

    # --- repl @ v4.26.0 ---
    os.chdir(VOL_ROOT)
    if not os.path.isdir(f"{VOL_ROOT}/repl/.git"):
        _sh(
            f"git clone --branch {REPL_REF} --single-branch --depth 1 "
            f"https://github.com/leanprover-community/repl.git {VOL_ROOT}/repl"
        )
    os.chdir(f"{VOL_ROOT}/repl")
    _sh("lake build")
    repl_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip()

    pin = textwrap.dedent(f"""\
        # FROZEN PIN — single source of truth. Do not edit by hand.
        LEAN_VERSION={LEAN_VERSION}
        MATHLIB_REF={MATHLIB_REF}
        MATHLIB_COMMIT={mathlib_commit}
        REPL_REF={REPL_REF}
        REPL_COMMIT={repl_commit}
    """)
    with open(f"{VOL_ROOT}/PIN.txt", "w") as f:
        f.write(pin)
    vol.commit()
    print("\n=== FROZEN PIN ===\n" + pin)
    print("Copy MATHLIB_COMMIT into EXPERIMENT.md §8 and memory.")


@app.function(image=image, volumes={VOL_ROOT: vol})
def show_pin():
    with open(f"{VOL_ROOT}/PIN.txt") as f:
        print(f.read())


@app.function(image=image, volumes={VOL_ROOT: vol}, timeout=60 * 20)
def sanity():
    """Compile a trivial proof against the frozen Mathlib to confirm the
    environment is usable."""
    import os
    os.chdir(f"{VOL_ROOT}/mathlib4")
    test = "import Mathlib\nexample : 1 + 1 = 2 := by norm_num\n"
    with open("/tmp/sanity.lean", "w") as f:
        f.write(test)
    _sh("lake env lean /tmp/sanity.lean && echo SANITY_OK")
