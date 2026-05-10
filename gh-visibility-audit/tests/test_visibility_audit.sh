#!/usr/bin/env bash
# =============================================================================
# test_visibility_audit.sh — Unit tests for gh-visibility-audit.sh
# Written by h3nryza
# =============================================================================
# Run from the project root:
#   bash tests/test_visibility_audit.sh
#
# Or with verbose output:
#   VERBOSE=true bash tests/test_visibility_audit.sh
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
MAIN_SCRIPT="${PROJECT_DIR}/gh-visibility-audit.sh"
MOCK_DIR="${SCRIPT_DIR}/mock_gh_responses"

# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0
FAILED_TESTS=()

# Colour helpers
if [[ -t 1 ]]; then
  RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
  CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
else
  RED=''; YELLOW=''; GREEN=''; CYAN=''; BOLD=''; RESET=''
fi

# Temporary directory cleaned up on exit
TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "${TMPDIR_TEST}"' EXIT

pass() { printf "${GREEN}  PASS${RESET} %s\n" "$1"; (( TESTS_PASSED++ )) || true; }
fail() {
  printf "${RED}  FAIL${RESET} %s\n" "$1"
  [[ -n "${2:-}" ]] && printf "       Expected: %s\n" "$2"
  [[ -n "${3:-}" ]] && printf "       Got:      %s\n" "$3"
  (( TESTS_FAILED++ )) || true
  FAILED_TESTS+=("$1")
}

run_test() {
  local name="$1"
  (( TESTS_RUN++ )) || true
  printf "${CYAN}TEST${RESET} %s\n" "${name}"
}

assert_eq() {
  local name="$1" expected="$2" actual="$3"
  if [[ "${expected}" == "${actual}" ]]; then
    pass "${name}"
  else
    fail "${name}" "${expected}" "${actual}"
  fi
}

assert_contains() {
  local name="$1" needle="$2" haystack="$3"
  # Use bash pattern matching to avoid BSD grep treating '--foo' as a flag
  if [[ "${haystack}" == *"${needle}"* ]]; then
    pass "${name}"
  else
    fail "${name}" "to contain '${needle}'" "${haystack:0:120}…"
  fi
}

assert_not_contains() {
  local name="$1" needle="$2" haystack="$3"
  if [[ "${haystack}" != *"${needle}"* ]]; then
    pass "${name}"
  else
    fail "${name}" "NOT to contain '${needle}'" "${haystack:0:120}…"
  fi
}

assert_file_exists() {
  local name="$1" file="$2"
  if [[ -f "${file}" ]]; then
    pass "${name}"
  else
    fail "${name}" "file to exist" "${file}"
  fi
}

assert_file_not_empty() {
  local name="$1" file="$2"
  if [[ -s "${file}" ]]; then
    pass "${name}"
  else
    fail "${name}" "file to be non-empty" "${file}"
  fi
}

assert_exit_code() {
  local name="$1" expected_code="$2"
  shift 2
  local actual_code=0
  "$@" >/dev/null 2>&1 || actual_code=$?
  assert_eq "${name}" "${expected_code}" "${actual_code}"
}

# ---------------------------------------------------------------------------
# Source the main script in a controlled way for unit testing internal fns
# ---------------------------------------------------------------------------
# We source the script at the TOP LEVEL (not inside a function) so that
# `declare` statements create globals, not function-scoped locals.
# Transforms applied by sed:
#   1. readonly → declare  (avoid "already readonly" errors)
#   2. Remove set -euo pipefail  (test harness controls errexit)
#   3. Disable the final main "$@" call
# shellcheck disable=SC1090
source <(sed \
  -e 's/^readonly /declare /g' \
  -e '/^set -euo pipefail/d' \
  -e 's/^main "\$@"$/: # main disabled for testing/' \
  "${MAIN_SCRIPT}")

# load_script_functions resets mutable globals between tests
load_script_functions() {
  AUTH_METHOD="gh"
  PAT_TOKEN=""
  APP_ID=""
  APP_KEY_FILE=""
  ENTERPRISE=""
  ORG=""
  USER_TARGET=""
  OUTPUT_FILE="/tmp/test_out.csv"
  IMPORT_FILE=""
  DRY_RUN=false
  INTERACTIVE=false
  VERBOSE=false
  MODE="audit"
  CSV_ROWS=()
}

