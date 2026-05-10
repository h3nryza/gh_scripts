# gh-pipeline-compliance — Usage Guide
Written by h3nryza

## Overview

`gh-pipeline-compliance` checks which repositories across a GitHub organization or enterprise are using the organization's reusable GitHub Actions workflows versus custom or no pipelines. It provides a security posture view of pipeline adoption.

---

## Quick Start

```bash
# 1. Set up the virtual environment
source setup_env.sh

# 2. Check an org for reusable workflow adoption
python gh_pipeline_compliance.py \
    -o my-org \
    --workflow "my-org/reusable-workflows/.github/workflows/ci.yml@main"

# 3. View the report
cat 20260510_143000_pipeline_compliance.csv
```

---

## Installation

### Local (from repo)

```bash
git clone https://github.com/h3nryza/gh_scripts.git
cd gh_scripts/gh-pipeline-compliance
bash install.sh
```

### Remote (no clone needed)

```bash
curl -sL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-pipeline-compliance/install.sh | bash
```

### Manual (Python only)

```bash
pip install -r requirements.txt
python gh_pipeline_compliance.py --help
```

---

## Authentication

### GH CLI (default, recommended for local use)

```bash
gh auth login
python gh_pipeline_compliance.py -o my-org --workflow "..."
```

### Personal Access Token

```bash
# Via environment variable (recommended)
export GITHUB_TOKEN="ghp_your_token_here"
python gh_pipeline_compliance.py -o my-org --workflow "..."

# Via flag
python gh_pipeline_compliance.py -o my-org --auth pat --token "ghp_..." --workflow "..."
```

**Required PAT scopes:**
- `repo` (for private repos)
- `read:org` (for org repo listing)
- `read:enterprise` (for enterprise listing — classic PAT only)

### GitHub App (recommended for Lambda / CI)

```bash
export GH_APP_ID="123456"
export GH_APP_KEY_FILE="/path/to/private-key.pem"

python gh_pipeline_compliance.py \
    -o my-org \
    --auth app \
    --workflow "my-org/reusable-workflows/.github/workflows/ci.yml@main"
```

**Required App permissions:**
- `Contents: Read` (to read workflow files)
- `Metadata: Read` (to list repos)
- `Members: Read` (for enterprise org listing)

---

## Usage Examples

### Check a single required workflow

```bash
python gh_pipeline_compliance.py \
    -o my-org \
    --workflow "my-org/reusable-workflows/.github/workflows/ci.yml@main"
```

### Check multiple required workflows from a file

```bash
# Create required.txt
cat > required.txt <<EOF
my-org/reusable-workflows/.github/workflows/ci.yml@main
my-org/reusable-workflows/.github/workflows/security.yml@main
my-org/reusable-workflows/.github/workflows/deploy.yml@main
EOF

python gh_pipeline_compliance.py -o my-org --workflows-file required.txt
```

### Search for any workflow files (pattern search)

```bash
# Uses GitHub Code Search API — fast, doesn't need to iterate Contents API
python gh_pipeline_compliance.py \
    -o my-org \
    --pattern ".github/workflows/*.yml"
```

### Search file contents for a regex pattern

```bash
# Find repos using a specific action
python gh_pipeline_compliance.py \
    -o my-org \
    --search "uses: actions/checkout@v4"

# Find repos with hardcoded secrets (example)
python gh_pipeline_compliance.py \
    -o my-org \
    --search "password:\s+['\"]?[A-Za-z0-9]"
```

### Enterprise-wide check

```bash
python gh_pipeline_compliance.py \
    -e my-enterprise \
    --workflow "my-org/reusable-workflows/.github/workflows/ci.yml@main" \
    --auth app
```

### JSON output

```bash
python gh_pipeline_compliance.py \
    -o my-org \
    --workflow "my-org/rw/.github/workflows/ci.yml" \
    --format json \
    --output report.json
```

### Summary only (no file output)

```bash
python gh_pipeline_compliance.py \
    -o my-org \
    --workflow "my-org/rw/.github/workflows/ci.yml" \
    --summary
```

### Interactive mode

```bash
python gh_pipeline_compliance.py -i
```

### Verbose mode (debug API calls)

```bash
python gh_pipeline_compliance.py \
    -o my-org \
    --workflow "my-org/rw/.github/workflows/ci.yml" \
    --verbose
```

