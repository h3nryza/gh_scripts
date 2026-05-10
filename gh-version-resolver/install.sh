#!/usr/bin/env bash
# install.sh — Install gh-version-resolver as a system command (symlink)
# Written by h3nryza
#
# Usage:
#   ./install.sh              # installs to /usr/local/bin (requires sudo on some systems)
#   PREFIX=/usr/local ./install.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAIN_SCRIPT="${SCRIPT_DIR}/gh_version_resolver.py"
INSTALL_DIR="${PREFIX:-/usr/local}/bin"
LINK_NAME="${INSTALL_DIR}/gh-version-resolver"

echo "[INFO] gh-version-resolver — install"

# Ensure the main script is executable
chmod +x "${MAIN_SCRIPT}"

# Run setup_env.sh to create venv
echo "[INFO] Setting up Python virtual environment..."
bash "${SCRIPT_DIR}/setup_env.sh"

VENV_PYTHON="${SCRIPT_DIR}/.venv/bin/python"

# Write a thin wrapper script
WRAPPER="${SCRIPT_DIR}/.gh_version_resolver_wrapper"
cat > "${WRAPPER}" <<WRAPPER_EOF
#!/usr/bin/env bash
exec "${VENV_PYTHON}" "${MAIN_SCRIPT}" "\$@"
WRAPPER_EOF
chmod +x "${WRAPPER}"

# Create symlink
if [[ -w "${INSTALL_DIR}" ]]; then
    ln -sf "${WRAPPER}" "${LINK_NAME}"
else
    echo "[INFO] ${INSTALL_DIR} requires elevated permissions. Using sudo..."
    sudo ln -sf "${WRAPPER}" "${LINK_NAME}"
fi

echo "[INFO] Installed: ${LINK_NAME}"
echo "[INFO] Run: gh-version-resolver --help"
