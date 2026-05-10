# gh-best-practices-audit

**GitHub Best Practices Auditor** — Written by h3nryza

Automated security audit of GitHub Enterprise, Organization, and Repository settings against the CIS GitHub Benchmark, OWASP CI/CD Top 10, and SANS Top 25. Runs locally or as an AWS Lambda function.

---

## Quick Start

```bash
# One-line remote install
curl -fsSL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-best-practices-audit/install.sh | bash

# Or set up locally
git clone https://github.com/h3nryza/gh_scripts.git
cd gh_scripts/gh-best-practices-audit
source setup_env.sh

# Interactive guided mode
python gh_best_practices_audit.py -i

# Audit an organization
python gh_best_practices_audit.py -o my-org

# Audit a single repository
python gh_best_practices_audit.py -r my-org/my-repo
```

---

## What It Checks

| Benchmark | Rules | Levels |
|-----------|-------|--------|
| CIS GitHub Benchmark | 39 | Enterprise, Org, Repo |
| OWASP CI/CD Top 10 | 24 | Repo |
| SANS Top 25 | 16 | Repo |

Every check produces one of: `PASS`, `FAIL`, `SKIP`, or `ERROR`. A scored summary is printed at the end of every run.

---

## Usage

```
python gh_best_practices_audit.py [OPTIONS]

TARGET (pick one):
  -e, --enterprise <slug>    Audit enterprise + all orgs + all repos
  -o, --org <name>           Audit organization + all repos
  -r, --repo <owner/repo>    Audit a single repository
  --local-path <dir>         File-based checks on a local directory

RULES:
  --benchmarks <list>        cis,owasp,sans or all  (default: all)
  --custom-rules <file>      Custom rules CSV or Excel file
  --severity <level>         critical|high|medium|low|info  (default: low)
  --category <cat>           Filter by: auth, branch-protection, secrets,
                             ci-cd, access, repo-settings, audit

AUTH:
  -a, --auth <method>        gh|pat|app  (default: gh)
  -t, --token <token>        PAT token (required when --auth pat)
  --app-id <id>              GitHub App ID
  --app-key <file>           GitHub App private key file

OUTPUT:
  --output <file>            Output path  (default: timestamped file)
  --format <fmt>             csv|json|html  (default: csv)
  --summary                  Print scorecard only, skip file output
  --s3-bucket <bucket>       Upload report to this S3 bucket
  --s3-prefix <prefix>       S3 key prefix

RUNTIME:
  -i, --interactive          Guided interactive mode
  -v, --verbose              Show each rule result as it runs
  --version                  Print version and exit
```

---

## Examples

```bash
# All benchmarks, HTML report
python gh_best_practices_audit.py -o my-org --format html --output org_report.html

# Critical issues only — fast summary
python gh_best_practices_audit.py -o my-org --severity critical --summary

# OWASP CI/CD pipeline checks
python gh_best_practices_audit.py -o my-org --benchmarks owasp --format html

# Secrets posture review
python gh_best_practices_audit.py -o my-org --category secrets --severity high

# Branch protection audit
python gh_best_practices_audit.py -o my-org --category branch-protection --benchmarks cis,owasp

# Enterprise audit, JSON to S3
python gh_best_practices_audit.py -e my-enterprise \
  --auth pat --token "$GITHUB_TOKEN" \
  --format json \
  --s3-bucket my-security-reports

# Single repo with PAT
python gh_best_practices_audit.py -r my-org/my-repo --auth pat --token ghp_xxxx

# Local repo file checks (no API required)
python gh_best_practices_audit.py --local-path /path/to/cloned/repos

# Custom org rules on top of built-ins
python gh_best_practices_audit.py -o my-org --custom-rules rules/custom_template.csv
```

---

## Custom Rules

Extend the built-in rules with your own checks. Copy the CSV template and add rows:

```bash
cp rules/custom_template.csv my_rules.csv
# edit my_rules.csv
python gh_best_practices_audit.py -o my-org --custom-rules my_rules.csv
```

Fields: `id, name, description, category, severity, level, check_type, api_endpoint, field, expected_value, remediation`

Supported `expected_value` syntax: `true`, `false`, `enabled`, `not_null`, `>=N`, `>N`, `<=N`, or any literal string.

Excel (`.xlsx`) files are also supported if `openpyxl` is installed.

---

## AWS Lambda

Deploy `lambda_handler.py` as a Lambda function. Required environment variables:

| Variable | Description |
|----------|-------------|
| `GITHUB_TOKEN` | GitHub PAT |
| `S3_BUCKET` | S3 bucket for report output |
| `SNS_TOPIC_ARN` | (optional) SNS topic for failure alerts |

Example event payload:

```json
{ "org": "my-org", "benchmarks": "cis,owasp", "severity": "high" }
```

---

## Requirements

- Python 3.9+
- `gh` CLI (authenticated) **or** a GitHub PAT
- `openpyxl` — optional, for Excel custom rules (`pip install openpyxl`)
- `boto3` — optional, for S3 upload (`pip install boto3`)

---

## Tests

```bash
pip install -r requirements.txt
pytest tests/ -v
pytest tests/ -v --cov=gh_best_practices_audit
```

---

## Full Documentation

See [docs/USAGE.md](docs/USAGE.md) for complete reference including all flags, rule descriptions, Lambda setup, and troubleshooting.

---

Written by h3nryza
