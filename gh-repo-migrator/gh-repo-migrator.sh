#!/usr/bin/env bash
# =============================================================================
# gh-repo-migrator.sh - GitHub Repository Migration Tool
# Written by h3nryza
# =============================================================================
# Transfers repositories between GitHub organizations (NOT enterprises).
# Supports single repo transfer or bulk transfer via CSV import.
# Reports success/failure in CSV format.
#
# Remote execution:
#   bash <(curl -fsSL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-repo-migrator/gh-repo-migrator.sh) [OPTIONS]
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
readonly SCRIPT_NAME="gh-repo-migrator"
readonly SCRIPT_VERSION="1.0.0"
readonly SCRIPT_AUTHOR="h3nryza"
readonly GITHUB_API="https://api.github.com"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
readonly TIMESTAMP
readonly DEFAULT_OUTPUT="migration_results_${TIMESTAMP}.csv"

# ---------------------------------------------------------------------------
# Colour helpers (disabled when not in a terminal)
# ---------------------------------------------------------------------------
if [[ -t 1 ]]; then
  RED='\033[0;31m'
  GREEN='\033[0;32m'
  YELLOW='\033[1;33m'
  BLUE='\033[0;34m'
  CYAN='\033[0;36m'
  BOLD='\033[1m'
  RESET='\033[0m'
else
  RED='' GREEN='' YELLOW='' BLUE='' CYAN='' BOLD='' RESET=''
fi

# ---------------------------------------------------------------------------
# Globals (set by CLI flags)
# ---------------------------------------------------------------------------
AUTH_METHOD="gh"
PAT_TOKEN=""
APP_ID=""
APP_KEY_FILE=""
REPO_NAME=""
SOURCE_ORG=""
DEST_ORG=""
IMPORT_FILE=""
EXPORT_FILE=""
DIFF_FILE=""
QUERY_ORG=""
OUTPUT_FILE="${DEFAULT_OUTPUT}"
DRY_RUN=false
CONFIRM=false
INTERACTIVE=false
VERBOSE=false
TEAM_IDS=""        # comma-separated team numeric IDs to grant access in dest org

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log_info()    { printf "${BLUE}[INFO]${RESET}  %s\n"    "$*" >&2; }
log_ok()      { printf "${GREEN}[OK]${RESET}    %s\n"   "$*" >&2; }
log_warn()    { printf "${YELLOW}[WARN]${RESET}  %s\n"  "$*" >&2; }
log_error()   { printf "${RED}[ERROR]${RESET} %s\n"     "$*" >&2; }
log_verbose() { [[ "${VERBOSE}" == true ]] && printf "${CYAN}[DEBUG]${RESET} %s\n" "$*" >&2 || true; }
log_dry()     { printf "${YELLOW}[DRY-RUN]${RESET} %s\n" "$*" >&2; }

die() {
  log_error "$*"
  exit 1
}

