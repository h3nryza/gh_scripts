#!/usr/bin/env bash
# setup_env.sh - Create and activate a Python venv for gh-pipeline-compliance
# Written by h3nryza
#
# Usage:
#   source setup_env.sh            # creates venv and activates it
#   source setup_env.sh --no-dev   # skip dev/test dependencies

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"
PYTHON="${PYTHON:-python3}"

NO_DEV=false
for arg in "$@"; do
    [[ "$arg" == "--no-dev" ]] && NO_DEV=true
done

# ── Create venv ────────────────────────────────────────────────────────────
if [[ ! -d "${VENV_DIR}" ]]; then
    echo "[setup] Creating virtual environment at ${VENV_DIR}"
    "${PYTHON}" -m venv "${VENV_DIR}"
fi

# ── Activate ───────────────────────────────────────────────────────────────
# shellcheck source=/dev/null
source "${VENV_DIR}/bin/activate"
echo "[setup] Activated venv: ${VIRTUAL_ENV}"

# ── Upgrade pip ────────────────────────────────────────────────────────────
pip install --quiet --upgrade pip

# ── Install dependencies ───────────────────────────────────────────────────
if [[ "${NO_DEV}" == true ]]; then
    echo "[setup] Installing runtime dependencies (no dev/test)"
    pip install --quiet boto3 cryptography PyYAML
else
    echo "[setup] Installing all dependencies from requirements.txt"
    pip install --quiet -r "${SCRIPT_DIR}/requirements.txt"
fi

echo "[setup] Done. Run: python gh_pipeline_compliance.py --help"
