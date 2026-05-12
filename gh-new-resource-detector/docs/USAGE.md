# gh-new-resource-detector — Usage Guide

**Written by h3nryza**

---

## Overview

`gh-new-resource-detector` is a Python CLI and AWS Lambda tool that detects newly
created GitHub repositories and organizations. It works at three levels:

| Level      | Flag              | What it scans                          |
|------------|-------------------|-----------------------------------------|
| Enterprise | `-e / --enterprise` | All orgs and their repos              |
| Org        | `-o / --org`        | One org's repos                       |
| User       | `-u / --user`       | One user's repos                      |

---

## Quick Start

### 1. Set up the environment

```bash
cd gh-new-resource-detector
./setup_env.sh
source .venv/bin/activate
```

### 2. Run with defaults (last 7 days, GH CLI auth)

```bash
python gh_new_resource_detector.py -o my-org
```

### 3. Interactive mode

```bash
python gh_new_resource_detector.py -i
```

---

## Authentication

### GH CLI (default)

Requires `gh auth login` first.

```bash
python gh_new_resource_detector.py -o my-org -a gh
```

### Personal Access Token (PAT)

```bash
python gh_new_resource_detector.py -o my-org -a pat -t ghp_YOUR_TOKEN
```

Required scopes: `read:org`, `read:enterprise`, `repo`

### GitHub App

```bash
python gh_new_resource_detector.py -e my-enterprise -a app --app-id 12345 --app-key /path/to/key.pem
```

---

## Filtering

### Last N days (default: 7)

```bash
python gh_new_resource_detector.py -e my-enterprise --days 30
```

### Since a specific date

```bash
python gh_new_resource_detector.py -o my-org --since 2026-01-01
```

### Resource type filter

```bash
# Only repos
python gh_new_resource_detector.py -e my-enterprise --type repos

# Only orgs (enterprise-level only)
python gh_new_resource_detector.py -e my-enterprise --type orgs

# Both (default)
python gh_new_resource_detector.py -e my-enterprise --type all
```

---

## Output

### Default: timestamped CSV in current directory

```
2026-05-10_143022_new_resources.csv
```

### Custom file

```bash
python gh_new_resource_detector.py -o my-org --output report.csv
```

### JSON format

```bash
python gh_new_resource_detector.py -o my-org --format json --output report.json
```

### CSV columns

| Column       | Description                          |
|--------------|--------------------------------------|
| Enterprise   | Enterprise slug (if applicable)      |
| Organization | Organization login                   |
| ResourceType | `repo` or `org`                      |
| Name         | Full repo name (org/repo) or org login |
| CreatedAt    | ISO 8601 creation timestamp          |
| CreatedBy    | Owner login                          |
| Visibility   | `public`, `private`, or `internal`   |
| URL          | GitHub URL                           |

---

## S3 Output (Lambda / local)

```bash
python gh_new_resource_detector.py -e my-enterprise \
  --s3-bucket my-audit-bucket \
  --s3-prefix github-reports/
```

Results are written to S3 at: `s3://my-audit-bucket/github-reports/<timestamp>_new_resources.csv`

---

## AWS Lambda

### Deploying

1. Package the Lambda:

```bash
pip install -r requirements.txt -t package/
cp gh_new_resource_detector.py lambda_handler.py package/
cd package && zip -r ../function.zip .
```

2. Create the Lambda with handler `lambda_handler.handler`.

3. Store the GitHub App private key in AWS Secrets Manager.

4. Set environment variables (optional — can be overridden by event):

| Variable              | Description                      |
|-----------------------|----------------------------------|
| `GH_ENTERPRISE`       | Enterprise slug                  |
| `GH_AUTH_METHOD`      | `app`, `pat`, or `gh`            |
| `GH_APP_ID`           | GitHub App ID                    |
| `GH_APP_SECRET_NAME`  | Secrets Manager secret name      |
| `GH_DAYS`             | Lookback window (default: 7)     |
| `GH_S3_BUCKET`        | Output S3 bucket                 |
| `GH_S3_PREFIX`        | Output S3 prefix                 |

### Event payload

```json
{
  "enterprise": "my-enterprise",
  "auth_method": "app",
  "app_id": "12345",
  "app_secret_name": "gh-app-private-key",
  "days": 7,
  "type": "all",
  "format": "csv",
  "s3_bucket": "my-audit-bucket",
  "s3_prefix": "github-audit/"
}
```

### Test Lambda locally

```bash
python lambda_handler.py '{"enterprise":"my-ent","days":7,"s3_bucket":"my-bucket"}'
```

---

## Org State Tracking

When running at enterprise level with `--type orgs` or `--type all`, the tool
maintains a state file (`.gh_detector_state.json`) to track known organizations.
New orgs detected between runs are flagged regardless of their `created_at` field.

In Lambda mode the state file lives in `/tmp/` and persists between warm invocations.

---

## Development

### Running tests

```bash
source .venv/bin/activate
pytest tests/ -v
pytest tests/ -v --cov=gh_new_resource_detector
```

### Teardown

```bash
./teardown_env.sh
```

---

## Remote Install

```bash
curl -fsSL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-new-resource-detector/install.sh | bash
```

---

*Written by h3nryza — gh-new-resource-detector v1.0.0*