# ---------------------------------------------------------------------------
# SECTION 1: Script basics
# ---------------------------------------------------------------------------
section_basics() {
  printf "\n${BOLD}=== Section 1: Script basics ===${RESET}\n"

  run_test "Script file exists"
  assert_file_exists "Script file exists" "${MAIN_SCRIPT}"

  run_test "Script is executable (or can be made so)"
  bash -n "${MAIN_SCRIPT}" 2>/dev/null && pass "Script is syntactically valid" || fail "Script is syntactically valid" "no syntax errors" "syntax errors found"

  run_test "--help exits 0"
  assert_exit_code "--help exits 0" 0 bash "${MAIN_SCRIPT}" --help

  run_test "--version exits 0"
  assert_exit_code "--version exits 0" 0 bash "${MAIN_SCRIPT}" --version

  run_test "--help contains USAGE"
  local help_out
  help_out="$(bash "${MAIN_SCRIPT}" --help 2>&1)"
  assert_contains "--help contains USAGE"          "USAGE:"          "${help_out}"
  assert_contains "--help contains EXAMPLES"       "EXAMPLES:"       "${help_out}"
  assert_contains "--help contains REMOTE EXEC"    "REMOTE EXECUTION:" "${help_out}"
  assert_contains "--help contains h3nryza"        "h3nryza"         "${help_out}"
  assert_contains "--help contains --interactive"  "--interactive"   "${help_out}"
  assert_contains "--help contains --import"       "--import"        "${help_out}"
  assert_contains "--help contains --dry-run"      "--dry-run"       "${help_out}"

  run_test "--version contains h3nryza"
  local ver_out
  ver_out="$(bash "${MAIN_SCRIPT}" --version 2>&1)"
  assert_contains "--version contains h3nryza" "h3nryza" "${ver_out}"
  assert_contains "--version contains version"  "1.0.0"   "${ver_out}"

  run_test "Unknown flag exits non-zero"
  local exit_code=0
  bash "${MAIN_SCRIPT}" --not-a-real-flag >/dev/null 2>&1 || exit_code=$?
  [[ "${exit_code}" -ne 0 ]] \
    && pass "Unknown flag exits non-zero" \
    || fail "Unknown flag exits non-zero" "non-zero exit" "0"
}

# ---------------------------------------------------------------------------
# SECTION 2: CSV helpers (unit tests via sourcing)
# ---------------------------------------------------------------------------
section_csv_helpers() {
  printf "\n${BOLD}=== Section 2: CSV helpers ===${RESET}\n"

  load_script_functions

  run_test "csv_escape: plain string"
  local result
  result="$(csv_escape "hello")"
  assert_eq "csv_escape plain" '"hello"' "${result}"

  run_test "csv_escape: string with double-quote"
  result="$(csv_escape 'say "hi"')"
  assert_eq "csv_escape with quote" '"say ""hi"""' "${result}"

  run_test "csv_escape: empty string"
  result="$(csv_escape "")"
  assert_eq "csv_escape empty" '""' "${result}"

  run_test "add_csv_row builds row correctly"
  CSV_ROWS=()
  add_csv_row "myent" "myorg" "myowner" "myrepo" "private" "https://github.com/myowner/myrepo"
  assert_eq "add_csv_row count" 1 "${#CSV_ROWS[@]}"
  assert_contains "add_csv_row contains org"   '"myorg"'    "${CSV_ROWS[0]}"
  assert_contains "add_csv_row contains repo"  '"myrepo"'   "${CSV_ROWS[0]}"
  assert_contains "add_csv_row contains vis"   '"private"'  "${CSV_ROWS[0]}"

  run_test "write_csv creates file with header"
  CSV_ROWS=()
  add_csv_row "e" "o" "owner" "repo1" "public" "https://github.com/owner/repo1"
  local csv_file="${TMPDIR_TEST}/test_write.csv"
  write_csv "${csv_file}" >/dev/null 2>&1
  assert_file_exists  "write_csv creates file"      "${csv_file}"
  assert_file_not_empty "write_csv file non-empty"  "${csv_file}"
  local first_line
  first_line="$(head -1 "${csv_file}")"
  assert_eq "write_csv header row" "Enterprise,Organization,Owner,Repository,Visibility,URL" "${first_line}"
}

