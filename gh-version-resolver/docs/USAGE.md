# gh-version-resolver — Usage Guide
Written by h3nryza

## Overview

`gh-version-resolver` converts between git commit hashes and release/tag versions for GitHub-hosted
dependencies. It is particularly useful for security dashboards where dependencies are pinned to
full commit hashes (a best practice) but you need to know the corresponding human-readable version,
and whether that version is still current.

Supported ecosystems:
- **GitHub Actions** — resolve hashes in workflow YAML files
- **Terraform modules** — resolve `?ref=` hashes in `.tf` sources
- **Terraform providers** — resolve provider version constraints
- **General** — any GitHub-hosted git repository

---

## Quick Start

```bash
# Set up the virtual environment
./setup_env.sh
source .venv/bin/activate

# Resolve a single hash
python gh_version_resolver.py \
  --hash-to-version b4ffde65f46336ab88eb53be808477a3936bae11 \
  --repo actions/checkout

# Scan a workflow file and check currency
python gh_version_resolver.py \
  --scan-file .github/workflows/ci.yml \
  --type github-action \
  --check-currency

# Interactive mode
python gh_version_resolver.py -i
```

---

## CLI Reference

### Resolve Mode

| Flag | Description |
|------|-------------|
| `--hash-to-version <hash>` | Convert a commit hash to its release tag. Supports partial hashes (minimum 7 chars). |
| `--version-to-hash <ver>` | Convert a release tag/version to the commit SHA it points to. |
| `--repo <owner/repo>` | Target GitHub repository (required for single-ref modes). |

```bash
# Hash to version (full or partial hash)
python gh_version_resolver.py \
  --hash-to-version b4ffde65f46336ab88eb53be808477a3936bae11 \
  --repo actions/checkout

# Partial hash (min 7 chars)
python gh_version_resolver.py --hash-to-version b4ffde6 --repo actions/checkout

# Version to hash
python gh_version_resolver.py --version-to-hash v4.1.1 --repo actions/checkout
```

### Bulk Mode

| Flag | Description |
|------|-------------|
| `--import <file>` | Import a CSV or JSON file containing items to resolve. |
| `--scan-file <file>` | Scan a single workflow (`.yml`/`.yaml`) or Terraform (`.tf`) file. |
| `--scan-dir <dir>` | Recursively scan a directory for all workflow and Terraform files. |

```bash
# Scan a GitHub Actions workflow
python gh_version_resolver.py \
  --scan-file .github/workflows/build.yml \
  --type github-action

# Scan all Terraform files in a directory
python gh_version_resolver.py \
  --scan-dir ./infrastructure/ \
  --type terraform-module \
  --check-currency

# Bulk import from CSV
python gh_version_resolver.py --import hashes.csv --check-currency

# Bulk import from JSON
python gh_version_resolver.py --import refs.json --check-currency
```

#### Import CSV Format

The CSV must contain at minimum a `repository` and either a `hash`, `version`, or `ref` column.
A `type` column is optional (defaults to `general`).

```csv
repository,hash,type
actions/checkout,b4ffde65f46336ab88eb53be808477a3936bae11,github-action
actions/setup-python,v4.7.0,github-action
hashicorp/terraform-provider-aws,v5.31.0,terraform-provider
```

#### Import JSON Format

```json
[
  {
    "repository": "actions/checkout",
    "hash": "b4ffde65f46336ab88eb53be808477a3936bae11",
    "type": "github-action"
  },
  {
    "repository": "actions/setup-python",
    "version": "v4.7.0",
    "type": "github-action"
  }
]
```

### Version Currency

| Flag | Description |
|------|-------------|
| `--check-currency` | Compare resolved version against the latest release. |
| `--current-version <ver>` | Manually specify the "latest" version (auto-detected from GitHub if omitted). |

Currency labels in the output:

| Label | Meaning |
|-------|---------|
| `up-to-date` | Resolved version exactly matches the latest release. |
| `patch-behind` | Same major.minor, but an older patch (e.g. v4.1.0 when v4.1.1 is latest). |
| `N-1` | One minor version behind (e.g. v4.0.x when v4.1.x is latest). |
| `M-1` | One major version behind (e.g. v3.x when v4.x is latest). |
| `older` | More than one minor or major version behind. |
| `unknown` | Version could not be parsed as semver, or data was unavailable. |

```bash
# Check currency for a single hash
python gh_version_resolver.py \
  --hash-to-version b4ffde65f46336ab88eb53be808477a3936bae11 \
  --repo actions/checkout \
  --check-currency

# Specify latest manually (useful in air-gapped or rate-limited environments)
python gh_version_resolver.py \
  --hash-to-version b4ffde65f46336ab88eb53be808477a3936bae11 \
  --repo actions/checkout \
  --check-currency \
  --current-version v4.1.1
```

### Ecosystem Type

| Value | Description |
|-------|-------------|
| `github-action` | GitHub Actions workflow `uses:` references. |
| `terraform-module` | Terraform module sources (git `?ref=` and registry). |
| `terraform-provider` | Terraform provider versions. |
| `npm` | NPM packages (informational label; resolution via GitHub tags). |
| `pypi` | PyPI packages (informational label; resolution via GitHub tags). |
| `general` | Any git repository hosted on GitHub. |

### Auth

| Flag | Description |
|------|-------------|
| `-a, --auth <method>` | Auth method: `gh` (GH CLI), `pat` (personal access token), `app` (GitHub App). Default: `gh`. |
| `-t, --token <token>` | PAT token (required when `--auth pat`). |
| `--app-id <id>` | GitHub App ID (required when `--auth app`). |
| `--app-key <file>` | Path to the App private key `.pem` file (required when `--auth app` in local mode). |

```bash
# Use GH CLI auth (default)
python gh_version_resolver.py --hash-to-version abc123f --repo owner/repo

# Use a PAT
python gh_version_resolver.py \
  --auth pat \
  --token ghp_xxxxxxxxxxxx \
  --hash-to-version abc123f \
  --repo owner/repo

# Use a GitHub App
python gh_version_resolver.py \
  --auth app \
  --app-id 123456 \
  --app-key ./private-key.pem \
  --hash-to-version abc123f \
  --repo owner/repo
```

### Output

| Flag | Description |
|------|-------------|
| `--output <file>` | Output file path. Default: `YYYY-MM-DD_HHMMSS_version_resolver.csv` in the current directory. |
| `--format <fmt>` | `csv` or `json`. Default: `csv`. |
| `--s3-bucket <bucket>` | Upload output to this S3 bucket (Lambda and local). |
| `--s3-prefix <prefix>` | S3 key prefix. Default: `github-audit/`. |

#### Output CSV Columns

| Column | Description |
|--------|-------------|
| `Repository` | GitHub repository (`owner/repo`). |
| `Reference` | Where this reference was found (file:offset for scans, or the raw ref). |
| `Type` | Ecosystem type. |
| `InputHash` | The commit hash that was input or resolved. |
| `ResolvedVersion` | The release tag resolved from the hash. |
| `LatestVersion` | The latest release at time of scan (when `--check-currency` is set). |
| `Currency` | Currency label (see above). |
| `VersionsBehind` | Human-readable description of how many versions behind. |

---

## Ecosystem Details

### GitHub Actions

In workflow files, actions are pinned by commit hash as a security best practice:

```yaml
- uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11
#                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
#                          This is the full commit SHA of tag v4.1.1
```

`gh-version-resolver` extracts all `uses: owner/repo@<ref>` lines and:
1. If `<ref>` is a commit hash — calls `resolve_hash_to_version()` to find the matching tag.
2. If `<ref>` is a version tag — calls `resolve_version_to_hash()` for the commit SHA.
3. Optionally checks currency with `--check-currency`.

### Terraform Modules

**Git source with ref:**
```hcl
module "vpc" {
  source = "git::https://github.com/terraform-aws-modules/terraform-aws-vpc.git?ref=a6604474cbf51e6e2b5a069b08cdb7a81dd5c24e"
}
```
The `?ref=` value can be a commit hash, tag, or branch name.

