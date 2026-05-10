#!/usr/bin/env bash
# =============================================================================
# gh-visibility-audit.sh
# GitHub Repository Visibility Auditor
# Written by h3nryza
# =============================================================================
# Audits and manages GitHub repository visibility (public/private/internal)
# across Enterprise, Organization, and User accounts.
# Exports results to CSV and can bulk-update visibility by importing a CSV.
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Constants & Defaults
# ---------------------------------------------------------------------------
readonly SCRIPT_NAME="gh-visibility-audit"
readonly SCRIPT_VERSION="1.0.0"
readonly SCRIPT_AUTHOR="h3nryza"
readonly GITHUB_API="https://api.github.com"
readonly DEFAULT_PER_PAGE=100
readonly MAX_RETRIES=3
readonly RETRY_DELAY=5
readonly CSV_HEADER="Enterprise,Organization,Owner,Repository,Visibility,URL"
readonly TIMESTAMP="$(date +%Y-%m-%d_%H%M%S)"
readonly DEFAULT_OUTPUT="${TIMESTAMP}_Github_visibility.csv"

# ---------------------------------------------------------------------------
# Globals (set by CLI parsing)
# ---------------------------------------------------------------------------
AUTH_METHOD="gh"
PAT_TOKEN=""
APP_ID=""
APP_KEY_FILE=""
ENTERPRISE=""
ORG=""
USER_TARGET=""
OUTPUT_FILE="${DEFAULT_OUTPUT}"
IMPORT_FILE=""
DRY_RUN=false
INTERACTIVE=false
VERBOSE=false
MODE="audit"   # audit | import

# Accumulates CSV rows before writing
CSV_ROWS=()

# ---------------------------------------------------------------------------
# Colour helpers (disabled when not a tty)
# ---------------------------------------------------------------------------
if [[ -t 1 ]]; then
  RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
  CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
else
  RED=''; YELLOW=''; GREEN=''; CYAN=''; BOLD=''; RESET=''
fi

# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------
log_info()    { printf "${CYAN}[INFO]${RESET}  %s\n"    "$*" >&2; }
log_ok()      { printf "${GREEN}[OK]${RESET}    %s\n"   "$*" >&2; }
log_warn()    { printf "${YELLOW}[WARN]${RESET}  %s\n"  "$*" >&2; }
log_error()   { printf "${RED}[ERROR]${RESET} %s\n"     "$*" >&2; }
log_verbose() { [[ "${VERBOSE}" == true ]] && printf "[VERBOSE] %s\n" "$*" >&2 || true; }
die()         { log_error "$*"; exit 1; }

# ---------------------------------------------------------------------------
# --help
# ---------------------------------------------------------------------------
show_help() {
cat <<EOF
${BOLD}${SCRIPT_NAME}${RESET} — GitHub Repository Visibility Auditor v${SCRIPT_VERSION}
Written by ${SCRIPT_AUTHOR}

${BOLD}USAGE:${RESET}
  gh-visibility-audit.sh [OPTIONS]

${BOLD}AUDIT MODE (default):${RESET}
  -e, --enterprise <name>    Target GitHub Enterprise (slug)
  -o, --org <name>           Target GitHub Organization
  -u, --user <name>          Target GitHub user/owner
  -a, --auth <method>        Auth method: gh | pat | app  (default: gh)
  -t, --token <token>        PAT token (required when --auth pat)
      --app-id <id>          GitHub App ID (required when --auth app)
      --app-key <file>       Path to GitHub App private key PEM file
      --output <file>        Output CSV file (default: ${DEFAULT_OUTPUT})

${BOLD}UPDATE MODE:${RESET}
      --import <file>        Import CSV to bulk-update visibility
      --dry-run              Show planned changes without applying them

${BOLD}COMMON:${RESET}
  -i, --interactive          Interactive mode — prompts for all options
  -h, --help                 Show this help message
  -v, --verbose              Verbose/debug output
      --version              Print version and exit

${BOLD}AUTH METHODS:${RESET}
  gh      Uses the GitHub CLI (gh) — must be authenticated via 'gh auth login'
  pat     Uses a Personal Access Token via curl
  app     Uses a GitHub App (JWT + installation token) via curl

${BOLD}CSV FORMAT:${RESET}
  ${CSV_HEADER}

  When importing (--import), the script reads only the Repository and
  Visibility columns; the other columns provide context but are not required
  to be accurate. To change a repo's visibility set the Visibility field to
  one of: public | private | internal

${BOLD}EXAMPLES:${RESET}
  # Audit all repos in an org (uses gh CLI auth)
  gh-visibility-audit.sh -o my-org

  # Audit an enterprise with a PAT and save to a named file
  gh-visibility-audit.sh -e my-enterprise -a pat -t ghp_xxxxx --output audit.csv

  # Audit a specific user's repos
  gh-visibility-audit.sh -u octocat

  # Dry-run: show what a CSV import would change
  gh-visibility-audit.sh --import changes.csv --dry-run

  # Apply visibility changes from CSV
  gh-visibility-audit.sh --import changes.csv -a pat -t ghp_xxxxx

  # Interactive mode
  gh-visibility-audit.sh -i

  # Verbose audit of an org using GitHub App auth
  gh-visibility-audit.sh -o my-org -a app --app-id 12345 --app-key app.pem -v

${BOLD}REMOTE EXECUTION:${RESET}
  curl -sL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-visibility-audit/gh-visibility-audit.sh \\
    | bash -s -- -o my-org

  curl -sL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-visibility-audit/gh-visibility-audit.sh \\
    | bash -s -- -e my-enterprise -a pat -t ghp_xxxxx

${BOLD}NOTES:${RESET}
  • Enterprise enumeration requires admin:enterprise or read:org scope.
  • Internal visibility is only valid for organisations inside an enterprise.
  • Rate limiting: the script automatically retries up to ${MAX_RETRIES} times with a
    ${RETRY_DELAY}-second back-off.
  • All API calls are paginated (${DEFAULT_PER_PAGE} results per page).
EOF
}

# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------
show_version() {
  echo "${SCRIPT_NAME} v${SCRIPT_VERSION} — written by ${SCRIPT_AUTHOR}"
}

# ---------------------------------------------------------------------------
# Dependency checks
# ---------------------------------------------------------------------------
check_deps() {
  local missing=()
  command -v curl  >/dev/null 2>&1 || missing+=("curl")
  command -v jq    >/dev/null 2>&1 || missing+=("jq")

  if [[ "${AUTH_METHOD}" == "gh" ]]; then
    command -v gh >/dev/null 2>&1 || missing+=("gh (GitHub CLI)")
  fi
  if [[ "${AUTH_METHOD}" == "app" ]]; then
    command -v openssl >/dev/null 2>&1 || missing+=("openssl")
  fi

  if [[ ${#missing[@]} -gt 0 ]]; then
    die "Missing required tools: ${missing[*]}"
  fi
}

# ---------------------------------------------------------------------------
# Interactive mode
# ---------------------------------------------------------------------------
interactive_mode() {
  log_info "Entering interactive mode…"
  echo ""

  # Mode selection
  local mode_choice
  read -r -p "Mode? [audit/import] (default: audit): " mode_choice
  mode_choice="${mode_choice:-audit}"
  if [[ "${mode_choice}" == "import" ]]; then
    MODE="import"
    read -r -p "Path to import CSV: " IMPORT_FILE
    [[ -f "${IMPORT_FILE}" ]] || die "File not found: ${IMPORT_FILE}"
    read -r -p "Dry-run? [y/N]: " dr
    [[ "${dr}" =~ ^[Yy]$ ]] && DRY_RUN=true
  else
    MODE="audit"

    # Target
    local target_type
    read -r -p "Target type? [enterprise/org/user]: " target_type
    case "${target_type}" in
      enterprise|e) read -r -p "Enterprise slug: " ENTERPRISE ;;
      org|o)        read -r -p "Organisation name: " ORG ;;
      user|u)       read -r -p "GitHub username: " USER_TARGET ;;
      *)            die "Unknown target type: ${target_type}" ;;
    esac

    # Output
    read -r -p "Output CSV file (default: ${DEFAULT_OUTPUT}): " out_file
    OUTPUT_FILE="${out_file:-${DEFAULT_OUTPUT}}"
  fi

  # Auth
  read -r -p "Auth method? [gh/pat/app] (default: gh): " auth_choice
  AUTH_METHOD="${auth_choice:-gh}"

  case "${AUTH_METHOD}" in
    pat)
      read -r -s -p "PAT token: " PAT_TOKEN; echo
      [[ -n "${PAT_TOKEN}" ]] || die "PAT token cannot be empty."
      ;;
    app)
      read -r -p "GitHub App ID: " APP_ID
      read -r -p "Path to App private key PEM: " APP_KEY_FILE
      [[ -f "${APP_KEY_FILE}" ]] || die "Key file not found: ${APP_KEY_FILE}"
      ;;
    gh)
      gh auth status >/dev/null 2>&1 || die "'gh' is not authenticated. Run: gh auth login"
      ;;
    *)
      die "Unknown auth method: ${AUTH_METHOD}"
      ;;
  esac

  # Verbose
  local verb
  read -r -p "Verbose output? [y/N]: " verb
  [[ "${verb}" =~ ^[Yy]$ ]] && VERBOSE=true

  echo ""
  log_info "Configuration:"
  log_info "  Mode       : ${MODE}"
  [[ -n "${ENTERPRISE}"   ]] && log_info "  Enterprise : ${ENTERPRISE}"
  [[ -n "${ORG}"          ]] && log_info "  Org        : ${ORG}"
  [[ -n "${USER_TARGET}"  ]] && log_info "  User       : ${USER_TARGET}"
  [[ "${MODE}" == "audit" ]] && log_info "  Output     : ${OUTPUT_FILE}"
  log_info "  Auth       : ${AUTH_METHOD}"
  echo ""
}