# ---------------------------------------------------------------------------
# SECTION 3: _process_repos (unit test via mock JSON)
# ---------------------------------------------------------------------------
section_process_repos() {
  printf "\n${BOLD}=== Section 3: _process_repos with mock data ===${RESET}\n"

  load_script_functions

  run_test "_process_repos: org repos"
  CSV_ROWS=()
  local repos_json
  repos_json="$(cat "${MOCK_DIR}/org_repos.json")"
  _process_repos "" "test-org" "${repos_json}"

  assert_eq "_process_repos: correct row count" 3 "${#CSV_ROWS[@]}"

  local row0="${CSV_ROWS[0]}" row1="${CSV_ROWS[1]}" row2="${CSV_ROWS[2]}"
  assert_contains "_process_repos row0 name"   '"alpha-service"' "${row0}"
  assert_contains "_process_repos row0 vis"    '"private"'       "${row0}"
  assert_contains "_process_repos row1 name"   '"beta-lib"'      "${row1}"
  assert_contains "_process_repos row1 vis"    '"public"'        "${row1}"
  assert_contains "_process_repos row2 name"   '"gamma-internal"' "${row2}"
  assert_contains "_process_repos row2 vis"    '"internal"'      "${row2}"

  run_test "_process_repos: user repos"
  CSV_ROWS=()
  local user_json
  user_json="$(cat "${MOCK_DIR}/user_repos.json")"
  _process_repos "" "" "${user_json}"
  assert_eq "_process_repos user: correct row count" 2 "${#CSV_ROWS[@]}"
  assert_contains "_process_repos user row0 name" '"my-public-tool"'  "${CSV_ROWS[0]}"
  assert_contains "_process_repos user row1 name" '"secret-project"'  "${CSV_ROWS[1]}"

  run_test "_process_repos: empty array"
  CSV_ROWS=()
  _process_repos "" "empty-org" "[]"
  assert_eq "_process_repos empty: no rows" 0 "${#CSV_ROWS[@]}"
}

# ---------------------------------------------------------------------------
# SECTION 4: import_csv / update_visibility (dry-run)
# ---------------------------------------------------------------------------
section_import_csv() {
  printf "\n${BOLD}=== Section 4: import_csv (dry-run, no real API calls) ===${RESET}\n"

  load_script_functions

  # Create a test CSV
  local test_csv="${TMPDIR_TEST}/import_test.csv"
  cat > "${test_csv}" <<'CSV'
Enterprise,Organization,Owner,Repository,Visibility,URL
"","test-org","test-org","alpha-service","private","https://github.com/test-org/alpha-service"
"","test-org","test-org","beta-lib","public","https://github.com/test-org/beta-lib"
CSV

  # Override update_visibility so it doesn't call gh/curl
  update_visibility() {
    MOCK_UPDATE_CALLS+=("$1/$2=$3")
  }
  MOCK_UPDATE_CALLS=()
  DRY_RUN=false
  AUTH_METHOD="gh"

  run_test "import_csv: calls update_visibility for each data row"
  import_csv "${test_csv}" >/dev/null 2>&1 || true
  assert_eq "import_csv: 2 update calls" 2 "${#MOCK_UPDATE_CALLS[@]}"
  assert_eq "import_csv: call 1 correct" "test-org/alpha-service=private" "${MOCK_UPDATE_CALLS[0]}"
  assert_eq "import_csv: call 2 correct" "test-org/beta-lib=public"       "${MOCK_UPDATE_CALLS[1]}"

  run_test "import_csv: dry-run mode skips updates"
  MOCK_UPDATE_CALLS=()

  # Override update_visibility to track dry-run calls
  update_visibility() {
    [[ "${DRY_RUN}" == true ]] && MOCK_UPDATE_CALLS+=("DRY:$1/$2=$3") || MOCK_UPDATE_CALLS+=("REAL:$1/$2=$3")
  }
  DRY_RUN=true
  import_csv "${test_csv}" >/dev/null 2>&1 || true
  assert_contains "dry-run: calls are tagged DRY" "DRY:" "${MOCK_UPDATE_CALLS[0]}"

  run_test "import_csv: missing file exits with error"
  local missing_exit=0
  # Run in subshell so die()/exit does not kill the test runner
  ( import_csv "/nonexistent/path/file.csv" >/dev/null 2>&1 ) || missing_exit=$?
  [[ "${missing_exit}" -ne 0 ]] \
    && pass "import_csv missing file exits non-zero" \
    || fail "import_csv missing file exits non-zero" "non-zero" "0"
}

