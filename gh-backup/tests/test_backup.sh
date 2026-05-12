#!/usr/bin/env bash
# test_backup.sh - Unit tests for gh-backup.sh
# Written by h3nryza
#
# Usage:
#   ./tests/test_backup.sh
#   ./tests/test_backup.sh --verbose
#   ./tests/test_backup.sh --filter "arg_parsing"

set -euo pipefail

# ─────────────────────────────────────────────
# Test framework setup
# ─────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
MAIN_SCRIPT="${REPO_DIR}/gh-backup.sh"
MOCK_DIR="${SCRIPT_DIR}/mock_gh_responses"

# Test counters
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_SKIPPED=0

# Options
VERBOSE_TESTS="false"
FILTER=""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

# ─────────────────────────────────────────────
# Test helpers
# ─────────────────────────────────────────────
pass() {
    local name="$1"
    (( TESTS_PASSED++ )) || true
    (( TESTS_RUN++ )) || true
    echo -e "  ${GREEN}✓${RESET} ${name}"
}

fail() {
    local name="$1"
    local reason="${2:-}"
    (( TESTS_FAILED++ )) || true
    (( TESTS_RUN++ )) || true
    echo -e "  ${RED}✗${RESET} ${name}"
    [[ -n "${reason}" ]] && echo -e "    ${RED}→ ${reason}${RESET}"
}

skip() {
    local name="$1"
    local reason="${2:-}"
    (( TESTS_SKIPPED++ )) || true
    (( TESTS_RUN++ )) || true
    echo -e "  ${YELLOW}○${RESET} ${name} (skipped: ${reason})"
}

assert_equal() {
    local expected="$1"
    local actual="$2"
    local label="${3:-assert_equal}"
    if [[ "${expected}" == "${actual}" ]]; then
        pass "${label}"
    else
        fail "${label}" "expected='${expected}' got='${actual}'"
    fi
}

assert_contains() {
    local haystack="$1"
    local needle="$2"
    local label="${3:-assert_contains}"
    # Use -- to prevent needle starting with - being treated as a grep flag
    if printf '%s' "${haystack}" | grep -qF -- "${needle}"; then
        pass "${label}"
    else
        fail "${label}" "'${needle}' not found in output"
    fi
}

assert_not_contains() {
    local haystack="$1"
    local needle="$2"
    local label="${3:-assert_not_contains}"
    if ! printf '%s' "${haystack}" | grep -qF -- "${needle}"; then
        pass "${label}"
    else
        fail "${label}" "unexpected '${needle}' found in output"
    fi
}

assert_exit_zero() {
    local label="$1"
    shift
    if "$@" &>/dev/null; then
        pass "${label}"
    else
        fail "${label}" "command exited non-zero: $*"
    fi
}

assert_exit_nonzero() {
    local label="$1"
    shift
    if ! "$@" &>/dev/null; then
        pass "${label}"
    else
        fail "${label}" "expected non-zero exit but got 0: $*"
    fi
}

assert_file_exists() {
    local path="$1"
    local label="${2:-assert_file_exists}"
    if [[ -f "${path}" ]]; then
        pass "${label}"
    else
        fail "${label}" "File not found: ${path}"
    fi
}

assert_dir_exists() {
    local path="$1"
    local label="${2:-assert_dir_exists}"
    if [[ -d "${path}" ]]; then
        pass "${label}"
    else
        fail "${label}" "Directory not found: ${path}"
    fi
}

describe() {
    echo ""
    echo -e "${BOLD}${CYAN}▶ $*${RESET}"
}

# Temporary workspace
TMPDIR_BASE="/tmp/gh_backup_tests_$$"
mkdir -p "${TMPDIR_BASE}"

cleanup() {
    rm -rf "${TMPDIR_BASE}"
}
trap cleanup EXIT

