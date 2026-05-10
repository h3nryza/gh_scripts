# gh-best-practices-audit - Usage Guide

Written by h3nryza

## Overview

`gh-best-practices-audit` performs comprehensive automated audits of GitHub Enterprise, Organization, and Repository settings against security best practices from three major benchmarks:

- **CIS GitHub Benchmark** - 39 rules covering enterprise, org, and repo settings
- **OWASP CI/CD Top 10** - 24 rules mapping CI/CD security risks to GitHub
- **SANS Top 25** - 16 rules mapping CWE entries to GitHub settings

## Quick Start

```bash
# Install remotely
curl -fsSL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-best-practices-audit/install.sh | bash

# Or set up locally
source setup_env.sh

# Run interactively
python gh_best_practices_audit.py -i

# Audit an organization
python gh_best_practices_audit.py -o my-org

# Audit a single repo
python gh_best_practices_audit.py -r my-org/my-repo
```

## Authentication

The tool supports three authentication methods:

### GitHub CLI (default)
```bash
# Ensure you're logged in
gh auth login
python gh_best_practices_audit.py -o my-org
```

### Personal Access Token
```bash
python gh_best_practices_audit.py -o my-org --auth pat --token ghp_xxxxxxxxxxxx
```

Required PAT scopes:
- `repo` - Full repo access
- `admin:org` - Org settings (for org audit)
- `admin:enterprise` - Enterprise settings (for enterprise audit)
- `read:org` - Org membership

### GitHub App
```bash
python gh_best_practices_audit.py -o my-org --auth app --app-id 12345 --app-key key.pem
```

## Target Selection

### Enterprise Audit
Audits enterprise settings, then discovers all organizations and audits each one (including their repositories):
```bash
python gh_best_practices_audit.py -e my-enterprise
```

### Organization Audit
Audits organization settings, then discovers all repositories and audits each one:
```bash
python gh_best_practices_audit.py -o my-org
```

### Single Repository Audit
Audits a single repository:
```bash
python gh_best_practices_audit.py -r my-org/my-repo
```

### Local Path Audit
Audits local files (checks for .gitignore, README, LICENSE, CODEOWNERS):
```bash
python gh_best_practices_audit.py --local-path ./my-repos
```

## Benchmark Selection

```bash
# All benchmarks (default)
python gh_best_practices_audit.py -o my-org --benchmarks all

# CIS only
python gh_best_practices_audit.py -o my-org --benchmarks cis

# Multiple benchmarks
python gh_best_practices_audit.py -o my-org --benchmarks cis,owasp

# SANS only
python gh_best_practices_audit.py -o my-org --benchmarks sans
```

## Severity Filtering

Only check rules at or above a minimum severity:
```bash
# Critical only
python gh_best_practices_audit.py -o my-org --severity critical

# High and above
python gh_best_practices_audit.py -o my-org --severity high

# Medium and above
python gh_best_practices_audit.py -o my-org --severity medium
```

## Category Filtering

Filter by specific security category:
```bash
python gh_best_practices_audit.py -o my-org --category auth
python gh_best_practices_audit.py -o my-org --category branch-protection
python gh_best_practices_audit.py -o my-org --category secrets
python gh_best_practices_audit.py -o my-org --category ci-cd
python gh_best_practices_audit.py -o my-org --category access
python gh_best_practices_audit.py -o my-org --category repo-settings
```

## Custom Rules

Create custom rules using the CSV template:
```bash
# Copy and modify the template
cp rules/custom_template.csv my_rules.csv
# Edit my_rules.csv with your custom rules

# Run with custom rules
python gh_best_practices_audit.py -o my-org --custom-rules my_rules.csv
```

Excel files (.xlsx) are also supported if `openpyxl` is installed.

### Custom Rule Fields

| Field | Description | Values |
|-------|-------------|--------|
| id | Unique rule identifier | e.g., CUSTOM-001 |
| name | Short rule name | Free text |
| description | Detailed description | Free text |
| category | Security category | auth, branch-protection, secrets, ci-cd, access, repo-settings |
| severity | Severity level | critical, high, medium, low, info |
| level | Check level | enterprise, organization, repository |
| check_type | Type of check | api, branch_protection, file_exists, file_exists_multi |
| api_endpoint | GitHub API endpoint | e.g., /repos/{owner}/{repo} |
| field | JSON field to check | Dot notation, e.g., security_and_analysis.secret_scanning.status |
| expected_value | Expected value | true, false, string, number, >=N, not_null |
| remediation | How to fix | Free text |

## Output Formats

### CSV (default)
```bash
python gh_best_practices_audit.py -o my-org --format csv
```

### JSON
```bash
python gh_best_practices_audit.py -o my-org --format json
```

### HTML
```bash
python gh_best_practices_audit.py -o my-org --format html
```

### Summary Only
```bash
python gh_best_practices_audit.py -o my-org --summary
```

### Custom Output File
```bash
python gh_best_practices_audit.py -o my-org --output my_report.csv
```

## AWS Lambda Deployment

### Environment Variables
| Variable | Description | Required |
|----------|-------------|----------|
| GITHUB_TOKEN | GitHub PAT | Yes |
| S3_BUCKET | Output S3 bucket | Yes |
| S3_PREFIX | S3 key prefix | No |
| BENCHMARKS | Benchmark list | No (default: all) |
| SEVERITY | Min severity | No (default: low) |
| OUTPUT_FORMAT | Output format | No (default: json) |
| SNS_TOPIC_ARN | SNS topic for alerts | No |

### Event Payload
```json
{
  "org": "my-org",
  "benchmarks": "cis,owasp",
  "severity": "high"
}
```

### S3 Output from CLI
```bash
python gh_best_practices_audit.py -o my-org --s3-bucket my-bucket --s3-prefix audits/
```

## Examples

### Full enterprise audit with HTML report
```bash
python gh_best_practices_audit.py -e my-enterprise --format html --output enterprise_audit.html -v
```

### Quick critical-only org check
```bash
python gh_best_practices_audit.py -o my-org --severity critical --summary
```

### CI/CD security audit
```bash
python gh_best_practices_audit.py -o my-org --benchmarks owasp --category ci-cd
```

### Secrets posture check
```bash
python gh_best_practices_audit.py -o my-org --category secrets --severity high
```

### Local repo file audit
```bash
python gh_best_practices_audit.py --local-path /path/to/repos --benchmarks cis
```

### Repo audit with PAT and JSON output
```bash
python gh_best_practices_audit.py -r my-org/my-repo \
  --auth pat --token ghp_xxxx \
  --format json --output repo_audit.json
```
