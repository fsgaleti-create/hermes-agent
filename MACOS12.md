# Hermes on Intel macOS 12 (compatibility fork)

This branch targets **darwin-x64 only**. The Node lock row intentionally contains
only that target: Node 22.23.3 (official archive, SHA-256 pinned), whose Mach-O
minimum is macOS 11. Other PM rows and the complete Python lock are unchanged.
It does **not** downgrade cryptography or replace system libc++.

Use Python 3.14.7. On the tested Mac it is `/opt/local/bin/python3.14`.
Builds are staged into a new generation, using the upstream PM
`pm.build_env` with the frozen `uv.lock`. Runtime activation retains the
explicit generation's venv. PM installs only the reviewed node/npm roots;
lazy installs remain disabled. This prevents an unreviewed cua-driver download
from replacing a separately fixed driver. `isolated/cua-driver.json` selects
an absolute custom driver path plus SHA-256; every launch checks its bytes
before exporting `HERMES_CUA_DRIVER_CMD`. The tested custom driver is 0.31.0,
compiled for macOS 12.0 without ScreenCaptureKit/Swift. Its SHA-256 is
`8efaf5cd1d1b4b7d98be156e6d15b026d7fdb6cd345c4bf91b49c711c4e91603`.
Only the isolated home enables `computer_use.allow_unsigned_driver` and
`computer_use.no_overlay` via the config CLI. Do not enable those flags on an
unreviewed driver, and do not run driver install/update/upgrade here.

The driver starts and its version/platform checks pass through the real
Hermes wrapper. Capture/input remain **blocked by pending Accessibility and
Screen Recording TCC grants**. The user must grant them manually; this is not
a claim that capture works. The existing active driver is left untouched.

PM staging explicitly reuses the ordinary uv cache at `~/.cache/uv`, including
the exact-version compatible cryptography wheel available on the tested Mac.
A cold cache without a Rust/OpenSSL toolchain is not validated by this receipt.

## Isolated installation / update

Clone this fork's `macos12-compatible` branch into a dedicated source checkout.
Use a separate root, never your real `HERMES_HOME`:

```sh
cd "$HOME/.hermes/macos12-build/source"
REV=$(git rev-parse HEAD)
/opt/local/bin/python3.14 -B scripts/macos12_runtime.py \
  --root "$HOME/.hermes/macos12-build/isolated" update "$REV"
```

The revision **must be a full SHA**, and must contain the reviewed Node pin.
A failed build/import/crypto/Node/CLI acceptance check leaves the selected
generation unchanged; the failed generation and its build log remain available.
No active Hermes checkout, launcher, config or profile is adopted.

```sh
# Launch (and forward arbitrary ordinary CLI arguments)
/opt/local/bin/python3.14 -B scripts/macos12_runtime.py \
  --root "$HOME/.hermes/macos12-build/isolated" launch --help

# Inspect selected and previous generation
/opt/local/bin/python3.14 -B scripts/macos12_runtime.py \
  --root "$HOME/.hermes/macos12-build/isolated" status

# Revert to the previous accepted generation (does not revert user data)
/opt/local/bin/python3.14 -B scripts/macos12_runtime.py \
  --root "$HOME/.hermes/macos12-build/isolated" rollback
```

For later updates, fetch **the compatibility branch**, inspect its diff, then
pass its full SHA to `update`. Do not run the normal `hermes update` or PM
mutation commands through this launcher; it blocks them. A tracked upstream
`main` is not a compatibility approval. Automatic main synchronization and
local Monterey promotion are deliberately separate operations.

`selection.json` records current+previous; `generations/*/acceptance.json`
records the tested commit, log and acceptance scope. Runtime state is under
`isolated/home`, tools under `isolated/tools`, logs under `isolated/logs`.
Accepted generations are retained; nothing automatically deletes rollback data.
Do not run concurrent updater/rollback commands against the same root.

## Acceptance scope

Automated controller acceptance covers core/native imports, Ed25519 signing
and verification with the exact locked cryptography, Node execution, CLI help
and serve help. It does not make a paid LLM call or assert GUI/TUI rendering.
Doctor's missing-provider/optional-tool warnings in an empty test home are not
platform runtime failures. Desktop building/rendering and custom cua-driver
acceptance must be recorded separately before claiming those surfaces work.

Regression tests: `tests/scripts/test_macos12.py` via `scripts/run_tests.sh`.
When using an explicit pytest-capable venv, **unset `__HERMES_ACTIVATED`** and
provide `HERMES_PYTHON`, isolated `HERMES_HOME`/`HERMES_RUNTIME_DIR` before the
runner: otherwise its initial shell activation installs all default PM roots.