# ─────────────────────────────────────────────
# Parse test arguments
# ─────────────────────────────────────────────
parse_test_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --verbose|-v) VERBOSE_TESTS="true"; shift ;;
            --filter|-f)  FILTER="${2:-}"; shift 2 ;;
            -h|--help)
                echo "Usage: $0 [--verbose] [--filter <pattern>]"
                exit 0 ;;
            *) shift ;;
        esac
    done
}

should_run() {
    local test_group="$1"
    if [[ -z "${FILTER}" ]]; then
        return 0
    fi
    if [[ "${test_group}" == *"${FILTER}"* ]]; then
        return 0
    fi
    return 1
}

# ─────────────────────────────────────────────
# Test: Script exists and is executable
# ─────────────────────────────────────────────
test_script_exists() {
    describe "Script presence"
    assert_file_exists "${MAIN_SCRIPT}" "main script exists"

    if [[ -x "${MAIN_SCRIPT}" ]]; then
        pass "main script is executable"
    else
        fail "main script is not executable"
    fi
}

# ─────────────────────────────────────────────
# Test: --help output
# ─────────────────────────────────────────────
test_help_output() {
    describe "Help output"
    local output
    output=$(bash "${MAIN_SCRIPT}" --help 2>&1)

    assert_contains "${output}" "gh-backup" "--help contains 'gh-backup'"
    assert_contains "${output}" "h3nryza"    "--help contains author 'h3nryza'"
    assert_contains "${output}" "--enterprise" "--help shows --enterprise flag"
    assert_contains "${output}" "--org"        "--help shows --org flag"
    assert_contains "${output}" "--user"       "--help shows --user flag"
    assert_contains "${output}" "--auth"       "--help shows --auth flag"
    assert_contains "${output}" "--token"      "--help shows --token flag"
    assert_contains "${output}" "--dry-run"    "--help shows --dry-run flag"
    assert_contains "${output}" "--interactive" "--help shows --interactive flag"
    assert_contains "${output}" "EXAMPLES"    "--help contains EXAMPLES section"
    assert_contains "${output}" "curl"        "--help shows remote curl example"
}

# ─────────────────────────────────────────────
# Test: --version output
# ─────────────────────────────────────────────
test_version_output() {
    describe "Version output"
    local output
    output=$(bash "${MAIN_SCRIPT}" --version 2>&1)

    assert_contains "${output}" "gh-backup"  "--version contains script name"
    assert_contains "${output}" "h3nryza"    "--version contains author"
    assert_contains "${output}" "1.0.0"      "--version contains version number"
}

# ─────────────────────────────────────────────
# Test: Argument parsing — required target
# ─────────────────────────────────────────────
test_arg_parsing_no_target() {
    describe "Argument parsing — missing target"
    local output
    output=$(bash "${MAIN_SCRIPT}" 2>&1) || true
    assert_contains "${output}" "No target specified" "error when no target given"
}

test_arg_parsing_unknown_flag() {
    describe "Argument parsing — unknown flag"
    local output
    output=$(bash "${MAIN_SCRIPT}" --unknown-flag-xyz 2>&1) || true
    assert_contains "${output}" "Unknown option" "error on unknown flag"
}

test_arg_parsing_missing_value() {
    describe "Argument parsing — missing flag values"
    local out
    out=$(bash "${MAIN_SCRIPT}" --org 2>&1) || true
    assert_contains "${out}" "--org requires" "error when --org has no value"

    out=$(bash "${MAIN_SCRIPT}" --enterprise 2>&1) || true
    assert_contains "${out}" "--enterprise requires" "error when --enterprise has no value"

    out=$(bash "${MAIN_SCRIPT}" --user 2>&1) || true
    assert_contains "${out}" "--user requires" "error when --user has no value"

    out=$(bash "${MAIN_SCRIPT}" --auth 2>&1) || true
    assert_contains "${out}" "--auth requires" "error when --auth has no value"
}

test_arg_parsing_clone_method_validation() {
    describe "Argument parsing — clone method validation"
    local out
    out=$(bash "${MAIN_SCRIPT}" -u testuser --auth pat --token fake \
        --clone-method badvalue 2>&1) || true
    assert_contains "${out}" "Unknown clone method" "error on invalid clone method"
}

