#!/usr/bin/env bash
# =============================================================================
# test_migrator.sh — Test suite for gh-repo-migrator.sh
# Written by h3nryza
# =============================================================================
# Tests use a mock curl shim injected via PATH manipulation so no real GitHub
# API calls are made.  Each test group sets up the desired mock responses.
#
# Run from the repo root or from within tests/:
#   bash tests/test_migrator.sh
#   bash tests/test_migrator.sh --verbose
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Resolve paths
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
MAIN_SCRIPT="${REPO_ROOT}/gh-repo-migrator.sh"
MOCK_DIR="${SCRIPT_DIR}/mock_gh_responses"
SHIM_DIR="$(mktemp -d)"   # Temporary directory for mock binaries
WORK_DIR="$(mktemp -d)"   # Temporary working directory for output files

VERBOSE=false
[[ "${1:-}" == "--verbose" ]] && VERBOSE=true

# ---------------------------------------------------------------------------
# Test framework
# ---------------------------------------------------------------------------
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0
FAILED_NAMES=()

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

log_test()  { printf "${CYAN}[TEST]${RESET}  %s\n" "$*"; }
log_pass()  { printf "${GREEN}[PASS]${RESET}  %s\n" "$*"; }
log_fail()  { printf "${RED}[FAIL]${RESET}  %s\n"  "$*" >&2; }
log_skip()  { printf "${YELLOW}[SKIP]${RESET}  %s\n" "$*"; }
log_debug() { [[ "${VERBOSE}" == true ]] && printf "[DEBUG] %s\n" "$*" || true; }

assert_eq() {
  local label="$1" expected="$2" actual="$3"
  if [[ "${expected}" == "${actual}" ]]; then
    log_pass "${label}"
    ((TESTS_PASSED++)) || true
  else
    log_fail "${label}"
    log_fail "  Expected : '${expected}'"
    log_fail "  Actual   : '${actual}'"
    ((TESTS_FAILED++)) || true
    FAILED_NAMES+=("${label}")
  fi
  ((TESTS_RUN++)) || true
}

assert_contains() {
  local label="$1" needle="$2" haystack="$3"
  if printf '%s' "${haystack}" | grep -qF "${needle}"; then
    log_pass "${label}"
    ((TESTS_PASSED++)) || true
  else
    log_fail "${label}"
    log_fail "  Expected to contain : '${needle}'"
    log_fail "  Actual output       : '${haystack}'"
    ((TESTS_FAILED++)) || true
    FAILED_NAMES+=("${label}")
  fi
  ((TESTS_RUN++)) || true
}

assert_not_contains() {
  local label="$1" needle="$2" haystack="$3"
  if ! printf '%s' "${haystack}" | grep -qF "${needle}"; then
    log_pass "${label}"
    ((TESTS_PASSED++)) || true
  else
    log_fail "${label}"
    log_fail "  Expected NOT to contain : '${needle}'"
    log_fail "  Actual output           : '${haystack}'"
    ((TESTS_FAILED++)) || true
    FAILED_NAMES+=("${label}")
  fi
  ((TESTS_RUN++)) || true
}

assert_file_contains() {
  local label="$1" needle="$2" file="$3"
  if [[ -f "${file}" ]] && grep -qF "${needle}" "${file}"; then
    log_pass "${label}"
    ((TESTS_PASSED++)) || true
  else
    log_fail "${label}"
    log_fail "  File '${file}' does not contain: '${needle}'"
    ((TESTS_FAILED++)) || true
    FAILED_NAMES+=("${label}")
  fi
  ((TESTS_RUN++)) || true
}

assert_exit_zero() {
  local label="$1" exit_code="$2"
  if [[ "${exit_code}" -eq 0 ]]; then
    log_pass "${label}"
    ((TESTS_PASSED++)) || true
  else
    log_fail "${label} (exit code ${exit_code})"
    ((TESTS_FAILED++)) || true
    FAILED_NAMES+=("${label}")
  fi
  ((TESTS_RUN++)) || true
}

