#!/usr/bin/env bash
# =============================================================================
# install.sh — Installer for gh-repo-migrator
# Written by h3nryza
# =============================================================================
# Usage:
#   bash <(curl -fsSL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-repo-migrator/install.sh)
#
# What it does:
#   1. Downloads gh-repo-migrator.sh to /usr/local/bin (or ~/bin as fallback)
#   2. Makes it executable
#   3. Optionally creates a shell alias
# =============================================================================

set -euo pipefail

readonly REPO_RAW="https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-repo-migrator"
readonly SCRIPT_NAME="gh-repo-migrator"
readonly SCRIPT_FILE="${SCRIPT_NAME}.sh"

# Colours
if [[ -t 1 ]]; then
  RED='\033[0;31m'
  GREEN='\033[0;32m'
  YELLOW='\033[1;33m'
  BLUE='\033[0;34m'
  BOLD='\033[1m'
  RESET='\033[0m'
else
  RED='' GREEN='' YELLOW='' BLUE='' BOLD='' RESET=''
fi

log_info()  { printf "${BLUE}[INFO]${RESET}  %s\n"  "$*"; }
log_ok()    { printf "${GREEN}[OK]${RESET}    %s\n"  "$*"; }
log_warn()  { printf "${YELLOW}[WARN]${RESET}  %s\n" "$*"; }
log_error() { printf "${RED}[ERROR]${RESET} %s\n"    "$*" >&2; }
die()       { log_error "$*"; exit 1; }

# ---------------------------------------------------------------------------
# Dependency check
# ---------------------------------------------------------------------------
check_deps() {
  local missing=()
  for cmd in curl bash; do
    command -v "${cmd}" &>/dev/null || missing+=("${cmd}")
  done
  [[ ${#missing[@]} -gt 0 ]] && die "Missing required tools: ${missing[*]}"
  log_ok "Dependencies OK (curl, bash)"
}

# ---------------------------------------------------------------------------
# Determine install directory
# ---------------------------------------------------------------------------
resolve_install_dir() {
  local dir=""

  if [[ -w "/usr/local/bin" ]]; then
    dir="/usr/local/bin"
  elif sudo -n true 2>/dev/null && sudo test -w "/usr/local/bin"; then
    dir="/usr/local/bin"
    USE_SUDO=true
  else
    # Fallback to ~/bin
    dir="${HOME}/bin"
    mkdir -p "${dir}"
    log_warn "/usr/local/bin not writable; installing to ${dir}"
    log_warn "Ensure ${dir} is in your PATH (add to ~/.bashrc or ~/.zshrc):"
    log_warn "  export PATH=\"\${HOME}/bin:\${PATH}\""
  fi

  printf '%s' "${dir}"
}

USE_SUDO=false

# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------
download_script() {
  local dest_dir="$1"
  local dest="${dest_dir}/${SCRIPT_FILE}"
  local url="${REPO_RAW}/${SCRIPT_FILE}"

  log_info "Downloading ${SCRIPT_FILE} from ${url}..."

  if [[ "${USE_SUDO}" == true ]]; then
    sudo curl -fsSL "${url}" -o "${dest}"
    sudo chmod +x "${dest}"
  else
    curl -fsSL "${url}" -o "${dest}"
    chmod +x "${dest}"
  fi

  log_ok "Installed to ${dest}"
}

# ---------------------------------------------------------------------------
# Verify installation
# ---------------------------------------------------------------------------
verify_install() {
  local dest_dir="$1"
  local dest="${dest_dir}/${SCRIPT_FILE}"

  if [[ ! -x "${dest}" ]]; then
    die "Installation failed: ${dest} is not executable"
  fi

  local version
  version=$(bash "${dest}" --version 2>/dev/null || echo "unknown")
  log_ok "Verified: ${version}"
}

# ---------------------------------------------------------------------------
# Optional alias setup
# ---------------------------------------------------------------------------
setup_alias() {
  local dest_dir="$1"
  local alias_line="alias ${SCRIPT_NAME}='${dest_dir}/${SCRIPT_FILE}'"

  printf '\n'
  read -r -p "Add shell alias '${SCRIPT_NAME}' -> ${dest_dir}/${SCRIPT_FILE}? [y/N]: " answer
  if [[ "${answer}" =~ ^[Yy]$ ]]; then
    local rc_file="${HOME}/.bashrc"
    [[ -n "${ZSH_VERSION:-}" ]] && rc_file="${HOME}/.zshrc"
    [[ "${SHELL}" == */zsh ]] && rc_file="${HOME}/.zshrc"

    if grep -q "alias ${SCRIPT_NAME}=" "${rc_file}" 2>/dev/null; then
      log_warn "Alias already exists in ${rc_file}"
    else
      printf '\n# gh-repo-migrator alias\n%s\n' "${alias_line}" >> "${rc_file}"
      log_ok "Alias added to ${rc_file}"
      log_info "Run: source ${rc_file}  (or open a new terminal)"
    fi
  else
    log_info "Skipped alias setup."
    log_info "You can run the script directly: ${dest_dir}/${SCRIPT_FILE} --help"
  fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
  printf '\n%s=== gh-repo-migrator Installer ===%s\n' "${BOLD}" "${RESET}"
  printf 'Written by h3nryza\n\n'

  check_deps

  local install_dir
  install_dir=$(resolve_install_dir)
  log_info "Install directory: ${install_dir}"

  download_script "${install_dir}"
  verify_install  "${install_dir}"
  setup_alias     "${install_dir}"

  printf '\n%s Installation complete! %s\n\n' "${GREEN}" "${RESET}"
  printf 'Usage:\n'
  printf '  %s --help\n' "${SCRIPT_NAME}.sh"
  printf '  %s -r my-repo -s old-org -d new-org\n' "${SCRIPT_NAME}.sh"
  printf '  %s --import transfers.csv\n\n' "${SCRIPT_NAME}.sh"
}

main "$@"
