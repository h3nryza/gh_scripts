#!/usr/bin/env bash
# =============================================================================
# install.sh — Remote installer for gh-visibility-audit
# Written by h3nryza
# =============================================================================
# Usage:
#   curl -sL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-visibility-audit/install.sh | bash
#
# This will install gh-visibility-audit.sh to ~/bin (or /usr/local/bin if run
# as root) and make it executable on your PATH.
# =============================================================================

set -euo pipefail

readonly RAW_BASE="https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-visibility-audit"
readonly SCRIPT_NAME="gh-visibility-audit.sh"
readonly INSTALL_NAME="gh-visibility-audit"

# Colour helpers
if [[ -t 1 ]]; then
  RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
else
  RED=''; GREEN=''; CYAN=''; BOLD=''; RESET=''
fi

log_info()  { printf "${CYAN}[INFO]${RESET}  %s\n" "$*"; }
log_ok()    { printf "${GREEN}[OK]${RESET}    %s\n" "$*"; }
log_error() { printf "${RED}[ERROR]${RESET} %s\n"   "$*" >&2; }
die()       { log_error "$*"; exit 1; }

# ---------------------------------------------------------------------------
# Determine install directory
# ---------------------------------------------------------------------------
pick_install_dir() {
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    echo "/usr/local/bin"
  elif [[ -d "${HOME}/bin" ]]; then
    echo "${HOME}/bin"
  elif [[ -d "${HOME}/.local/bin" ]]; then
    echo "${HOME}/.local/bin"
  else
    # Create ~/bin and suggest adding to PATH
    mkdir -p "${HOME}/bin"
    echo "${HOME}/bin"
  fi
}

# ---------------------------------------------------------------------------
# Check required tools
# ---------------------------------------------------------------------------
check_deps() {
  local missing=()
  command -v curl >/dev/null 2>&1 || missing+=("curl")
  command -v jq   >/dev/null 2>&1 || missing+=("jq")
  if [[ ${#missing[@]} -gt 0 ]]; then
    die "Missing required dependencies: ${missing[*]}"
  fi
}

# ---------------------------------------------------------------------------
# Download and install
# ---------------------------------------------------------------------------
install_script() {
  local install_dir
  install_dir="$(pick_install_dir)"

  local dest="${install_dir}/${INSTALL_NAME}"
  local url="${RAW_BASE}/${SCRIPT_NAME}"

  log_info "Downloading ${SCRIPT_NAME}…"
  log_info "  Source : ${url}"
  log_info "  Dest   : ${dest}"

  if ! curl -fsSL "${url}" -o "${dest}"; then
    die "Download failed. Check your internet connection or the URL."
  fi

  chmod +x "${dest}"
  log_ok "Installed: ${dest}"

  # PATH check
  if ! echo ":${PATH}:" | grep -q ":${install_dir}:"; then
    printf "\n${BOLD}NOTE:${RESET} %s is not in your PATH.\n" "${install_dir}"
    printf "Add the following line to your shell profile (~/.bashrc, ~/.zshrc, etc.):\n\n"
    printf "  export PATH=\"%s:\$PATH\"\n\n" "${install_dir}"
  fi
}

# ---------------------------------------------------------------------------
# Verify installation
# ---------------------------------------------------------------------------
verify_install() {
  local dest
  dest="$(pick_install_dir)/${INSTALL_NAME}"
  if [[ -x "${dest}" ]]; then
    log_ok "Verification passed — ${dest} is executable"
    "${dest}" --version
  else
    die "Verification failed — ${dest} is not executable"
  fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
  printf "\n${BOLD}gh-visibility-audit installer${RESET} — written by h3nryza\n\n"
  check_deps
  install_script
  verify_install
  printf "\n${GREEN}Installation complete!${RESET} Run: gh-visibility-audit --help\n\n"
}

main "$@"