# ---------------------------------------------------------------------------
# Usage / Help
# ---------------------------------------------------------------------------
show_help() {
  cat <<EOF
${BOLD}${SCRIPT_NAME}${RESET} - GitHub Repository Migration Tool
Written by ${SCRIPT_AUTHOR} | v${SCRIPT_VERSION}

${BOLD}USAGE:${RESET}
  ${SCRIPT_NAME}.sh [OPTIONS]

${BOLD}SINGLE TRANSFER:${RESET}
  -r, --repo <name>          Repository name to transfer
  -s, --source <org>         Source organization / owner
  -d, --dest <org>           Destination organization

${BOLD}BULK TRANSFER:${RESET}
  --import <file>            Import CSV with transfers (SourceOrg,RepoName,DestOrg)
  --export <file>            Export source org repos to CSV for editing
                             (requires --query-org or -s)

${BOLD}QUERY MODE:${RESET}
  --diff <file>              Compare CSV against current state, show what would change
  --query-org <org>          List all repos in org (to build transfer list)

${BOLD}OPTIONS:${RESET}
  -a, --auth <method>        Auth method: gh|pat|app (default: gh)
  -t, --token <token>        PAT token (used with --auth pat)
  --app-id <id>              GitHub App ID (used with --auth app)
  --app-key <file>           GitHub App private key file (used with --auth app)
  --team-ids <ids>           Comma-separated team IDs to grant access in dest org
  --output <file>            Results output file (default: ${DEFAULT_OUTPUT})
  --dry-run                  Show what would transfer without doing it
  --confirm                  Skip confirmation prompt (for automation / CI)

${BOLD}COMMON:${RESET}
  -i, --interactive          Interactive mode (guided prompts)
  -h, --help                 Show this help
  -v, --verbose              Verbose / debug output
  --version                  Show version

${BOLD}CSV IMPORT FORMAT:${RESET}
  SourceOrg,RepoName,DestOrg
  my-org,cool-repo,new-org
  my-org,another-repo,new-org

  First line may be a header and is auto-detected.

${BOLD}CSV OUTPUT FORMAT:${RESET}
  SourceOrg,RepoName,DestOrg,Status,Message,Timestamp

${BOLD}AUTH METHODS:${RESET}
  gh   - Uses the GitHub CLI (gh auth token). Recommended for interactive use.
  pat  - Personal Access Token via -t/--token or GITHUB_TOKEN env var.
  app  - GitHub App JWT (requires --app-id and --app-key).

${BOLD}IMPORTANT NOTES:${RESET}
  - Transfers only work between orgs on the SAME GitHub instance (not across enterprises).
  - The caller must be an admin of the source repo and have create-repo permissions in dest org.
  - The GitHub API returns 202 (Accepted) immediately; the transfer completes asynchronously.
  - Forks cannot be transferred. Private repos may reveal billing information to dest org.
  - Existing webhooks, deploy keys, and some integrations are removed during transfer.

${BOLD}EXAMPLES:${RESET}
  # Single transfer
  ${SCRIPT_NAME}.sh -r my-repo -s old-org -d new-org

  # Single transfer with explicit PAT auth
  ${SCRIPT_NAME}.sh -r my-repo -s old-org -d new-org --auth pat --token ghp_xxx

  # Bulk transfer from CSV
  ${SCRIPT_NAME}.sh --import transfers.csv

  # Bulk transfer, skip confirmation (CI/CD)
  ${SCRIPT_NAME}.sh --import transfers.csv --confirm

  # Dry run to preview changes
  ${SCRIPT_NAME}.sh --import transfers.csv --dry-run

  # Export org repos to CSV for editing
  ${SCRIPT_NAME}.sh --query-org my-org --export repos.csv

  # Diff a CSV against live state
  ${SCRIPT_NAME}.sh --diff planned.csv

  # Interactive mode
  ${SCRIPT_NAME}.sh -i

  # Remote execution
  bash <(curl -fsSL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-repo-migrator/gh-repo-migrator.sh) -r my-repo -s old-org -d new-org

EOF
}

show_version() {
  echo "${SCRIPT_NAME} v${SCRIPT_VERSION} — written by ${SCRIPT_AUTHOR}"
}

# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------
parse_args() {
  [[ $# -eq 0 ]] && { show_help; exit 0; }

  while [[ $# -gt 0 ]]; do
    case "$1" in
      -r|--repo)       REPO_NAME="$2";    shift 2 ;;
      -s|--source)     SOURCE_ORG="$2";   shift 2 ;;
      -d|--dest)       DEST_ORG="$2";     shift 2 ;;
      --import)        IMPORT_FILE="$2";  shift 2 ;;
      --export)        EXPORT_FILE="$2";  shift 2 ;;
      --diff)          DIFF_FILE="$2";    shift 2 ;;
      --query-org)     QUERY_ORG="$2";    shift 2 ;;
      -a|--auth)       AUTH_METHOD="$2";  shift 2 ;;
      -t|--token)      PAT_TOKEN="$2";    shift 2 ;;
      --app-id)        APP_ID="$2";       shift 2 ;;
      --app-key)       APP_KEY_FILE="$2"; shift 2 ;;
      --team-ids)      TEAM_IDS="$2";     shift 2 ;;
      --output)        OUTPUT_FILE="$2";  shift 2 ;;
      --dry-run)       DRY_RUN=true;      shift   ;;
      --confirm)       CONFIRM=true;      shift   ;;
      -i|--interactive) INTERACTIVE=true; shift   ;;
      -v|--verbose)    VERBOSE=true;      shift   ;;
      -h|--help)       show_help; exit 0          ;;
      --version)       show_version; exit 0       ;;
      *)               die "Unknown option: $1. Use --help for usage." ;;
    esac
  done
}

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

# Resolve the active token based on auth method
resolve_token() {
  case "${AUTH_METHOD}" in
    gh)
      if ! command -v gh &>/dev/null; then
        die "GitHub CLI (gh) not found. Install from https://cli.github.com or use --auth pat."
      fi
      if ! gh auth status &>/dev/null; then
        die "Not authenticated with gh CLI. Run 'gh auth login' first."
      fi
      PAT_TOKEN="$(gh auth token)"
      log_verbose "Resolved token via gh CLI"
      ;;
    pat)
      if [[ -z "${PAT_TOKEN}" ]]; then
        PAT_TOKEN="${GITHUB_TOKEN:-}"
      fi
      [[ -z "${PAT_TOKEN}" ]] && die "PAT token required. Use -t/--token <token> or set GITHUB_TOKEN."
      log_verbose "Using PAT token"
      ;;
    app)
      [[ -z "${APP_ID}" ]]       && die "--app-id required when using --auth app"
      [[ -z "${APP_KEY_FILE}" ]] && die "--app-key required when using --auth app"
      [[ -f "${APP_KEY_FILE}" ]] || die "App key file not found: ${APP_KEY_FILE}"
      PAT_TOKEN="$(generate_app_token)"
      log_verbose "Generated GitHub App installation token"
      ;;
    *)
      die "Unknown auth method '${AUTH_METHOD}'. Choose from: gh, pat, app"
      ;;
  esac
}

