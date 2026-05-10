# gh-backup Usage Guide

**Written by h3nryza**

---

## Overview

`gh-backup` is a bash script that backs up repositories and gists from GitHub Enterprise, Organization, or User accounts. It maintains the original GitHub directory hierarchy in the backup output and generates a full CSV manifest and Markdown index.

---

## Installation

### Remote (one-liner)

```bash
curl -fsSL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-backup/install.sh | bash
```

### Manual

```bash
git clone https://github.com/h3nryza/gh_scripts.git
chmod +x gh_scripts/gh-backup/gh-backup.sh
# optionally symlink:
ln -sf "$(pwd)/gh_scripts/gh-backup/gh-backup.sh" /usr/local/bin/gh-backup
```

---

## Quick Start

```bash
# Back up an organisation (uses gh CLI auth by default)
gh-backup.sh -o my-org

# Back up a user and their gists
gh-backup.sh -u h3nryza --include-gists

# Back up an entire enterprise
gh-backup.sh -e my-enterprise

# Interactive guided mode
gh-backup.sh -i

# Dry run — preview what would be backed up
gh-backup.sh -u h3nryza --dry-run
```

---

## Authentication

### Method 1: GitHub CLI (default)

```bash
# Log in first
gh auth login

# Then run gh-backup with default auth
gh-backup.sh -o my-org
```

### Method 2: Personal Access Token (PAT)

```bash
# Via flag
gh-backup.sh -o my-org --auth pat --token ghp_YourTokenHere

# Via environment variable
export GITHUB_TOKEN=ghp_YourTokenHere
gh-backup.sh -o my-org --auth pat
```

Required PAT scopes:
- `repo` — access private repositories
- `read:org` — enumerate organisation repositories
- `admin:enterprise` — enumerate enterprise organisations (for `-e`)
- `gist` — access gists

### Method 3: GitHub App

```bash
gh-backup.sh -o my-org --auth app \
  --app-id 123456 \
  --app-key /path/to/private-key.pem
```

Requires `openssl` installed. The app must be installed on the target organisation or enterprise.

---

## CLI Reference

```
USAGE:
  gh-backup.sh [OPTIONS]

TARGET:
  -e, --enterprise <name>    Backup entire enterprise (enumerates orgs→repos)
  -o, --org <name>           Backup organization (enumerates repos)
  -u, --user <name>          Backup user (repos + gists)

AUTH:
  -a, --auth <method>        Auth method: gh | pat | app  (default: gh)
  -t, --token <token>        PAT token (required when --auth pat)
  --app-id <id>              GitHub App ID
  --app-key <file>           GitHub App private key file

OPTIONS:
  --output-dir <dir>         Output directory (default: backup_TIMESTAMP/)
  --include-gists            Include gists (automatically on for -u)
  --exclude-archived         Skip archived repositories
  --exclude-forks            Skip forked repositories
  --clone-method <method>    Clone method: archive | clone | mirror  (default: clone)
  --shallow                  Shallow clone (--depth 1) for faster backups
  --resume                   Skip repos already present in output directory
  --export <file>            Export manifest CSV to a specified path
  --import <file>            Import list of repos to back up selectively

COMMON:
  -i, --interactive          Launch interactive guided mode
  -h, --help                 Show help and exit
  -v, --verbose              Verbose output
  --version                  Show version and exit
  --dry-run                  List what would be backed up (no cloning)
```

---

## Output Structure

```
backup_2026-05-10_120000/
├── index.md                  # Master index with descriptions
├── backup_manifest.csv       # Full CSV manifest
├── my-enterprise/
│   ├── org-one/
│   │   ├── repo-a/           # Cloned repository
│   │   ├── repo-b/
│   │   └── org_index.md      # Org-level index
│   └── org-two/
│       └── ...
└── h3nryza/
    ├── repos/
    │   ├── personal-repo/
    │   └── ...
    └── gists/
        ├── abc123def456/
        └── ...
```

### index.md

