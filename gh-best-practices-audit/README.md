# gh-best-practices-audit

**GitHub Best Practices Auditor** - Written by h3nryza

Comprehensive automated audit of GitHub Enterprise, Organization, and Repository settings against security best practices from CIS GitHub Benchmark, OWASP CI/CD Top 10, and SANS Top 25.

## Features

- **79 built-in rules** across three major security benchmarks
- Enterprise, Organization, and Repository level audits
- Custom rules via CSV or Excel files
- Multiple output formats: CSV, JSON, HTML
- Interactive mode for guided usage
- AWS Lambda support with S3 output and SNS notifications
- Severity and category filtering
- Summary scorecard with pass/fail breakdown

## Quick Start

```bash
# Install
curl -fsSL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-best-practices-audit/install.sh | bash

# Or run locally
source setup_env.sh
python gh_best_practices_audit.py -i
```

## Usage

```
gh-best-practices-audit - GitHub Best Practices Auditor
Written by h3nryza

USAGE:
  python gh_best_practices_audit.py [OPTIONS]

TARGET:
  -e, --enterprise <name>    Audit enterprise settings + all orgs
  -o, --org <name>           Audit organization + all repos
  -r, --repo <owner/repo>    Audit single repository
  --local-path <dir>         Audit local repo files (downloaded state)

RULES:
  --benchmarks <list>        Benchmarks: cis,owasp,sans,all (default: all)
  --custom-rules <file>      Custom rules file (CSV or Excel)
  --severity <level>         Min severity: critical,high,medium,low,info (default: low)
  --category <cat>           Filter: auth,branch-protection,secrets,ci-cd,access,repo-settings

AUTH:
  -a, --auth <method>        Auth: gh|pat|app (default: gh)
  -t, --token <token>        PAT token
  --app-id <id>              GitHub App ID
  --app-key <file>           App private key

OUTPUT:
  --output <file>            Output file (default: timestamped CSV)
  --format <fmt>             csv|json|html (default: csv)
  --s3-bucket <bucket>       S3 bucket for Lambda output
  --s3-prefix <prefix>       S3 key prefix
  --summary                  Print summary scorecard only

RUNTIME:
  --mode <mode>              local|lambda (default: local)
  -i, --interactive          Interactive mode
  -v, --verbose              Verbose output
  --version                  Show version
```

## Benchmarks

### CIS GitHub Benchmark (39 rules)
- 5 Enterprise-level rules (SSO, audit logging, IP allow list, GHAS, member privileges)
- 14 Organization-level rules (2FA, permissions, forking, security features)
- 20 Repository-level rules (branch protection, secret scanning, file checks)

### OWASP CI/CD Top 10 (24 rules)
- SEC-1: Insufficient Flow Control
- SEC-2: Inadequate Identity and Access Management
- SEC-3: Dependency Chain Abuse
- SEC-4: Poisoned Pipeline Execution
- SEC-5: Insufficient PBAC
- SEC-6: Insufficient Credential Hygiene
- SEC-7: Insecure System Configuration
- SEC-8: Ungoverned Usage of 3rd Party Services
- SEC-9: Improper Artifact Integrity Validation
- SEC-10: Insufficient Logging

### SANS Top 25 (16 rules)
- CWE-798: Use of Hardcoded Credentials
- CWE-284: Improper Access Control
- CWE-269: Improper Privilege Management
- CWE-311: Missing Encryption of Sensitive Data
- CWE-502: Deserialization of Untrusted Data
- CWE-829: Inclusion of Untrusted Functionality

## Examples

```bash
# Audit an organization with all benchmarks
python gh_best_practices_audit.py -o my-org

# Enterprise audit, high severity only, HTML report
python gh_best_practices_audit.py -e my-enterprise --severity high --format html

# Single repo with CIS benchmark
python gh_best_practices_audit.py -r my-org/my-repo --benchmarks cis

# Custom rules with JSON output
python gh_best_practices_audit.py -o my-org --custom-rules my_rules.csv --format json

# Local path audit
python gh_best_practices_audit.py --local-path ./repos --benchmarks all

# Interactive mode
python gh_best_practices_audit.py -i
```

## Requirements

- Python 3.9+
- GitHub CLI (`gh`) or Personal Access Token
- Optional: `openpyxl` for Excel custom rules
- Optional: `boto3` for S3 upload

## License

Written by h3nryza
