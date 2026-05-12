#!/usr/bin/env bash
# teardown_env.sh - Remove Python virtual environment for gh-best-practices-audit
# Written by h3nryza
#
# Usage:
#   source teardown_env.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
RESET='\033[0m'

log_info()    { echo -e "${CYAN}[INFO]${RESET} $*"; }
log_success() { echo -e "${GREEN}[OK]${RESET} $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${RESET} $*"; }

echo -e "${BOLD}${CYAN}"
echo "╔══════════════════════════════════════════════════╗"
echo "║  gh-best-practices-audit — Environment Teardown  ║"
echo "║  Written by h3nryza                               ║"
echo "╚══════════════════════════════════════════════════╝"
echo -e "${RESET}"

# Deactivate if active
if [[ -n "${VIRTUAL_ENV:-}" ]]; then
    log_info "Deactivating virtual environment..."
    deactivate 2>/dev/null || true
    log_success "Virtual environment deactivated"
fi

# Remove virtual environment
if [[ -d "${VENV_DIR}" ]]; then
    log_info "Removing virtual environment at ${VENV_DIR}..."
    rm -rf "${VENV_DIR}"
    log_success "Virtual environment removed"
else
    log_warn "No virtual environment found at ${VENV_DIR}"
fi

echo ""
echo -e "${BOLD}Teardown complete.${RESET}"
echo -e "${CYAN}Written by h3nryza${RESET}"
