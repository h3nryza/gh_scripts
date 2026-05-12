#!/usr/bin/env bash
# gh-backup.sh - GitHub Backup Tool
# Written by h3nryza
# Backs up repositories and gists from GitHub Enterprise, Organization, or User accounts
# Maintains original GitHub directory hierarchy in the backup output

set -euo pipefail

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────
readonly VERSION="1.0.0"
readonly SCRIPT_NAME="gh-backup"
readonly AUTHOR="h3nryza"
TIMESTAMP="$(date +%Y-%m-%d_%H%M%S)"
readonly TIMESTAMP
readonly DEFAULT_OUTPUT_DIR="backup_${TIMESTAMP}"
readonly CSV_COLUMNS="Enterprise,Organization,Owner,Name,Type,Description,Visibility,Language,LastUpdated,Size,BackupPath,Status"

# ─────────────────────────────────────────────
# Color codes
# ─────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

# ─────────────────────────────────────────────
# Default option values
# ─────────────────────────────────────────────
TARGET_ENTERPRISE=""
TARGET_ORG=""
TARGET_USER=""
AUTH_METHOD="gh"
PAT_TOKEN=""
APP_ID=""
APP_KEY_FILE=""
OUTPUT_DIR="${DEFAULT_OUTPUT_DIR}"
INCLUDE_GISTS="false"
EXCLUDE_ARCHIVED="false"
EXCLUDE_FORKS="false"
CLONE_METHOD="clone"
EXPORT_FILE=""
IMPORT_FILE=""
INTERACTIVE="false"
VERBOSE="false"
DRY_RUN="false"
SHALLOW_CLONE="false"
RESUME="false"

# Runtime state
BACKUP_ROOT=""
MANIFEST_FILE=""
INDEX_FILE=""
TOTAL_REPOS=0
BACKED_UP=0
SKIPPED=0
FAILED=0

# ─────────────────────────────────────────────
# Utility functions
# ─────────────────────────────────────────────
log_info() {
    echo -e "${BLUE}[INFO]${RESET} $*"
}

log_success() {
    echo -e "${GREEN}[OK]${RESET} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${RESET} $*" >&2
}

log_error() {
    echo -e "${RED}[ERROR]${RESET} $*" >&2
}

log_verbose() {
    if [[ "${VERBOSE}" == "true" ]]; then
        echo -e "${CYAN}[VERBOSE]${RESET} $*"
    fi
}

log_dry() {
    echo -e "${YELLOW}[DRY-RUN]${RESET} $*"
}

die() {
    log_error "$*"
    exit 1
}

banner() {
    echo -e "${BOLD}${CYAN}"
    echo "╔══════════════════════════════════════════════════╗"
    echo "║           gh-backup - GitHub Backup Tool         ║"
    echo "║                  Written by h3nryza              ║"
    echo "╚══════════════════════════════════════════════════╝"
    echo -e "${RESET}"
}

progress() {
    local current="$1"
    local total="$2"
    local label="$3"
    local pct=0
    if [[ "${total}" -gt 0 ]]; then
        pct=$(( current * 100 / total ))
    fi
    printf "\r${CYAN}[%3d%%]${RESET} (%d/%d) %s" "${pct}" "${current}" "${total}" "${label}"
}

# ─────────────────────────────────────────────
# Help
# ─────────────────────────────────────────────
show_help() {
    banner
    cat <<EOF
${BOLD}USAGE:${RESET}
  ${SCRIPT_NAME}.sh [OPTIONS]

${BOLD}TARGET:${RESET}
  -e, --enterprise <name>    Backup entire enterprise (enumerates orgs→repos)
  -o, --org <name>           Backup organization (enumerates repos)
  -u, --user <name>          Backup user (repos + gists)

${BOLD}AUTH:${RESET}
  -a, --auth <method>        Auth method: gh | pat | app  (default: gh)
  -t, --token <token>        PAT token (required when --auth pat)
  --app-id <id>              GitHub App ID
  --app-key <file>           GitHub App private key file

${BOLD}OPTIONS:${RESET}
  --output-dir <dir>         Output directory (default: backup_TIMESTAMP/)
  --include-gists            Include gists (automatically on for user backup)
  --exclude-archived         Skip archived repositories
  --exclude-forks            Skip forked repositories
  --clone-method <method>    Clone method: archive | clone | mirror  (default: clone)
  --shallow                  Shallow clone (--depth 1) for faster backups
  --resume                   Skip repos already present in output directory
  --export <file>            Export manifest CSV to specified path
  --import <file>            Import repo list to backup selectively

${BOLD}COMMON:${RESET}
  -i, --interactive          Launch interactive mode
  -h, --help                 Show this help message
  -v, --verbose              Verbose output
  --version                  Show version
  --dry-run                  List what would be backed up (no cloning)

${BOLD}EXAMPLES:${RESET}
  # Back up an entire organisation
  ${SCRIPT_NAME}.sh -o my-org

  # Back up an enterprise, skipping forks and archived repos
  ${SCRIPT_NAME}.sh -e my-enterprise --exclude-forks --exclude-archived

  # Back up a user's repos and gists using a PAT
  ${SCRIPT_NAME}.sh -u h3nryza --include-gists --auth pat --token \$GITHUB_TOKEN

  # Shallow clone to a custom directory, verbose
  ${SCRIPT_NAME}.sh -o my-org --output-dir /backups/my-org --shallow -v

  # Interactive mode
  ${SCRIPT_NAME}.sh -i

  # Dry run to preview what would be backed up
  ${SCRIPT_NAME}.sh -u h3nryza --dry-run

  # Remote execution
  curl -fsSL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-backup/gh-backup.sh | bash -s -- -u h3nryza

EOF
}