# ---------------------------------------------------------------------------
# SECTION 5: update_visibility validation
# ---------------------------------------------------------------------------
section_update_visibility() {
  printf "\n${BOLD}=== Section 5: update_visibility validation ===${RESET}\n"

  load_script_functions

  # Restore the real update_visibility (section 4 may have overridden it with a mock)
  # Re-source just the update_visibility function by re-running load_script_functions
  # which re-declares all functions freshly.
  # (load_script_functions no longer re-sources; re-define manually)
  # We use a helper subshell that has the real function sourced fresh.

  run_test "update_visibility: invalid visibility is skipped"
  local warn_output
  warn_output="$(bash -c '
    source <(sed \
      -e "s/^readonly /declare /g" \
      -e "/^set -euo pipefail/d" \
      -e "s/^main \"\\\$@\"\$/: # main disabled/" \
      "/Users/henry/repos/personal/h3nryza/gh_scripts/gh-visibility-audit/gh-visibility-audit.sh")
    DRY_RUN=false; AUTH_METHOD="gh"
    gh() { echo "mocked"; }
    update_visibility "myorg" "myrepo" "invalid-vis" 2>&1 || true
  ')"
  assert_contains "update_visibility: warns on invalid vis" "Invalid visibility" "${warn_output}"

  run_test "update_visibility: dry-run does not call API"
  local drrun_out
  drrun_out="$(bash -c '
    source <(sed \
      -e "s/^readonly /declare /g" \
      -e "/^set -euo pipefail/d" \
      -e "s/^main \"\\\$@\"\$/: # main disabled/" \
      "/Users/henry/repos/personal/h3nryza/gh_scripts/gh-visibility-audit/gh-visibility-audit.sh")
    DRY_RUN=true; AUTH_METHOD="pat"; PAT_TOKEN="fake"
    curl() { echo "CURL_WAS_CALLED"; }
    update_visibility "myorg" "myrepo" "private" 2>&1 || true
  ')"
  if [[ "${drrun_out}" != *"CURL_WAS_CALLED"* ]]; then
    pass "update_visibility dry-run: no curl call"
  else
    fail "update_visibility dry-run: no curl call" "no curl called" "curl was called"
  fi
}