---

## Lambda Deployment

### Quick deploy with AWS SAM

```bash
# Package
zip -r gh-pipeline-compliance.zip gh_pipeline_compliance.py lambda_handler.py

# Or use SAM template (see lambda/ directory)
sam build
sam deploy --guided
```

### Event payload

```json
{
    "org": "my-org",
    "workflow": "my-org/reusable-workflows/.github/workflows/ci.yml@main",
    "auth": "pat",
    "s3_bucket": "my-compliance-reports",
    "s3_prefix": "pipeline-compliance/",
    "format": "csv",
    "verbose": false
}
```

### Environment variables for Lambda

| Variable | Description |
|---|---|
| `GITHUB_TOKEN` | PAT token |
| `GH_APP_ID` | GitHub App ID |
| `GH_APP_KEY_FILE` | Path to App private key |
| `S3_BUCKET` | Default S3 bucket |
| `S3_PREFIX` | Default S3 key prefix |

### Lambda response

```json
{
    "statusCode": 200,
    "body": {
        "version": "1.0.0",
        "output": "s3://my-bucket/pipeline-compliance/20260510_143000_pipeline_compliance.csv",
        "summary": {
            "total": 150,
            "compliant": 89,
            "non_compliant": 41,
            "no_pipeline": 20,
            "compliant_pct": 59.3,
            "non_compliant_pct": 27.3,
            "no_pipeline_pct": 13.3
        }
    }
}
```

---

## Output Format

### CSV columns

| Column | Type | Description |
|---|---|---|
| `Enterprise` | string | Enterprise name (empty if not applicable) |
| `Organization` | string | GitHub organization login |
| `Repository` | string | Repository name |
| `HasWorkflows` | bool | Whether `.github/workflows/` contains YAML files |
| `UsesRequiredWorkflow` | bool | Whether any workflow uses the required reusable workflow |
| `WorkflowFiles` | string | Pipe-separated list of workflow file names |
| `ComplianceStatus` | string | `COMPLIANT`, `NON_COMPLIANT`, or `NO_PIPELINE` |
| `LastUpdated` | ISO 8601 | Repository's last updated timestamp |

### Compliance status definitions

| Status | Meaning |
|---|---|
| `COMPLIANT` | Repo uses the required reusable workflow |
| `NON_COMPLIANT` | Repo has workflows but does not use the required one |
| `NO_PIPELINE` | Repo has no `.github/workflows/` files at all |

### Summary output

```
Pipeline Compliance Summary for org: my-org
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total Repos:        150
Compliant:          89 (59.3%)
Non-Compliant:      41 (27.3%)
No Pipeline:        20 (13.3%)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Running Tests

```bash
# Set up venv first
source setup_env.sh

# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=gh_pipeline_compliance --cov-report=term-missing

# Run a specific test class
pytest tests/test_compliance.py::TestCalculateSummary -v
```

---

## Feeding This Tool's Output Into Other Tools

The CSV output is designed to chain with other `gh_scripts` tools:

```bash
# 1. Run compliance check
python gh_pipeline_compliance.py -o my-org \
    --workflow "my-org/rw/.github/workflows/ci.yml"

# 2. Feed non-compliant repos into gh-best-practices-audit
# (filter the CSV, extract repo names, pass to audit tool)
awk -F, '$8 == "NON_COMPLIANT" {print $3}' 20260510_*_pipeline_compliance.csv \
    > non_compliant_repos.txt
```

---

## Troubleshooting

### Rate limiting

The tool automatically backs off when GitHub's rate limit is hit. For large orgs (500+ repos), use a GitHub App token (15,000 req/hr vs 5,000 for PAT).

### 403 on enterprise endpoint

Enterprise API requires an enterprise admin PAT or GitHub App with enterprise-level installation. Standard org admin tokens won't work for `/enterprises/{enterprise}/organizations`.

### Empty workflow files

Some repos may have `.github/workflows/` with no `.yml` files (e.g., only `.json` or template files). These are treated as `NO_PIPELINE`.

### App auth: "not installed on org"

The GitHub App must be installed on the target organization. Visit:
`https://github.com/organizations/{org}/settings/installations`

---

*Written by h3nryza*