show_version() {
    echo "${SCRIPT_NAME} v${VERSION} - Written by ${AUTHOR}"
}

# ─────────────────────────────────────────────
# Argument parsing
# ─────────────────────────────────────────────
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -e|--enterprise)
                TARGET_ENTERPRISE="${2:-}"
                [[ -z "${TARGET_ENTERPRISE}" ]] && die "--enterprise requires a name argument"
                shift 2 ;;
            -o|--org)
                TARGET_ORG="${2:-}"
                [[ -z "${TARGET_ORG}" ]] && die "--org requires a name argument"
                shift 2 ;;
            -u|--user)
                TARGET_USER="${2:-}"
                [[ -z "${TARGET_USER}" ]] && die "--user requires a name argument"
                shift 2 ;;
            -a|--auth)
                AUTH_METHOD="${2:-}"
                [[ -z "${AUTH_METHOD}" ]] && die "--auth requires a method: gh|pat|app"
                shift 2 ;;
            -t|--token)
                PAT_TOKEN="${2:-}"
                [[ -z "${PAT_TOKEN}" ]] && die "--token requires a token value"
                shift 2 ;;
            --app-id)
                APP_ID="${2:-}"
                shift 2 ;;
            --app-key)
                APP_KEY_FILE="${2:-}"
                shift 2 ;;
            --output-dir)
                OUTPUT_DIR="${2:-}"
                [[ -z "${OUTPUT_DIR}" ]] && die "--output-dir requires a path"
                shift 2 ;;
            --include-gists)
                INCLUDE_GISTS="true"
                shift ;;
            --exclude-archived)
                EXCLUDE_ARCHIVED="true"
                shift ;;
            --exclude-forks)
                EXCLUDE_FORKS="true"
                shift ;;
            --clone-method)
                CLONE_METHOD="${2:-}"
                [[ -z "${CLONE_METHOD}" ]] && die "--clone-method requires: archive|clone|mirror"
                shift 2 ;;
            --shallow)
                SHALLOW_CLONE="true"
                shift ;;
            --resume)
                RESUME="true"
                shift ;;
            --export)
                EXPORT_FILE="${2:-}"
                [[ -z "${EXPORT_FILE}" ]] && die "--export requires a file path"
                shift 2 ;;
            --import)
                IMPORT_FILE="${2:-}"
                [[ -z "${IMPORT_FILE}" ]] && die "--import requires a file path"
                shift 2 ;;
            -i|--interactive)
                INTERACTIVE="true"
                shift ;;
            -v|--verbose)
                VERBOSE="true"
                shift ;;
            --dry-run)
                DRY_RUN="true"
                shift ;;
            --version)
                show_version
                exit 0 ;;
            -h|--help)
                show_help
                exit 0 ;;
            *)
                die "Unknown option: $1 (use --help for usage)" ;;
        esac
    done
}

