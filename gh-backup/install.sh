#!/usr/bin/env bash
# install.sh - Remote installer for gh-backup
# Written by h3nryza
#
# Usage (remote):
#   curl -fsSL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-backup/install.sh | bash
#
# Usage (local):
#   ./install.sh [--prefix /usr/local] [--no-symlink]

set -euo pipefail

readonly REPO_RAW="https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-backup"
readonly SCRIPT_NAME="gh-backup"
readonly VERSION="1.0.0"

# Defaults
INSTALL_DIR="${HOME}/.local/bin"
SYMLINK_DIR="/usr/local/bin"
CREATE_SYMLINK="true"
LOCAL_MODE="false"

# Colors
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

show_banner() {
    echo -e "${BOLD}${CYAN}"
    echo "╔══════════════════════════════════════════════════╗"
    echo "║        gh-backup Installer — by h3nryza          ║"
    echo "╚══════════════════════════════════════════════════╝"
    echo -e "${RESET}"
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --prefix)
                INSTALL_DIR="${2:-}"
                [[ -z "${INSTALL_DIR}" ]] && die "--prefix requires a path"
                shift 2 ;;
            --no-symlink)
                CREATE_SYMLINK="false"
                shift ;;
            --local)
                LOCAL_MODE="true"
                shift ;;
            -h|--help)
                show_help
                exit 0 ;;
            *)
                die "Unknown option: $1" ;;
        esac
    done
}

show_help() {
    cat <<EOF
gh-backup installer — Written by h3nryza

USAGE:
  ./install.sh [OPTIONS]

OPTIONS:
  --prefix <dir>    Installation directory (default: ~/.local/bin)
  --no-symlink      Do not create symlink in /usr/local/bin
  --local           Install from local filesystem instead of remote download
  -h, --help        Show this help

REMOTE INSTALL:
  curl -fsSL ${REPO_RAW}/install.sh | bash

EOF
}

check_prerequisites() {
    local missing=()
    command -v curl &>/dev/null || missing+=("curl")
    command -v git &>/dev/null  || missing+=("git")

    if [[ ${#missing[@]} -gt 0 ]]; then
        die "Missing prerequisites: ${missing[*]}"
    fi
}

download_script() {
    log_info "Downloading ${SCRIPT_NAME}.sh from GitHub..."
    local url="${REPO_RAW}/${SCRIPT_NAME}.sh"
    local dest="${INSTALL_DIR}/${SCRIPT_NAME}.sh"

    if command -v curl &>/dev/null; then
        curl -fsSL "${url}" -o "${dest}"
    elif command -v wget &>/dev/null; then
        wget -qO "${dest}" "${url}"
    else
        die "Neither curl nor wget found. Cannot download script."
    fi
}

install_local() {
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local src="${script_dir}/${SCRIPT_NAME}.sh"

    if [[ ! -f "${src}" ]]; then
        die "Local script not found: ${src}"
    fi

    log_info "Installing from local file: ${src}"
    cp "${src}" "${INSTALL_DIR}/${SCRIPT_NAME}.sh"
}

create_symlink() {
    local target="${INSTALL_DIR}/${SCRIPT_NAME}.sh"
    local link="${SYMLINK_DIR}/${SCRIPT_NAME}"

    if [[ -w "${SYMLINK_DIR}" ]]; then
        ln -sf "${target}" "${link}"
        log_success "Symlink created: ${link} → ${target}"
    else
        log_warn "Cannot write to ${SYMLINK_DIR}. Trying with sudo..."
        if sudo ln -sf "${target}" "${link}" 2>/dev/null; then
            log_success "Symlink created (sudo): ${link} → ${target}"
        else
            log_warn "Could not create symlink in ${SYMLINK_DIR}. Add ${INSTALL_DIR} to your PATH."
        fi
    fi
}

add_to_path_hint() {
    local shell_rc=""
    case "${SHELL}" in
        */zsh)  shell_rc="${HOME}/.zshrc" ;;
        */bash) shell_rc="${HOME}/.bashrc" ;;
    esac

    if [[ -n "${shell_rc}" ]]; then
        if ! grep -q "${INSTALL_DIR}" "${shell_rc}" 2>/dev/null; then
            echo "" >> "${shell_rc}"
            echo "# Added by gh-backup installer" >> "${shell_rc}"
            echo "export PATH=\"${INSTALL_DIR}:\$PATH\"" >> "${shell_rc}"
            log_info "Added ${INSTALL_DIR} to PATH in ${shell_rc}"
            log_warn "Run: source ${shell_rc}   (or open a new terminal)"
        fi
    fi
}

verify_installation() {
    local dest="${INSTALL_DIR}/${SCRIPT_NAME}.sh"
    if [[ ! -f "${dest}" ]]; then
        die "Installation failed: ${dest} not found"
    fi
    if [[ ! -x "${dest}" ]]; then
        die "Installation failed: ${dest} is not executable"
    fi
    log_success "Installation verified: ${dest}"
}

main() {
    parse_args "$@"
    show_banner
    check_prerequisites

    # Create install dir if needed
    mkdir -p "${INSTALL_DIR}"

    # Download or copy
    if [[ "${LOCAL_MODE}" == "true" ]]; then
        install_local
    else
        download_script
    fi

    # Make executable
    chmod +x "${INSTALL_DIR}/${SCRIPT_NAME}.sh"
    log_success "Made executable: ${INSTALL_DIR}/${SCRIPT_NAME}.sh"

    # Optional symlink
    if [[ "${CREATE_SYMLINK}" == "true" ]]; then
        create_symlink
    fi

    # PATH hint
    add_to_path_hint

    verify_installation

    echo ""
    echo -e "${BOLD}Installation complete!${RESET}"
    echo ""
    echo "  Run: ${SCRIPT_NAME}.sh --help"
    echo "  Or:  ${SCRIPT_NAME}.sh -i   (interactive mode)"
    echo ""
    echo -e "${CYAN}Written by h3nryza — gh-backup v${VERSION}${RESET}"
}

main "$@"
