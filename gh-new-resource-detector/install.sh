#!/usr/bin/env bash
# install.sh — Remote installer for gh-new-resource-detector
# Written by h3nryza
#
# Usage (remote):
#   curl -fsSL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-new-resource-detector/install.sh | bash
#
# Usage (local):
#   ./install.sh [--prefix ~/.local/bin] [--no-symlink] [--no-venv]

set -euo pipefail

readonly REPO_RAW="https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-new-resource-detector"
readonly SCRIPT_NAME="gh-new-resource-detector"
readonly MAIN_SCRIPT="gh_new_resource_detector.py"
readonly LAMBDA_SCRIPT="lambda_handler.py"
readonly REQUIREMENTS="requirements.txt"
readonly VERSION="1.0.0"

# Defaults
INSTALL_DIR="${HOME}/.local/bin/${SCRIPT_NAME}"
SYMLINK_DIR="/usr/local/bin"
CREATE_SYMLINK="true"
SETUP_VENV="true"
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
    echo "║  gh-new-resource-detector Installer — h3nryza   ║"
    echo "╚══════════════════════════════════════════════════╝"
    echo -e "${RESET}"
}

show_help() {
    cat <<EOF
gh-new-resource-detector installer — Written by h3nryza

USAGE:
  ./install.sh [OPTIONS]

OPTIONS:
  --prefix <dir>    Installation directory (default: ~/.local/bin/gh-new-resource-detector)
  --no-symlink      Do not create symlink in /usr/local/bin
  --no-venv         Skip virtual environment setup
  --local           Install from local filesystem instead of remote download
  -h, --help        Show this help

REMOTE INSTALL:
  curl -fsSL ${REPO_RAW}/install.sh | bash

EOF
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
            --no-venv)
                SETUP_VENV="false"
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