# ─────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────
validate_args() {
    # At least one target required (unless interactive)
    if [[ "${INTERACTIVE}" == "false" ]]; then
        if [[ -z "${TARGET_ENTERPRISE}" && -z "${TARGET_ORG}" && -z "${TARGET_USER}" ]]; then
            die "No target specified. Use -e, -o, or -u (or -i for interactive mode)."
        fi
    fi

    # Auth validation
    case "${AUTH_METHOD}" in
        gh)
            if ! command -v gh &>/dev/null; then
                die "GitHub CLI (gh) not found. Install from https://cli.github.com or use --auth pat."
            fi
            if ! gh auth status &>/dev/null; then
                die "GitHub CLI is not authenticated. Run: gh auth login"
            fi
            ;;
        pat)
            if [[ -z "${PAT_TOKEN}" ]]; then
                # Try GITHUB_TOKEN env var as fallback
                PAT_TOKEN="${GITHUB_TOKEN:-}"
                if [[ -z "${PAT_TOKEN}" ]]; then
                    die "PAT auth requires --token <token> or GITHUB_TOKEN env var."
                fi
            fi
            ;;
        app)
            if [[ -z "${APP_ID}" || -z "${APP_KEY_FILE}" ]]; then
                die "App auth requires --app-id and --app-key."
            fi
            if [[ ! -f "${APP_KEY_FILE}" ]]; then
                die "App key file not found: ${APP_KEY_FILE}"
            fi
            ;;
        *)
            die "Unknown auth method: ${AUTH_METHOD}. Use: gh | pat | app"
            ;;
    esac

    # Clone method validation
    case "${CLONE_METHOD}" in
        archive|clone|mirror) ;;
        *) die "Unknown clone method: ${CLONE_METHOD}. Use: archive | clone | mirror" ;;
    esac

    # Import file validation
    if [[ -n "${IMPORT_FILE}" && ! -f "${IMPORT_FILE}" ]]; then
        die "Import file not found: ${IMPORT_FILE}"
    fi

    # User backup implicitly includes gists
    if [[ -n "${TARGET_USER}" ]]; then
        INCLUDE_GISTS="true"
    fi
}

# ─────────────────────────────────────────────
# Interactive mode
# ─────────────────────────────────────────────
interactive_mode() {
    banner
    echo -e "${BOLD}Interactive Backup Setup${RESET}"
    echo ""

    # Target selection
    echo "Select backup target:"
    echo "  1) Enterprise"
    echo "  2) Organisation"
    echo "  3) User"
    read -rp "Choice [1-3]: " target_choice
    case "${target_choice}" in
        1)
            read -rp "Enterprise name: " TARGET_ENTERPRISE ;;
        2)
            read -rp "Organisation name: " TARGET_ORG ;;
        3)
            read -rp "Username: " TARGET_USER
            INCLUDE_GISTS="true" ;;
        *)
            die "Invalid choice." ;;
    esac

    # Auth method
    echo ""
    echo "Select auth method:"
    echo "  1) GitHub CLI (gh)  [default]"
    echo "  2) Personal Access Token (PAT)"
    echo "  3) GitHub App"
    read -rp "Choice [1-3, default 1]: " auth_choice
    case "${auth_choice}" in
        2)
            AUTH_METHOD="pat"
            read -rsp "PAT token: " PAT_TOKEN
            echo "" ;;
        3)
            AUTH_METHOD="app"
            read -rp "App ID: " APP_ID
            read -rp "Private key file path: " APP_KEY_FILE ;;
        *)
            AUTH_METHOD="gh" ;;
    esac

    # Output directory
    echo ""
    read -rp "Output directory [${DEFAULT_OUTPUT_DIR}]: " custom_dir
    if [[ -n "${custom_dir}" ]]; then
        OUTPUT_DIR="${custom_dir}"
    fi

    # Options
    echo ""
    read -rp "Exclude archived repos? [y/N]: " excl_arch
    [[ "${excl_arch}" =~ ^[Yy]$ ]] && EXCLUDE_ARCHIVED="true"

    read -rp "Exclude forked repos? [y/N]: " excl_fork
    [[ "${excl_fork}" =~ ^[Yy]$ ]] && EXCLUDE_FORKS="true"

    read -rp "Shallow clone (faster, less storage)? [y/N]: " shallow
    [[ "${shallow}" =~ ^[Yy]$ ]] && SHALLOW_CLONE="true"

    read -rp "Dry run (preview only, no cloning)? [y/N]: " dry
    [[ "${dry}" =~ ^[Yy]$ ]] && DRY_RUN="true"

    read -rp "Verbose output? [y/N]: " vrb
    [[ "${vrb}" =~ ^[Yy]$ ]] && VERBOSE="true"

    echo ""
    log_info "Configuration ready."
}

# ─────────────────────────────────────────────
# API helpers
# ─────────────────────────────────────────────
gh_api() {
    local endpoint="$1"
    shift
    case "${AUTH_METHOD}" in
        gh)
            gh api "${endpoint}" "$@" ;;
        pat)
            curl -fsSL \
                -H "Authorization: token ${PAT_TOKEN}" \
                -H "Accept: application/vnd.github+json" \
                -H "X-GitHub-Api-Version: 2022-11-28" \
                "https://api.github.com${endpoint}" "$@" ;;
        app)
            # Generate JWT for App auth (requires openssl)
            local jwt
            jwt="$(generate_app_jwt)"
            # Exchange JWT for installation token (simplified - assumes single installation)
            local install_token
            install_token="$(curl -fsSL \
                -H "Authorization: Bearer ${jwt}" \
                -H "Accept: application/vnd.github+json" \
                "https://api.github.com/app/installations" \
                | python3 -c "import sys,json; d=json.load(sys.stdin); print(d[0]['id'])" 2>/dev/null)"
            curl -fsSL \
                -H "Authorization: token ${install_token}" \
                -H "Accept: application/vnd.github+json" \
                "https://api.github.com${endpoint}" "$@" ;;
    esac
}

