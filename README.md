# gh_scripts

**A suite of independent GitHub management tools for Enterprise, Organization, and User administration.**

Written by [h3nryza](https://github.com/h3nryza)

> **You do NOT need to clone this repository.** Every tool can be run remotely via `curl` or installed via `gh`. See each tool's "Remote Execution" section below.

---

## Quick Start

Each tool is self-contained. Pick the one you need and run it directly:

```bash
# Example: Audit repo visibility across your org (no clone needed)
curl -sL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-visibility-audit/gh-visibility-audit.sh | bash -s -- -o my-org

# Example: Run with GitHub CLI extension
gh extension install h3nryza/gh_scripts
```

All tools support three authentication methods:
- **`gh` CLI** (default) — uses your existing `gh auth` session
- **PAT** — pass a Personal Access Token via `-t` / `--token`
- **GitHub App** — use an OAuth/GitHub App with `--app-id` and `--app-key`

---

## Tools

### 1. gh-visibility-audit — Repository Visibility Auditor

Audit and manage repository visibility (public/private/internal) across your GitHub Enterprise, Organizations, or User accounts. Export results to CSV, or import a CSV to bulk-update visibility settings.

**Use when:** You need to ensure no repos are accidentally public, audit visibility across an enterprise, or bulk-change visibility for compliance.

**Language:** Bash

```bash
# Remote execution
curl -sL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-visibility-audit/gh-visibility-audit.sh | bash -s -- -o my-org

# Audit an org
./gh-visibility-audit.sh -o my-org

# Audit enterprise with PAT
./gh-visibility-audit.sh -e my-enterprise -a pat -t ghp_xxxxx

# Bulk update visibility from CSV
./gh-visibility-audit.sh --import changes.csv

# Interactive mode (asks you questions)
./gh-visibility-audit.sh -i

# Full help
./gh-visibility-audit.sh -h
```

**Output:** `YYYY-MM-DD_HHMMSS_Github_visibility.csv` with columns: Enterprise, Organization, Owner, Repository, Visibility, URL

[Full documentation →](gh-visibility-audit/docs/USAGE.md)

---

### 2. gh-backup — GitHub Backup Tool

Download and backup all repositories and gists from a GitHub Enterprise, Organization, or User account. Maintains the original GitHub directory hierarchy (enterprise/org/repo). Generates an index.md with descriptions and a detailed CSV manifest.

**Use when:** You need offline backups, disaster recovery, migration preparation, or compliance archival of your GitHub assets.

**Language:** Bash

```bash
# Remote execution
curl -sL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-backup/gh-backup.sh | bash -s -- -o my-org

# Backup an org
./gh-backup.sh -o my-org

# Backup enterprise (enumerates all orgs)
./gh-backup.sh -e my-enterprise --exclude-forks

# Backup user with gists
./gh-backup.sh -u h3nryza --include-gists

# Interactive mode
./gh-backup.sh -i

# Full help
./gh-backup.sh -h
```

**Output:** Timestamped directory (`backup_YYYY-MM-DD_HHMMSS/`) maintaining GitHub's hierarchy, plus `index.md` and `backup_manifest.csv`

[Full documentation →](gh-backup/docs/USAGE.md)

---

### 3. gh-repo-migrator — Repository Migration Tool

Transfer repositories between organizations (not enterprises). Supports single transfers or bulk migration via CSV import. Reports success/failure with detailed feedback CSV.

**Use when:** You're reorganizing orgs, consolidating repos, or splitting an org and need to move repos in bulk with an audit trail.

**Language:** Bash

```bash
# Remote execution
curl -sL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-repo-migrator/gh-repo-migrator.sh | bash -s -- -r my-repo -s old-org -d new-org

# Single transfer
./gh-repo-migrator.sh -r my-repo -s old-org -d new-org

# Bulk transfer from CSV
./gh-repo-migrator.sh --import transfers.csv

# Export org repos to build transfer list
./gh-repo-migrator.sh --export repos.csv --query-org my-org

# Dry run
./gh-repo-migrator.sh --import transfers.csv --dry-run

# Interactive mode
./gh-repo-migrator.sh -i

# Full help
./gh-repo-migrator.sh -h
```

**Output:** `YYYY-MM-DD_HHMMSS_migration_results.csv` with columns: SourceOrg, RepoName, DestOrg, Status, Message, Timestamp

[Full documentation →](gh-repo-migrator/docs/USAGE.md)

---

### 4. gh-new-resource-detector — New Resource Detector

Detect newly created repositories and organizations across your GitHub Enterprise. Enumerates from enterprise down to org and account level. Runs locally (with Python venv) or as an AWS Lambda function.

**Use when:** You need visibility into shadow IT — repos or orgs being created without your knowledge. Audit new resources on a schedule.

**Language:** Python | **Runtime:** Local + AWS Lambda

```bash
# Remote execution
curl -sL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-new-resource-detector/install.sh | bash
python gh_new_resource_detector.py -e my-enterprise --days 7

# Setup venv (first time)
./setup_env.sh

# Detect new repos in last 7 days
python gh_new_resource_detector.py -e my-enterprise --days 7

# Detect new orgs since a date
python gh_new_resource_detector.py -e my-enterprise --since 2026-01-01 --type orgs

# Interactive mode
python gh_new_resource_detector.py -i

# Teardown venv
./teardown_env.sh
```

**Lambda:** Deploy `lambda_handler.py` with event containing enterprise, auth, and S3 bucket details. Output goes to S3.

**Output:** `YYYY-MM-DD_HHMMSS_new_resources.csv` (local) or S3 object (Lambda)

[Full documentation →](gh-new-resource-detector/docs/USAGE.md)

---

### 5. gh-pipeline-compliance — Pipeline Compliance Checker

Check which repositories across your org/enterprise are using your organization's reusable GitHub Actions workflows versus custom pipelines. See the security posture of pipeline adoption at a glance.

**Use when:** You've built reusable workflows but need to know who's actually using them vs rolling their own. Enforce pipeline standards.

**Language:** Python | **Runtime:** Local + AWS Lambda

```bash
# Remote execution
curl -sL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-pipeline-compliance/install.sh | bash
python gh_pipeline_compliance.py -o my-org --workflow "my-org/reusable-workflows/.github/workflows/ci.yml"

# Setup venv
./setup_env.sh

# Check reusable workflow adoption
python gh_pipeline_compliance.py -o my-org --workflow "my-org/reusable-workflows/.github/workflows/ci.yml"

# Search for any workflow files
python gh_pipeline_compliance.py -o my-org --pattern ".github/workflows/*.yml"

# Summary view
python gh_pipeline_compliance.py -o my-org --workflow "my-org/ci.yml" --summary

# Interactive mode
python gh_pipeline_compliance.py -i

# Teardown
./teardown_env.sh
```

**Output:** `YYYY-MM-DD_HHMMSS_pipeline_compliance.csv` with compliance status per repo

Also includes `docs/henrysexplanation.md` — explains how to automatically install and enforce reusable workflows.

[Full documentation →](gh-pipeline-compliance/docs/USAGE.md)

---

### 6. gh-best-practices-audit — Best Practices Auditor

Comprehensive automated audit of GitHub Enterprise, Organization, and Repository settings against industry security benchmarks: CIS GitHub Benchmark, OWASP CI/CD Top 10, and SANS Top 25. Supports custom rules via Excel/CSV.

**Use when:** Security compliance review, preparing for audits, establishing baseline security posture, or ongoing governance monitoring.

**Language:** Python | **Runtime:** Local + AWS Lambda

```bash
# Remote execution
curl -sL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-best-practices-audit/install.sh | bash
python gh_best_practices_audit.py -o my-org --benchmarks all

# Setup venv
./setup_env.sh

# Full audit against all benchmarks
python gh_best_practices_audit.py -o my-org --benchmarks all

# Enterprise audit, critical findings only
python gh_best_practices_audit.py -e my-enterprise --severity critical

# Single repo with custom rules
python gh_best_practices_audit.py -r my-org/my-repo --custom-rules my_rules.csv

# Audit local/downloaded repos
python gh_best_practices_audit.py --local-path ./downloaded-repos --benchmarks cis

# Summary scorecard
python gh_best_practices_audit.py -o my-org --summary

# Interactive mode
python gh_best_practices_audit.py -i

# Teardown
./teardown_env.sh
```

**Output:** `YYYY-MM-DD_HHMMSS_best_practices_audit.csv` with per-rule pass/fail, plus a summary scorecard

[Full documentation →](gh-best-practices-audit/docs/USAGE.md)

---

### 7. gh-version-resolver — Version Resolver

Convert between git commit hashes and release versions. Scan workflow files and Terraform configs to resolve pinned hashes to human-readable versions. Check version currency (current, M-1, N-1, or older) for your security dashboard.

**Use when:** Your security dashboard shows hashes instead of versions, you need to verify dependency currency, or you want to convert between hash and tag formats.

**Language:** Python | **Runtime:** Local + AWS Lambda

```bash
# Remote execution
curl -sL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-version-resolver/install.sh | bash
python gh_version_resolver.py --hash-to-version abc123f --repo actions/checkout

# Setup venv
./setup_env.sh

# Hash to version
python gh_version_resolver.py --hash-to-version abc123f --repo actions/checkout

# Version to hash
python gh_version_resolver.py --version-to-hash v4.1.0 --repo actions/checkout

# Scan a workflow file for pinned hashes
python gh_version_resolver.py --scan-file .github/workflows/ci.yml --type github-action --check-currency

# Scan terraform directory
python gh_version_resolver.py --scan-dir ./terraform/ --type terraform-module --check-currency

# Interactive mode
python gh_version_resolver.py -i

# Teardown
./teardown_env.sh
```

**Output:** `YYYY-MM-DD_HHMMSS_version_resolution.csv` with resolved versions and currency status

[Full documentation →](gh-version-resolver/docs/USAGE.md)

---

## Authentication

### GitHub CLI (Default)
```bash
gh auth login
./any-tool.sh -o my-org  # Uses gh auth automatically
```

### Personal Access Token (PAT)
```bash
./any-tool.sh -o my-org -a pat -t ghp_your_token_here
# Or set environment variable
export GITHUB_TOKEN=ghp_your_token_here
./any-tool.sh -o my-org -a pat
```

### GitHub App (OAuth)
```bash
./any-tool.sh -o my-org -a app --app-id 12345 --app-key /path/to/private-key.pem
```

### How GitHub App Authentication Works

1. **Enterprise Level:** Create a GitHub App at the enterprise level with required permissions
2. **Installation:** Install the app on each organization you want to manage
3. **Drill Down:** The app authenticates at the enterprise level, then enumerates installations to access org-level and repo-level data
4. **JWT Flow:**
   - Generate JWT from App ID + private key
   - List installations: `GET /app/installations`
   - Get installation token per org: `POST /app/installations/{id}/access_tokens`
   - Use installation token for org/repo API calls

**Mandatory App Installation Issue:** If your GitHub App is not being installed on all orgs:
- Use enterprise-level "mandatory installation" policy (Enterprise Settings → GitHub Apps → Install on all orgs)
- Or create an org-level ruleset that requires the app
- Or use enterprise audit log to detect orgs without the app installed
- Script 4 (gh-new-resource-detector) can help detect orgs missing the app

---

## Remote Execution (No Clone Required)

Every tool is designed to run without cloning this repository:

### Via curl
```bash
# Bash tools
curl -sL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/<tool-name>/<tool-script> | bash -s -- [OPTIONS]

# Python tools (use installer)
curl -sL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/<tool-name>/install.sh | bash
```

### Via gh CLI
```bash
# Run directly
gh api repos/h3nryza/gh_scripts/contents/<tool-name>/<script> --jq '.content' | base64 -d | bash -s -- [OPTIONS]
```

### Via installer
Each tool has an `install.sh` that downloads the tool and its dependencies to your local machine:
```bash
curl -sL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/<tool-name>/install.sh | bash
```

---

## Project Structure

```
gh_scripts/
├── gh-visibility-audit/          # Tool 1: Repo visibility audit & bulk update
├── gh-backup/                    # Tool 2: Enterprise/Org/User backup
├── gh-repo-migrator/             # Tool 3: Cross-org repo migration
├── gh-new-resource-detector/     # Tool 4: New resource detection (Python/Lambda)
├── gh-pipeline-compliance/       # Tool 5: Pipeline compliance checker (Python/Lambda)
├── gh-best-practices-audit/      # Tool 6: Best practices auditor (Python/Lambda)
├── gh-version-resolver/          # Tool 7: Hash/version resolver (Python/Lambda)
├── claudefiles/                  # Project meta (prompts, thinking, learnings)
│   ├── prompts/                  # Raw prompts and prompt critique
│   ├── files/                    # Decision records, changelog, diagrams
│   └── learnt/                   # Agent patterns, skills, lessons
├── CLAUDE.md                     # AI assistant project config
└── README.md                     # This file
```

---

## License

MIT

---

*Written by h3nryza | GitHub Scripts Suite v1.0.0*
