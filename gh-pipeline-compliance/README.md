# gh-pipeline-compliance
Written by h3nryza

GitHub Pipeline Compliance Checker — checks which repos across an org/enterprise are using the organization's reusable GitHub Actions workflows vs custom pipelines. Shows security posture of pipeline adoption.

## Features

- Checks repos for reusable workflow adoption
- Supports multiple required workflows via file
- Searches for arbitrary file patterns using GitHub Code Search
- Searches workflow file contents via regex
- Enterprise-wide, org-wide, or user-level scope
- Three auth methods: GH CLI, PAT, GitHub App
- CSV and JSON output
- Summary stats with compliance percentages
- Local and AWS Lambda runtime modes
- Interactive mode for guided usage

## Quick Start

```bash
# Install
bash install.sh

# Or: source setup_env.sh && python gh_pipeline_compliance.py ...

# Check org for reusable workflow adoption
python gh_pipeline_compliance.py \
    -o my-org \
    --workflow "my-org/reusable-workflows/.github/workflows/ci.yml@main"
```

## Output

```
Pipeline Compliance Summary for org: my-org
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total Repos:        150
Compliant:          89 (59.3%)
Non-Compliant:      41 (27.3%)
No Pipeline:        20 (13.3%)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[output] Report written to: 20260510_143000_pipeline_compliance.csv
```

## CSV Columns

`Enterprise, Organization, Repository, HasWorkflows, UsesRequiredWorkflow, WorkflowFiles, ComplianceStatus, LastUpdated`

**ComplianceStatus values:** `COMPLIANT`, `NON_COMPLIANT`, `NO_PIPELINE`

## Documentation

- [USAGE.md](docs/USAGE.md) — full CLI reference and examples
- [henrysexplanation.md](docs/henrysexplanation.md) — how to automatically enforce reusable workflow adoption

## Tests

```bash
source setup_env.sh
pytest tests/ -v --cov=gh_pipeline_compliance
```

## Remote Execution

```bash
curl -sL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-pipeline-compliance/install.sh | bash
```
