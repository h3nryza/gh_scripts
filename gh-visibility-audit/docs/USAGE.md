# gh-visibility-audit — Usage Guide

> Written by h3nryza

## Overview

`gh-visibility-audit` audits and manages GitHub repository visibility
(`public`, `private`, `internal`) across Enterprise, Organization, and User
accounts. Results are exported to CSV. The same CSV can be edited and
re-imported to bulk-update repository visibility.

---

## Installation

### Option 1 — Remote install (recommended)

```bash
curl -sL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-visibility-audit/install.sh | bash
```

This places `gh-visibility-audit` in `~/bin` (or `/usr/local/bin` when run as
root) and makes it executable.

### Option 2 — Remote execution (no install)

```bash
curl -sL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-visibility-audit/gh-visibility-audit.sh \
  | bash -s -- -o my-org
```

### Option 3 — Manual

```bash
curl -sLO https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-visibility-audit/gh-visibility-audit.sh
chmod +x gh-visibility-audit.sh
./gh-visibility-audit.sh --help
```

---

## Authentication

Three auth methods are supported via `-a` / `--auth`:

| Method | Flag value | Requirements |
|--------|-----------|--------------|
| GitHub CLI | `gh` (default) | `gh` installed and authenticated via `gh auth login` |
| Personal Access Token | `pat` | Pass token with `-t` / `--token` |
| GitHub App | `app` | Pass `--app-id` and `--app-key` (PEM file) |

### Required token scopes

| Target | Minimum scopes |
|--------|----------------|
| User repos | `repo` |
| Org repos | `repo`, `read:org` |
| Enterprise orgs | `admin:enterprise` or `read:org` |
| Update visibility | `repo` (write access to the target repo) |

---

## Audit Mode

Audits repositories and writes a CSV report.

### Audit an organisation

```bash
gh-visibility-audit.sh -o my-org
```

### Audit with a PAT and custom output file

```bash
gh-visibility-audit.sh -o my-org -a pat -t ghp_xxxxx --output org-audit.csv
```

### Audit an entire enterprise

```bash
gh-visibility-audit.sh -e my-enterprise -a pat -t ghp_xxxxx
```

Enterprise audits enumerate every organisation in the enterprise and then
fetch all repositories per organisation. This requires the token to have
`admin:enterprise` or `read:org` scope for the enterprise.

### Audit a user's repositories

```bash
gh-visibility-audit.sh -u octocat
```

### Verbose mode

```bash
gh-visibility-audit.sh -o my-org -v
```

---

## CSV Format

```
Enterprise,Organization,Owner,Repository,Visibility,URL
"","my-org","my-org","alpha-service","private","https://github.com/my-org/alpha-service"
"","my-org","my-org","beta-lib","public","https://github.com/my-org/beta-lib"
"my-ent","child-org","child-org","gamma-internal","internal","https://github.com/child-org/gamma-internal"
```

All fields are double-quoted. Internal double-quotes are escaped as `""`.

### Default output filename

If `--output` is not specified, the CSV is written to the current directory
with a timestamp:

```
2024-06-15_143022_Github_visibility.csv
```

---

## Update / Import Mode

Edit the CSV to change the `Visibility` column, then re-import it.

Valid visibility values: `public`, `private`, `internal`

> `internal` is only valid for organisations within a GitHub Enterprise.

### Dry-run (preview changes)

```bash
gh-visibility-audit.sh --import changes.csv --dry-run
```

### Apply changes

```bash
gh-visibility-audit.sh --import changes.csv -a pat -t ghp_xxxxx
```

The script reads the `Owner` column (falling back to `Organization`) to
determine the repository owner. Only `Owner`, `Repository`, and `Visibility`
fields are used during import; the others are context only.

---

## Interactive Mode

```bash
gh-visibility-audit.sh -i
```

The script will prompt you for:

1. Mode (`audit` or `import`)
2. Target type (enterprise / org / user) and name
3. Output file (audit mode) or import CSV path
4. Auth method and credentials
5. Verbose output preference

---

## Rate Limiting

All API calls are paginated (`100` results per page). If a `429` or `403`
response is received, the script automatically retries up to **3 times**
with a **5-second** back-off between attempts.

---

## Enterprise Auditing Notes

- The enterprise slug is the URL-friendly name shown in
  `https://github.com/enterprises/<slug>`.
- The script calls `/enterprises/{slug}/organizations` to list all orgs,
  then `/orgs/{org}/repos?type=all` for each.
- This may take several minutes for large enterprises.

---

## Examples Reference

```bash
# Help
gh-visibility-audit.sh --help

# Version
gh-visibility-audit.sh --version

# Interactive
gh-visibility-audit.sh -i

# Audit org (gh CLI auth)
gh-visibility-audit.sh -o acme-corp

# Audit org (PAT)
gh-visibility-audit.sh -o acme-corp -a pat -t ghp_xxxxx

# Audit user (PAT)
gh-visibility-audit.sh -u octocat -a pat -t ghp_xxxxx --output octocat_repos.csv

# Audit enterprise (PAT, verbose)
gh-visibility-audit.sh -e acme-enterprise -a pat -t ghp_xxxxx -v

# Audit enterprise (GitHub App)
gh-visibility-audit.sh -e acme-enterprise -a app --app-id 98765 --app-key /path/to/key.pem

# Dry-run import
gh-visibility-audit.sh --import audit_edited.csv --dry-run

# Apply import (PAT)
gh-visibility-audit.sh --import audit_edited.csv -a pat -t ghp_xxxxx

# Remote execution (org)
curl -sL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-visibility-audit/gh-visibility-audit.sh \
  | bash -s -- -o acme-corp

# Remote execution (enterprise, PAT)
curl -sL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-visibility-audit/gh-visibility-audit.sh \
  | bash -s -- -e acme-enterprise -a pat -t ghp_xxxxx
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `gh CLI is not authenticated` | gh CLI needs login | Run `gh auth login` |
| `Missing required tools: jq` | jq not installed | `brew install jq` / `apt install jq` |
| `API call failed after 3 attempts` | Bad token or network | Verify token scopes and network access |
| Enterprise returns no orgs | Insufficient token scope | Add `admin:enterprise` scope |
| `internal` visibility rejected | Repo not in an enterprise org | `internal` requires GitHub Enterprise |

---

*Written by h3nryza*
