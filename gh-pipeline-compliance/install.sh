#!/usr/bin/env bash
# install.sh - Install gh-pipeline-compliance (local or remote)
# Written by h3nryza
#
# Remote usage (no clone needed):
#   curl -sL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-pipeline-compliance/install.sh | bash
#
# Local usage:
#   bash install.sh

set -euo pipefail

TOOL_NAME="gh-pipeline-compliance"
REPO_RAW="https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-pipeline-compliance"
INSTALL_DIR="${HOME}/.local/share/${TOOL_NAME}"
BIN_DIR="${HOME}/.local/bin"

FILES=(
    "gh_pipeline_compliance.py"
    "lambda_handler.py"
    "requirements.txt"
    "setup_env.sh"
    "teardown_env.sh"
)

TESTS_FILES=(
    "tests/test_compliance.py"
    "tests/conftest.py"
)

DOCS_FILES=(
    "docs/USAGE.md"
    "docs/henrysexplanation.md"
)

echo ""
echo "Installing ${TOOL_NAME}..."
echo ""

# ── Detect if running locally (in the repo) ───────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-install.sh}")" 2>/dev/null && pwd || echo "")"
LOCAL_INSTALL=false
if [[ -f "${SCRIPT_DIR}/gh_pipeline_compliance.py" ]]; then
    LOCAL_INSTALL=true
    SOURCE_DIR="${SCRIPT_DIR}"
    echo "[install] Local mode: copying from ${SOURCE_DIR}"
else
    echo "[install] Remote mode: downloading from GitHub"
fi

# ── Create install directories ────────────────────────────────────────────
mkdir -p "${INSTALL_DIR}" "${INSTALL_DIR}/tests" "${INSTALL_DIR}/docs" "${BIN_DIR}"

# ── Copy or download files ────────────────────────────────────────────────
for file in "${FILES[@]}"; do
    if [[ "${LOCAL_INSTALL}" == true ]]; then
        cp "${SOURCE_DIR}/${file}" "${INSTALL_DIR}/${file}"
    else
        curl -sL "${REPO_RAW}/${file}" -o "${INSTALL_DIR}/${file}"
    fi
    echo "  [ok] ${file}"
done

for file in "${TESTS_FILES[@]}"; do
    filename="${file#tests/}"
    if [[ "${LOCAL_INSTALL}" == true ]]; then
        cp "${SOURCE_DIR}/${file}" "${INSTALL_DIR}/tests/${filename}"
    else
        curl -sL "${REPO_RAW}/${file}" -o "${INSTALL_DIR}/tests/${filename}"
    fi
    echo "  [ok] ${file}"
done

for file in "${DOCS_FILES[@]}"; do
    filename="${file#docs/}"
    if [[ "${LOCAL_INSTALL}" == true ]]; then
        cp "${SOURCE_DIR}/${file}" "${INSTALL_DIR}/docs/${filename}"
    else
        curl -sL "${REPO_RAW}/${file}" -o "${INSTALL_DIR}/docs/${filename}"
    fi
    echo "  [ok] ${file}"
done

# ── Make scripts executable ───────────────────────────────────────────────
chmod +x "${INSTALL_DIR}/setup_env.sh"
chmod +x "${INSTALL_DIR}/teardown_env.sh"

# ── Create wrapper in PATH ────────────────────────────────────────────────
WRAPPER="${BIN_DIR}/gh-pipeline-compliance"
cat > "${WRAPPER}" <<'WRAPPER_EOF'
#!/usr/bin/env bash
INSTALL_DIR="${HOME}/.local/share/gh-pipeline-compliance"
PYTHON="${INSTALL_DIR}/.venv/bin/python"

if [[ ! -f "${PYTHON}" ]]; then
    echo "[gh-pipeline-compliance] venv not found. Setting up..."
    # shellcheck source=/dev/null
    source "${INSTALL_DIR}/setup_env.sh" --no-dev
fi

exec "${PYTHON}" "${INSTALL_DIR}/gh_pipeline_compliance.py" "$@"
WRAPPER_EOF
chmod +x "${WRAPPER}"

# ── Check PATH ────────────────────────────────────────────────────────────
if [[ ":${PATH}:" != *":${BIN_DIR}:"* ]]; then
    echo ""
    echo "[install] Add the following to your shell profile:"
    echo "  export PATH=\"\${HOME}/.local/bin:\${PATH}\""
fi

echo ""
echo "[install] Setup virtual environment now?"
read -rp "  [y/N]: " setup_venv
if [[ "${setup_venv,,}" == "y" ]]; then
    # shellcheck source=/dev/null
    source "${INSTALL_DIR}/setup_env.sh"
fi

echo ""
echo "[install] ${TOOL_NAME} installed successfully!"
echo ""
echo "  Usage:"
echo "    gh-pipeline-compliance --help"
echo "    gh-pipeline-compliance -o my-org --workflow 'my-org/rw/.github/workflows/ci.yml'"
echo "    gh-pipeline-compliance -i"
echo ""
