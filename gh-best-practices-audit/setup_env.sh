#!/usr/bin/env bash
# setup_env.sh - Set up Python virtual environment for gh-best-practices-audit
# Written by h3nryza
#
# Usage:
#   source setup_env.sh

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
log_error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; }

echo -e "${BOLD}${CYAN}"
echo "╔══════════════════════════════════════════════════╗"
echo "║  gh-best-practices-audit — Environment Setup     ║"
echo "║  Written by h3nryza                               ║"
echo "╚══════════════════════════════════════════════════╝"
echo -e "${RESET}"

# Check Python version
if ! command -v python3 &>/dev/null; then
    log_error "Python 3 is required but not found."
    return 1 2>/dev/null || exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
log_info "Python version: ${PYTHON_VERSION}"

# Create virtual environment if it doesn't exist
if [[ ! -d "${VENV_DIR}" ]]; then
    log_info "Creating virtual environment at ${VENV_DIR}..."
    python3 -m venv "${VENV_DIR}"
    log_success "Virtual environment created"
else
    log_info "Virtual environment already exists at ${VENV_DIR}"
fi

# Activate virtual environment
log_info "Activating virtual environment..."
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
log_success "Virtual environment activated"

# Upgrade pip
log_info "Upgrading pip..."
pip install --upgrade pip --quiet

# Install dependencies
log_info "Installing dependencies..."
pip install -r "${SCRIPT_DIR}/requirements.txt" --quiet
log_success "Dependencies installed"

# Verify installation
log_info "Verifying installation..."
python3 -c "import csv, json, subprocess; print('Core modules OK')"

# Check optional dependencies
if python3 -c "import openpyxl" 2>/dev/null; then
    log_success "openpyxl available (Excel support)"
else
    log_warn "openpyxl not available (Excel custom rules will not work)"
fi

if python3 -c "import boto3" 2>/dev/null; then
    log_success "boto3 available (S3/Lambda support)"
else
    log_warn "boto3 not available (S3 upload will fall back to AWS CLI)"
fi

echo ""
echo -e "${BOLD}Environment ready!${RESET}"
echo ""
echo "  Run:  python gh_best_practices_audit.py --help"
echo "  Or:   python gh_best_practices_audit.py -i"
echo ""
echo -e "${CYAN}Written by h3nryza — gh-best-practices-audit v1.0.0${RESET}"