generate_app_jwt() {
    # RS256 JWT for GitHub App authentication
    local header payload signature iat exp
    iat=$(date +%s)
    exp=$(( iat + 600 ))
    header=$(printf '{"alg":"RS256","typ":"JWT"}' | base64 | tr -d '=' | tr '/+' '_-' | tr -d '\n')
    payload=$(printf '{"iat":%d,"exp":%d,"iss":"%s"}' "${iat}" "${exp}" "${APP_ID}" \
        | base64 | tr -d '=' | tr '/+' '_-' | tr -d '\n')
    signature=$(printf '%s.%s' "${header}" "${payload}" \
        | openssl dgst -sha256 -sign "${APP_KEY_FILE}" \
        | base64 | tr -d '=' | tr '/+' '_-' | tr -d '\n')
    printf '%s.%s.%s' "${header}" "${payload}" "${signature}"
}

gh_api_paginate() {
    # Paginate through all pages of a gh API endpoint, output JSON array items
    local endpoint="$1"
    local jq_filter="${2:-.[]}"
    case "${AUTH_METHOD}" in
        gh)
            gh api --paginate "${endpoint}" --jq "${jq_filter}" ;;
        pat)
            local page=1
            while true; do
                local result
                result=$(curl -fsSL \
                    -H "Authorization: token ${PAT_TOKEN}" \
                    -H "Accept: application/vnd.github+json" \
                    -H "X-GitHub-Api-Version: 2022-11-28" \
                    "https://api.github.com${endpoint}?per_page=100&page=${page}")
                local count
                count=$(printf '%s' "${result}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d) if isinstance(d,list) else 1)" 2>/dev/null || echo 0)
                printf '%s' "${result}" | python3 -c "
import sys, json
data = json.load(sys.stdin)
items = data if isinstance(data, list) else [data]
for item in items:
    print(json.dumps(item))
" 2>/dev/null
                [[ "${count}" -lt 100 ]] && break
                (( page++ ))
            done ;;
        app)
            gh_api "${endpoint}" ;;
    esac
}

# ─────────────────────────────────────────────
# Clone helpers
# ─────────────────────────────────────────────
clone_repo() {
    local clone_url="$1"
    local dest_dir="$2"
    local repo_name="$3"

    if [[ "${DRY_RUN}" == "true" ]]; then
        log_dry "Would clone: ${repo_name} → ${dest_dir}"
        return 0
    fi

    if [[ "${RESUME}" == "true" && -d "${dest_dir}/.git" ]]; then
        log_verbose "Skipping (already exists): ${repo_name}"
        (( SKIPPED++ )) || true
        return 0
    fi

    # Inject token into URL for PAT auth
    local auth_url="${clone_url}"
    if [[ "${AUTH_METHOD}" == "pat" ]]; then
        auth_url="${clone_url/https:\/\//https:\/\/${PAT_TOKEN}@}"
    fi

    local clone_args=()
    case "${CLONE_METHOD}" in
        clone)
            clone_args=(clone)
            [[ "${SHALLOW_CLONE}" == "true" ]] && clone_args+=(--depth 1)
            clone_args+=("${auth_url}" "${dest_dir}")
            ;;
        mirror)
            clone_args=(clone --mirror "${auth_url}" "${dest_dir}")
            ;;
        archive)
            # Use gh repo archive download via API
            mkdir -p "${dest_dir}"
            local archive_url="${clone_url%.git}/archive/refs/heads/main.tar.gz"
            if [[ "${AUTH_METHOD}" == "gh" ]]; then
                gh repo clone "${clone_url}" "${dest_dir}" -- --depth 1 2>/dev/null \
                    || { log_warn "Archive download fallback to clone for ${repo_name}"; git clone --depth 1 "${auth_url}" "${dest_dir}"; }
            else
                curl -fsSL -L \
                    -H "Authorization: token ${PAT_TOKEN}" \
                    "${archive_url}" -o "${dest_dir}/archive.tar.gz" \
                    && tar -xzf "${dest_dir}/archive.tar.gz" -C "${dest_dir}" --strip-components=1 \
                    && rm "${dest_dir}/archive.tar.gz" \
                    || { log_warn "Archive failed, falling back to clone for ${repo_name}"; git clone --depth 1 "${auth_url}" "${dest_dir}"; }
            fi
            return 0
            ;;
    esac

    if git "${clone_args[@]}" 2>/dev/null; then
        (( BACKED_UP++ )) || true
        log_verbose "Cloned: ${repo_name}"
    else
        log_warn "Failed to clone: ${repo_name}"
        (( FAILED++ )) || true
        return 1
    fi
}

