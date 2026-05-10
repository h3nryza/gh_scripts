#!/usr/bin/env bash
# setup_env.sh — Create and activate a Python virtual environment for gh-version-resolver
# Written by h3nryza
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"

echo "[INFO] gh-version-resolver — environment setup"
echo "[INFO] Script dir: ${SCRIPT_DIR}"

# Require Python 3.10+
PYTHON="${PYTHON:-python3}"
PY_VERSION=$("${PYTHON}" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "${PY_VERSION}" | cut -d. -f1)
PY_MINOR=$(echo "${PY_VERSION}" | cut -d. -f2)

if [[ "${PY_MAJOR}" -lt 3 ]] || [[ "${PY_MAJOR}" -eq 3 && "${PY_MINOR}" -lt 10 ]]; then
    echo "[ERROR] Python 3.10+ required. Found: ${PY_VERSION}" >&2
    exit 1
fi

echo "[INFO] Using Python ${PY_VERSION} ($(which "${PYTHON}"))"

# Create venv if it doesn't exist
if [[ ! -d "${VENV_DIR}" ]]; then
    echo "[INFO] Creating virtual environment at ${VENV_DIR}"
    "${PYTHON}" -m venv "${VENV_DIR}"
else
    echo "[INFO] Virtual environment already exists at ${VENV_DIR}"
fi

# Activate and install
# shellcheck source=/dev/null
source "${VENV_DIR}/bin/activate"

echo "[INFO] Upgrading pip..."
pip install --quiet --upgrade pip

echo "[INFO] Installing dependencies from requirements.txt..."
pip install --quiet -r "${SCRIPT_DIR}/requirements.txt"

echo ""
echo "[INFO] Setup complete. To activate the environment run:"
echo "       source ${VENV_DIR}/bin/activate"
echo ""
echo "[INFO] To run the script:"
echo "       python ${SCRIPT_DIR}/gh_version_resolver.py --help"
