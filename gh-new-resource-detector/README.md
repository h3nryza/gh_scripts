# gh-new-resource-detector

**Written by h3nryza**

Detects newly created GitHub repositories and organizations across a GitHub
Enterprise, organization, or user account. Runs locally or as an AWS Lambda.

---

## Features

- Enumerate from enterprise → org → repo level
- Detect new repos by `created_at` field
- Detect new orgs via state-file comparison
- Local CSV/JSON output with timestamped filenames
- S3 upload for Lambda deployments
- GitHub App, PAT, or GH CLI authentication
- Exponential backoff on rate limits
- Interactive mode (`-i`)

---

## Install

```bash
# Remote
curl -fsSL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/gh-new-resource-detector/install.sh | bash

# Local
git clone https://github.com/h3nryza/gh_scripts.git
cd gh_scripts/gh-new-resource-detector
./setup_env.sh && source .venv/bin/activate
```

---

## Usage

```bash
python gh_new_resource_detector.py --help

# Scan an enterprise (last 7 days)
python gh_new_resource_detector.py -e my-enterprise --days 7

# Scan an org since a date
python gh_new_resource_detector.py -o my-org --since 2026-01-01

# Interactive
python gh_new_resource_detector.py -i
```

See [docs/USAGE.md](docs/USAGE.md) for full documentation.

---

*gh-new-resource-detector v1.0.0 — written by h3nryza*