# ─────────────────────────────────────────────
# CSV manifest helpers
# ─────────────────────────────────────────────
init_manifest() {
    MANIFEST_FILE="${BACKUP_ROOT}/backup_manifest.csv"
    if [[ "${DRY_RUN}" != "true" ]]; then
        printf '%s\n' "${CSV_COLUMNS}" > "${MANIFEST_FILE}"
    fi
}

append_manifest() {
    local enterprise="${1:-}"
    local org="${2:-}"
    local owner="${3:-}"
    local name="${4:-}"
    local type="${5:-repo}"
    local description="${6:-}"
    local visibility="${7:-}"
    local language="${8:-}"
    local last_updated="${9:-}"
    local size="${10:-0}"
    local backup_path="${11:-}"
    local status="${12:-ok}"

    # Sanitise: strip commas and newlines from free-text fields
    description="${description//,/ }"
    description="${description//$'\n'/ }"

    local row="${enterprise},${org},${owner},${name},${type},${description},${visibility},${language},${last_updated},${size},${backup_path},${status}"

    if [[ "${DRY_RUN}" == "true" ]]; then
        log_dry "Manifest row: ${row}"
        return 0
    fi

    printf '%s\n' "${row}" >> "${MANIFEST_FILE}"
}

# ─────────────────────────────────────────────
# Index generation
# ─────────────────────────────────────────────
init_index() {
    INDEX_FILE="${BACKUP_ROOT}/index.md"
    if [[ "${DRY_RUN}" != "true" ]]; then
        cat > "${INDEX_FILE}" <<EOF
# GitHub Backup Index

**Generated:** $(date -u '+%Y-%m-%d %H:%M:%S UTC')
**Tool:** ${SCRIPT_NAME} v${VERSION} — Written by ${AUTHOR}

---

EOF
    fi
}

append_index_header() {
    local level="$1"  # 1=enterprise, 2=org, 3=user
    local title="$2"
    if [[ "${DRY_RUN}" == "true" ]]; then return 0; fi
    local hashes
    hashes="$(printf '#%.0s' $(seq 1 "${level}"))"
    printf '\n%s %s\n\n' "${hashes}" "${title}" >> "${INDEX_FILE}"
    printf '| Name | Type | Visibility | Language | Last Updated | Description |\n' >> "${INDEX_FILE}"
    printf '|------|------|------------|----------|--------------|-------------|\n' >> "${INDEX_FILE}"
}

append_index_row() {
    local name="$1"
    local type="$2"
    local visibility="$3"
    local language="$4"
    local last_updated="$5"
    local description="$6"
    if [[ "${DRY_RUN}" == "true" ]]; then return 0; fi
    printf '| %s | %s | %s | %s | %s | %s |\n' \
        "${name}" "${type}" "${visibility}" "${language:-N/A}" \
        "${last_updated}" "${description:-—}" >> "${INDEX_FILE}"
}

append_org_index() {
    local org_dir="$1"
    local org_name="$2"
    local -a repo_rows=("${@:3}")
    if [[ "${DRY_RUN}" == "true" ]]; then return 0; fi

    local org_index="${org_dir}/org_index.md"
    cat > "${org_index}" <<EOF
# Organisation: ${org_name}

**Generated:** $(date -u '+%Y-%m-%d %H:%M:%S UTC')

| Name | Visibility | Language | Last Updated | Description |
|------|------------|----------|--------------|-------------|
EOF
    for row in "${repo_rows[@]:-}"; do
        [[ -n "${row}" ]] && printf '%s\n' "${row}" >> "${org_index}"
    done
}

