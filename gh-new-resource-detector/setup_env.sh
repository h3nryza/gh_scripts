#!/usr/bin/env bash
# setup_env.sh — Create virtualenv and install dependencies for gh-new-resource-detector
# Written by h3nryza

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly VENV_DIR="${SCRIPT_DIR}/.venv"
readonly REQUIREMENTS="${SCRIPT_DIR}/requirements.txt"

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
die()         { log_error "$*"; exit 1; }

echo -e "${BOLD}${CYAN}"
echo "╔══════════════════════════════════════════════════╗"
echo "║   gh-new-resource-detector — Environment Setup   ║"
echo "║                    by h3nryza                    ║"
echo "╚══════════════════════════════════════════════════╝"
echo -e "${RESET}"

# Check Python
if command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    PYTHON="python"
else
    die "Python 3 is required but not found in PATH."
fi

PY_VERSION="$("${PYTHON}" --version 2>&1 | awk '{print $2}')"
log_info "Using Python ${PY_VERSION} at $(command -v "${PYTHON}")"

MAJOR="$(echo "${PY_VERSION}" | cut -d. -f1)"
MINOR="$(echo "${PY_VERSION}" | cut -d. -f2)"
if [[ "${MAJOR}" -lt 3 ]] || { [[ "${MAJOR}" -eq 3 ]] && [[ "${MINOR}" -lt 9 ]]; }; then
    die "Python 3.9+ is required (found ${PY_VERSION})"
fi

# Create venv
if [[ -d "${VENV_DIR}" ]]; then
    log_warn "Virtual environment already exists at ${VENV_DIR}"
    log_info "Delete it first with teardown_env.sh if you want a clean install."
else
    log_info "Creating virtual environment at ${VENV_DIR} ..."
    "${PYTHON}" -m venv "${VENV_DIR}"
    log_success "Virtual environment created."
fi

# Activate and install
log_info "Installing dependencies from requirements.txt ..."
"${VENV_DIR}/bin/pip" install --quiet --upgrade pip
"${VENV_DIR}/bin/pip" install --quiet -r "${REQUIREMENTS}"
log_success "Dependencies installed."

echo ""
echo -e "${BOLD}Setup complete.${RESET}"
echo ""
echo "  Activate the environment:   source ${VENV_DIR}/bin/activate"
echo "  Run the tool:               python gh_new_resource_detector.py --help"
echo "  Run tests:                  pytest tests/"
echo ""
echo -e "${CYAN}Written by h3nryza — gh-new-resource-detector${RESET}"