# Generate a GitHub App installation token using JWT
# Requires: openssl, python3 (or python), jq
generate_app_token() {
  local now exp header payload signing_input signature jwt install_id token

  # Detect python command
  local python_cmd
  if command -v python3 &>/dev/null; then
    python_cmd="python3"
  elif command -v python &>/dev/null; then
    python_cmd="python"
  else
    die "python3 is required for GitHub App authentication."
  fi

  now=$(date +%s)
  exp=$((now + 540))   # 9 minutes — GitHub enforces max 10 min

  header=$(printf '{"alg":"RS256","typ":"JWT"}' | base64 | tr -d '=' | tr '/+' '_-' | tr -d '\n')
  payload=$(printf '{"iat":%s,"exp":%s,"iss":"%s"}' "$now" "$exp" "$APP_ID" | base64 | tr -d '=' | tr '/+' '_-' | tr -d '\n')
  signing_input="${header}.${payload}"

  signature=$(printf '%s' "${signing_input}" | openssl dgst -sha256 -sign "${APP_KEY_FILE}" | base64 | tr -d '=' | tr '/+' '_-' | tr -d '\n')
  jwt="${signing_input}.${signature}"

  # Get the first installation id for this app
  install_id=$(api_call_jwt "${jwt}" "GET" "app/installations" | \
    "${python_cmd}" -c "import sys,json; d=json.load(sys.stdin); print(d[0]['id']) if d else sys.exit(1)" 2>/dev/null) || \
    die "No installations found for GitHub App ${APP_ID}"

  token=$(api_call_jwt "${jwt}" "POST" "app/installations/${install_id}/access_tokens" '{}' | \
    "${python_cmd}" -c "import sys,json; print(json.load(sys.stdin)['token'])" 2>/dev/null) || \
    die "Failed to create installation access token for App ${APP_ID}"

  printf '%s' "${token}"
}

# Raw API call using a JWT (before we have a PAT)
api_call_jwt() {
  local jwt="$1" method="$2" path="$3" body="${4:-}"
  local args=(-fsSL -X "${method}"
    -H "Authorization: Bearer ${jwt}"
    -H "Accept: application/vnd.github+json"
    -H "X-GitHub-Api-Version: 2022-11-28")

  [[ -n "${body}" ]] && args+=(-d "${body}")
  curl "${args[@]}" "${GITHUB_API}/${path}"
}

# Authenticated API call
api_call() {
  local method="$1" path="$2" body="${3:-}"
  local args=(-fsSL -X "${method}"
    -H "Authorization: Bearer ${PAT_TOKEN}"
    -H "Accept: application/vnd.github+json"
    -H "X-GitHub-Api-Version: 2022-11-28")

  [[ -n "${body}" ]] && args+=(-d "${body}")
  log_verbose "API ${method} ${GITHUB_API}/${path}"
  curl "${args[@]}" "${GITHUB_API}/${path}"
}

# API call that also returns the HTTP status code; body written to stdout, status to fd3
# Usage: body=$(api_call_with_status GET "repos/org/repo" "" 3>&1 1>&4 4>&- | read_status); ...
# Simpler: api_call_status method path body -> prints "STATUS\n{json}"
api_call_status() {
  local method="$1" path="$2" body="${3:-}"
  local args=(-sL -X "${method}" -w '\n__STATUS__%{http_code}'
    -H "Authorization: Bearer ${PAT_TOKEN}"
    -H "Accept: application/vnd.github+json"
    -H "X-GitHub-Api-Version: 2022-11-28")

  [[ -n "${body}" ]] && args+=(-d "${body}")
  log_verbose "API ${method} ${GITHUB_API}/${path}"
  curl "${args[@]}" "${GITHUB_API}/${path}"
}

# Extract HTTP status appended by api_call_status
parse_status() {
  # Input: "...body...\n__STATUS__202"
  # Prints: 202
  grep -o '__STATUS__[0-9]*' | sed 's/__STATUS__//'
}

parse_body() {
  # Remove trailing __STATUS__NNN line
  sed 's/__STATUS__[0-9]*$//'
}

# ---------------------------------------------------------------------------
# Verify helpers
# ---------------------------------------------------------------------------