# ─────────────────────────────────────────────
# Core backup functions
# ─────────────────────────────────────────────
backup_repo() {
    local enterprise="${1:-}"
    local org="${2:-}"
    local owner="${3:-}"
    local repo_json="$4"
    local base_dir="$5"

    local name visibility description language last_updated size clone_url archived fork

    name=$(printf '%s' "${repo_json}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('name',''))" 2>/dev/null)
    visibility=$(printf '%s' "${repo_json}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('visibility','unknown'))" 2>/dev/null)
    description=$(printf '%s' "${repo_json}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('description','') or '')" 2>/dev/null)
    language=$(printf '%s' "${repo_json}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('language','') or '')" 2>/dev/null)
    last_updated=$(printf '%s' "${repo_json}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('pushed_at','') or d.get('updated_at',''))" 2>/dev/null)
    size=$(printf '%s' "${repo_json}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('size',0))" 2>/dev/null)
    clone_url=$(printf '%s' "${repo_json}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('clone_url',''))" 2>/dev/null)
    archived=$(printf '%s' "${repo_json}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('archived',False))" 2>/dev/null)
    fork=$(printf '%s' "${repo_json}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('fork',False))" 2>/dev/null)

    [[ -z "${name}" ]] && { log_warn "Skipping repo with no name"; return 0; }

    # Apply filters
    if [[ "${EXCLUDE_ARCHIVED}" == "true" && "${archived}" == "True" ]]; then
        log_verbose "Skipping archived: ${name}"
        (( SKIPPED++ )) || true
        append_manifest "${enterprise}" "${org}" "${owner}" "${name}" "repo" \
            "${description}" "${visibility}" "${language}" "${last_updated}" "${size}" "" "skipped-archived"
        return 0
    fi

    if [[ "${EXCLUDE_FORKS}" == "true" && "${fork}" == "True" ]]; then
        log_verbose "Skipping fork: ${name}"
        (( SKIPPED++ )) || true
        append_manifest "${enterprise}" "${org}" "${owner}" "${name}" "repo" \
            "${description}" "${visibility}" "${language}" "${last_updated}" "${size}" "" "skipped-fork"
        return 0
    fi

    local dest_dir="${base_dir}/${name}"
    local rel_path="${dest_dir#"${BACKUP_ROOT}/"}"

    (( TOTAL_REPOS++ )) || true
    progress "${BACKED_UP}" "${TOTAL_REPOS}" "${name}"

    local status="ok"
    if clone_repo "${clone_url}" "${dest_dir}" "${name}"; then
        status="ok"
    else
        status="failed"
    fi

    append_manifest "${enterprise}" "${org}" "${owner}" "${name}" "repo" \
        "${description}" "${visibility}" "${language}" "${last_updated}" "${size}" \
        "${rel_path}" "${status}"
    append_index_row "${name}" "repo" "${visibility}" "${language}" "${last_updated}" "${description}"
}

backup_gist() {
    local user="${1}"
    local gist_json="$2"
    local base_dir="$3"

    local gist_id description last_updated git_pull_url public

    gist_id=$(printf '%s' "${gist_json}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id',''))" 2>/dev/null)
    description=$(printf '%s' "${gist_json}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('description','') or '')" 2>/dev/null)
    last_updated=$(printf '%s' "${gist_json}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('updated_at',''))" 2>/dev/null)
    git_pull_url=$(printf '%s' "${gist_json}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('git_pull_url',''))" 2>/dev/null)
    public=$(printf '%s' "${gist_json}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('public',True))" 2>/dev/null)

    [[ -z "${gist_id}" ]] && { log_warn "Skipping gist with no ID"; return 0; }

    local visibility="public"
    [[ "${public}" == "False" ]] && visibility="secret"

    local dest_dir="${base_dir}/${gist_id}"
    local rel_path="${dest_dir#"${BACKUP_ROOT}/"}"

    (( TOTAL_REPOS++ )) || true
    progress "${BACKED_UP}" "${TOTAL_REPOS}" "gist:${gist_id}"

    local status="ok"
    if clone_repo "${git_pull_url}" "${dest_dir}" "gist:${gist_id}"; then
        status="ok"
    else
        status="failed"
    fi

    append_manifest "" "" "${user}" "${gist_id}" "gist" \
        "${description}" "${visibility}" "" "${last_updated}" "0" \
        "${rel_path}" "${status}"
    append_index_row "${gist_id}" "gist" "${visibility}" "" "${last_updated}" "${description}"
}

backup_user() {
    local user="${1}"
    log_info "Backing up user: ${user}"

    local user_dir="${BACKUP_ROOT}/${user}"
    local repos_dir="${user_dir}/repos"
    local gists_dir="${user_dir}/gists"

    if [[ "${DRY_RUN}" != "true" ]]; then
        mkdir -p "${repos_dir}" "${gists_dir}"
    fi

    append_index_header 2 "User: ${user}"

    # Fetch repos
    log_info "Fetching repositories for user: ${user}"
    local repos_json
    repos_json=$(gh_api_paginate "/users/${user}/repos")

    local repo_count=0
    while IFS= read -r repo_line; do
        [[ -z "${repo_line}" ]] && continue
        (( repo_count++ )) || true
        backup_repo "" "" "${user}" "${repo_line}" "${repos_dir}"
    done < <(printf '%s\n' "${repos_json}")

    echo ""  # newline after progress

    # Gists
    if [[ "${INCLUDE_GISTS}" == "true" ]]; then
        log_info "Fetching gists for user: ${user}"
        local gists_json
        gists_json=$(gh_api_paginate "/users/${user}/gists")

        while IFS= read -r gist_line; do
            [[ -z "${gist_line}" ]] && continue
            backup_gist "${user}" "${gist_line}" "${gists_dir}"
        done < <(printf '%s\n' "${gists_json}")

        echo ""
    fi
}

