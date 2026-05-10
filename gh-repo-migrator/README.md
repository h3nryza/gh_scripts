# gh-repo-migrator

> GitHub Repository Migration Tool — Written by h3nryza

Transfer repositories between GitHub organizations with a single command or in bulk via CSV. Supports dry-run, diff preview, org export, and three auth methods.

---

## Quick Start

```bash
# Remote — no install needed
bash <(curl -fsSL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-repo-migrator/gh-repo-migrator.sh) \
  -r my-repo -s old-org -d new-org

# Install locally
bash <(curl -fsSL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-repo-migrator/install.sh)

# Then use
gh-repo-migrator.sh --help
```

---

## Features

- Single repo transfer or bulk transfer via CSV
- Dry-run mode — preview without making changes
- Diff mode — compare a plan CSV against live GitHub state
- Export an org's repos to CSV for editing and reimport
- Pre-flight checks: admin access, fork detection, cross-enterprise guard
- Three auth methods: `gh` CLI, PAT, GitHub App
- Optional team-ID grant in destination org
- Timestamped result CSV output
- Interactive guided mode (`-i`)
- Shellcheck-clean

---

## Usage

```
gh-repo-migrator.sh [OPTIONS]

SINGLE TRANSFER:
  -r, --repo <name>     Repository name
  -s, --source <org>    Source organization
  -d, --dest <org>      Destination organization

BULK TRANSFER:
  --import <file>       CSV: SourceOrg,RepoName,DestOrg
  --export <file>       Export org repos to CSV

QUERY:
  --diff <file>         Show diff vs live state
  --query-org <org>     List all repos in org

OPTIONS:
  -a, --auth gh|pat|app   Auth method (default: gh)
  -t, --token <token>     PAT token
  --dry-run               Preview only
  --confirm               Skip confirmation (CI)
  -i, --interactive       Guided mode
  --help / --version
```

Full reference: [docs/USAGE.md](docs/USAGE.md)

---

## CSV Format

**Import** (`SourceOrg,RepoName,DestOrg`):
```csv
SourceOrg,RepoName,DestOrg
my-org,cool-repo,new-org
my-org,another-repo,new-org
```

**Output** (`SourceOrg,RepoName,DestOrg,Status,Message,Timestamp`):
```csv
my-org,cool-repo,new-org,ACCEPTED,"Transfer initiated (async)",2024-01-15T10:30:00Z
```

---

## Examples

```bash
# Single transfer
gh-repo-migrator.sh -r my-repo -s old-org -d new-org

# Bulk from CSV, CI mode
gh-repo-migrator.sh --import transfers.csv --confirm

# Dry run
gh-repo-migrator.sh --import transfers.csv --dry-run

# Export → edit → transfer workflow
gh-repo-migrator.sh --query-org old-org --export repos.csv
# edit repos.csv to fill DestOrg column
gh-repo-migrator.sh --diff repos.csv
gh-repo-migrator.sh --import repos.csv --confirm

# GitHub App auth
gh-repo-migrator.sh --auth app --app-id 12345 --app-key key.pem --import transfers.csv
```

---

## File Structure

```
gh-repo-migrator/
├── gh-repo-migrator.sh          # Main script
├── install.sh                   # Remote installer
├── README.md
├── tests/
│   ├── test_migrator.sh         # Test suite (no real API calls)
│   └── mock_gh_responses/       # JSON fixtures
└── docs/
    └── USAGE.md                 # Full usage guide
```

---

## Running Tests

```bash
bash tests/test_migrator.sh
bash tests/test_migrator.sh --verbose   # debug output
```

Tests use a mock `curl` shim — no real GitHub API calls are made.

---

## Limitations

- Transfers only work between orgs on the **same GitHub instance** (not across enterprises)
- Forks cannot be transferred
- Transfer is **asynchronous** — GitHub returns 202, actual move happens in background
- Caller must have **admin** access on source repo and create-repo access in dest org

---

*Part of the [gh_scripts](https://github.com/h3nryza/gh_scripts) suite — written by h3nryza.*
