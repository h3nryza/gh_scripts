# gh-version-resolver

**Audit dependency versions at scale. Resolve commit hashes to semantic versions, scan workflows and Terraform files, and track version currency.**

`gh-version-resolver` converts between commit hashes and release versions for GitHub-hosted dependencies. Perfect for security dashboards where dependencies are pinned to full commit hashes but you need human-readable versions and currency information.

**Ecosystems:** GitHub Actions | Terraform modules & providers | General git repositories
**Deployment:** Local CLI | AWS Lambda with S3 output
**Written by h3nryza**

---

## Features

- **Bidirectional Resolution** — Convert commit hash ↔ version tag (supports partial hashes, min 7 chars)
- **Workflow Scanning** — Extract and resolve GitHub Actions `uses:` references automatically
- **Terraform Support** — Parse git `?ref=` hashes and Terraform Registry version constraints
- **Version Currency** — Classify as up-to-date, patch-behind, N-1, M-1, or older
- **Bulk Operations** — Import CSV/JSON with multiple repos and resolve all at once
- **Multiple Auth Methods** — GH CLI, Personal Access Tokens (PAT), and GitHub Apps
- **Flexible Output** — CSV, JSON, or S3 upload for Lambda integration
- **Resilient API Client** — Automatic rate-limit backoff and retry logic
- **Tag Dereferencing** — Correctly handles both lightweight and annotated Git tags

---

## Installation

**Clone and setup (recommended):**
```bash
git clone https://github.com/h3nryza/gh_scripts.git
cd gh_scripts/gh-version-resolver
./setup_env.sh
source .venv/bin/activate
```

**Or install globally:**
```bash
curl -fsSL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-version-resolver/gh_version_resolver.py \
  -o /usr/local/bin/gh-version-resolver
chmod +x /usr/local/bin/gh-version-resolver
```

**Requires:** Python 3.9+, git, and a GitHub token (defaults to GH CLI auth)

---

## Quick Usage

**Resolve a single hash:**
```bash
python gh_version_resolver.py \
  --hash-to-version b4ffde65f46336ab88eb53be808477a3936bae11 \
  --repo actions/checkout
```

**Convert version to commit hash:**
```bash
python gh_version_resolver.py --version-to-hash v4.1.1 --repo actions/checkout
```

**Scan a workflow file and check version currency:**
```bash
python gh_version_resolver.py \
  --scan-file .github/workflows/ci.yml \
  --type github-action \
  --check-currency
```

**Audit all Terraform modules:**
```bash
python gh_version_resolver.py \
  --scan-dir ./infrastructure/ \
  --type terraform-module \
  --check-currency
```

**Bulk resolve from CSV/JSON:**
```bash
python gh_version_resolver.py --import dependencies.csv --check-currency
```

**Interactive mode (guided prompts):**
```bash
python gh_version_resolver.py -i
```

See **[docs/USAGE.md](docs/USAGE.md)** for complete CLI reference, output formats, Lambda deployment, and GitHub Actions secrets integration.

## Output

Results are saved as timestamped files (default: CSV):

```
2026-05-10_143022_version_resolver.csv
```

**CSV Columns:**
- `Repository` — GitHub repo (owner/repo)
- `Reference` — Where found or the input reference
- `Type` — Ecosystem type (github-action, terraform-module, etc.)
- `InputHash` — Commit hash provided or resolved
- `ResolvedVersion` — Release tag corresponding to the hash
- `LatestVersion` — Latest release at time of scan (with --check-currency)
- `Currency` — up-to-date | patch-behind | N-1 | M-1 | older | unknown
- `VersionsBehind` — Human-readable version delta

**Output formats:** CSV (default), JSON, or S3 upload via `--format` and `--s3-bucket`

## Version Currency

Currency labels tell you how current a dependency is:

| Label | Meaning | Example |
|-------|---------|---------|
| `up-to-date` | Exact match with latest | v4.1.0 is latest |
| `patch-behind` | Same major.minor, older patch | v4.1.0 when v4.1.2 is latest |
| `N-1` | One minor version behind | v4.0.x when v4.1.x is latest |
| `M-1` | One major version behind | v3.x when v4.x is latest |
| `older` | Multiple versions behind | v2.x when v5.x is latest |
| `unknown` | Cannot parse or unavailable | Non-semver tags |

## Lambda Deployment

Deploy to AWS Lambda for automated audits:

```json
{
  "mode": "scan-dir",
  "scan_dir": "/mnt/efs/terraform",
  "type": "terraform-module",
  "check_currency": true,
  "auth_method": "app",
  "app_id": "12345",
  "app_secret_name": "prod/gh-app-private-key",
  "s3_bucket": "my-audit-bucket",
  "s3_prefix": "version-resolver/"
}
```

See [docs/USAGE.md](docs/USAGE.md#lambda-deployment) for IAM permissions, environment variables, and full configuration options.

## Tests

```bash
./setup_env.sh && source .venv/bin/activate
pytest tests/ -v --cov=gh_version_resolver --cov-report=term-missing
```