# Check repo exists and caller has admin access
verify_repo_admin() {
  local owner="$1" repo="$2"
  local raw status body

  raw=$(api_call_status GET "repos/${owner}/${repo}")
  status=$(printf '%s' "${raw}" | parse_status)
  body=$(printf '%s' "${raw}" | parse_body)

  if [[ "${status}" == "404" ]]; then
    return 1  # repo not found
  fi

  if [[ "${status}" != "200" ]]; then
    log_verbose "Unexpected status ${status} checking repo ${owner}/${repo}"
    return 2
  fi

  # Check permissions.admin (handle optional space: "admin": true  or  "admin":true)
  local has_admin
  has_admin=$(printf '%s' "${body}" | grep -o '"admin": *[a-z]*' | head -1 | sed 's/.*: *//') || true
  if [[ "${has_admin}" != "true" ]]; then
    return 3  # exists but no admin access
  fi

  return 0
}

# Check destination org exists and caller can create repos
verify_dest_org() {
  local org="$1"
  local raw status body

  raw=$(api_call_status GET "orgs/${org}")
  status=$(printf '%s' "${raw}" | parse_status)
  body=$(printf '%s' "${raw}" | parse_body)

  if [[ "${status}" == "404" ]]; then
    return 1  # org not found
  fi
  if [[ "${status}" != "200" ]]; then
    log_verbose "Unexpected status ${status} checking org ${org}"
    return 2
  fi

  # Check if caller is a member with appropriate privileges
  local member_raw member_status
  member_raw=$(api_call_status GET "orgs/${org}/memberships/$(get_authenticated_user)")
  member_status=$(printf '%s' "${member_raw}" | parse_status)
  if [[ "${member_status}" != "200" ]]; then
    log_verbose "Not a member of org ${org} or cannot check membership"
    # Not necessarily fatal — caller may still be an owner; we proceed but warn
    log_warn "Could not verify membership in dest org '${org}' — proceeding anyway."
  fi

  return 0
}

# Get the authenticated user's login
get_authenticated_user() {
  # Use api_call_status to get body cleanly via parse_body
  local raw login
  raw=$(api_call_status GET "user")
  login=$(printf '%s' "${raw}" | parse_body | grep -o '"login": *"[^"]*"' | head -1 | grep -o '"[^"]*"$' | tr -d '"') || true
  printf '%s' "${login}"
}

# Check if a repo is a fork (forks cannot be transferred)
is_fork() {
  local owner="$1" repo="$2"
  local fork_val
  # Handle JSON with optional space: "fork": true  or  "fork":true
  fork_val=$(api_call GET "repos/${owner}/${repo}" | grep -o '"fork": *[a-z]*' | head -1 | sed 's/.*: *//') || true
  [[ "${fork_val}" == "true" ]]
}

# Get the current owner of a repo (post-transfer detection)
get_repo_owner() {
  local owner="$1" repo="$2"
  # Use api_call_status so we can distinguish 404 from valid response
  local raw body status
  raw=$(api_call_status GET "repos/${owner}/${repo}" 2>/dev/null) || true
  status=$(printf '%s' "${raw}" | parse_status)
  body=$(printf '%s' "${raw}" | parse_body)
  if [[ "${status}" != "200" ]]; then
    printf 'NOT_FOUND'
    return 0
  fi
  local owner_name
  owner_name=$(printf '%s' "${body}" | grep -o '"full_name": *"[^"]*"' | head -1 | sed 's/.*": *"//' | tr -d '"' | cut -d'/' -f1) || true
  printf '%s' "${owner_name}"
}

# ---------------------------------------------------------------------------
# Core transfer logic
# ---------------------------------------------------------------------------

# Transfer a single repository; sets TRANSFER_STATUS and TRANSFER_MESSAGE
TRANSFER_STATUS=""
TRANSFER_MESSAGE=""

