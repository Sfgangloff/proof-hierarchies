"""
Stage 0b (infra) — clone the ntp-toolkit fork base onto the SAME Volume and
build it against our frozen Mathlib (zero skew: ntp-toolkit @ fbde6c4 pins
Mathlib 2df2f015… which the Volume already has cached).

We pin to the SHA (not a branch head): the verified "Update to v4.26.0"
commit on cmu-l3/ntp-toolkit's `hammer` history.

Usage (after Stage 0a build):
  .venv/bin/modal run modal/build_ntp.py::build_ntp     # clone + cache get + lake build
  .venv/bin/modal run modal/build_ntp.py::smoke         # run an existing extractor on 1 module
"""

import modal

NTP_REPO = "https://github.com/cmu-l3/ntp-toolkit.git"
NTP_SHA = "fbde6c4265eda8a83ab74112987f5e6c17d8858d"   # verified v4.26.0 state
EXPECTED_MATHLIB = "2df2f0150c275ad53cb3c90f7c98ec15a56a1a67"  # must match PIN.txt

VOLUME_NAME = "proof-hierarchies-lean"
VOL_ROOT = "/lean"

app = modal.App("proof-hierarchies-ntp")
vol = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)

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


def _sh(cmd: str, cwd: str | None = None) -> None:
    import subprocess
    print(f"+ {cmd}", flush=True)
    subprocess.run(cmd, shell=True, check=True, cwd=cwd, executable="/bin/bash")


@app.function(image=image, volumes={VOL_ROOT: vol}, timeout=60 * 60 * 2)
def build_ntp():
    import os, subprocess

    # Guard: confirm Stage 0a pin is present and consistent.
    pin = open(f"{VOL_ROOT}/PIN.txt").read()
    assert f"MATHLIB_COMMIT={EXPECTED_MATHLIB}" in pin, \
        f"Volume Mathlib pin != {EXPECTED_MATHLIB}; aborting (skew risk).\n{pin}"
    print("PIN.txt OK:\n" + pin)

    dst = f"{VOL_ROOT}/ntp-toolkit"
    if not os.path.isdir(f"{dst}/.git"):
        _sh(f"git clone {NTP_REPO} {dst}")
    _sh(f"git fetch --all", cwd=dst)
    _sh(f"git checkout {NTP_SHA}", cwd=dst)

    # Sanity: the checked-out manifest must reference our exact Mathlib.
    manifest = open(f"{dst}/lake-manifest.json").read()
    assert EXPECTED_MATHLIB in manifest, \
        "ntp-toolkit lake-manifest Mathlib rev != frozen pin — STOP."
    print("ntp-toolkit lake-manifest Mathlib rev matches frozen pin ✓")

    _sh("elan show || true", cwd=dst)
    _sh("lake exe cache get", cwd=dst)   # same Mathlib oleans → warm cache
    _sh("lake build", cwd=dst)           # ntp-toolkit's own Lean + exes

    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=dst, text=True).strip()
    with open(f"{VOL_ROOT}/NTP_PIN.txt", "w") as f:
        f.write(f"NTP_REPO={NTP_REPO}\nNTP_COMMIT={sha}\n")
    vol.commit()
    print(f"\nntp-toolkit built at {sha}. Stage 0b infra ready.")
    print("Available exes: full_proof_training_data, premises, declarations, training_data, …")


@app.function(image=image, volumes={VOL_ROOT: vol}, timeout=60 * 5)
def status():
    """Volume-side completion check — robust to local network drops during
    the detached build. Prints NTP_PIN.txt if the build finished."""
    import os
    for f in ("PIN.txt", "NTP_PIN.txt"):
        p = f"{VOL_ROOT}/{f}"
        print(f"--- {f} ---")
        print(open(p).read() if os.path.exists(p) else "(absent)")
    ntp = f"{VOL_ROOT}/ntp-toolkit"
    print("ntp-toolkit dir:", "present" if os.path.isdir(ntp) else "absent")


@app.function(image=image, volumes={VOL_ROOT: vol}, timeout=60 * 30)
def smoke():
    """Run an existing ntp-toolkit extractor on one tiny module to confirm
    the toolchain works end-to-end before we add the have_tree module."""
    dst = f"{VOL_ROOT}/ntp-toolkit"
    _sh("lake exe declarations Mathlib.Logic.Basic | head -c 600 ; echo", cwd=dst)