**Terraform Registry source:**
```hcl
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"
}
```
Registry modules are resolved against the Terraform Registry API (`registry.terraform.io/v1/modules`).

---

## Secrets Field Format

This section documents how GitHub Actions secrets work for teams integrating
`gh-version-resolver` into automated pipelines or CI/CD environments where tokens
must be provided securely.

### How GitHub Actions Secrets Work

GitHub Actions secrets are encrypted environment variables stored at the repository,
environment, or organization level. They are injected into workflow runs and
referenced as:

```yaml
env:
  GH_TOKEN: ${{ secrets.GH_PAT_TOKEN }}
```

Secrets are **write-only** through the UI; their values cannot be read back once set.
They are available inside Actions steps as environment variables.

### Storing a Secret via the GitHub API

Secrets must be **encrypted** with the repository's public key before being stored.
The encryption uses [libsodium sealed boxes](https://libsodium.gitbook.io/doc/public-key_cryptography/sealed_boxes).

**Step 1: Get the repository public key**

```
GET /repos/{owner}/{repo}/actions/secrets/public-key
```

Response:
```json
{
  "key_id": "012345678912345678",
  "key":    "2Sg8iYjAxxmI2LvUXpJjkYrMxURPc8r+dB7TJyvvcCU="
}
```

The `key` field is the Base64-encoded public key (32 bytes, X25519).

**Step 2: Encrypt the secret value**

```python
from base64 import b64encode
from nacl.public import PublicKey, SealedBox

def encrypt_secret(public_key_b64: str, secret_value: str) -> str:
    """Encrypt a secret value using libsodium sealed box."""
    public_key_bytes = b64decode(public_key_b64)
    sealed_box = SealedBox(PublicKey(public_key_bytes))
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return b64encode(encrypted).decode("utf-8")
```

Required Python package: `PyNaCl` (`pip install PyNaCl`).

**Step 3: Create or update the secret**

```
PUT /repos/{owner}/{repo}/actions/secrets/{secret_name}
```

Request body:
```json
{
  "encrypted_value": "<base64-encrypted-value>",
  "key_id":          "012345678912345678"
}
```

The `key_id` must match the `key_id` returned in Step 1.

Successful response: `201 Created` (new secret) or `204 No Content` (update).

**Complete example (Python):**

```python
import os
import requests
from base64 import b64encode, b64decode
from nacl.public import PublicKey, SealedBox

GITHUB_TOKEN = os.environ["GH_TOKEN"]
REPO = "owner/repo"
SECRET_NAME = "MY_SECRET"
SECRET_VALUE = "super-secret-value"

headers = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

# Step 1: Get the public key
key_resp = requests.get(
    f"https://api.github.com/repos/{REPO}/actions/secrets/public-key",
    headers=headers,
)
key_resp.raise_for_status()
key_data = key_resp.json()
key_id = key_data["key_id"]
public_key_b64 = key_data["key"]

# Step 2: Encrypt
public_key_bytes = b64decode(public_key_b64)
sealed_box = SealedBox(PublicKey(public_key_bytes))
encrypted_bytes = sealed_box.encrypt(SECRET_VALUE.encode("utf-8"))
encrypted_b64 = b64encode(encrypted_bytes).decode("utf-8")

# Step 3: Store
put_resp = requests.put(
    f"https://api.github.com/repos/{REPO}/actions/secrets/{SECRET_NAME}",
    headers=headers,
    json={"encrypted_value": encrypted_b64, "key_id": key_id},
)
put_resp.raise_for_status()
print(f"Secret '{SECRET_NAME}' stored (HTTP {put_resp.status_code})")
```

### Secret Scopes

| Scope | API path | Who can set |
|-------|----------|-------------|
| Repository secret | `PUT /repos/{owner}/{repo}/actions/secrets/{name}` | Repo admins |
| Environment secret | `PUT /repos/{owner}/{repo}/environments/{env}/secrets/{name}` | Repo admins |
| Organization secret | `PUT /orgs/{org}/actions/secrets/{name}` | Org admins |

### Using Secrets in This Tool

When running `gh-version-resolver` in a GitHub Actions workflow, provide the token as:

```yaml
- name: Run gh-version-resolver
  env:
    GH_TOKEN: ${{ secrets.GH_PAT_TOKEN }}
  run: |
    python gh_version_resolver.py \
      --auth pat \
      --token "$GH_TOKEN" \
      --scan-dir ./terraform/ \
      --check-currency
```

For Lambda deployments, store the GitHub App private key in **AWS Secrets Manager**
and reference it via the `app_secret_name` event field or `GH_APP_SECRET_NAME` environment variable.

---

## Lambda Deployment

### Event Payload

```json
{
  "mode":             "scan-dir",
  "scan_dir":         "/mnt/efs/terraform",
  "type":             "terraform-module",
  "check_currency":   true,
  "auth_method":      "app",
  "app_id":           "12345",
  "app_secret_name":  "prod/gh-app-private-key",
  "format":           "csv",
  "s3_bucket":        "my-audit-bucket",
  "s3_prefix":        "version-resolver/"
}
```

### Supported Modes in Lambda

| Mode | Required fields |
|------|----------------|
| `hash-to-version` | `hash`, `repo` |
| `version-to-hash` | `version`, `repo` |
| `scan-file` | `scan_file` (path accessible to Lambda, e.g. via EFS) |
| `scan-dir` | `scan_dir` (path accessible to Lambda) |
| `import` | `import_items` (inline JSON array) |

### Environment Variables

All event fields can be overridden via environment variables on the Lambda function:

| Environment Variable | Event Field Equivalent |
|---------------------|------------------------|
| `GH_AUTH_METHOD` | `auth_method` |
| `GH_PAT_TOKEN` | `pat_token` |
| `GH_APP_ID` | `app_id` |
| `GH_APP_SECRET_NAME` | `app_secret_name` |
| `GH_ECOSYSTEM_TYPE` | `type` |
| `GH_CHECK_CURRENCY` | `check_currency` |
| `GH_CURRENT_VERSION` | `current_version` |
| `GH_S3_BUCKET` | `s3_bucket` |
| `GH_S3_PREFIX` | `s3_prefix` |
| `GH_FORMAT` | `format` |

### IAM Permissions

The Lambda execution role needs:
```json
{
  "Effect": "Allow",
  "Action": [
    "secretsmanager:GetSecretValue"
  ],
  "Resource": "arn:aws:secretsmanager:*:*:secret:prod/gh-app-private-key*"
},
{
  "Effect": "Allow",
  "Action": [
    "s3:PutObject"
  ],
  "Resource": "arn:aws:s3:::my-audit-bucket/version-resolver/*"
}
```

---

## Examples

### Resolve a single GitHub Actions hash

```bash
python gh_version_resolver.py \
  --hash-to-version b4ffde65f46336ab88eb53be808477a3936bae11 \
  --repo actions/checkout
```

Output (stdout summary):
```
Repository                               ResolvedVersion      Currency       VersionsBehind
────────────────────────────────────────────────────────────────────────────────────────────
actions/checkout                         v4.1.1               —
```

### Check currency of all actions in a workflow

```bash
python gh_version_resolver.py \
  --scan-file .github/workflows/ci.yml \
  --type github-action \
  --check-currency \
  --format json \
  --output results.json
```

### Scan all Terraform in a mono-repo

```bash
python gh_version_resolver.py \
  --scan-dir ./infrastructure/ \
  --type terraform-module \
  --check-currency \
  --output 2026-05-10_terraform_versions.csv
```

### Bulk resolution with PAT auth

```bash
python gh_version_resolver.py \
  --import pinned_refs.csv \
  --auth pat \
  --token "$GITHUB_TOKEN" \
  --check-currency \
  --format json
```

---

## Running Tests

```bash
# Install dependencies
./setup_env.sh
source .venv/bin/activate

# Run all tests
pytest tests/ -v

# With coverage
pytest tests/ -v --cov=gh_version_resolver --cov-report=term-missing
```