backup_org() {
    local org="${1}"
    local enterprise="${2:-}"
    local parent_dir="${3:-${BACKUP_ROOT}}"

    log_info "Backing up organisation: ${org}"

    local org_dir="${parent_dir}/${org}"
    if [[ "${DRY_RUN}" != "true" ]]; then
        mkdir -p "${org_dir}"
    fi

    append_index_header 2 "Organisation: ${org}"

    # Fetch repos
    local repos_json
    repos_json=$(gh_api_paginate "/orgs/${org}/repos")

    local org_rows=()
    while IFS= read -r repo_line; do
        [[ -z "${repo_line}" ]] && continue
        backup_repo "${enterprise}" "${org}" "${org}" "${repo_line}" "${org_dir}"
        # Capture last appended index row for org_index.md (simplified)
        local rname rvis rlang rupdated rdesc
        rname=$(printf '%s' "${repo_line}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('name',''))" 2>/dev/null)
        rvis=$(printf '%s' "${repo_line}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('visibility',''))" 2>/dev/null)
        rlang=$(printf '%s' "${repo_line}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('language','') or '')" 2>/dev/null)
        rupdated=$(printf '%s' "${repo_line}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('pushed_at',''))" 2>/dev/null)
        rdesc=$(printf '%s' "${repo_line}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('description','') or '')" 2>/dev/null)
        org_rows+=("| ${rname} | ${rvis} | ${rlang:-N/A} | ${rupdated} | ${rdesc:-—} |")
    done < <(printf '%s\n' "${repos_json}")

    echo ""

    # Write org_index.md
    if [[ "${DRY_RUN}" != "true" ]]; then
        append_org_index "${org_dir}" "${org}" "${org_rows[@]:-}"
    fi
}

backup_enterprise() {
    local enterprise="${1}"
    log_info "Backing up enterprise: ${enterprise}"

    local ent_dir="${BACKUP_ROOT}/${enterprise}"
    if [[ "${DRY_RUN}" != "true" ]]; then
        mkdir -p "${ent_dir}"
    fi

    append_index_header 1 "Enterprise: ${enterprise}"

    # Enumerate organisations - REST endpoint (requires enterprise admin token)
    log_info "Fetching organisations for enterprise: ${enterprise}"

    local orgs_json
    # Try REST first
    orgs_json=$(gh_api_paginate "/enterprises/${enterprise}/organizations" 2>/dev/null) || true

    if [[ -z "${orgs_json}" ]]; then
        # Fallback: GraphQL
        log_verbose "REST enumeration empty; trying GraphQL..."
        local graphql_query
        graphql_query=$(cat <<'GRAPHQL'
query($enterprise: String!, $after: String) {
  enterprise(slug: $enterprise) {
    organizations(first: 100, after: $after) {
      pageInfo { hasNextPage endCursor }
      nodes { login }
    }
  }
}
GRAPHQL
)
        local cursor="null"
        while true; do
            local gql_result
            gql_result=$(gh api graphql \
                -f query="${graphql_query}" \
                -f enterprise="${enterprise}" \
                -f after="${cursor}" 2>/dev/null) || break

            local has_next
            has_next=$(printf '%s' "${gql_result}" | python3 -c \
                "import sys,json; d=json.load(sys.stdin); print(d['data']['enterprise']['organizations']['pageInfo']['hasNextPage'])" 2>/dev/null)

            printf '%s' "${gql_result}" | python3 -c \
                "import sys,json; d=json.load(sys.stdin)
nodes=d['data']['enterprise']['organizations']['nodes']
for n in nodes: print(json.dumps({'login': n['login']}))" 2>/dev/null >> /tmp/gh_backup_orgs_$$.tmp

            cursor=$(printf '%s' "${gql_result}" | python3 -c \
                "import sys,json; d=json.load(sys.stdin); print(d['data']['enterprise']['organizations']['pageInfo']['endCursor'] or 'null')" 2>/dev/null)

            [[ "${has_next}" == "False" ]] && break
            [[ "${cursor}" == "null" ]] && break
        done
        orgs_json=$(cat /tmp/gh_backup_orgs_$$.tmp 2>/dev/null || echo "")
        rm -f /tmp/gh_backup_orgs_$$.tmp
    fi

    if [[ -z "${orgs_json}" ]]; then
        log_warn "No organisations found for enterprise: ${enterprise}. Check permissions."
        return 0
    fi

    while IFS= read -r org_line; do
        [[ -z "${org_line}" ]] && continue
        local org_login
        org_login=$(printf '%s' "${org_line}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('login',''))" 2>/dev/null)
        [[ -z "${org_login}" ]] && continue
        backup_org "${org_login}" "${enterprise}" "${ent_dir}"
    done < <(printf '%s\n' "${orgs_json}")
}

