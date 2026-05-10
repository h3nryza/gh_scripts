#!/usr/bin/env bash
# teardown_env.sh - Deactivate and remove the Python venv
# Written by h3nryza
#
# Usage:
#   source teardown_env.sh          # deactivate only (keep .venv)
#   source teardown_env.sh --clean  # deactivate and delete .venv

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"

CLEAN=false
for arg in "$@"; do
    [[ "$arg" == "--clean" ]] && CLEAN=true
done

# ── Deactivate if active ───────────────────────────────────────────────────
if [[ -n "${VIRTUAL_ENV:-}" ]]; then
    deactivate 2>/dev/null || true
    echo "[teardown] Deactivated venv"
fi

# ── Remove if --clean ─────────────────────────────────────────────────────
if [[ "${CLEAN}" == true ]]; then
    if [[ -d "${VENV_DIR}" ]]; then
        rm -rf "${VENV_DIR}"
        echo "[teardown] Removed ${VENV_DIR}"
    else
        echo "[teardown] No venv found at ${VENV_DIR}"
    fi
fi

echo "[teardown] Done"