# ---------------------------------------------------------------------------
# GitHub API helper — wraps curl or gh api with retry + pagination awareness
# ---------------------------------------------------------------------------

# Returns raw JSON for a single page
_api_get_page() {
  local endpoint="$1"
  local attempt=0
  local response http_code body

  while (( attempt < MAX_RETRIES )); do
    (( attempt++ )) || true

    case "${AUTH_METHOD}" in
      gh)
        log_verbose "gh api ${endpoint}"
        if response=$(gh api "${endpoint}" --paginate=false 2>&1); then
          echo "${response}"
          return 0
        fi
        ;;
      pat)
        log_verbose "curl ${GITHUB_API}${endpoint}"
        response=$(curl -sS -w "\n%{http_code}" \
          -H "Authorization: token ${PAT_TOKEN}" \
          -H "Accept: application/vnd.github+json" \
          -H "X-GitHub-Api-Version: 2022-11-28" \
          "${GITHUB_API}${endpoint}")
        http_code="${response##*$'\n'}"
        body="${response%$'\n'*}"
        if [[ "${http_code}" == "200" ]]; then
          echo "${body}"
          return 0
        fi
        if [[ "${http_code}" == "429" || "${http_code}" == "403" ]]; then
          log_warn "Rate limited (HTTP ${http_code}). Retrying in ${RETRY_DELAY}s…"
          sleep "${RETRY_DELAY}"
          continue
        fi
        log_warn "API error HTTP ${http_code}: ${body}"
        ;;
      app)
        local install_token
        install_token="$(_app_installation_token)"
        log_verbose "curl (app token) ${GITHUB_API}${endpoint}"
        response=$(curl -sS -w "\n%{http_code}" \
          -H "Authorization: token ${install_token}" \
          -H "Accept: application/vnd.github+json" \
          -H "X-GitHub-Api-Version: 2022-11-28" \
          "${GITHUB_API}${endpoint}")
        http_code="${response##*$'\n'}"
        body="${response%$'\n'*}"
        if [[ "${http_code}" == "200" ]]; then
          echo "${body}"
          return 0
        fi
        log_warn "API error HTTP ${http_code}: ${body}"
        ;;
    esac

    log_warn "Attempt ${attempt}/${MAX_RETRIES} failed. Retrying in ${RETRY_DELAY}s…"
    sleep "${RETRY_DELAY}"
  done

  die "API call failed after ${MAX_RETRIES} attempts: ${endpoint}"
}