backup_gists_only() {
    local user="${1}"
    log_info "Fetching gists for: ${user}"

    local gists_dir="${BACKUP_ROOT}/${user}/gists"
    if [[ "${DRY_RUN}" != "true" ]]; then
        mkdir -p "${gists_dir}"
    fi

    local gists_json
    gists_json=$(gh_api_paginate "/users/${user}/gists")

    while IFS= read -r gist_line; do
        [[ -z "${gist_line}" ]] && continue
        backup_gist "${user}" "${gist_line}" "${gists_dir}"
    done < <(printf '%s\n' "${gists_json}")
    echo ""
}

# ─────────────────────────────────────────────
# Import filter
# ─────────────────────────────────────────────
should_backup_repo() {
    local full_name="$1"
    if [[ -z "${IMPORT_FILE}" ]]; then
        return 0
    fi
    if grep -qxF "${full_name}" "${IMPORT_FILE}" 2>/dev/null; then
        return 0
    fi
    return 1
}

# ─────────────────────────────────────────────
# Finalise
# ─────────────────────────────────────────────
generate_summary() {
    echo ""
    echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo -e "${BOLD}Backup Summary${RESET}"
    echo -e "  Total items processed : ${TOTAL_REPOS}"
    echo -e "  ${GREEN}Successfully backed up : ${BACKED_UP}${RESET}"
    echo -e "  ${YELLOW}Skipped               : ${SKIPPED}${RESET}"
    echo -e "  ${RED}Failed                : ${FAILED}${RESET}"
    if [[ "${DRY_RUN}" != "true" ]]; then
        echo -e "  Output directory      : ${BACKUP_ROOT}"
        echo -e "  Manifest CSV          : ${MANIFEST_FILE}"
        echo -e "  Index                 : ${INDEX_FILE}"
    fi
    echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo -e "${CYAN}Written by ${AUTHOR}${RESET}"
}

copy_export() {
    if [[ -n "${EXPORT_FILE}" && "${DRY_RUN}" != "true" ]]; then
        cp "${MANIFEST_FILE}" "${EXPORT_FILE}"
        log_success "Manifest exported to: ${EXPORT_FILE}"
    fi
}

# ─────────────────────────────────────────────
# Prerequisite checks
# ─────────────────────────────────────────────
check_prerequisites() {
    local missing=()

    command -v git &>/dev/null || missing+=("git")
    command -v python3 &>/dev/null || missing+=("python3")

    if [[ "${AUTH_METHOD}" == "gh" || "${AUTH_METHOD}" == "" ]]; then
        command -v gh &>/dev/null || missing+=("gh (GitHub CLI)")
    fi

    if [[ "${AUTH_METHOD}" == "app" ]]; then
        command -v openssl &>/dev/null || missing+=("openssl")
    fi

    if [[ ${#missing[@]} -gt 0 ]]; then
        die "Missing prerequisites: ${missing[*]}"
    fi
}

# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
main() {
    parse_args "$@"

    if [[ "${INTERACTIVE}" == "true" ]]; then
        interactive_mode
    fi

    validate_args
    check_prerequisites

    banner

    BACKUP_ROOT="$(pwd)/${OUTPUT_DIR}"

    if [[ "${DRY_RUN}" != "true" ]]; then
        mkdir -p "${BACKUP_ROOT}"
        log_success "Backup root: ${BACKUP_ROOT}"
    else
        log_info "DRY RUN — no files will be written."
    fi

    init_manifest
    init_index

    # Run backup targets
    if [[ -n "${TARGET_ENTERPRISE}" ]]; then
        backup_enterprise "${TARGET_ENTERPRISE}"
    fi

    if [[ -n "${TARGET_ORG}" ]]; then
        backup_org "${TARGET_ORG}"
    fi

    if [[ -n "${TARGET_USER}" ]]; then
        backup_user "${TARGET_USER}"
    fi

    # Finalise index footer
    if [[ "${DRY_RUN}" != "true" ]]; then
        cat >> "${INDEX_FILE}" <<EOF

---
*Generated by ${SCRIPT_NAME} v${VERSION} — Written by ${AUTHOR}*
EOF
    fi

    copy_export
    generate_summary

    if [[ "${FAILED}" -gt 0 ]]; then
        exit 1
    fi
}

main "$@"