assert_exit_nonzero() {
  local label="$1" exit_code="$2"
  if [[ "${exit_code}" -ne 0 ]]; then
    log_pass "${label}"
    ((TESTS_PASSED++)) || true
  else
    log_fail "${label} (expected non-zero exit)"
    ((TESTS_FAILED++)) || true
    FAILED_NAMES+=("${label}")
  fi
  ((TESTS_RUN++)) || true
}

# ---------------------------------------------------------------------------
# Mock curl shim builder
# ---------------------------------------------------------------------------
# The shim is a bash script placed in SHIM_DIR (prepended to PATH).
# It reads MOCK_CURL_RESPONSE and MOCK_CURL_STATUS env vars to decide
# what to output.  Complex tests can write a "routing" shim that inspects
# the URL and selects the right fixture.

create_simple_shim() {
  local status_code="$1" response_body="$2"
  # Escape single quotes in body for embedding in heredoc
  local escaped_body="${response_body//\'/\'\\\'\'}"
  cat > "${SHIM_DIR}/curl" <<SHIM
#!/usr/bin/env bash
# Simple mock curl
# Detect whether caller wants -w (status suffix) or just the body
wants_status=false
for arg in "\$@"; do
  [[ "\${arg}" == "-w" || "\${arg}" == --write-out* ]] && wants_status=true
done
body='${escaped_body}'
if [[ "\${wants_status}" == true ]]; then
  printf '%s__STATUS__%s' "\${body}" '${status_code}'
else
  printf '%s' "\${body}"
fi
SHIM
  chmod +x "${SHIM_DIR}/curl"
}

# More advanced shim driven by MOCK_ROUTES env var:
# MOCK_ROUTES is a newline-separated list of "PATTERN|STATUS|BODY_FILE"
create_routing_shim() {
  # routes_file arg is accepted but not used here — the shim reads MOCK_ROUTES_FILE from env.
  # shellcheck disable=SC2034
  local routes_file="$1"
  cat > "${SHIM_DIR}/curl" <<'SHIM'
#!/usr/bin/env bash
# Routing mock curl — matches URL patterns against MOCK_ROUTES_FILE
# Respects whether -w flag is present to decide if __STATUS__ suffix is appended
url=""
wants_status=false
for arg in "$@"; do
  case "${arg}" in
    https://*|http://*) url="${arg}" ;;
    -w|--write-out*)    wants_status=true ;;
  esac
done

routes_file="${MOCK_ROUTES_FILE:-}"
if [[ -z "${routes_file}" || ! -f "${routes_file}" ]]; then
  if [[ "${wants_status}" == true ]]; then
    printf '{"message":"mock not configured"}__STATUS__500'
  else
    printf '{"message":"mock not configured"}'
  fi
  exit 0
fi

matched=false
while IFS='|' read -r pattern status body_file; do
  [[ "${url}" == *"${pattern}"* ]] || continue
  body=""
  [[ -f "${body_file}" ]] && body="$(cat "${body_file}")"
  if [[ "${wants_status}" == true ]]; then
    printf '%s__STATUS__%s' "${body}" "${status}"
  else
    printf '%s' "${body}"
  fi
  matched=true
  break
done < "${routes_file}"

if [[ "${matched}" == false ]]; then
  if [[ "${wants_status}" == true ]]; then
    printf '{"message":"no mock route for %s"}__STATUS__404' "${url}"
  else
    printf '{"message":"no mock route for %s"}' "${url}"
  fi
fi
SHIM
  chmod +x "${SHIM_DIR}/curl"
}

# Also mock 'gh' to avoid requiring actual gh CLI
create_gh_shim() {
  local token="${1:-test-token-abc123}"
  cat > "${SHIM_DIR}/gh" <<SHIM
#!/usr/bin/env bash
case "\$1 \$2" in
  "auth status") exit 0 ;;
  "auth token")  printf '%s\n' '${token}' ;;
  *)             exit 1 ;;