# ---------------------------------------------------------------------------
# SECTION 6: CLI argument parsing
# validate_inputs uses die() which calls exit.
# We override die() temporarily to return non-zero instead of exiting,
# so failures don't kill the test runner.
# ---------------------------------------------------------------------------
section_arg_parsing() {
  printf "\n${BOLD}=== Section 6: CLI argument parsing ===${RESET}\n"

  # Each validate_inputs call runs in a fresh bash subshell so die()->exit 1
  # doesn't kill the test runner. We source the main script inside each subshell.
  local SCRIPT="${MAIN_SCRIPT}"

  _vi_subshell() {
    # Args: AUTH_METHOD PAT_TOKEN ENTERPRISE ORG USER_TARGET
    bash -c "
      source <(sed \
        -e 's/^readonly /declare /g' \
        -e '/^set -euo pipefail/d' \
        -e 's/^main \"\\\$@\"\$/: # disabled/' \
        '${SCRIPT}')
      AUTH_METHOD='$1'; PAT_TOKEN='$2'
      ENTERPRISE='$3'; ORG='$4'; USER_TARGET='$5'
      MODE='audit'; IMPORT_FILE=''
      validate_inputs
    " 2>/dev/null
  }

  local ec

  run_test "validate_inputs: no target fails"
  ec=0; _vi_subshell "pat" "tok" "" "" "" || ec=$?
  [[ "${ec}" -ne 0 ]] \
    && pass "validate_inputs: no target fails" \
    || fail "validate_inputs: no target fails" "non-zero exit" "0"

  run_test "validate_inputs: two targets fails"
  ec=0; _vi_subshell "pat" "tok" "ent" "org" "" || ec=$?
  [[ "${ec}" -ne 0 ]] \
    && pass "validate_inputs: two targets fails" \
    || fail "validate_inputs: two targets fails" "non-zero exit" "0"

  run_test "validate_inputs: pat without token fails"
  ec=0; _vi_subshell "pat" "" "" "myorg" "" || ec=$?
  [[ "${ec}" -ne 0 ]] \
    && pass "validate_inputs: pat without token fails" \
    || fail "validate_inputs: pat without token fails" "non-zero exit" "0"

  run_test "validate_inputs: app without app-id fails"
  ec=0; _vi_subshell "app" "" "" "myorg" "" || ec=$?
  [[ "${ec}" -ne 0 ]] \
    && pass "validate_inputs: app without app-id fails" \
    || fail "validate_inputs: app without app-id fails" "non-zero exit" "0"

  load_script_functions
}

# ---------------------------------------------------------------------------
# SECTION 7: Integration-style — audit_org writes CSV
# ---------------------------------------------------------------------------
section_integration_audit_org() {
  printf "\n${BOLD}=== Section 7: Integration — audit_org writes CSV ===${RESET}\n"

  load_script_functions

  # Stub api_get_all to return mock data
  api_get_all() {
    cat "${MOCK_DIR}/org_repos.json"
  }

  local out_csv="${TMPDIR_TEST}/integration_org.csv"
  CSV_ROWS=()
  OUTPUT_FILE="${out_csv}"

  run_test "audit_org + write_csv: file is created"
  audit_org "test-org" "" >/dev/null 2>&1
  write_csv "${out_csv}" >/dev/null 2>&1
  assert_file_exists "integration CSV exists" "${out_csv}"

  run_test "audit_org + write_csv: header present"
  local hdr
  hdr="$(head -1 "${out_csv}")"
  assert_eq "integration CSV header" "Enterprise,Organization,Owner,Repository,Visibility,URL" "${hdr}"

  run_test "audit_org + write_csv: correct row count (3 repos + 1 header)"
  local line_count
  line_count="$(wc -l < "${out_csv}" | tr -d ' ')"
  assert_eq "integration CSV line count" "4" "${line_count}"

  run_test "audit_org + write_csv: alpha-service in CSV"
  assert_contains "alpha-service in CSV" "alpha-service" "$(cat "${out_csv}")"

  run_test "audit_org + write_csv: internal repo in CSV"
  assert_contains "internal visibility in CSV" "internal" "$(cat "${out_csv}")"
}

# ---------------------------------------------------------------------------
# SECTION 8: Integration-style — audit_user writes CSV
# ---------------------------------------------------------------------------
section_integration_audit_user() {
  printf "\n${BOLD}=== Section 8: Integration — audit_user writes CSV ===${RESET}\n"

  load_script_functions

  api_get_all() {
    cat "${MOCK_DIR}/user_repos.json"
  }

  local out_csv="${TMPDIR_TEST}/integration_user.csv"
  CSV_ROWS=()
  OUTPUT_FILE="${out_csv}"

  audit_user "octocat" >/dev/null 2>&1
  write_csv "${out_csv}" >/dev/null 2>&1

  run_test "user audit: CSV exists"
  assert_file_exists "user CSV exists" "${out_csv}"

  run_test "user audit: 2 repos"
  local line_count
  line_count="$(wc -l < "${out_csv}" | tr -d ' ')"
  assert_eq "user CSV line count" "3" "${line_count}"

  run_test "user audit: my-public-tool in CSV"
  assert_contains "my-public-tool in CSV" "my-public-tool" "$(cat "${out_csv}")"
}