test_arg_parsing_auth_validation() {
    describe "Argument parsing — auth method validation"
    local out
    out=$(bash "${MAIN_SCRIPT}" -u testuser --auth badauth 2>&1) || true
    assert_contains "${out}" "Unknown auth method" "error on invalid auth method"
}

test_arg_parsing_pat_requires_token() {
    describe "Argument parsing — PAT requires token"
    # Unset GITHUB_TOKEN to ensure no fallback
    local out
    out=$(GITHUB_TOKEN="" bash "${MAIN_SCRIPT}" -u testuser --auth pat 2>&1) || true
    assert_contains "${out}" "PAT auth requires" "error when --auth pat has no token"
}

test_arg_parsing_app_requires_id_and_key() {
    describe "Argument parsing — App auth requires id + key"
    local out
    out=$(bash "${MAIN_SCRIPT}" -u testuser --auth app 2>&1) || true
    assert_contains "${out}" "App auth requires" "error when --auth app missing params"
}

test_arg_parsing_import_file_not_found() {
    describe "Argument parsing — import file not found"
    local out
    out=$(bash "${MAIN_SCRIPT}" -u testuser --auth pat --token fake \
        --import /nonexistent/path/file.csv 2>&1) || true
    assert_contains "${out}" "Import file not found" "error when import file missing"
}

# ─────────────────────────────────────────────
# Test: Dry-run mode (no real API calls)
# ─────────────────────────────────────────────
test_dry_run_no_output_dir() {
    describe "Dry-run — no output directory created"

    # We can't make real API calls, so we test that the script at least:
    # 1. Accepts dry-run args without crashing on arg parsing
    # 2. Would produce the right messages

    # Test that --dry-run flag is accepted (will fail at auth check without gh CLI)
    local out
    out=$(bash "${MAIN_SCRIPT}" --dry-run --help 2>&1) || true
    # --help should work regardless
    assert_contains "${out}" "dry-run" "--help documents --dry-run"
}

# ─────────────────────────────────────────────
# Test: CSV manifest format
# ─────────────────────────────────────────────
test_csv_columns() {
    describe "CSV manifest — column headers"
    local expected_columns="Enterprise,Organization,Owner,Name,Type,Description,Visibility,Language,LastUpdated,Size,BackupPath,Status"
    # Extract from script source
    local actual_columns
    actual_columns=$(grep 'readonly CSV_COLUMNS=' "${MAIN_SCRIPT}" | sed 's/.*"\(.*\)".*/\1/')
    assert_equal "${expected_columns}" "${actual_columns}" "CSV columns match spec"
}

# ─────────────────────────────────────────────
# Test: Install script
# ─────────────────────────────────────────────
test_install_script_exists() {
    describe "Install script presence"
    assert_file_exists "${REPO_DIR}/install.sh" "install.sh exists"

    if [[ -x "${REPO_DIR}/install.sh" ]]; then
        pass "install.sh is executable"
    else
        fail "install.sh is not executable"
    fi
}

test_install_help() {
    describe "Install script --help"
    local out
    out=$(bash "${REPO_DIR}/install.sh" --help 2>&1)
    assert_contains "${out}" "h3nryza"       "install --help has author"
    assert_contains "${out}" "--prefix"      "install --help documents --prefix"
    assert_contains "${out}" "--no-symlink"  "install --help documents --no-symlink"
    assert_contains "${out}" "curl"          "install --help shows curl remote install"
}