esac
SHIM
  chmod +x "${SHIM_DIR}/gh"
}

write_routes_file() {
  local file="$1"
  shift
  printf '' > "${file}"
  while [[ $# -ge 3 ]]; do
    printf '%s|%s|%s\n' "$1" "$2" "$3" >> "${file}"
    shift 3
  done
}

# ---------------------------------------------------------------------------
# Setup / Teardown
# ---------------------------------------------------------------------------
setup() {
  # Prepend shim dir so our mocks take precedence
  export PATH="${SHIM_DIR}:${PATH}"
  create_gh_shim "fake-pat-token"
}

teardown() {
  # Remove temp dirs
  rm -rf "${SHIM_DIR}" "${WORK_DIR}"
}
trap teardown EXIT

# ---------------------------------------------------------------------------
# Test helper: run main script with given args, capture output and exit code
# ---------------------------------------------------------------------------
run_script() {
  local exit_code=0
  OUTPUT="$(bash "${MAIN_SCRIPT}" "$@" 2>&1)" || exit_code=$?
  SCRIPT_EXIT_CODE="${exit_code}"
  log_debug "run_script exit=${exit_code}"
  log_debug "run_script output=${OUTPUT}"
}

# ---------------------------------------------------------------------------
# ============================================================
# TEST GROUPS
# ============================================================
# ---------------------------------------------------------------------------

test_cli_basics() {
  printf '\n%s=== CLI Basics ===%s\n' "${BOLD}" "${RESET}"

  # --help exits 0
  run_script --help
  assert_exit_zero "--help exits 0" "${SCRIPT_EXIT_CODE}"
  assert_contains "--help contains USAGE" "USAGE:" "${OUTPUT}"
  assert_contains "--help contains EXAMPLES" "EXAMPLES:" "${OUTPUT}"
  assert_contains "--help contains auth section" "AUTH METHODS:" "${OUTPUT}"
  assert_contains "--help contains h3nryza" "h3nryza" "${OUTPUT}"

  # --version exits 0
  run_script --version
  assert_exit_zero "--version exits 0" "${SCRIPT_EXIT_CODE}"
  assert_contains "--version shows version string" "gh-repo-migrator" "${OUTPUT}"
  assert_contains "--version shows author" "h3nryza" "${OUTPUT}"

  # No args exits 0 (shows help)
  run_script || true
  assert_eq "no args exits 0" "0" "${SCRIPT_EXIT_CODE}"

  # Unknown flag exits non-zero
  run_script --does-not-exist || true
  assert_exit_nonzero "unknown flag exits non-zero" "${SCRIPT_EXIT_CODE}"
}

test_arg_validation() {
  printf '\n%s=== Argument Validation ===%s\n' "${BOLD}" "${RESET}"

  # Missing dest should fail after resolve_token (no valid mode)
  # We provide --auth pat to avoid gh dependency
  run_script --auth pat --token fake -r my-repo -s source-org || true
  assert_exit_nonzero "missing --dest triggers error" "${SCRIPT_EXIT_CODE}"

  # --import with non-existent file exits non-zero
  run_script --auth pat --token fake --import /tmp/no_such_file_xyz_123.csv || true
  assert_exit_nonzero "missing import file exits non-zero" "${SCRIPT_EXIT_CODE}"

  # --auth app without --app-id exits non-zero
  run_script --auth app --repo r -s src -d dst || true
  assert_exit_nonzero "--auth app missing --app-id exits non-zero" "${SCRIPT_EXIT_CODE}"

  # --auth pat without token exits non-zero (GITHUB_TOKEN not set)
  unset GITHUB_TOKEN || true
  run_script --auth pat --repo r -s src -d dst || true
  assert_exit_nonzero "--auth pat no token exits non-zero" "${SCRIPT_EXIT_CODE}"
}

test_dry_run_single() {
  printf '\n%s=== Dry Run — Single Transfer ===%s\n' "${BOLD}" "${RESET}"

  # Set up routing shim:
  #   GET repos/source-org/my-repo -> 200 + admin
  #   GET orgs/dest-org             -> 200
  #   GET orgs/source-org           -> 200 (for enterprise boundary check)
  #   GET user                      -> simple login response
  #   GET orgs/dest-org/memberships/* -> 200
  local routes="${WORK_DIR}/routes.txt"
  cat > "${routes}" <<ROUTES
repos/source-org/my-repo|200|${MOCK_DIR}/repo_200_admin.json
orgs/dest-org/memberships|200|${MOCK_DIR}/org_200.json
orgs/dest-org|200|${MOCK_DIR}/org_200.json
orgs/source-org|200|${MOCK_DIR}/org_200.json
user|200|${MOCK_DIR}/org_200.json
ROUTES
  export MOCK_ROUTES_FILE="${routes}"
  create_routing_shim "${routes}"
  create_gh_shim "fake-token"

  local out_file="${WORK_DIR}/dry_result.csv"
  run_script --auth pat --token fake \
    -r my-repo -s source-org -d dest-org \
    --dry-run --confirm \
    --output "${out_file}" || true

  assert_exit_zero "dry-run single exits 0" "${SCRIPT_EXIT_CODE}"
  assert_contains "dry-run single shows DRY-RUN" "DRY-RUN" "${OUTPUT}"
  assert_file_contains "dry-run single writes DRY_RUN to CSV" "DRY_RUN" "${out_file}"
  assert_file_contains "dry-run single CSV has header" "SourceOrg,RepoName,DestOrg,Status" "${out_file}"
}

test_dry_run_no_admin() {
  printf '\n%s=== Dry Run — No Admin Access ===%s\n' "${BOLD}" "${RESET}"

  local routes="${WORK_DIR}/routes_noadmin.txt"
  cat > "${routes}" <<ROUTES
repos/source-org/my-repo|200|${MOCK_DIR}/repo_200_noadmin.json
orgs/dest-org|200|${MOCK_DIR}/org_200.json
orgs/source-org|200|${MOCK_DIR}/org_200.json
user|200|${MOCK_DIR}/org_200.json
ROUTES
  export MOCK_ROUTES_FILE="${routes}"
  create_routing_shim "${routes}"
  create_gh_shim "fake-token"

  local out_file="${WORK_DIR}/noadmin_result.csv"
  run_script --auth pat --token fake \
    -r my-repo -s source-org -d dest-org \
    --dry-run --confirm \
    --output "${out_file}" || true

  assert_exit_zero "no-admin exits 0 (SKIPPED)" "${SCRIPT_EXIT_CODE}"
  assert_file_contains "no-admin writes SKIPPED" "SKIPPED" "${out_file}"
}

test_dry_run_fork() {
  printf '\n%s=== Dry Run — Fork Cannot Be Transferred ===%s\n' "${BOLD}" "${RESET}"

  local routes="${WORK_DIR}/routes_fork.txt"
  cat > "${routes}" <<ROUTES
repos/source-org/forked-repo|200|${MOCK_DIR}/repo_fork.json
orgs/dest-org|200|${MOCK_DIR}/org_200.json
orgs/source-org|200|${MOCK_DIR}/org_200.json
user|200|${MOCK_DIR}/org_200.json
ROUTES
  export MOCK_ROUTES_FILE="${routes}"
  create_routing_shim "${routes}"
  create_gh_shim "fake-token"

  local out_file="${WORK_DIR}/fork_result.csv"
  run_script --auth pat --token fake \
    -r forked-repo -s source-org -d dest-org \
    --confirm \
    --output "${out_file}" || true

  assert_exit_zero "fork exits 0 (SKIPPED)" "${SCRIPT_EXIT_CODE}"
  assert_file_contains "fork writes SKIPPED" "SKIPPED" "${out_file}"
  assert_file_contains "fork message mentions fork" "Forks cannot" "${out_file}"
}

test_dry_run_repo_not_found() {
  printf '\n%s=== Dry Run — Repo Not Found ===%s\n' "${BOLD}" "${RESET}"

  local routes="${WORK_DIR}/routes_404.txt"
  cat > "${routes}" <<ROUTES
repos/source-org/missing-repo|404|${MOCK_DIR}/repo_404.json
orgs/dest-org|200|${MOCK_DIR}/org_200.json
orgs/source-org|200|${MOCK_DIR}/org_200.json
user|200|${MOCK_DIR}/org_200.json
ROUTES
  export MOCK_ROUTES_FILE="${routes}"
  create_routing_shim "${routes}"
  create_gh_shim "fake-token"

  local out_file="${WORK_DIR}/404_result.csv"
  run_script --auth pat --token fake \
    -r missing-repo -s source-org -d dest-org \
    --confirm \
    --output "${out_file}" || true

  assert_exit_zero "repo-not-found exits 0 (SKIPPED)" "${SCRIPT_EXIT_CODE}"
  assert_file_contains "repo-not-found writes SKIPPED" "SKIPPED" "${out_file}"
}

test_bulk_transfer_dry_run() {
  printf '\n%s=== Bulk Transfer — Dry Run ===%s\n' "${BOLD}" "${RESET}"

  # Create a sample CSV
  local csv_file="${WORK_DIR}/bulk_input.csv"
  cat > "${csv_file}" <<CSV
SourceOrg,RepoName,DestOrg
source-org,my-repo,dest-org
source-org,forked-repo,dest-org
source-org,missing-repo,dest-org
CSV

  local routes="${WORK_DIR}/routes_bulk.txt"
  cat > "${routes}" <<ROUTES
repos/source-org/my-repo|200|${MOCK_DIR}/repo_200_admin.json
repos/source-org/forked-repo|200|${MOCK_DIR}/repo_fork.json
repos/source-org/missing-repo|404|${MOCK_DIR}/repo_404.json
orgs/dest-org/memberships|200|${MOCK_DIR}/org_200.json
orgs/dest-org|200|${MOCK_DIR}/org_200.json
orgs/source-org|200|${MOCK_DIR}/org_200.json
user|200|${MOCK_DIR}/org_200.json
ROUTES
  export MOCK_ROUTES_FILE="${routes}"
  create_routing_shim "${routes}"
  create_gh_shim "fake-token"

  local out_file="${WORK_DIR}/bulk_result.csv"
  run_script --auth pat --token fake \
    --import "${csv_file}" \
    --dry-run --confirm \
    --output "${out_file}"

  assert_exit_zero "bulk dry-run exits 0" "${SCRIPT_EXIT_CODE}"
  assert_file_contains "bulk dry-run has CSV header" "SourceOrg,RepoName,DestOrg,Status" "${out_file}"
  assert_file_contains "bulk dry-run has DRY_RUN row" "DRY_RUN" "${out_file}"
  assert_file_contains "bulk dry-run has SKIPPED (fork)" "SKIPPED" "${out_file}"
  # Summary shows in output
  assert_contains "bulk dry-run shows summary" "Summary" "${OUTPUT}"
}

test_bulk_malformed_csv() {
  printf '\n%s=== Bulk Transfer — Malformed CSV ===%s\n' "${BOLD}" "${RESET}"

  local csv_file="${WORK_DIR}/malformed.csv"
  cat > "${csv_file}" <<CSV
source-org,my-repo
# this is a comment line
source-org,,dest-org
source-org,good-repo,dest-org
CSV

  local routes="${WORK_DIR}/routes_malformed.txt"
  cat > "${routes}" <<ROUTES
repos/source-org/good-repo|200|${MOCK_DIR}/repo_200_admin.json
repos/source-org/my-repo|200|${MOCK_DIR}/repo_200_admin.json
orgs/dest-org/memberships|200|${MOCK_DIR}/org_200.json
orgs/dest-org|200|${MOCK_DIR}/org_200.json
orgs/source-org|200|${MOCK_DIR}/org_200.json
user|200|${MOCK_DIR}/org_200.json
ROUTES
  export MOCK_ROUTES_FILE="${routes}"
  create_routing_shim "${routes}"
  create_gh_shim "fake-token"

  local out_file="${WORK_DIR}/malformed_result.csv"
  run_script --auth pat --token fake \
    --import "${csv_file}" \
    --dry-run --confirm \
    --output "${out_file}"

  assert_exit_zero "malformed CSV exits 0 (skips bad rows)" "${SCRIPT_EXIT_CODE}"
  assert_file_contains "malformed CSV skips rows with SKIPPED" "SKIPPED" "${out_file}"
}

test_export_org_repos() {
  printf '\n%s=== Export Org Repos ===%s\n' "${BOLD}" "${RESET}"

  # Shim returns the org_repos_page1 JSON for any repos endpoint
  create_simple_shim "200" "$(cat "${MOCK_DIR}/org_repos_page1.json")"
  create_gh_shim "fake-token"

  local out_file="${WORK_DIR}/export_output.csv"
  run_script --auth pat --token fake \
    --query-org my-org \
    --export "${out_file}"

  assert_exit_zero "export exits 0" "${SCRIPT_EXIT_CODE}"
  assert_file_contains "export has CSV header" "SourceOrg,RepoName,DestOrg" "${out_file}"
  assert_file_contains "export contains repo names" "repo-alpha" "${out_file}"
  assert_file_contains "export contains org name" "my-org" "${out_file}"
}

test_query_org_repos() {
  printf '\n%s=== Query Org Repos (stdout) ===%s\n' "${BOLD}" "${RESET}"

  create_simple_shim "200" "$(cat "${MOCK_DIR}/org_repos_page1.json")"
  create_gh_shim "fake-token"

  run_script --auth pat --token fake \
    --query-org my-org

  assert_exit_zero "query-org exits 0" "${SCRIPT_EXIT_CODE}"
  assert_contains "query-org outputs repo names" "repo-alpha" "${OUTPUT}"
  assert_contains "query-org outputs all repos" "repo-epsilon" "${OUTPUT}"
}

test_output_csv_format() {
  printf '\n%s=== Output CSV Format ===%s\n' "${BOLD}" "${RESET}"

  local routes="${WORK_DIR}/routes_fmt.txt"
  cat > "${routes}" <<ROUTES
repos/source-org/my-repo|200|${MOCK_DIR}/repo_200_admin.json
orgs/dest-org/memberships|200|${MOCK_DIR}/org_200.json
orgs/dest-org|200|${MOCK_DIR}/org_200.json
orgs/source-org|200|${MOCK_DIR}/org_200.json
user|200|${MOCK_DIR}/org_200.json
ROUTES
  export MOCK_ROUTES_FILE="${routes}"
  create_routing_shim "${routes}"
  create_gh_shim "fake-token"

  local out_file="${WORK_DIR}/fmt_result.csv"
  run_script --auth pat --token fake \
    -r my-repo -s source-org -d dest-org \
    --dry-run --confirm \
    --output "${out_file}"

  assert_exit_zero "CSV format test exits 0" "${SCRIPT_EXIT_CODE}"

  # Verify exact header
  local header
  header=$(head -1 "${out_file}")
  assert_eq "CSV header is correct" "SourceOrg,RepoName,DestOrg,Status,Message,Timestamp" "${header}"

  # Verify row has 6 comma-separated fields (message may be quoted)
  local row
  row=$(tail -1 "${out_file}")
  # Count columns: should have source-org, my-repo, dest-org, DRY_RUN, message, timestamp
  assert_contains "CSV row has source org" "source-org" "${row}"
  assert_contains "CSV row has repo name" "my-repo" "${row}"
  assert_contains "CSV row has dest org" "dest-org" "${row}"
  assert_contains "CSV row has timestamp with Z" "Z" "${row}"
}

test_auth_gh_cli() {
  printf '\n%s=== Auth — GH CLI ===%s\n' "${BOLD}" "${RESET}"

  local routes="${WORK_DIR}/routes_ghauth.txt"
  cat > "${routes}" <<ROUTES
repos/source-org/my-repo|200|${MOCK_DIR}/repo_200_admin.json
orgs/dest-org/memberships|200|${MOCK_DIR}/org_200.json
orgs/dest-org|200|${MOCK_DIR}/org_200.json
orgs/source-org|200|${MOCK_DIR}/org_200.json
user|200|${MOCK_DIR}/org_200.json
ROUTES
  export MOCK_ROUTES_FILE="${routes}"
  create_routing_shim "${routes}"
  # gh shim returns a valid token
  create_gh_shim "ghcli-resolved-token"

  local out_file="${WORK_DIR}/ghauth_result.csv"
  run_script --auth gh \
    -r my-repo -s source-org -d dest-org \
    --dry-run --confirm \
    --output "${out_file}"

  assert_exit_zero "gh CLI auth exits 0" "${SCRIPT_EXIT_CODE}"
  assert_file_contains "gh CLI auth writes result" "DRY_RUN" "${out_file}"
}

test_auth_pat_via_env() {
  printf '\n%s=== Auth — PAT via GITHUB_TOKEN env ===%s\n' "${BOLD}" "${RESET}"

  local routes="${WORK_DIR}/routes_patenv.txt"
  cat > "${routes}" <<ROUTES
repos/source-org/my-repo|200|${MOCK_DIR}/repo_200_admin.json
orgs/dest-org/memberships|200|${MOCK_DIR}/org_200.json
orgs/dest-org|200|${MOCK_DIR}/org_200.json
orgs/source-org|200|${MOCK_DIR}/org_200.json
user|200|${MOCK_DIR}/org_200.json
ROUTES
  export MOCK_ROUTES_FILE="${routes}"
  create_routing_shim "${routes}"
  create_gh_shim "should-not-be-called"

  local out_file="${WORK_DIR}/patenv_result.csv"
  GITHUB_TOKEN="env-provided-pat" run_script --auth pat \
    -r my-repo -s source-org -d dest-org \
    --dry-run --confirm \
    --output "${out_file}"

  assert_exit_zero "PAT via GITHUB_TOKEN exits 0" "${SCRIPT_EXIT_CODE}"
  assert_file_contains "PAT via env writes result" "DRY_RUN" "${out_file}"
}

test_diff_plan() {
  printf '\n%s=== Diff Plan ===%s\n' "${BOLD}" "${RESET}"

  # Create plan CSV
  local csv_file="${WORK_DIR}/plan.csv"
  cat > "${csv_file}" <<CSV
SourceOrg,RepoName,DestOrg
source-org,my-repo,dest-org
source-org,missing-repo,dest-org
CSV

  # my-repo shows up in source-org (not yet transferred)
  # missing-repo returns 404
  local routes="${WORK_DIR}/routes_diff.txt"
  # For diff we call GET repos/{owner}/{repo} to get full_name
  cat > "${routes}" <<ROUTES
repos/source-org/my-repo|200|${MOCK_DIR}/repo_200_admin.json
repos/source-org/missing-repo|404|${MOCK_DIR}/repo_404.json
user|200|${MOCK_DIR}/org_200.json
ROUTES
  export MOCK_ROUTES_FILE="${routes}"
  create_routing_shim "${routes}"
  create_gh_shim "fake-token"

  run_script --auth pat --token fake --diff "${csv_file}"

  assert_exit_zero "diff exits 0" "${SCRIPT_EXIT_CODE}"
  assert_contains "diff shows NEEDS TRANSFER" "NEEDS TRANSFER" "${OUTPUT}"
  assert_contains "diff shows NOT FOUND" "NOT FOUND" "${OUTPUT}"
}

test_shellcheck() {
  printf '\n%s=== Shellcheck ===%s\n' "${BOLD}" "${RESET}"

  if ! command -v shellcheck &>/dev/null; then
    log_skip "shellcheck not installed — skipping"
    return
  fi

  local sc_out
  sc_out=$(shellcheck --shell=bash --severity=warning "${MAIN_SCRIPT}" 2>&1) || true

  if [[ -z "${sc_out}" ]]; then
    log_pass "shellcheck: no warnings or errors"
    ((TESTS_PASSED++)) || true
  else
    log_fail "shellcheck found issues:"
    printf '%s\n' "${sc_out}" >&2
    ((TESTS_FAILED++)) || true
    FAILED_NAMES+=("shellcheck clean")
  fi
  ((TESTS_RUN++)) || true

  # Also check install.sh
  local sc_install
  sc_install=$(shellcheck --shell=bash --severity=warning "${REPO_ROOT}/install.sh" 2>&1) || true
  if [[ -z "${sc_install}" ]]; then
    log_pass "shellcheck install.sh: no warnings or errors"
    ((TESTS_PASSED++)) || true
  else
    log_fail "shellcheck install.sh found issues:"
    printf '%s\n' "${sc_install}" >&2
    ((TESTS_FAILED++)) || true
    FAILED_NAMES+=("shellcheck install.sh clean")
  fi
  ((TESTS_RUN++)) || true
}

# ---------------------------------------------------------------------------
# Main test runner
# ---------------------------------------------------------------------------
main() {
  printf '\n%s============================================%s\n' "${BOLD}" "${RESET}"
  printf '%sgh-repo-migrator — Test Suite%s\n' "${BOLD}" "${RESET}"
  printf '%sWritten by h3nryza%s\n' "${CYAN}" "${RESET}"
  printf '%s============================================%s\n\n' "${BOLD}" "${RESET}"

  [[ -f "${MAIN_SCRIPT}" ]] || { printf 'FATAL: main script not found: %s\n' "${MAIN_SCRIPT}"; exit 1; }
  [[ -d "${MOCK_DIR}" ]]   || { printf 'FATAL: mock dir not found: %s\n' "${MOCK_DIR}";       exit 1; }

  setup

  test_cli_basics
  test_arg_validation
  test_dry_run_single
  test_dry_run_no_admin
  test_dry_run_fork
  test_dry_run_repo_not_found
  test_bulk_transfer_dry_run
  test_bulk_malformed_csv
  test_export_org_repos
  test_query_org_repos
  test_output_csv_format
  test_auth_gh_cli
  test_auth_pat_via_env
  test_diff_plan
  test_shellcheck

  printf '\n%s============================================%s\n' "${BOLD}" "${RESET}"
  printf 'Results: %s%d passed%s  %s%d failed%s  %d total\n' \
    "${GREEN}" "${TESTS_PASSED}" "${RESET}" \
    "${RED}"   "${TESTS_FAILED}" "${RESET}" \
    "${TESTS_RUN}"
  if [[ ${#FAILED_NAMES[@]} -gt 0 ]]; then
    printf '\n%sFailed tests:%s\n' "${RED}" "${RESET}"
    for name in "${FAILED_NAMES[@]}"; do
      printf '  - %s\n' "${name}"
    done
  fi
  printf '%s============================================%s\n\n' "${BOLD}" "${RESET}"

  [[ "${TESTS_FAILED}" -eq 0 ]]
}

main "$@"