transfer_single() {
  local source="$1" repo="$2" dest="$3"
  local raw status body

  log_info "Transferring ${source}/${repo} -> ${dest}/${repo}"

  # --- Pre-flight checks ---
  log_verbose "Verifying source repo admin access..."
  local verify_rc=0
  verify_repo_admin "${source}" "${repo}" || verify_rc=$?
  case "${verify_rc}" in
    1) TRANSFER_STATUS="SKIPPED"; TRANSFER_MESSAGE="Source repo not found: ${source}/${repo}"; return 0 ;;
    2) TRANSFER_STATUS="SKIPPED"; TRANSFER_MESSAGE="API error checking source repo ${source}/${repo}"; return 0 ;;
    3) TRANSFER_STATUS="SKIPPED"; TRANSFER_MESSAGE="No admin access on ${source}/${repo}"; return 0 ;;
  esac

  log_verbose "Checking source repo is not a fork..."
  if is_fork "${source}" "${repo}"; then
    TRANSFER_STATUS="SKIPPED"
    TRANSFER_MESSAGE="Forks cannot be transferred: ${source}/${repo}"
    return 0
  fi

  log_verbose "Verifying destination org..."
  local dest_rc=0
  verify_dest_org "${dest}" || dest_rc=$?
  case "${dest_rc}" in
    1) TRANSFER_STATUS="SKIPPED"; TRANSFER_MESSAGE="Destination org not found: ${dest}"; return 0 ;;
    2) TRANSFER_STATUS="SKIPPED"; TRANSFER_MESSAGE="API error checking dest org ${dest}"; return 0 ;;
  esac

  # --- Enterprise boundary check ---
  # Extract the API base URL from each org's response to detect cross-instance transfers.
  # Patterns handle both "url":"..." and "url": "..." formats. Use || true to prevent
  # grep-no-match from triggering set -e.
  local source_url dest_url
  source_url=$(api_call GET "orgs/${source}" 2>/dev/null | grep -o '"url": *"[^"]*"' | head -1 | sed 's/.*": *"//' | tr -d '"' | sed 's|/orgs/.*||') || true
  dest_url=$(api_call GET "orgs/${dest}" 2>/dev/null | grep -o '"url": *"[^"]*"' | head -1 | sed 's/.*": *"//' | tr -d '"' | sed 's|/orgs/.*||') || true
  log_verbose "Source org API URL base: ${source_url}"
  log_verbose "Dest org API URL base:   ${dest_url}"
  if [[ -n "${source_url}" && -n "${dest_url}" && "${source_url}" != "${dest_url}" ]]; then
    TRANSFER_STATUS="SKIPPED"
    TRANSFER_MESSAGE="Cross-enterprise transfers are not supported (${source_url} vs ${dest_url})"
    return 0
  fi

  # --- Dry run ---
  if [[ "${DRY_RUN}" == true ]]; then
    log_dry "Would transfer: ${source}/${repo} -> ${dest}/${repo}"
    TRANSFER_STATUS="DRY_RUN"
    TRANSFER_MESSAGE="Would transfer ${source}/${repo} to ${dest}"
    return 0
  fi

  # --- Build request body ---
  local body_json
  if [[ -n "${TEAM_IDS}" ]]; then
    # Convert comma list to JSON array of ints
    local team_array
    team_array=$(printf '%s' "${TEAM_IDS}" | \
      awk 'BEGIN{RS=",";ORS=","}{gsub(/ /,""); printf "%s", $0}' | \
      sed 's/,$//' | \
      awk 'BEGIN{printf "["}{printf (NR>1?",":"")$0}END{printf "]"}')
    body_json="{\"new_owner\":\"${dest}\",\"team_ids\":${team_array}}"
  else
    body_json="{\"new_owner\":\"${dest}\"}"
  fi

  # --- Execute transfer ---
  raw=$(api_call_status POST "repos/${source}/${repo}/transfer" "${body_json}")
  status=$(printf '%s' "${raw}" | parse_status)
  body=$(printf '%s' "${raw}" | parse_body)

  log_verbose "Transfer API status: ${status}"

  case "${status}" in
    202)
      TRANSFER_STATUS="ACCEPTED"
      TRANSFER_MESSAGE="Transfer initiated (async); GitHub is processing in background"
      log_ok "Transfer accepted for ${source}/${repo} -> ${dest}/${repo}"
      ;;
    403)
      local err_msg_403
      err_msg_403=$(printf '%s' "${body}" | grep -o '"message": *"[^"]*"' | head -1 | sed 's/.*": *"//' | tr -d '"') || true
      TRANSFER_STATUS="FAILED"
      TRANSFER_MESSAGE="Permission denied: ${err_msg_403}"
      log_error "Transfer forbidden for ${source}/${repo}"
      ;;
    404)
      TRANSFER_STATUS="FAILED"
      TRANSFER_MESSAGE="Not found: repo or org missing"
      log_error "Transfer 404 for ${source}/${repo} -> ${dest}"
      ;;
    422)
      local msg
      msg=$(printf '%s' "${body}" | grep -o '"message": *"[^"]*"' | head -1 | sed 's/.*": *"//' | tr -d '"') || true
      TRANSFER_STATUS="FAILED"
      TRANSFER_MESSAGE="Validation error: ${msg}"
      log_error "Transfer validation error for ${source}/${repo}: ${msg}"
      ;;
    *)
      local err_msg_other
      err_msg_other=$(printf '%s' "${body}" | grep -o '"message": *"[^"]*"' | head -1 | sed 's/.*": *"//' | tr -d '"') || true
      TRANSFER_STATUS="FAILED"
      TRANSFER_MESSAGE="Unexpected HTTP ${status}: ${err_msg_other}"
      log_error "Unexpected response ${status} for ${source}/${repo}"
      ;;
  esac
}