The master `index.md` contains a table of all backed-up repositories and gists, with:
- Name
- Type (repo / gist)
- Visibility
- Language
- Last push date
- Description

### backup_manifest.csv

Full CSV manifest with columns:

| Column | Description |
|--------|-------------|
| Enterprise | Enterprise slug (if applicable) |
| Organization | Organisation login (if applicable) |
| Owner | Repository owner login |
| Name | Repository or gist name/ID |
| Type | `repo` or `gist` |
| Description | Repository description |
| Visibility | `public`, `private`, or `internal` |
| Language | Primary language |
| LastUpdated | ISO 8601 push timestamp |
| Size | Repository size in KB |
| BackupPath | Relative path within backup root |
| Status | `ok`, `failed`, `skipped-archived`, `skipped-fork` |

---

## Examples

### Basic Organisation Backup

```bash
gh-backup.sh -o acme-corp
```

Output: `./backup_2026-05-10_120000/acme-corp/`

### Enterprise Backup, Skipping Forks and Archived

```bash
gh-backup.sh -e my-enterprise \
  --exclude-forks \
  --exclude-archived \
  --output-dir /data/backups/enterprise
```

### User Backup with PAT, Shallow Clone

```bash
gh-backup.sh -u h3nryza \
  --auth pat \
  --token "${GITHUB_TOKEN}" \
  --shallow \
  --output-dir /backups/h3nryza
```

### Resume an Interrupted Backup

```bash
gh-backup.sh -o my-org \
  --output-dir /backups/my-org \
  --resume
```

Repos already present in the output directory are skipped.

### Export Manifest to a Custom Location

```bash
gh-backup.sh -o my-org --export /reports/my-org-manifest.csv
```

### Mirror Clone (for full git history and refs)

```bash
gh-backup.sh -o my-org --clone-method mirror
```

### Selective Backup via Import File

Create `repos-to-backup.txt`:
```
my-org/service-api
my-org/frontend
my-org/shared-lib
```

Then run:
```bash
gh-backup.sh -o my-org --import repos-to-backup.txt
```

### Remote Execution

Run directly without cloning the repo:
```bash
curl -fsSL \
  https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-backup/gh-backup.sh \
  | bash -s -- -u h3nryza --dry-run
```

### Interactive Mode

```bash
gh-backup.sh -i
```

Walks through target selection, auth, and options interactively.

---

## Permissions

### GitHub CLI

`gh auth login` with appropriate scopes is sufficient for most use cases.

### PAT Scopes Required

| Target | Minimum Scopes |
|--------|----------------|
| User repos | `repo` |
| User gists | `gist` |
| Org repos | `repo`, `read:org` |
| Enterprise | `repo`, `read:org`, `admin:enterprise` |

### GitHub App

The app requires the following repository permissions:
- `Contents: Read`
- `Metadata: Read`

And organisation permissions:
- `Members: Read` (to enumerate org repos)

---

## Troubleshooting

### `gh: command not found`

Install the GitHub CLI: <https://cli.github.com>

Or switch to PAT auth: `--auth pat --token <your-token>`

### `GitHub CLI is not authenticated`

Run: `gh auth login`

### Enterprise enumeration returns 0 organisations

- Ensure your token has `admin:enterprise` scope.
- Enterprise enumeration via REST requires an enterprise admin token.
- The script automatically falls back to GraphQL if REST returns empty.

### Clone failures

- For private repos over HTTPS with PAT auth, the token is injected into the clone URL automatically.
- For SSH clones, ensure your SSH key is configured: `~/.ssh/config`

### Gists not cloning

- Gists use `git_pull_url` from the API which is always HTTPS.
- Ensure `git` is installed and `github.com` is reachable.

---

## Running Tests

```bash
# Full test suite
./tests/test_backup.sh

# Verbose
./tests/test_backup.sh --verbose

# Filter by group
./tests/test_backup.sh --filter arg_parsing
./tests/test_backup.sh --filter mock_data
./tests/test_backup.sh --filter shellcheck
```

---

## Version

gh-backup v1.0.0 — Written by h3nryza
