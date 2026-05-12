#!/usr/bin/env bash
# teardown_env.sh — Remove virtualenv for gh-new-resource-detector
# Written by h3nryza

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly VENV_DIR="${SCRIPT_DIR}/.venv"

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
RESET='\033[0m'

log_info()    { echo -e "${CYAN}[INFO]${RESET} $*"; }
log_success() { echo -e "${GREEN}[OK]${RESET} $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${RESET} $*" >&2; }
log_error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; }

echo -e "${BOLD}${CYAN}"
echo "╔══════════════════════════════════════════════════╗"
echo "║  gh-new-resource-detector — Environment Teardown ║"
echo "║                    by h3nryza                    ║"
echo "╚══════════════════════════════════════════════════╝"
echo -e "${RESET}"

if [[ -d "${VENV_DIR}" ]]; then
    log_info "Removing virtual environment at ${VENV_DIR} ..."
    rm -rf "${VENV_DIR}"
    log_success "Virtual environment removed."
else
    log_warn "No virtual environment found at ${VENV_DIR} — nothing to remove."
fi

# Remove compiled bytecode
find "${SCRIPT_DIR}" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "${SCRIPT_DIR}" -name "*.pyc" -delete 2>/dev/null || true
log_info "Cleaned up __pycache__ and .pyc files."

# Remove state file if present
STATE_FILE="${SCRIPT_DIR}/.gh_detector_state.json"
if [[ -f "${STATE_FILE}" ]]; then
    rm -f "${STATE_FILE}"
    log_info "Removed state file: ${STATE_FILE}"
fi

echo ""
echo -e "${BOLD}Teardown complete.${RESET}"
echo ""
echo "  Re-create the environment:  ./setup_env.sh"
echo ""
echo -e "${CYAN}Written by h3nryza — gh-new-resource-detector${RESET}"
