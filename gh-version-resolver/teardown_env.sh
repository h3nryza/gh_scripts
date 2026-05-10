#!/usr/bin/env bash
# teardown_env.sh — Remove the Python virtual environment for gh-version-resolver
# Written by h3nryza
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"

if [[ -d "${VENV_DIR}" ]]; then
    echo "[INFO] Removing virtual environment at ${VENV_DIR}"
    rm -rf "${VENV_DIR}"
    echo "[INFO] Virtual environment removed."
else
    echo "[INFO] No virtual environment found at ${VENV_DIR} — nothing to remove."
fi