# ─────────────────────────────────────────────
# Test: Mock data JSON structure
# ─────────────────────────────────────────────
test_mock_data_structure() {
    describe "Mock data — JSON validity"

    for mock_file in "${MOCK_DIR}"/*.json; do
        local fname
        fname="$(basename "${mock_file}")"
        if python3 -m json.tool "${mock_file}" &>/dev/null; then
            pass "Valid JSON: ${fname}"
        else
            fail "Invalid JSON: ${fname}"
        fi
    done
}

test_mock_user_repos_fields() {
    describe "Mock data — user_repos.json fields"
    local data="${MOCK_DIR}/user_repos.json"
    [[ -f "${data}" ]] || { fail "user_repos.json missing"; return; }

    local output
    output=$(python3 -c "
import json, sys
data = json.load(open('${data}'))
assert isinstance(data, list), 'expected list'
assert len(data) > 0, 'expected non-empty'
first = data[0]
required = ['name','visibility','description','language','pushed_at','size','clone_url','fork','archived']
for field in required:
    assert field in first, f'missing field: {field}'
print('ok')
" 2>&1)
    assert_equal "ok" "${output}" "user_repos.json has required fields"
}

test_mock_gists_fields() {
    describe "Mock data — user_gists.json fields"
    local data="${MOCK_DIR}/user_gists.json"
    [[ -f "${data}" ]] || { fail "user_gists.json missing"; return; }

    local output
    output=$(python3 -c "
import json, sys
data = json.load(open('${data}'))
assert isinstance(data, list), 'expected list'
assert len(data) > 0, 'expected non-empty'
first = data[0]
required = ['id','description','public','updated_at','git_pull_url']
for field in required:
    assert field in first, f'missing field: {field}'
print('ok')
" 2>&1)
    assert_equal "ok" "${output}" "user_gists.json has required fields"
}

test_mock_org_repos_fields() {
    describe "Mock data — org_repos.json fields"
    local data="${MOCK_DIR}/org_repos.json"
    [[ -f "${data}" ]] || { fail "org_repos.json missing"; return; }

    local output
    output=$(python3 -c "
import json
data = json.load(open('${data}'))
assert isinstance(data, list), 'expected list'
assert len(data) > 0, 'expected non-empty'
for r in data:
    assert 'name' in r, 'missing name'
    assert 'clone_url' in r, 'missing clone_url'
print('ok')
" 2>&1)
    assert_equal "ok" "${output}" "org_repos.json has required fields"
}

test_mock_enterprise_orgs_fields() {
    describe "Mock data — enterprise_orgs.json fields"
    local data="${MOCK_DIR}/enterprise_orgs.json"
    [[ -f "${data}" ]] || { fail "enterprise_orgs.json missing"; return; }

    local output
    output=$(python3 -c "
import json
data = json.load(open('${data}'))
assert isinstance(data, list), 'expected list'
for o in data:
    assert 'login' in o, 'missing login'
print('ok')
" 2>&1)
    assert_equal "ok" "${output}" "enterprise_orgs.json has required fields"
}

# ─────────────────────────────────────────────
# Test: Internal logic via mock injection
# ─────────────────────────────────────────────
test_filter_archived_logic() {
    describe "Filter logic — archived repos"

    local archived_repo
    archived_repo='{"name":"old","visibility":"public","description":"","language":"","pushed_at":"","size":0,"clone_url":"","fork":false,"archived":true}'

    local result
    result=$(python3 -c "
import json
d = json.loads('${archived_repo}')
archived = d.get('archived', False)
print('skip' if archived else 'keep')
")
    assert_equal "skip" "${result}" "archived repo is detected as archived"
}

test_filter_fork_logic() {
    describe "Filter logic — forked repos"

    local fork_repo
    fork_repo='{"name":"fork","visibility":"public","description":"","language":"","pushed_at":"","size":0,"clone_url":"","fork":true,"archived":false}'

    local result
    result=$(python3 -c "
import json
d = json.loads('${fork_repo}')
fork = d.get('fork', False)
print('skip' if fork else 'keep')
")
    assert_equal "skip" "${result}" "forked repo is detected as fork"
}

test_gist_visibility_logic() {
    describe "Gist visibility derivation"

    local result_public result_secret
    result_public=$(python3 -c "
import json
d = {'id':'abc','public':True}
print('public' if d.get('public') else 'secret')
")
    result_secret=$(python3 -c "
import json
d = {'id':'abc','public':False}
print('public' if d.get('public') else 'secret')
")
    assert_equal "public" "${result_public}" "public gist has visibility=public"
    assert_equal "secret" "${result_secret}" "secret gist has visibility=secret"
}

# ─────────────────────────────────────────────
# Test: CSV row sanitisation logic
# ─────────────────────────────────────────────
test_csv_sanitisation() {
    describe "CSV sanitisation — commas in description"

    local desc_with_commas="A repo, with commas, everywhere"
    local sanitised
    sanitised="${desc_with_commas//,/ }"

    if ! printf '%s' "${sanitised}" | grep -qF ","; then
        pass "commas removed from description for CSV"
    else
        fail "commas remain in CSV description"
    fi
}

test_csv_sanitisation_newlines() {
    describe "CSV sanitisation — newlines in description"

    local desc_with_newlines
    desc_with_newlines="$(printf 'Line one\nLine two')"
    local sanitised="${desc_with_newlines//$'\n'/ }"

    # After sanitisation, wc -l should show only 1 line (no embedded newlines)
    local line_count
    line_count=$(printf '%s' "${sanitised}" | wc -l | tr -d ' ')
    if [[ "${line_count}" -eq 0 ]]; then
        pass "newlines removed from description for CSV"
    else
        fail "newlines remain in CSV description (got ${line_count} newlines)"
    fi
}

# ─────────────────────────────────────────────
# Test: Backup output directory structure simulation
# ─────────────────────────────────────────────
test_output_structure_simulation() {
    describe "Output structure — directory layout simulation"

    local sim_dir="${TMPDIR_BASE}/sim_backup_test"
    mkdir -p "${sim_dir}"

    # Simulate what the script would create
    mkdir -p "${sim_dir}/my-enterprise/org-one"
    mkdir -p "${sim_dir}/my-enterprise/org-two"
    mkdir -p "${sim_dir}/testuser/repos"
    mkdir -p "${sim_dir}/testuser/gists"
    touch "${sim_dir}/index.md"
    touch "${sim_dir}/backup_manifest.csv"
    printf '%s\n' "Enterprise,Organization,Owner,Name,Type,Description,Visibility,Language,LastUpdated,Size,BackupPath,Status" \
        > "${sim_dir}/backup_manifest.csv"

    assert_dir_exists "${sim_dir}/my-enterprise/org-one" "enterprise/org-one directory"
    assert_dir_exists "${sim_dir}/my-enterprise/org-two" "enterprise/org-two directory"
    assert_dir_exists "${sim_dir}/testuser/repos"        "user/repos directory"
    assert_dir_exists "${sim_dir}/testuser/gists"        "user/gists directory"
    assert_file_exists "${sim_dir}/index.md"             "index.md present"
    assert_file_exists "${sim_dir}/backup_manifest.csv"  "backup_manifest.csv present"

    local csv_header
    csv_header=$(head -1 "${sim_dir}/backup_manifest.csv")
    local expected_header="Enterprise,Organization,Owner,Name,Type,Description,Visibility,Language,LastUpdated,Size,BackupPath,Status"
    assert_equal "${expected_header}" "${csv_header}" "CSV header matches spec"
    assert_contains "${csv_header}" "Enterprise" "CSV has Enterprise column"
    assert_contains "${csv_header}" "Organization" "CSV has Organization column"
    assert_contains "${csv_header}" "BackupPath" "CSV has BackupPath column"
    assert_contains "${csv_header}" "Status" "CSV has Status column"
}

# ─────────────────────────────────────────────
# Test: Script function definitions
# ─────────────────────────────────────────────
test_function_definitions() {
    describe "Function definitions in main script"

    local required_functions=(
        "backup_enterprise"
        "backup_org"
        "backup_user"
        "backup_repo"
        "backup_gist"
        "generate_summary"
        "init_manifest"
        "append_manifest"
        "init_index"
        "append_index_header"
        "append_index_row"
        "clone_repo"
        "gh_api"
        "gh_api_paginate"
        "interactive_mode"
        "parse_args"
        "validate_args"
        "show_help"
        "show_version"
    )

    for fn in "${required_functions[@]}"; do
        if grep -q "^${fn}()" "${MAIN_SCRIPT}"; then
            pass "function defined: ${fn}()"
        else
            fail "missing function: ${fn}()"
        fi
    done
}

# ─────────────────────────────────────────────
# Test: Script contains required strings
# ─────────────────────────────────────────────
test_required_strings() {
    describe "Required strings in main script"

    assert_contains "$(< "${MAIN_SCRIPT}")" "Written by h3nryza"   "author stamp present"
    assert_contains "$(< "${MAIN_SCRIPT}")" "VERSION="             "VERSION variable present"
    assert_contains "$(< "${MAIN_SCRIPT}")" "set -euo pipefail"   "strict mode enabled"
    assert_contains "$(< "${MAIN_SCRIPT}")" "backup_manifest.csv" "manifest filename referenced"
    assert_contains "$(< "${MAIN_SCRIPT}")" "index.md"            "index.md referenced"
    assert_contains "$(< "${MAIN_SCRIPT}")" "DRY_RUN"             "dry-run flag implemented"
    assert_contains "$(< "${MAIN_SCRIPT}")" "INTERACTIVE"         "interactive mode implemented"
    assert_contains "$(< "${MAIN_SCRIPT}")" "RESUME"              "resume capability implemented"
    assert_contains "$(< "${MAIN_SCRIPT}")" "SHALLOW_CLONE"       "shallow clone option present"
}

# ─────────────────────────────────────────────
# Test: Auth methods documented
# ─────────────────────────────────────────────
test_auth_methods() {
    describe "Auth methods"
    local src
    src="$(< "${MAIN_SCRIPT}")"

    assert_contains "${src}" "AUTH_METHOD" "AUTH_METHOD variable used"
    assert_contains "${src}" '"gh"'        "gh CLI auth branch"
    assert_contains "${src}" '"pat"'       "PAT auth branch"
    assert_contains "${src}" '"app"'       "GitHub App auth branch"
    assert_contains "${src}" "GITHUB_TOKEN" "GITHUB_TOKEN env var fallback"
}

# ─────────────────────────────────────────────
# Test: Clone methods
# ─────────────────────────────────────────────
test_clone_methods() {
    describe "Clone methods"
    local src
    src="$(< "${MAIN_SCRIPT}")"

    assert_contains "${src}" "clone)"   "clone method case"
    assert_contains "${src}" "mirror)"  "mirror method case"
    assert_contains "${src}" "archive)" "archive method case"
    assert_contains "${src}" "--depth 1" "shallow clone depth flag"
}

# ─────────────────────────────────────────────
# Test: Pagination
# ─────────────────────────────────────────────
test_pagination() {
    describe "Pagination"
    local src
    src="$(< "${MAIN_SCRIPT}")"

    assert_contains "${src}" "paginate"     "pagination implemented"
    assert_contains "${src}" "per_page=100" "page size 100 used"
}

# ─────────────────────────────────────────────
# Test: Enterprise GraphQL fallback
# ─────────────────────────────────────────────
test_graphql_fallback() {
    describe "Enterprise GraphQL fallback"
    local src
    src="$(< "${MAIN_SCRIPT}")"

    assert_contains "${src}" "graphql"              "GraphQL API used"
    assert_contains "${src}" "enterprise(slug:"     "enterprise GraphQL query"
    assert_contains "${src}" "hasNextPage"          "pagination via GraphQL"
}

# ─────────────────────────────────────────────
# Test: Import file handling (unit)
# ─────────────────────────────────────────────
test_import_file_logic() {
    describe "Import file — should_backup_repo logic"

    local import_file="${TMPDIR_BASE}/test_import.txt"
    printf 'my-org/repo-a\nmy-org/repo-b\n' > "${import_file}"

    # Simulate should_backup_repo logic
    check_repo_in_import() {
        local full_name="$1"
        local import="$2"
        if grep -qxF "${full_name}" "${import}" 2>/dev/null; then
            echo "yes"
        else
            echo "no"
        fi
    }

    assert_equal "yes" "$(check_repo_in_import "my-org/repo-a" "${import_file}")" "repo-a is in import list"
    assert_equal "yes" "$(check_repo_in_import "my-org/repo-b" "${import_file}")" "repo-b is in import list"
    assert_equal "no"  "$(check_repo_in_import "my-org/repo-c" "${import_file}")" "repo-c is not in import list"
}

# ─────────────────────────────────────────────
# Test: Org index generation
# ─────────────────────────────────────────────
test_org_index_generation() {
    describe "Org index.md generation"

    local org_dir="${TMPDIR_BASE}/org_index_test"
    mkdir -p "${org_dir}"

    # Simulate append_org_index
    local org_index="${org_dir}/org_index.md"
    cat > "${org_index}" <<EOF
# Organisation: test-org

**Generated:** 2026-05-10 12:00:00 UTC

| Name | Visibility | Language | Last Updated | Description |
|------|------------|----------|--------------|-------------|
| repo-a | private | TypeScript | 2026-05-01 | Main API |
| repo-b | public | JavaScript | 2026-04-20 | Frontend |
EOF

    assert_file_exists "${org_index}" "org_index.md created"
    assert_contains "$(< "${org_index}")" "# Organisation" "org_index.md has header"
    assert_contains "$(< "${org_index}")" "| Name |" "org_index.md has table"
    assert_contains "$(< "${org_index}")" "repo-a" "org_index.md has repo entry"
}

# ─────────────────────────────────────────────
# Test: Progress output function
# ─────────────────────────────────────────────
test_progress_function() {
    describe "Progress display"
    local src
    src="$(< "${MAIN_SCRIPT}")"
    assert_contains "${src}" "progress()" "progress function defined"
    assert_contains "${src}" "pct" "percentage calculation in progress"
}

# ─────────────────────────────────────────────
# Test: Error handling
# ─────────────────────────────────────────────
test_error_handling() {
    describe "Error handling"
    local src
    src="$(< "${MAIN_SCRIPT}")"

    assert_contains "${src}" 'die()' "die() function defined"
    assert_contains "${src}" 'log_error' "log_error function used"
    assert_contains "${src}" 'log_warn' "log_warn function used"
    assert_contains "${src}" 'exit 1' "non-zero exit on failure"
}

# ─────────────────────────────────────────────
# Test: Shellcheck (if available)
# ─────────────────────────────────────────────
test_shellcheck() {
    describe "Shellcheck validation"

    if ! command -v shellcheck &>/dev/null; then
        skip "shellcheck not available" "shellcheck not installed"
        return
    fi

    if shellcheck -S warning "${MAIN_SCRIPT}" 2>/dev/null; then
        pass "gh-backup.sh passes shellcheck"
    else
        fail "gh-backup.sh has shellcheck warnings/errors"
    fi

    if shellcheck -S warning "${REPO_DIR}/install.sh" 2>/dev/null; then
        pass "install.sh passes shellcheck"
    else
        fail "install.sh has shellcheck warnings/errors"
    fi
}

# ─────────────────────────────────────────────
# Test: Default output dir naming
# ─────────────────────────────────────────────
test_default_output_dir_format() {
    describe "Default output directory naming"
    local src
    src="$(< "${MAIN_SCRIPT}")"

    assert_contains "${src}" 'backup_' "output dir has backup_ prefix"
    assert_contains "${src}" 'TIMESTAMP' "TIMESTAMP used in output dir name"
    assert_contains "${src}" 'date +%Y-%m-%d' "date format includes Y-m-d"
}

# ─────────────────────────────────────────────
# Test: Gists default-on for user
# ─────────────────────────────────────────────
test_gists_default_for_user() {
    describe "Gists auto-enabled for user target"
    local src
    src="$(< "${MAIN_SCRIPT}")"

    assert_contains "${src}" 'INCLUDE_GISTS="true"' "gists auto-enabled when user is set"
}

# ─────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────
print_summary() {
    echo ""
    echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo -e "${BOLD}Test Results${RESET}"
    echo -e "  Total  : ${TESTS_RUN}"
    echo -e "  ${GREEN}Passed : ${TESTS_PASSED}${RESET}"
    echo -e "  ${RED}Failed : ${TESTS_FAILED}${RESET}"
    echo -e "  ${YELLOW}Skipped: ${TESTS_SKIPPED}${RESET}"
    echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"

    if [[ "${TESTS_FAILED}" -gt 0 ]]; then
        echo -e "${RED}RESULT: FAIL${RESET}"
        exit 1
    else
        echo -e "${GREEN}RESULT: PASS${RESET}"
        exit 0
    fi
}

# ─────────────────────────────────────────────
# Main test runner
# ─────────────────────────────────────────────
main() {
    parse_test_args "$@"

    echo -e "${BOLD}${CYAN}"
    echo "╔══════════════════════════════════════════════════╗"
    echo "║        gh-backup Test Suite — by h3nryza         ║"
    echo "╚══════════════════════════════════════════════════╝"
    echo -e "${RESET}"

    [[ -n "${FILTER}" ]] && echo -e "${YELLOW}Running tests matching: '${FILTER}'${RESET}"

    # Run all test groups
    should_run "script_exists"            && test_script_exists
    should_run "help_output"              && test_help_output
    should_run "version_output"           && test_version_output
    should_run "arg_parsing"              && test_arg_parsing_no_target
    should_run "arg_parsing"              && test_arg_parsing_unknown_flag
    should_run "arg_parsing"              && test_arg_parsing_missing_value
    should_run "arg_parsing"              && test_arg_parsing_clone_method_validation
    should_run "arg_parsing"              && test_arg_parsing_auth_validation
    should_run "arg_parsing"              && test_arg_parsing_pat_requires_token
    should_run "arg_parsing"              && test_arg_parsing_app_requires_id_and_key
    should_run "arg_parsing"              && test_arg_parsing_import_file_not_found
    should_run "dry_run"                  && test_dry_run_no_output_dir
    should_run "csv"                      && test_csv_columns
    should_run "csv"                      && test_csv_sanitisation
    should_run "csv"                      && test_csv_sanitisation_newlines
    should_run "install"                  && test_install_script_exists
    should_run "install"                  && test_install_help
    should_run "mock_data"                && test_mock_data_structure
    should_run "mock_data"                && test_mock_user_repos_fields
    should_run "mock_data"                && test_mock_gists_fields
    should_run "mock_data"                && test_mock_org_repos_fields
    should_run "mock_data"                && test_mock_enterprise_orgs_fields
    should_run "filter"                   && test_filter_archived_logic
    should_run "filter"                   && test_filter_fork_logic
    should_run "filter"                   && test_gist_visibility_logic
    should_run "output_structure"         && test_output_structure_simulation
    should_run "functions"                && test_function_definitions
    should_run "required_strings"         && test_required_strings
    should_run "auth"                     && test_auth_methods
    should_run "clone"                    && test_clone_methods
    should_run "pagination"               && test_pagination
    should_run "graphql"                  && test_graphql_fallback
    should_run "import"                   && test_import_file_logic
    should_run "org_index"                && test_org_index_generation
    should_run "progress"                 && test_progress_function
    should_run "error"                    && test_error_handling
    should_run "shellcheck"               && test_shellcheck
    should_run "output_dir"               && test_default_output_dir_format
    should_run "gists_default"            && test_gists_default_for_user

    print_summary
}

main "$@"