# ---------------------------------------------------------------------------
# SECTION 9: Integration-style — audit_enterprise
# ---------------------------------------------------------------------------
section_integration_audit_enterprise() {
  printf "\n${BOLD}=== Section 9: Integration — audit_enterprise ===${RESET}\n"

  load_script_functions

  # api_get_all dispatches based on the URL argument:
  # - enterprise org list calls → enterprise_orgs.json
  # - org repo list calls       → org_repos.json
  api_get_all() {
    local endpoint="$1"
    if [[ "${endpoint}" == */organizations* ]]; then
      cat "${MOCK_DIR}/enterprise_orgs.json"
    else
      cat "${MOCK_DIR}/org_repos.json"
    fi
  }

  local out_csv="${TMPDIR_TEST}/integration_enterprise.csv"
  CSV_ROWS=()
  OUTPUT_FILE="${out_csv}"

  audit_enterprise "test-ent" >/dev/null 2>&1
  write_csv "${out_csv}" >/dev/null 2>&1

  run_test "enterprise audit: CSV exists"
  assert_file_exists "enterprise CSV exists" "${out_csv}"

  run_test "enterprise audit: alpha-service in CSV"
  assert_contains "alpha-service in enterprise CSV" "alpha-service" "$(cat "${out_csv}")"

  run_test "enterprise audit: enterprise column populated"
  assert_contains "enterprise column in CSV" "test-ent" "$(cat "${out_csv}")"
}

# ---------------------------------------------------------------------------
# SECTION 10: Edge cases
# ---------------------------------------------------------------------------
section_edge_cases() {
  printf "\n${BOLD}=== Section 10: Edge cases ===${RESET}\n"

  load_script_functions

  run_test "csv_escape: commas in value are quoted"
  local result
  result="$(csv_escape "one,two,three")"
  assert_eq "csv_escape commas" '"one,two,three"' "${result}"

  run_test "csv_escape: newline in value"
  result="$(csv_escape $'line1\nline2')"
  assert_contains "csv_escape newline" "line1" "${result}"

  run_test "Empty CSV_ROWS: write_csv still writes header"
  load_script_functions
  CSV_ROWS=()
  local empty_csv="${TMPDIR_TEST}/empty.csv"
  write_csv "${empty_csv}" >/dev/null 2>&1
  assert_file_exists "empty CSV exists"       "${empty_csv}"
  local first_line
  first_line="$(head -1 "${empty_csv}")"
  assert_eq "empty CSV header" "Enterprise,Organization,Owner,Repository,Visibility,URL" "${first_line}"
  local line_count
  line_count="$(wc -l < "${empty_csv}" | tr -d ' ')"
  assert_eq "empty CSV exactly 1 line" "1" "${line_count}"
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print_summary() {
  printf "\n${BOLD}======================================${RESET}\n"
  printf "${BOLD}Test Summary${RESET}\n"
  printf "  Total  : %d\n" "${TESTS_RUN}"
  printf "${GREEN}  Passed : %d${RESET}\n" "${TESTS_PASSED}"
  if (( TESTS_FAILED > 0 )); then
    printf "${RED}  Failed : %d${RESET}\n" "${TESTS_FAILED}"
    printf "\nFailed tests:\n"
    for t in "${FAILED_TESTS[@]}"; do
      printf "${RED}  - %s${RESET}\n" "${t}"
    done
  else
    printf "${GREEN}  Failed : 0${RESET}\n"
  fi
  printf "${BOLD}======================================${RESET}\n\n"
}

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
main() {
  printf "\n${BOLD}gh-visibility-audit — Test Suite${RESET}\n"
  printf "Written by h3nryza\n"
  printf "Script: %s\n" "${MAIN_SCRIPT}"
  printf "Mocks:  %s\n\n" "${MOCK_DIR}"

  section_basics
  section_csv_helpers
  section_process_repos
  section_import_csv
  section_update_visibility
  section_arg_parsing
  section_integration_audit_org
  section_integration_audit_user
  section_integration_audit_enterprise
  section_edge_cases

  print_summary

  (( TESTS_FAILED == 0 ))  # exit 0 on success, 1 on failure
}

main "$@"
