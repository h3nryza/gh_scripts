# gh-best-practices-audit — Usage Guide

Written by h3nryza

---

## Table of Contents

1. [Overview](#overview)
2. [Installation](#installation)
3. [Authentication](#authentication)
4. [Targets](#targets)
5. [Benchmark Selection](#benchmark-selection)
6. [Severity and Category Filtering](#severity-and-category-filtering)
7. [Custom Rules](#custom-rules)
8. [Output Formats](#output-formats)
9. [Interactive Mode](#interactive-mode)
10. [AWS Lambda Deployment](#aws-lambda-deployment)
11. [Rule Reference](#rule-reference)
12. [Examples](#examples)
13. [Troubleshooting](#troubleshooting)

---

## Overview

`gh-best-practices-audit` performs a comprehensive automated audit of GitHub Enterprise, Organization, and Repository settings against three industry security benchmarks:

| Benchmark | Rules | Scope |
|-----------|-------|-------|
| CIS GitHub Benchmark | 39 | Enterprise, Org, Repo |
| OWASP CI/CD Top 10 | 24 | Repo (branch protection, CI/CD) |
| SANS Top 25 | 16 | Repo (secrets, dependencies, access) |

For every rule the tool checks, it reports one of four statuses:

| Status | Meaning |
|--------|---------|
| `PASS` | The setting matches the expected value |
| `FAIL` | The setting does not match — remediation required |
| `SKIP` | The check was skipped (insufficient permissions or feature not enabled) |
| `ERROR` | An unexpected error occurred during the check |

At the end of each run a scorecard is printed to stdout. Results are also saved to a file (CSV, JSON, or HTML).

---

## Installation

### Remote (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-best-practices-audit/install.sh | bash
```

This downloads all scripts and rules files, creates a Python virtual environment, installs dependencies, and places a wrapper on your `PATH`.

After installation:

```bash
gh-best-practices-audit --help
gh-best-practices-audit -i        # interactive mode
```

### Local

Clone the repo, then run the setup script:

```bash
git clone https://github.com/h3nryza/gh_scripts.git
cd gh_scripts/gh-best-practices-audit
source setup_env.sh
python gh_best_practices_audit.py --help
```

### Install options

```
./install.sh [OPTIONS]

  --prefix <dir>    Override install directory (default: ~/.local/bin/gh-best-practices-audit)
  --no-symlink      Skip creating a symlink in /usr/local/bin
  --no-venv         Skip virtual environment creation
  --local           Copy from current directory instead of downloading
```

### Dependencies

| Dependency | Required | Purpose |
|------------|----------|---------|
| Python 3.9+ | Yes | Runtime |
| `gh` CLI or PAT | Yes | GitHub API access |
| `openpyxl` | No | Excel (.xlsx) custom rules |
| `boto3` | No | S3 report upload (Lambda) |
| `aws` CLI | No | S3 fallback if boto3 absent |

---

## Authentication

Three authentication methods are supported. Pass `--auth <method>` to select one.

### GitHub CLI (default)

Requires the `gh` CLI to be installed and authenticated.

```bash
# Authenticate once
gh auth login

# Run audit using gh CLI auth
python gh_best_practices_audit.py -o my-org
```

The tool calls `gh auth status` at startup to verify the session is active.

### Personal Access Token (PAT)

```bash
python gh_best_practices_audit.py -o my-org \
  --auth pat \
  --token ghp_xxxxxxxxxxxxxxxxxxxx
```

You can also set the token via an environment variable and pass it in:

```bash
export GITHUB_TOKEN="ghp_xxxx"
python gh_best_practices_audit.py -o my-org --auth pat --token "$GITHUB_TOKEN"
```

**Required PAT scopes:**

| Scope | Required for |
|-------|-------------|
| `repo` | Repository-level checks |
| `read:org` | Organization membership |
| `admin:org` | Organization security settings |
| `admin:enterprise` | Enterprise-level checks |

### GitHub App

```bash
python gh_best_practices_audit.py -o my-org \
  --auth app \
  --app-id 12345 \
  --app-key /path/to/private-key.pem
```

The App must be installed on the target organization or enterprise and granted the necessary permissions (repository administration, organization administration).

---

## Targets

Exactly one target must be specified per run.

### Enterprise

Audits enterprise-level settings, then discovers and audits all organizations (and their repositories) within the enterprise.

```bash
python gh_best_practices_audit.py --enterprise my-enterprise-slug
# or
python gh_best_practices_audit.py -e my-enterprise-slug
```

Enterprise-level rules check: SAML SSO, audit log streaming, IP allow list, GitHub Advanced Security, and member privilege restrictions.

### Organization

Audits organization-level settings, then discovers and audits all non-archived repositories in the organization.

```bash
python gh_best_practices_audit.py --org my-org
# or
python gh_best_practices_audit.py -o my-org
```

Organization-level rules check: 2FA enforcement, default repository permissions, forking controls, dependency graph, Dependabot, secret scanning defaults, and webhook security.

### Single Repository

Audits one repository only.

```bash
python gh_best_practices_audit.py --repo my-org/my-repo
# or
python gh_best_practices_audit.py -r my-org/my-repo
```

### Local Path

Runs file-based checks only against a local directory (no API calls required). Useful for auditing cloned repositories without API access.

```bash
python gh_best_practices_audit.py --local-path /path/to/repos
```

The tool detects whether the path is a single repository (contains `.git`) or a parent directory of multiple repositories. It checks for the presence of: `README`, `LICENSE`, `.gitignore`, `SECURITY.md`, `CODEOWNERS`, and workflow files.

---

## Benchmark Selection

Use `--benchmarks` to select which benchmarks to run. Accepts a comma-separated list or `all`.

```bash
# All benchmarks (default)
python gh_best_practices_audit.py -o my-org --benchmarks all

# CIS GitHub Benchmark only
python gh_best_practices_audit.py -o my-org --benchmarks cis

# OWASP CI/CD Top 10 only
python gh_best_practices_audit.py -o my-org --benchmarks owasp

# SANS Top 25 only
python gh_best_practices_audit.py -o my-org --benchmarks sans

# CIS and OWASP combined
python gh_best_practices_audit.py -o my-org --benchmarks cis,owasp
```

---

## Severity and Category Filtering

### Severity

Only rules at or above the specified severity level are checked. Levels in order: `critical > high > medium > low > info`.

```bash
# Critical rules only (fastest, most impactful)
python gh_best_practices_audit.py -o my-org --severity critical

# High and critical
python gh_best_practices_audit.py -o my-org --severity high

# Medium and above
python gh_best_practices_audit.py -o my-org --severity medium

# Low and above (default — all rules except informational)
python gh_best_practices_audit.py -o my-org --severity low

# All rules including informational
python gh_best_practices_audit.py -o my-org --severity info
```

### Category

Filter to a single security category:

```bash
python gh_best_practices_audit.py -o my-org --category auth
python gh_best_practices_audit.py -o my-org --category branch-protection
python gh_best_practices_audit.py -o my-org --category secrets
python gh_best_practices_audit.py -o my-org --category ci-cd
python gh_best_practices_audit.py -o my-org --category access
python gh_best_practices_audit.py -o my-org --category repo-settings
python gh_best_practices_audit.py -o my-org --category audit
```

Combine with severity for targeted checks:

```bash
# Critical authentication issues only
python gh_best_practices_audit.py -o my-org --category auth --severity critical

# All secrets-related checks
python gh_best_practices_audit.py -o my-org --category secrets
```

---

## Custom Rules

Custom rules extend the built-in benchmark rules. Use the CSV template at `rules/custom_template.csv` as a starting point.

### CSV Format

```bash
cp rules/custom_template.csv my_custom_rules.csv
# Edit my_custom_rules.csv
python gh_best_practices_audit.py -o my-org --custom-rules my_custom_rules.csv
```

### Field Reference

| Field | Required | Description | Example |
|-------|----------|-------------|---------|
| `id` | Yes | Unique rule identifier | `CUSTOM-001` |
| `name` | Yes | Short rule name | `Disable wiki` |
| `description` | No | Detailed explanation | Free text |
| `category` | Yes | Security category | `repo-settings` |
| `severity` | Yes | `critical`, `high`, `medium`, `low`, `info` | `medium` |
| `level` | Yes | `enterprise`, `organization`, `repository` | `repository` |
| `check_type` | Yes | Type of check (see below) | `api` |
| `api_endpoint` | Yes | GitHub API path with `{variables}` | `/repos/{owner}/{repo}` |
| `field` | Yes | JSON field path (dot notation) | `has_wiki` |
| `expected_value` | Yes | Expected result (see below) | `false` |
| `remediation` | Yes | How to fix if the check fails | Free text |
| `check_paths` | No | Semicolon-separated paths for `file_exists_multi` | `CODEOWNERS;.github/CODEOWNERS` |

### Check Types

| check_type | Description |
|------------|-------------|
| `api` | Fetches the endpoint and checks a field value |
| `branch_protection` | Checks a field in the branch protection response |
| `file_exists` | Checks whether a specific file exists |
| `file_exists_multi` | Checks whether a file exists at any of several paths |

### Expected Value Syntax

| Syntax | Meaning | Example |
|--------|---------|---------|
| `true` / `false` | Boolean match | `true` |
| `"string"` | Exact string match | `enabled` |
| `not_null` | Any non-null value | `not_null` |
| `>=N` | Greater than or equal to N | `>=1` |
| `>N` | Greater than N | `>0` |
| `<=N` | Less than or equal to N | `<=100` |
| `review_required` | Informational — always passes, logs the value | `review_required` |

### Variable Substitution

Endpoints support these placeholders:

| Variable | Value |
|----------|-------|
| `{owner}` | Repository owner or org login |
| `{repo}` | Repository name |
| `{org}` | Organization login |
| `{enterprise}` | Enterprise slug |
| `{branch}` | Default branch name |

### Excel Support

Excel files (`.xlsx`) are supported if `openpyxl` is installed:

```bash
pip install openpyxl
python gh_best_practices_audit.py -o my-org --custom-rules my_rules.xlsx
```

---

## Output Formats

### CSV (default)

```bash
python gh_best_practices_audit.py -o my-org --format csv
```

Output columns: `Target, Level, RuleID, RuleName, Benchmark, Category, Severity, Status, CurrentValue, ExpectedValue, Remediation`

### JSON

```bash
python gh_best_practices_audit.py -o my-org --format json
```

Output structure:

```json
{
  "audit_timestamp": "2026-05-10_143022",
  "tool": "gh-best-practices-audit",
  "version": "1.0.0",
  "total_rules": 79,
  "passed": 60,
  "failed": 12,
  "skipped": 7,
  "results": [
    {
      "target": "my-org",
      "level": "organization",
      "rule_id": "CIS-O1",
      "rule_name": "Two-factor authentication required",
      "benchmark": "CIS",
      "category": "auth",
      "severity": "critical",
      "status": "PASS",
      "current_value": "True",
      "expected_value": "True",
      "remediation": ""
    }
  ]
}
```

### HTML

```bash
python gh_best_practices_audit.py -o my-org --format html --output report.html
```

Generates a dark-themed HTML report with summary cards, severity badges, a results table, and remediation guidance.

### Summary Scorecard Only

To print the scorecard without saving a file:

```bash
python gh_best_practices_audit.py -o my-org --summary
```

The scorecard shows:
- Overall score (0–100)
- Breakdown by benchmark
- Breakdown by severity
- Top 10 failures sorted by severity

### Custom Output File

```bash
python gh_best_practices_audit.py -o my-org --output /tmp/audit_results.csv
```

If `--output` is not specified, the file is named automatically:
`audit_<target>_<timestamp>.<format>`

---

## Interactive Mode

Interactive mode prompts you for all options step by step. Useful for first-time users and ad-hoc audits.

```bash
python gh_best_practices_audit.py -i
# or
python gh_best_practices_audit.py --interactive
```

You will be prompted for:
1. Audit target (enterprise / org / repo / local path)
2. Benchmarks to run
3. Minimum severity level
4. Custom rules file (optional)
5. Output format
6. Output file (optional)
7. Summary-only mode
8. Verbose output
9. Authentication method

---

## AWS Lambda Deployment

The `lambda_handler.py` file wraps `gh_best_practices_audit.py` for deployment as an AWS Lambda function.

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GITHUB_TOKEN` | Yes | — | GitHub PAT for authentication |
| `S3_BUCKET` | Yes | — | S3 bucket to upload reports to |
| `S3_PREFIX` | No | `""` | S3 key prefix (e.g., `audits/2026/`) |
| `BENCHMARKS` | No | `all` | Comma-separated benchmark list |
| `SEVERITY` | No | `low` | Minimum severity level |
| `OUTPUT_FORMAT` | No | `json` | Report format: `csv`, `json`, `html` |
| `SNS_TOPIC_ARN` | No | — | SNS topic ARN for failure alerts |

### Event Payload

The Lambda function accepts an event dict with the same keys as the CLI flags:

```json
{
  "org": "my-org",
  "benchmarks": "cis,owasp",
  "severity": "high",
  "format": "json",
  "summary": false,
  "verbose": false
}
```

Or for an enterprise audit:

```json
{
  "enterprise": "my-enterprise",
  "benchmarks": "all",
  "severity": "critical"
}
```

### Response

```json
{
  "statusCode": 200,
  "body": "{\"status\": \"ok\", \"target\": \"my-org\", \"total\": 79, \"passed\": 65, \"failed\": 7, \"skipped\": 7, \"output_file\": \"/tmp/audit_my-org.json\", \"s3_url\": \"s3://my-bucket/audits/audit_my-org.json\"}"
}
```

### S3 Upload from CLI

You can also upload reports to S3 from the CLI:

```bash
python gh_best_practices_audit.py -o my-org \
  --format json \
  --s3-bucket my-security-reports \
  --s3-prefix audits/2026/
```

### SNS Notifications

When `SNS_TOPIC_ARN` is set and the audit finds failures, the Lambda sends a notification containing the summary counts and S3 report URL.

---

## Rule Reference

### CIS GitHub Benchmark (39 rules)

**Enterprise Level (5 rules)**

| ID | Name | Severity | Category |
|----|------|----------|----------|
| CIS-E1 | Enterprise SSO/SAML configured | critical | auth |
| CIS-E2 | Enterprise audit log streaming enabled | high | audit |
| CIS-E3 | IP allow list configured | high | access |
| CIS-E4 | GitHub Advanced Security enabled | high | repo-settings |
| CIS-E5 | Member privilege restrictions configured | medium | access |

**Organization Level (14 rules)**

| ID | Name | Severity | Category |
|----|------|----------|----------|
| CIS-O1 | Two-factor authentication required | critical | auth |
| CIS-O2 | Default repository permissions set to read | high | access |
| CIS-O3 | Members cannot create repositories | medium | access |
| CIS-O4 | Members cannot fork private repositories | medium | access |
| CIS-O5 | Members cannot invite outside collaborators | medium | access |
| CIS-O6 | Members cannot create public pages | low | access |
| CIS-O7 | Dependency graph enabled | medium | repo-settings |
| CIS-O8 | Dependabot alerts enabled | critical | secrets |
| CIS-O9 | Dependabot security updates enabled | high | secrets |
| CIS-O10 | Secret scanning enabled by default | critical | secrets |
| CIS-O11 | Code scanning enabled by default | high | ci-cd |
| CIS-O12 | Security advisories enabled | medium | repo-settings |
| CIS-O13 | Webhook security | high | repo-settings |
| CIS-O14 | Installed GitHub Apps reviewed | info | access |

**Repository Level (20 rules)**

| ID | Name | Severity | Category |
|----|------|----------|----------|
| CIS-R1 | Branch protection on default branch | critical | branch-protection |
| CIS-R2 | Pull request reviews required | critical | branch-protection |
| CIS-R3 | Stale reviews dismissed | high | branch-protection |
| CIS-R4 | Code owner reviews required | high | branch-protection |
| CIS-R5 | Status checks required before merge | high | branch-protection |
| CIS-R6 | Signed commits required | medium | branch-protection |
| CIS-R7 | Admin enforcement of branch protection | high | branch-protection |
| CIS-R8 | Force pushes blocked | critical | branch-protection |
| CIS-R9 | Secret scanning enabled | critical | secrets |
| CIS-R10 | Secret scanning push protection enabled | high | secrets |
| CIS-R11 | Dependabot alerts enabled | critical | secrets |
| CIS-R12 | Dependabot security updates enabled | high | secrets |
| CIS-R13 | Actions permissions restricted | high | ci-cd |
| CIS-R14 | Workflow permissions set to read-only | high | ci-cd |
| CIS-R15 | README file exists | low | repo-settings |
| CIS-R16 | LICENSE file exists | low | repo-settings |
| CIS-R17 | .gitignore file exists | medium | repo-settings |
| CIS-R18 | SECURITY.md exists | medium | repo-settings |
| CIS-R19 | CODEOWNERS file exists | medium | access |
| CIS-R20 | Delete branch on merge enabled | low | repo-settings |

### OWASP CI/CD Top 10 (24 rules)

Maps OWASP CICD-SEC-1 through CICD-SEC-10 to GitHub settings. Covers: flow control, identity management, dependency chain, pipeline poisoning, credentials, artifact integrity, and logging.

### SANS Top 25 (16 rules)

Maps CWE entries (CWE-798, CWE-284, CWE-269, CWE-311, CWE-502, CWE-829) to GitHub repository settings and workflow configurations.

---

## Examples

### Typical organization security audit

```bash
python gh_best_practices_audit.py -o my-org \
  --benchmarks all \
  --severity low \
  --format html \
  --output org_audit.html \
  --verbose
```

### Quick critical-only check before a release

```bash
python gh_best_practices_audit.py -r my-org/my-repo \
  --severity critical \
  --summary
```

### Enterprise-wide audit with JSON output to S3

```bash
python gh_best_practices_audit.py -e my-enterprise \
  --auth pat --token "$GITHUB_TOKEN" \
  --format json \
  --s3-bucket security-reports \
  --s3-prefix "github-audit/$(date +%Y/%m)"
```

### Secrets posture review

```bash
python gh_best_practices_audit.py -o my-org \
  --category secrets \
  --severity high \
  --format csv \
  --output secrets_posture.csv
```

### Branch protection audit only

```bash
python gh_best_practices_audit.py -o my-org \
  --category branch-protection \
  --benchmarks cis,owasp \
  --severity high
```

### OWASP CI/CD pipeline security check

```bash
python gh_best_practices_audit.py -o my-org \
  --benchmarks owasp \
  --format html \
  --output owasp_cicd_report.html
```

### Local repo file audit (offline, no API needed)

```bash
git clone --depth 1 https://github.com/my-org/my-repo.git /tmp/my-repo
python gh_best_practices_audit.py \
  --local-path /tmp/my-repo \
  --benchmarks cis
```

### Custom rules added to a standard audit

```bash
python gh_best_practices_audit.py -o my-org \
  --custom-rules my_company_rules.csv \
  --format json \
  --output full_audit.json
```

### PAT auth with verbose output

```bash
python gh_best_practices_audit.py -r my-org/my-repo \
  --auth pat --token ghp_xxxx \
  --verbose \
  --format csv
```

---

## Troubleshooting

### "GitHub CLI is not authenticated"

```bash
gh auth login
# Then retry
python gh_best_practices_audit.py -o my-org
```

Or switch to PAT auth:

```bash
python gh_best_practices_audit.py -o my-org --auth pat --token ghp_xxxx
```

### "PAT auth requires --token"

The `--auth pat` flag requires `--token <TOKEN>`. Do not pass an empty string.

### Many SKIP results

`SKIP` means the API endpoint returned a 403 (permission denied) or the feature is not enabled on the target. This is normal for:
- Enterprise-level checks when you do not have enterprise admin access
- Advanced Security features on organizations without GHAS enabled
- Audit log checks without `admin:org` or `admin:enterprise` scope

To reduce SKIPs: use a PAT with broader scopes or a GitHub App with the required permissions.

### Rules file not found

The tool looks for rules in the `rules/` directory relative to `gh_best_practices_audit.py`. If you moved the script, ensure the `rules/` directory is in the same location.

```bash
ls "$(dirname gh_best_practices_audit.py)/rules/"
# Should list: cis_benchmark.json  owasp_cicd.json  sans_top25.json
```

### openpyxl not installed

Excel custom rules require `openpyxl`:

```bash
pip install openpyxl
# Or reinstall all dependencies
pip install -r requirements.txt
```

### Python version error

The tool requires Python 3.9 or later:

```bash
python3 --version
# If < 3.9, install a newer version via your OS package manager or pyenv
```

### Running tests

```bash
cd gh-best-practices-audit
pip install -r requirements.txt
pytest tests/ -v
pytest tests/ -v --cov=gh_best_practices_audit
```