check_prerequisites() {
    local missing=()
    command -v python3 &>/dev/null || missing+=("python3")

    if [[ "${LOCAL_MODE}" == "false" ]]; then
        command -v curl &>/dev/null || command -v wget &>/dev/null || missing+=("curl or wget")
    fi

    if [[ ${#missing[@]} -gt 0 ]]; then
        die "Missing prerequisites: ${missing[*]}"
    fi

    PY_VERSION="$(python3 --version 2>&1 | awk '{print $2}')"
    MAJOR="$(echo "${PY_VERSION}" | cut -d. -f1)"
    MINOR="$(echo "${PY_VERSION}" | cut -d. -f2)"
    if [[ "${MAJOR}" -lt 3 ]] || { [[ "${MAJOR}" -eq 3 ]] && [[ "${MINOR}" -lt 9 ]]; }; then
        die "Python 3.9+ is required (found ${PY_VERSION})"
    fi
    log_info "Python ${PY_VERSION} OK"
}

download_file() {
    local url="$1"
    local dest="$2"
    if command -v curl &>/dev/null; then
        curl -fsSL "${url}" -o "${dest}"
    elif command -v wget &>/dev/null; then
        wget -qO "${dest}" "${url}"
    else
        die "Neither curl nor wget found."
    fi
}

download_all() {
    log_info "Downloading files from GitHub..."
    for f in "${MAIN_SCRIPT}" "${LAMBDA_SCRIPT}" "${REQUIREMENTS}" "setup_env.sh" "teardown_env.sh"; do
        download_file "${REPO_RAW}/${f}" "${INSTALL_DIR}/${f}"
        log_success "Downloaded: ${f}"
    done
}

install_local() {
    local src_dir
    src_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    log_info "Installing from local directory: ${src_dir}"
    for f in "${MAIN_SCRIPT}" "${LAMBDA_SCRIPT}" "${REQUIREMENTS}" "setup_env.sh" "teardown_env.sh"; do
        [[ -f "${src_dir}/${f}" ]] || { log_warn "Skipping missing file: ${f}"; continue; }
        cp "${src_dir}/${f}" "${INSTALL_DIR}/${f}"
        log_success "Copied: ${f}"
    done
}

setup_venv() {
    log_info "Setting up virtual environment..."
    python3 -m venv "${INSTALL_DIR}/.venv"
    "${INSTALL_DIR}/.venv/bin/pip" install --quiet --upgrade pip
    "${INSTALL_DIR}/.venv/bin/pip" install --quiet -r "${INSTALL_DIR}/${REQUIREMENTS}"
    log_success "Virtual environment ready: ${INSTALL_DIR}/.venv"
}

create_wrapper() {
    local wrapper="${INSTALL_DIR}/${SCRIPT_NAME}"
    cat > "${wrapper}" <<WRAPPER
#!/usr/bin/env bash
# Auto-generated wrapper for gh-new-resource-detector
SCRIPT_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
VENV="\${SCRIPT_DIR}/.venv"
if [[ -d "\${VENV}" ]]; then
    exec "\${VENV}/bin/python" "\${SCRIPT_DIR}/${MAIN_SCRIPT}" "\$@"
else
    exec python3 "\${SCRIPT_DIR}/${MAIN_SCRIPT}" "\$@"
fi
WRAPPER
    chmod +x "${wrapper}"
    log_success "Wrapper script created: ${wrapper}"
}

create_symlink() {
    local target="${INSTALL_DIR}/${SCRIPT_NAME}"
    local link="${SYMLINK_DIR}/${SCRIPT_NAME}"

    if [[ -w "${SYMLINK_DIR}" ]]; then
        ln -sf "${target}" "${link}"
        log_success "Symlink: ${link} → ${target}"
    else
        log_warn "Cannot write to ${SYMLINK_DIR}. Trying with sudo..."
        if sudo ln -sf "${target}" "${link}" 2>/dev/null; then
            log_success "Symlink (sudo): ${link} → ${target}"
        else
            log_warn "Could not create symlink. Add ${INSTALL_DIR} to your PATH."
        fi
    fi
}

add_to_path_hint() {
    local shell_rc=""
    case "${SHELL:-}" in
        */zsh)  shell_rc="${HOME}/.zshrc" ;;
        */bash) shell_rc="${HOME}/.bashrc" ;;
    esac

    if [[ -n "${shell_rc}" ]]; then
        if ! grep -q "${INSTALL_DIR}" "${shell_rc}" 2>/dev/null; then
            {
                echo ""
                echo "# Added by gh-new-resource-detector installer"
                echo "export PATH=\"${INSTALL_DIR}:\$PATH\""
            } >> "${shell_rc}"
            log_info "Added ${INSTALL_DIR} to PATH in ${shell_rc}"
            log_warn "Run: source ${shell_rc}   (or open a new terminal)"
        fi
    fi
}

main() {
    parse_args "$@"
    show_banner
    check_prerequisites

    mkdir -p "${INSTALL_DIR}"

    if [[ "${LOCAL_MODE}" == "true" ]]; then
        install_local
    else
        download_all
    fi

    # Make shell scripts executable
    chmod +x "${INSTALL_DIR}/setup_env.sh" "${INSTALL_DIR}/teardown_env.sh"

    if [[ "${SETUP_VENV}" == "true" ]]; then
        setup_venv
    fi

    create_wrapper

    if [[ "${CREATE_SYMLINK}" == "true" ]]; then
        create_symlink
    fi

    add_to_path_hint

    echo ""
    echo -e "${BOLD}Installation complete!${RESET}"
    echo ""
    echo "  Run:              ${SCRIPT_NAME} --help"
    echo "  Interactive:      ${SCRIPT_NAME} -i"
    echo "  Install path:     ${INSTALL_DIR}"
    echo ""
    echo -e "${CYAN}Written by h3nryza — ${SCRIPT_NAME} v${VERSION}${RESET}"
}

main "$@"
