# gh-repo-migrator — Usage Guide

**Written by h3nryza**

A production-grade Bash script that transfers GitHub repositories between organizations. Supports single-repo transfer and bulk transfer via CSV, with dry-run, diff, and query modes.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Authentication](#authentication)
4. [Modes of Operation](#modes-of-operation)
5. [CSV Format](#csv-format)
6. [Options Reference](#options-reference)
7. [Examples](#examples)
8. [Troubleshooting](#troubleshooting)
9. [Limitations & GitHub API Notes](#limitations--github-api-notes)

---

## Prerequisites

| Tool | Required | Purpose |
|------|----------|---------|
| `bash` | Yes (>=4.0) | Script runtime |
| `curl` | Yes | GitHub API calls |
| `gh` CLI | Only when `--auth gh` | Token resolution |
| `openssl` | Only when `--auth app` | JWT signing |
| `python3` | Only when `--auth app` | JSON parsing for app tokens |
| `shellcheck` | Optional | Linting (tests only) |

macOS ships with bash 3.x. Install bash 4+ via Homebrew: `brew install bash`.

---

## Installation

### Remote (no clone required)

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-repo-migrator/install.sh)
```

The installer:
- Downloads `gh-repo-migrator.sh` to `/usr/local/bin` (or `~/bin` as fallback)
- Makes it executable
- Optionally sets up a shell alias

### Manual

```bash
curl -fsSLO https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-repo-migrator/gh-repo-migrator.sh
chmod +x gh-repo-migrator.sh
./gh-repo-migrator.sh --help
```

### From source

```bash
git clone https://github.com/h3nryza/gh_scripts.git
cd gh_scripts/gh-repo-migrator
chmod +x gh-repo-migrator.sh install.sh
./gh-repo-migrator.sh --help
```

---

## Authentication

Three auth methods are supported via `-a`/`--auth`:

### 1. GitHub CLI (`--auth gh`) — Default

Uses `gh auth token` to resolve the current token. Requires the `gh` CLI to be installed and authenticated.

```bash
gh auth login
gh-repo-migrator.sh -r my-repo -s source-org -d dest-org
```

### 2. Personal Access Token (`--auth pat`)

Pass the token directly via `-t`/`--token` or set the `GITHUB_TOKEN` environment variable.

Required token scopes:
- `repo` — full control of private repositories
- `admin:org` — read org members (for membership verification)

```bash
export GITHUB_TOKEN=ghp_xxxxxxxxxxxx
gh-repo-migrator.sh --auth pat -r my-repo -s source-org -d dest-org

# Or inline:
gh-repo-migrator.sh --auth pat --token ghp_xxx -r my-repo -s source-org -d dest-org
```

### 3. GitHub App (`--auth app`)

Generates a JWT, exchanges it for an installation token, then proceeds with API calls.

```bash
gh-repo-migrator.sh --auth app \
  --app-id 123456 \
  --app-key /path/to/private-key.pem \
  -r my-repo -s source-org -d dest-org
```

The App must be installed on both the source and destination orgs with `Contents: write` and `Administration: write` permissions.

---

## Modes of Operation

### Single Transfer

Transfer one repository from a source org to a destination org.

```
gh-repo-migrator.sh -r <repo> -s <source-org> -d <dest-org> [OPTIONS]
```

Pre-flight checks performed:
1. Source repo exists and caller has **admin** access
2. Source repo is not a fork
3. Destination org exists
4. Both orgs are on the same GitHub instance (no cross-enterprise transfers)

The GitHub API returns **202 Accepted** immediately — the actual transfer happens asynchronously in the background (usually within seconds to minutes).

### Bulk Transfer via CSV

Transfer multiple repositories from a CSV file.

```
gh-repo-migrator.sh --import transfers.csv [OPTIONS]
```

A confirmation prompt is shown before bulk operations (bypass with `--confirm`).

Progress is displayed as `[N/M] Processing source/repo -> dest`.

Results are written to the output CSV (default: `migration_results_YYYYMMDD_HHMMSS.csv`).

### Export Org Repos

Export all repositories from an org to a CSV file for editing, then use the CSV for bulk import.

```
gh-repo-migrator.sh --query-org <org> --export repos.csv
```

The exported CSV has an empty `DestOrg` column. Fill it in and run `--import`.

### Query Mode

List all repos in an org to stdout.

```
gh-repo-migrator.sh --query-org <org>
```

### Diff Mode

Compare a planned CSV against the live GitHub state to show what still needs transferring.

```
gh-repo-migrator.sh --diff planned.csv
```

Output columns:
- `REPO` — source/repo-name
- `CURRENT OWNER` — who currently owns the repo
- `DEST ORG` — where the plan says it should go
- `STATUS` — `NEEDS TRANSFER`, `ALREADY DONE`, or `NOT FOUND`

### Interactive Mode

Guided prompts to select and configure an operation.

```
gh-repo-migrator.sh -i
```

---

## CSV Format

### Import CSV

```csv
SourceOrg,RepoName,DestOrg
my-org,cool-repo,new-org
my-org,another-repo,new-org
old-org,legacy-service,platform-org
```

Rules:
- Header row is auto-detected and skipped
- Lines starting with `#` are comments
- Blank lines are skipped
- Rows with missing `RepoName` or `DestOrg` are flagged as `SKIPPED`
- Leading/trailing whitespace is trimmed from all fields

### Output CSV

```csv
SourceOrg,RepoName,DestOrg,Status,Message,Timestamp
my-org,cool-repo,new-org,ACCEPTED,"Transfer initiated (async); GitHub is processing in background",2024-01-15T10:30:00Z
my-org,another-repo,new-org,SKIPPED,"No admin access on my-org/another-repo",2024-01-15T10:30:01Z
old-org,legacy-service,platform-org,FAILED,"Validation error: Repository already exists on the destination organization.",2024-01-15T10:30:02Z
```

**Status values:**

| Status | Meaning |
|--------|---------|
| `ACCEPTED` | Transfer API returned 202 — processing in background |
| `DRY_RUN` | Would transfer (dry-run mode) |
| `SKIPPED` | Pre-flight check failed — repo/org not found, no admin, fork, etc. |
| `FAILED` | Transfer API returned error (403, 422, etc.) |

---

## Options Reference

| Flag | Short | Description | Default |
|------|-------|-------------|---------|
| `--repo` | `-r` | Repository name | — |
| `--source` | `-s` | Source organization | — |
| `--dest` | `-d` | Destination organization | — |
| `--import` | — | Bulk import CSV file | — |
| `--export` | — | Export CSV file path | — |
| `--diff` | — | Diff plan CSV file | — |
| `--query-org` | — | Org name for listing/export | — |
| `--auth` | `-a` | Auth method: `gh`\|`pat`\|`app` | `gh` |
| `--token` | `-t` | PAT token | `$GITHUB_TOKEN` |
| `--app-id` | — | GitHub App ID | — |
| `--app-key` | — | GitHub App private key file | — |
| `--team-ids` | — | Comma-separated team IDs for dest org | — |
| `--output` | — | Output CSV path | `migration_results_TIMESTAMP.csv` |
| `--dry-run` | — | Preview only, no real transfers | false |
| `--confirm` | — | Skip confirmation prompt | false |
| `--interactive` | `-i` | Interactive guided mode | false |
| `--verbose` | `-v` | Debug output | false |
| `--help` | `-h` | Show help | — |
| `--version` | — | Show version | — |

---

## Examples

### Single transfer (default gh CLI auth)

```bash
gh-repo-migrator.sh -r my-repo -s old-org -d new-org
```

### Single transfer with PAT

```bash
gh-repo-migrator.sh \
  --auth pat --token ghp_xxxxxxxxxxxx \
  -r my-repo -s old-org -d new-org
```

### Dry run a single transfer

```bash
gh-repo-migrator.sh -r my-repo -s old-org -d new-org --dry-run
```

### Bulk transfer from CSV, CI mode (no prompt)

```bash
gh-repo-migrator.sh --import transfers.csv --confirm
```

### Bulk dry run

```bash
gh-repo-migrator.sh --import transfers.csv --dry-run
```

### Export org repos to CSV, fill in dest, then transfer

```bash
# Step 1: Export
gh-repo-migrator.sh --query-org old-org --export to_migrate.csv

# Step 2: Edit to_migrate.csv, fill in DestOrg column

# Step 3: Diff to preview
gh-repo-migrator.sh --diff to_migrate.csv

# Step 4: Dry run
gh-repo-migrator.sh --import to_migrate.csv --dry-run

# Step 5: Transfer for real
gh-repo-migrator.sh --import to_migrate.csv --confirm
```

### Transfer with team access in destination org

```bash
# Grant team IDs 11111 and 22222 access in destination org
gh-repo-migrator.sh \
  -r my-repo -s old-org -d new-org \
  --team-ids 11111,22222
```

### GitHub App auth

```bash
gh-repo-migrator.sh \
  --auth app \
  --app-id 123456 \
  --app-key ./my-app-private-key.pem \
  --import transfers.csv --confirm
```

### Custom output file

```bash
gh-repo-migrator.sh --import transfers.csv --output ./results/migration_$(date +%Y%m%d).csv
```

### Remote execution (no install needed)

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-repo-migrator/gh-repo-migrator.sh) \
  -r my-repo -s old-org -d new-org
```

---

## Troubleshooting

### "Must have admin rights to Repository"

You need admin access on the source repo. Check in GitHub settings or via the API:

```bash
curl -H "Authorization: Bearer $GITHUB_TOKEN" \
  https://api.github.com/repos/SOURCE_ORG/REPO \
  | grep -A3 '"permissions"'
```

### "Forks cannot be transferred"

GitHub does not allow fork transfers. You need to detach the fork or create a new independent repo.

### "Cross-enterprise transfers are not supported"

The transfer API only works within the same GitHub instance. If source and destination are in different GitHub Enterprise Server instances (or one is on GitHub.com and the other is GHES), you must use a different migration approach (e.g., `gh-migration-toolkit`).

### Transfer shows ACCEPTED but repo doesn't appear in dest org

The transfer is asynchronous. GitHub typically completes it within a few seconds to minutes. Use `--diff` to check the current state:

```bash
gh-repo-migrator.sh --diff your-plan.csv
```

### Authentication fails with `gh auth`

Ensure you are logged in:

```bash
gh auth status
gh auth login   # if needed
```

### Rate limiting

GitHub's REST API allows 5,000 requests/hour for authenticated users. Bulk operations against very large orgs (hundreds of repos) may hit this limit. Consider adding delays between batches or using a GitHub App token (higher rate limits).

---

## Limitations & GitHub API Notes

- **Async operation**: `POST /repos/{owner}/{repo}/transfer` returns `202 Accepted`. The actual transfer happens in the background. Poll with `GET /repos/{dest}/{repo}` to confirm completion.
- **Forks**: Cannot be transferred.
- **Enterprise boundary**: Transfers only work within the same GitHub instance.
- **Webhooks & deploy keys**: Existing webhooks, deploy keys, and some integrations are removed during transfer. Reconfigure them after transfer.
- **Private repos**: Visibility may change and billing information about private repos could be revealed to the destination org owners.
- **Team IDs**: You must know the numeric team IDs (not slugs) to grant access via `--team-ids`. Find them with: `GET /orgs/{org}/teams`.
- **Re-transfer**: If a repo already exists at the destination, the transfer will fail with a 422 Validation error.

---

*Written by h3nryza — part of the [gh_scripts](https://github.com/h3nryza/gh_scripts) suite.*