# Paginates through all pages and concatenates JSON arrays
api_get_all() {
  local base_endpoint="$1"
  local page=1
  local all_items=()
  local page_items page_count

  while true; do
    local sep="?"
    [[ "${base_endpoint}" == *"?"* ]] && sep="&"
    local endpoint="${base_endpoint}${sep}per_page=${DEFAULT_PER_PAGE}&page=${page}"

    local response
    response="$(_api_get_page "${endpoint}")"

    # Handle both array and object-with-repos responses
    page_items=$(echo "${response}" | jq -c '
      if type == "array" then .
      elif .repositories then .repositories
      elif .repos then .repos
      else []
      end
    ')

    page_count=$(echo "${page_items}" | jq 'length')
    log_verbose "Page ${page}: ${page_count} items from ${endpoint}"

    if (( page_count == 0 )); then
      break
    fi

    # Collect individual items
    while IFS= read -r item; do
      all_items+=("${item}")
    done < <(echo "${page_items}" | jq -c '.[]')

    if (( page_count < DEFAULT_PER_PAGE )); then
      break
    fi

    (( page++ )) || true
  done

  # Output as JSON array
  if (( ${#all_items[@]} == 0 )); then
    echo "[]"
    return
  fi
  printf '%s\n' "${all_items[@]}" | jq -s '.'
}

# ---------------------------------------------------------------------------
# GitHub App auth — generate JWT and exchange for installation token
# ---------------------------------------------------------------------------
_app_jwt() {
  [[ -n "${APP_ID}" ]]       || die "--app-id is required for app auth"
  [[ -f "${APP_KEY_FILE}" ]] || die "App key file not found: ${APP_KEY_FILE}"

  local now expiry header payload sig jwt
  now=$(date +%s)
  expiry=$(( now + 540 ))   # 9-minute window (max 10)

  header=$(printf '{"alg":"RS256","typ":"JWT"}' | openssl base64 -e -A | tr '+/' '-_' | tr -d '=')
  payload=$(printf '{"iat":%d,"exp":%d,"iss":"%s"}' "${now}" "${expiry}" "${APP_ID}" \
    | openssl base64 -e -A | tr '+/' '-_' | tr -d '=')

  sig=$(printf '%s.%s' "${header}" "${payload}" \
    | openssl dgst -sha256 -sign "${APP_KEY_FILE}" \
    | openssl base64 -e -A | tr '+/' '-_' | tr -d '=')

  jwt="${header}.${payload}.${sig}"
  echo "${jwt}"
}

_app_installation_token() {
  local jwt installations install_id token
  jwt="$(_app_jwt)"

  installations=$(curl -sS \
    -H "Authorization: Bearer ${jwt}" \
    -H "Accept: application/vnd.github+json" \
    "${GITHUB_API}/app/installations")

  install_id=$(echo "${installations}" | jq -r '.[0].id // empty')
  [[ -n "${install_id}" ]] || die "No GitHub App installations found."

  token=$(curl -sS -X POST \
    -H "Authorization: Bearer ${jwt}" \
    -H "Accept: application/vnd.github+json" \
    "${GITHUB_API}/app/installations/${install_id}/access_tokens" \
    | jq -r '.token // empty')

  [[ -n "${token}" ]] || die "Failed to obtain App installation token."
  echo "${token}"
}

# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------
csv_escape() {
  # Wrap in double-quotes and escape internal double-quotes
  local val="$1"
  val="${val//\"/\"\"}"
  echo "\"${val}\""
}

add_csv_row() {
  local enterprise="$1" org="$2" owner="$3" repo="$4" visibility="$5" url="$6"
  CSV_ROWS+=("$(csv_escape "${enterprise}"),$(csv_escape "${org}"),$(csv_escape "${owner}"),$(csv_escape "${repo}"),$(csv_escape "${visibility}"),$(csv_escape "${url}")")
}

write_csv() {
  local file="$1"
  {
    echo "${CSV_HEADER}"
    if (( ${#CSV_ROWS[@]} > 0 )); then
      printf '%s\n' "${CSV_ROWS[@]}"
    fi
  } > "${file}"
  log_ok "CSV written to: ${file} (${#CSV_ROWS[@]} repositories)"
}

# ---------------------------------------------------------------------------
# Core audit functions
# ---------------------------------------------------------------------------

# Process a raw JSON array of repository objects
_process_repos() {
  local enterprise_val="$1"
  local org_val="$2"
  local repos_json="$3"

  local count
  count=$(echo "${repos_json}" | jq 'length')
  log_verbose "Processing ${count} repositories"

  while IFS= read -r repo; do
    local name visibility url owner_login
    name=$(echo        "${repo}" | jq -r '.name')
    visibility=$(echo  "${repo}" | jq -r '.visibility // "unknown"')
    url=$(echo         "${repo}" | jq -r '.html_url // ""')
    owner_login=$(echo "${repo}" | jq -r '.owner.login // ""')

    log_verbose "  ${owner_login}/${name} → ${visibility}"
    add_csv_row "${enterprise_val}" "${org_val}" "${owner_login}" "${name}" "${visibility}" "${url}"
  done < <(echo "${repos_json}" | jq -c '.[]')
}

audit_org() {
  local org_name="$1"
  local enterprise_val="${2:-}"
  log_info "Auditing org: ${org_name}"

  local repos
  repos=$(api_get_all "/orgs/${org_name}/repos?type=all")
  _process_repos "${enterprise_val}" "${org_name}" "${repos}"
}

audit_user() {
  local username="$1"
  log_info "Auditing user: ${username}"

  local repos
  repos=$(api_get_all "/users/${username}/repos?type=all")
  _process_repos "" "" "${repos}"
}

audit_enterprise() {
  local enterprise_slug="$1"
  log_info "Auditing enterprise: ${enterprise_slug}"

  # List all orgs in the enterprise
  local orgs
  orgs=$(api_get_all "/enterprises/${enterprise_slug}/organizations")

  local org_count
  org_count=$(echo "${orgs}" | jq 'length')
  log_info "Found ${org_count} organisations in enterprise '${enterprise_slug}'"

  while IFS= read -r org_login; do
    [[ -n "${org_login}" ]] || continue
    audit_org "${org_login}" "${enterprise_slug}"
  done < <(echo "${orgs}" | jq -r '.[].login')
}

# ---------------------------------------------------------------------------
# Update / import functions
# ---------------------------------------------------------------------------

update_visibility() {
  local owner="$1"
  local repo="$2"
  local new_visibility="$3"

  case "${new_visibility}" in
    public|private|internal) ;;
    *) log_warn "Invalid visibility '${new_visibility}' for ${owner}/${repo} — skipping"; return ;;
  esac

  if [[ "${DRY_RUN}" == true ]]; then
    log_info "[DRY-RUN] Would set ${owner}/${repo} → ${new_visibility}"
    return
  fi

  log_info "Updating ${owner}/${repo} → ${new_visibility}…"

  local response http_code body

  case "${AUTH_METHOD}" in
    gh)
      if response=$(gh api --method PATCH "/repos/${owner}/${repo}" \
          -f visibility="${new_visibility}" 2>&1); then
        log_ok "  ${owner}/${repo} → ${new_visibility}"
      else
        log_error "  Failed to update ${owner}/${repo}: ${response}"
      fi
      ;;
    pat|app)
      local auth_header
      if [[ "${AUTH_METHOD}" == "pat" ]]; then
        auth_header="token ${PAT_TOKEN}"
      else
        auth_header="token $(_app_installation_token)"
      fi
      response=$(curl -sS -w "\n%{http_code}" -X PATCH \
        -H "Authorization: ${auth_header}" \
        -H "Accept: application/vnd.github+json" \
        -H "X-GitHub-Api-Version: 2022-11-28" \
        -H "Content-Type: application/json" \
        -d "{\"visibility\":\"${new_visibility}\"}" \
        "${GITHUB_API}/repos/${owner}/${repo}")
      http_code="${response##*$'\n'}"
      body="${response%$'\n'*}"
      if [[ "${http_code}" == "200" ]]; then
        log_ok "  ${owner}/${repo} → ${new_visibility}"
      else
        log_error "  Failed to update ${owner}/${repo} (HTTP ${http_code}): ${body}"
      fi
      ;;
  esac
}

import_csv() {
  local file="$1"
  [[ -f "${file}" ]] || die "Import file not found: ${file}"

  log_info "Importing changes from: ${file}"
  [[ "${DRY_RUN}" == true ]] && log_warn "Dry-run mode — no changes will be applied"

  local line_num=0
  local updated=0 skipped=0

  while IFS=',' read -r enterprise org owner repo visibility url; do
    (( line_num++ )) || true

    # Skip header
    [[ "${line_num}" -eq 1 && "${enterprise}" =~ ^\"?Enterprise\"?$ ]] && continue

    # Strip surrounding quotes (simple CSV — no embedded commas in field values)
    enterprise="${enterprise//\"/}"
    org="${org//\"/}"
    owner="${owner//\"/}"
    repo="${repo//\"/}"
    visibility="${visibility//\"/}"
    url="${url//\"/}"

    # Skip blank rows
    [[ -z "${repo}" ]] && continue

    # Determine owner from Owner or Org column
    local effective_owner="${owner}"
    [[ -z "${effective_owner}" ]] && effective_owner="${org}"
    [[ -z "${effective_owner}" ]] && { log_warn "Line ${line_num}: cannot determine owner for repo '${repo}' — skipping"; (( skipped++ )) || true; continue; }

    update_visibility "${effective_owner}" "${repo}" "${visibility}"
    (( updated++ )) || true
  done < "${file}"

  log_info "Import complete — ${updated} repos processed, ${skipped} skipped"
}

# ---------------------------------------------------------------------------
# Validate CLI inputs before running
# ---------------------------------------------------------------------------
validate_inputs() {
  case "${AUTH_METHOD}" in
    gh)
      if ! command -v gh >/dev/null 2>&1; then
        die "GitHub CLI (gh) is not installed. Choose --auth pat or --auth app."
      fi
      if ! gh auth status >/dev/null 2>&1; then
        die "gh CLI is not authenticated. Run: gh auth login"
      fi
      ;;
    pat)
      [[ -n "${PAT_TOKEN}" ]] || die "--token is required when --auth pat"
      ;;
    app)
      [[ -n "${APP_ID}" ]]       || die "--app-id is required when --auth app"
      [[ -n "${APP_KEY_FILE}" ]] || die "--app-key is required when --auth app"
      [[ -f "${APP_KEY_FILE}" ]] || die "App key file not found: ${APP_KEY_FILE}"
      ;;
    *)
      die "Unknown auth method '${AUTH_METHOD}'. Valid values: gh | pat | app"
      ;;
  esac

  if [[ "${MODE}" == "audit" ]]; then
    local targets=0
    [[ -n "${ENTERPRISE}"  ]] && (( targets++ )) || true
    [[ -n "${ORG}"         ]] && (( targets++ )) || true
    [[ -n "${USER_TARGET}" ]] && (( targets++ )) || true
    (( targets > 0 )) || die "Specify at least one target: --enterprise, --org, or --user"
    (( targets == 1 )) || die "Specify only one target at a time (enterprise, org, or user)"
  fi

  if [[ "${MODE}" == "import" ]]; then
    [[ -n "${IMPORT_FILE}" ]] || die "--import requires a file path"
    [[ -f "${IMPORT_FILE}" ]] || die "Import file not found: ${IMPORT_FILE}"
  fi
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
parse_args() {
  if [[ $# -eq 0 ]]; then
    INTERACTIVE=true
    return
  fi

  while [[ $# -gt 0 ]]; do
    case "$1" in
      -h|--help)        show_help; exit 0 ;;
      --version)        show_version; exit 0 ;;
      -i|--interactive) INTERACTIVE=true ;;
      -v|--verbose)     VERBOSE=true ;;
      -e|--enterprise)  ENTERPRISE="${2:?'--enterprise requires a value'}"; shift ;;
      -o|--org)         ORG="${2:?'--org requires a value'}"; shift ;;
      -u|--user)        USER_TARGET="${2:?'--user requires a value'}"; shift ;;
      -a|--auth)        AUTH_METHOD="${2:?'--auth requires a value'}"; shift ;;
      -t|--token)       PAT_TOKEN="${2:?'--token requires a value'}"; shift ;;
      --app-id)         APP_ID="${2:?'--app-id requires a value'}"; shift ;;
      --app-key)        APP_KEY_FILE="${2:?'--app-key requires a value'}"; shift ;;
      --output)         OUTPUT_FILE="${2:?'--output requires a value'}"; shift ;;
      --import)         IMPORT_FILE="${2:?'--import requires a value'}"; MODE="import"; shift ;;
      --dry-run)        DRY_RUN=true ;;
      -*) die "Unknown option: $1. Use --help for usage." ;;
      *)  die "Unexpected argument: $1. Use --help for usage." ;;
    esac
    shift
  done
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
  parse_args "$@"

  [[ "${INTERACTIVE}" == true ]] && interactive_mode

  check_deps
  validate_inputs

  case "${MODE}" in
    audit)
      log_info "Starting visibility audit…"

      if [[ -n "${ENTERPRISE}" ]]; then
        audit_enterprise "${ENTERPRISE}"
      elif [[ -n "${ORG}" ]]; then
        audit_org "${ORG}"
      elif [[ -n "${USER_TARGET}" ]]; then
        audit_user "${USER_TARGET}"
      fi

      if (( ${#CSV_ROWS[@]} == 0 )); then
        log_warn "No repositories found — CSV not written"
      else
        write_csv "${OUTPUT_FILE}"
      fi
      ;;
    import)
      import_csv "${IMPORT_FILE}"
      ;;
    *)
      die "Unknown mode: ${MODE}"
      ;;
  esac

  log_ok "Done. Written by ${SCRIPT_AUTHOR}."
}

main "$@"