# ---------------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------------

init_output_csv() {
  printf 'SourceOrg,RepoName,DestOrg,Status,Message,Timestamp\n' > "${OUTPUT_FILE}"
  log_info "Results will be written to: ${OUTPUT_FILE}"
}

append_result() {
  local source="$1" repo="$2" dest="$3" status="$4" message="$5"
  local ts
  ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  # Escape double quotes in message
  message="${message//\"/\"\"}"
  printf '%s,%s,%s,%s,"%s",%s\n' "${source}" "${repo}" "${dest}" "${status}" "${message}" "${ts}" >> "${OUTPUT_FILE}"
}

# ---------------------------------------------------------------------------
# Bulk transfer
# ---------------------------------------------------------------------------

transfer_bulk() {
  local file="$1"
  [[ -f "${file}" ]] || die "Import file not found: ${file}"

  # Count non-blank, non-comment lines (may include header — subtract 1 if header present)
  local total
  total=$(grep -cE '^[^#[:space:]]' "${file}" || true)
  # Detect if a header row is present and subtract it from total
  local first_field
  first_field=$(head -1 "${file}" | cut -d',' -f1 | tr '[:upper:]' '[:lower:]' | tr -d ' ')
  case "${first_field}" in sourceorg|source|org) total=$((total - 1)) ;; esac
  [[ "${total}" -le 0 ]] && die "No transfer rows found in ${file}"

  local skipped_header=false
  local current=0 success=0 failed=0 skipped=0

  log_info "Loaded ${total} transfer(s) from ${file}"

  if [[ "${DRY_RUN}" == false && "${CONFIRM}" == false ]]; then
    printf '\n'
    printf '%s[CONFIRM]%s About to transfer %d repo(s). This is irreversible.\n' "${YELLOW}" "${RESET}" "${total}"
    printf '  Source file : %s\n' "${file}"
    printf '  Output file : %s\n' "${OUTPUT_FILE}"
    printf '\n'
    read -r -p "Type 'yes' to proceed: " answer
    [[ "${answer}" == "yes" ]] || { log_warn "Aborted by user."; exit 1; }
  fi

  init_output_csv

  while IFS=',' read -r src rpo dst || [[ -n "${src}" ]]; do
    # Trim whitespace
    src="${src#"${src%%[![:space:]]*}"}"
    src="${src%"${src##*[![:space:]]}"}"
    rpo="${rpo#"${rpo%%[![:space:]]*}"}"
    rpo="${rpo%"${rpo##*[![:space:]]}"}"
    dst="${dst#"${dst%%[![:space:]]*}"}"
    dst="${dst%"${dst##*[![:space:]]}"}"

    # Skip blank lines and comments
    [[ -z "${src}" ]] && continue
    [[ "${src}" == \#* ]] && continue

    # Skip header row (case-insensitive match on common header values)
    if [[ "${skipped_header}" == false ]]; then
      local src_lower
      src_lower=$(printf '%s' "${src}" | tr '[:upper:]' '[:lower:]')
      if [[ "${src_lower}" == "sourceorg" || "${src_lower}" == "source" || "${src_lower}" == "org" ]]; then
        skipped_header=true
        log_verbose "Skipped CSV header row"
        continue
      fi
      skipped_header=true
    fi

    # Validate columns
    if [[ -z "${rpo}" || -z "${dst}" ]]; then
      log_warn "Skipping malformed row: '${src},${rpo},${dst}'"
      append_result "${src}" "${rpo}" "${dst}" "SKIPPED" "Malformed CSV row"
      ((skipped++)) || true
      continue
    fi

    ((current++)) || true
    printf '\n%s[%d/%d]%s Processing %s/%s -> %s\n' "${CYAN}" "${current}" "${total}" "${RESET}" "${src}" "${rpo}" "${dst}"

    TRANSFER_STATUS=""
    TRANSFER_MESSAGE=""
    transfer_single "${src}" "${rpo}" "${dst}"

    append_result "${src}" "${rpo}" "${dst}" "${TRANSFER_STATUS}" "${TRANSFER_MESSAGE}"

    case "${TRANSFER_STATUS}" in
      ACCEPTED|DRY_RUN) ((success++)) || true ;;
      SKIPPED)          ((skipped++)) || true ;;
      *)                ((failed++))  || true ;;
    esac

  done < "${file}"

  echo
  log_info "=== Bulk Transfer Summary ==="
  log_ok    "  Accepted : ${success}"
  [[ "${failed}"  -gt 0 ]] && log_error "  Failed   : ${failed}"
  [[ "${skipped}" -gt 0 ]] && log_warn  "  Skipped  : ${skipped}"
  log_info "  Results  -> ${OUTPUT_FILE}"
}

# ---------------------------------------------------------------------------
# Export org repos to CSV
# ---------------------------------------------------------------------------

export_org_repos() {
  local org="$1" out_file="$2"
  local page=1 per_page=100 repos total_written=0

  log_info "Exporting repos for org '${org}' to ${out_file}..."
  printf 'SourceOrg,RepoName,DestOrg\n' > "${out_file}"

  while true; do
    repos=$(api_call GET "orgs/${org}/repos?per_page=${per_page}&page=${page}&type=all")

    local count
    count=$(printf '%s' "${repos}" | grep -o '"name"' | wc -l | tr -d ' ')
    [[ "${count}" -eq 0 ]] && break

    while IFS= read -r name; do
      [[ -z "${name}" ]] && continue
      printf '%s,%s,\n' "${org}" "${name}" >> "${out_file}"
      ((total_written++)) || true
    done < <(printf '%s' "${repos}" | grep -o '"name": *"[^"]*"' | sed 's/.*": *"//' | tr -d '"')

    log_verbose "Page ${page}: wrote ${count} repos"
    [[ "${count}" -lt "${per_page}" ]] && break
    ((page++)) || true
  done

  log_ok "Exported ${total_written} repo(s) to ${out_file}"
  log_info "Edit the DestOrg column, then run: ${SCRIPT_NAME}.sh --import ${out_file}"
}

# ---------------------------------------------------------------------------
# Query org repos to stdout
# ---------------------------------------------------------------------------

query_org_repos() {
  local org="$1"
  local page=1 per_page=100

  log_info "Listing repos for org '${org}'..."

  while true; do
    local repos
    repos=$(api_call GET "orgs/${org}/repos?per_page=${per_page}&page=${page}&type=all")

    local count
    count=$(printf '%s' "${repos}" | grep -o '"name"' | wc -l | tr -d ' ')
    [[ "${count}" -eq 0 ]] && break

    printf '%s' "${repos}" | grep -o '"name": *"[^"]*"' | sed 's/.*": *"//' | tr -d '"'

    log_verbose "Page ${page}: ${count} repos"
    [[ "${count}" -lt "${per_page}" ]] && break
    ((page++)) || true
  done
}

# ---------------------------------------------------------------------------
# Diff mode: compare CSV plan against live state
# ---------------------------------------------------------------------------

diff_plan() {
  local file="$1"
  [[ -f "${file}" ]] || die "Diff file not found: ${file}"

  local skipped_header=false already_done=0 needed=0 not_found=0

  printf '\n%sREPO TRANSFER DIFF%s — %s\n\n' "${BOLD}" "${RESET}" "${file}"
  printf '%-30s %-25s %-25s %s\n' "REPO" "CURRENT OWNER" "DEST ORG" "STATUS"
  printf '%s\n' "$(printf '%0.s-' {1..100})"

  while IFS=',' read -r src rpo dst || [[ -n "${src}" ]]; do
    src="${src#"${src%%[![:space:]]*}"}"; src="${src%"${src##*[![:space:]]}"}"
    rpo="${rpo#"${rpo%%[![:space:]]*}"}"; rpo="${rpo%"${rpo##*[![:space:]]}"}"
    dst="${dst#"${dst%%[![:space:]]*}"}"; dst="${dst%"${dst##*[![:space:]]}"}"

    [[ -z "${src}" ]] && continue
    [[ "${src}" == \#* ]] && continue

    if [[ "${skipped_header}" == false ]]; then
      local src_lower
      src_lower=$(printf '%s' "${src}" | tr '[:upper:]' '[:lower:]')
      if [[ "${src_lower}" == "sourceorg" || "${src_lower}" == "source" || "${src_lower}" == "org" ]]; then
        skipped_header=true
        continue
      fi
      skipped_header=true
    fi

    [[ -z "${rpo}" || -z "${dst}" ]] && continue

    # Get current owner
    local current_owner
    current_owner=$(get_repo_owner "${src}" "${rpo}" 2>/dev/null || printf 'NOT_FOUND')

    if [[ "${current_owner}" == "NOT_FOUND" ]]; then
      printf '%-30s %-25s %-25s %s\n' "${src}/${rpo}" "NOT FOUND" "${dst}" "${RED}NOT FOUND${RESET}"
      ((not_found++)) || true
    elif [[ "${current_owner}" == "${dst}" ]]; then
      printf '%-30s %-25s %-25s %s\n' "${src}/${rpo}" "${current_owner}" "${dst}" "${GREEN}ALREADY DONE${RESET}"
      ((already_done++)) || true
    else
      printf '%-30s %-25s %-25s %s\n' "${src}/${rpo}" "${current_owner}" "${dst}" "${YELLOW}NEEDS TRANSFER${RESET}"
      ((needed++)) || true
    fi
  done < "${file}"

  printf '\n'
  log_info "Needs transfer : ${needed}"
  log_info "Already done   : ${already_done}"
  [[ "${not_found}" -gt 0 ]] && log_warn "Not found      : ${not_found}"
}

# ---------------------------------------------------------------------------
# Interactive mode
# ---------------------------------------------------------------------------

interactive_mode() {
  printf '\n%s%s — Interactive Mode%s\n\n' "${BOLD}" "${SCRIPT_NAME}" "${RESET}"

  printf 'What would you like to do?\n'
  printf '  1) Transfer a single repository\n'
  printf '  2) Bulk transfer from a CSV file\n'
  printf '  3) Export org repos to CSV\n'
  printf '  4) Diff a CSV plan against live state\n'
  printf '  5) List all repos in an org\n'
  printf '  q) Quit\n'
  printf '\n'
  read -r -p "Choice [1-5/q]: " choice

  case "${choice}" in
    1)
      read -r -p "Source org:        " SOURCE_ORG
      read -r -p "Repository name:   " REPO_NAME
      read -r -p "Destination org:   " DEST_ORG
      read -r -p "Dry run? [y/N]:    " dr
      [[ "${dr}" =~ ^[Yy]$ ]] && DRY_RUN=true
      printf '\n'
      init_output_csv
      transfer_single "${SOURCE_ORG}" "${REPO_NAME}" "${DEST_ORG}"
      append_result "${SOURCE_ORG}" "${REPO_NAME}" "${DEST_ORG}" "${TRANSFER_STATUS}" "${TRANSFER_MESSAGE}"
      log_info "Result: ${TRANSFER_STATUS} — ${TRANSFER_MESSAGE}"
      ;;
    2)
      read -r -p "CSV import file:   " IMPORT_FILE
      read -r -p "Dry run? [y/N]:    " dr
      [[ "${dr}" =~ ^[Yy]$ ]] && DRY_RUN=true
      transfer_bulk "${IMPORT_FILE}"
      ;;
    3)
      read -r -p "Source org:        " QUERY_ORG
      read -r -p "Output CSV file:   " EXPORT_FILE
      export_org_repos "${QUERY_ORG}" "${EXPORT_FILE}"
      ;;
    4)
      read -r -p "CSV plan file:     " DIFF_FILE
      diff_plan "${DIFF_FILE}"
      ;;
    5)
      read -r -p "Org name:          " QUERY_ORG
      query_org_repos "${QUERY_ORG}"
      ;;
    q|Q) log_info "Goodbye."; exit 0 ;;
    *)   die "Invalid choice: ${choice}" ;;
  esac
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
  parse_args "$@"

  # Interactive mode takes precedence
  if [[ "${INTERACTIVE}" == true ]]; then
    interactive_mode
    exit 0
  fi

  # Determine mode
  local mode="none"
  [[ -n "${REPO_NAME}" && -n "${SOURCE_ORG}" && -n "${DEST_ORG}" ]] && mode="single"
  [[ -n "${IMPORT_FILE}" ]] && mode="bulk"
  [[ -n "${QUERY_ORG}" && -n "${EXPORT_FILE}" ]] && mode="export"
  [[ -n "${QUERY_ORG}" && -z "${EXPORT_FILE}" && -z "${IMPORT_FILE}" ]] && mode="query"
  [[ -n "${DIFF_FILE}" ]] && mode="diff"

  if [[ "${mode}" == "none" ]]; then
    log_error "No operation specified."
    printf '\nUse --help to see available options.\n' >&2
    exit 1
  fi

  # Resolve authentication (not needed for dry-run diff, but resolve anyway for consistency)
  resolve_token

  case "${mode}" in
    single)
      init_output_csv
      transfer_single "${SOURCE_ORG}" "${REPO_NAME}" "${DEST_ORG}"
      append_result "${SOURCE_ORG}" "${REPO_NAME}" "${DEST_ORG}" "${TRANSFER_STATUS}" "${TRANSFER_MESSAGE}"
      log_info "Status  : ${TRANSFER_STATUS}"
      log_info "Message : ${TRANSFER_MESSAGE}"
      log_info "Results : ${OUTPUT_FILE}"
      ;;
    bulk)
      transfer_bulk "${IMPORT_FILE}"
      ;;
    export)
      export_org_repos "${QUERY_ORG}" "${EXPORT_FILE}"
      ;;
    query)
      query_org_repos "${QUERY_ORG}"
      ;;
    diff)
      diff_plan "${DIFF_FILE}"
      ;;
  esac
}

main "$@"
