# Henry's Explanation: How to Automatically Enforce Reusable Workflow Adoption
Written by h3nryza

> This document explains the full range of mechanisms GitHub provides to enforce reusable workflow adoption across your organization. Think of it as the "what do I do after I run the compliance checker?" guide.

---

## The Problem

You've run `gh-pipeline-compliance` and found 41 repos that have their own custom pipelines instead of using your org's reusable workflows. You can't manually audit every PR that touches `.github/workflows/`. You need **automatic enforcement**.

There are six main mechanisms available. Each has different trade-offs. Use them in combination.

---

## 1. GitHub Organization Required Workflows

**What it is:** A native GitHub feature (GA as of 2024) that lets org owners declare one or more workflows that must run and pass on all repositories in the organization before a pull request can be merged.

**Where to find it:**
`https://github.com/organizations/{your-org}/settings/actions` → scroll to **"Required workflows"**

**How it works:**
- You specify a workflow from a source repository (e.g., `.github/workflows/security.yml` in `my-org/reusable-workflows`)
- GitHub automatically adds that workflow as a required status check on every repo in the org
- The workflow runs on every PR, even if the target repo doesn't reference it
- No changes needed to individual repo workflow files

**The catch:**
This is about *running* a workflow, not *adopting* it. Repos can still have their own pipelines alongside the required one. But it guarantees your security/compliance checks run everywhere.

**Setup steps:**

```
1. Go to: https://github.com/organizations/{org}/settings/actions
2. Under "Required workflows", click "Add workflow"
3. Select source repository (e.g., "reusable-workflows")
4. Select workflow file (e.g., ".github/workflows/security.yml")
5. Select which repos it applies to: "All repositories" or specific ones
6. Click "Add workflow"
```

**Via GitHub API (automation):**

```bash
# Add required workflow to org
curl -X PUT \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/orgs/my-org/actions/required_workflows \
  -d '{
    "workflow_file_path": ".github/workflows/security.yml",
    "repository_id": 123456789
  }'
```

---

## 2. Repository Rulesets (Require Workflows)

**What it is:** Repository rulesets (available at org and repo level) allow you to define merge rules including "require a workflow to pass". Unlike branch protection rules, rulesets can be applied at org-level and cascade to all repos.

**Where to find it:**
`https://github.com/organizations/{your-org}/settings/rules`

**How rulesets differ from required workflows:**

| Feature | Required Workflows | Rulesets |
|---|---|---|
| Scope | Org-level, all repos | Org or repo level |
| Bypasses | No bypass by default | Configurable bypass actors |
| Target | All PRs | Specific branches/tags/refs |
| Insight | Basic | Rich "ruleset insights" dashboard |

**Setting up a ruleset to require workflow status checks:**

```
1. Go to: https://github.com/organizations/{org}/settings/rules
2. Click "New ruleset"
3. Name: "Require CI Pipeline"
4. Enforcement status: "Active"
5. Target: "Branches" → add pattern "main" (or "*")
6. Rules → check "Require status checks to pass"
7. Add required status check: enter the exact name of your reusable workflow job
   (e.g., "call-ci / build")
8. Save
```

**Tip:** The status check name is the workflow job name as it appears in the GitHub Checks UI. If your reusable workflow job is named `build`, the check name is `build` (or `{calling-job-name} / build` if it's a matrix).

**Via API:**

```bash
curl -X POST \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/orgs/my-org/rulesets \
  -d '{
    "name": "Require CI Pipeline",
    "target": "branch",
    "enforcement": "active",
    "conditions": {
      "ref_name": {
        "include": ["refs/heads/main", "refs/heads/master"],
        "exclude": []
      }
    },
    "rules": [
      {
        "type": "required_status_checks",
        "parameters": {
          "strict_required_status_checks_policy": false,
          "required_status_checks": [
            { "context": "call-ci / build" }
          ]
        }
      }
    ]
  }'
```

---

## 3. GitHub App: Webhook → Check Workflow Files on Push

**What it is:** A custom GitHub App that listens for `push` and `pull_request` events, reads the `.github/workflows/` directory of the target repo, and posts a failing check if the required reusable workflow is not referenced.

**Why use this:** It's the most flexible option. You can write any custom logic — check for specific `uses:` references, validate workflow structure, require specific permissions blocks, etc.

**Architecture:**

```
Push/PR event → GitHub Webhook → Your GitHub App (Lambda/Server)
                                        ↓
                          Read repo's .github/workflows/
                                        ↓
                          Parse YAML, find `uses:` references
                                        ↓
                          POST /repos/{owner}/{repo}/check-runs
                          status: "completed"
                          conclusion: "success" | "failure"
```

**Minimal implementation (Python, runs as Lambda):**

```python
import json, base64, re, hmac, hashlib
import urllib.request

REQUIRED_WORKFLOW = "my-org/reusable-workflows/.github/workflows/ci.yml"
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]

def handler(event, context):
    # 1. Verify webhook signature
    body = event["body"]
    sig = event["headers"].get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), body.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return {"statusCode": 401, "body": "Invalid signature"}

    payload = json.loads(body)
    repo = payload["repository"]["full_name"]
    sha = payload.get("after") or payload.get("pull_request", {}).get("head", {}).get("sha")
    if not sha:
        return {"statusCode": 200, "body": "No SHA"}

    # 2. Create a pending check run
    check_run_id = create_check_run(repo, sha, "pending")

    # 3. Check the workflows directory
    compliant = repo_uses_required_workflow(repo, sha)

    # 4. Update the check run
    conclusion = "success" if compliant else "failure"
    update_check_run(repo, check_run_id, conclusion)

    return {"statusCode": 200, "body": "OK"}

def repo_uses_required_workflow(repo, sha):
    url = f"https://api.github.com/repos/{repo}/contents/.github/workflows?ref={sha}"
    # ... fetch, parse YAML, check for `uses: {REQUIRED_WORKFLOW}`
    ...
```

**Deploy this app:**

```bash
# Package
zip lambda.zip app.py requirements.txt

# Deploy via AWS SAM or Terraform
# Set environment variables:
#   GITHUB_TOKEN: your app's installation token
#   WEBHOOK_SECRET: random secret matching your App's webhook config
```

**Register the webhook in your GitHub App settings:**
- Payload URL: `https://your-lambda-url/webhook`
- Content type: `application/json`
- Secret: your `WEBHOOK_SECRET`
- Events: `Push`, `Pull request`

---

## 4. Org-Level Starter Workflows

**What it is:** Starter workflows are workflow templates stored in `.github/workflow-templates/` of your org's `.github` repository. When a developer creates a new workflow in any repo in the org, GitHub suggests your starter workflows first.

**Where to configure:**
Create a public repo named `.github` in your org, then add files:

```
.github/
└── workflow-templates/
    ├── ci.yml                    # The starter workflow template
    └── ci.properties.json       # Metadata for the template
```

**Example `ci.yml`:**

```yaml
name: CI Pipeline

on: [push, pull_request]

jobs:
  call-org-ci:
    uses: my-org/reusable-workflows/.github/workflows/ci.yml@main
    secrets: inherit
```

**Example `ci.properties.json`:**

```json
{
    "name": "CI Pipeline",
    "description": "Standard CI pipeline using org reusable workflow",
    "iconName": "octicon-gear",
    "categories": ["continuous-integration"]
}
```

**Limitation:** Starter workflows are suggestions, not enforcement. A developer can still write a custom workflow. Use this alongside rulesets for full enforcement.

**Best practice:** Make your starter workflow a thin wrapper that just calls the reusable workflow with `uses:`. This makes adoption zero-effort for developers.

---

## 5. CODEOWNERS for `.github/workflows/`

**What it is:** A `CODEOWNERS` file in a repo specifies that certain file paths require review from specific individuals or teams. You can require your platform/DevOps team to review any changes to workflow files.

**How to implement:**

Create or update `.github/CODEOWNERS` in each repo (or in the org's `.github` repo as a default):

```
# Require platform team review for all workflow changes
.github/workflows/  @my-org/platform-team

# Require specific workflow file approval
.github/workflows/ci.yml  @my-org/platform-team @my-org/security-team
```

**How CODEOWNERS interacts with branch protection:**

1. Repo has a branch protection rule on `main` requiring code review
2. `.github/CODEOWNERS` specifies `@platform-team` owns `.github/workflows/`
3. Any PR that modifies workflow files requires approval from `@platform-team`
4. Platform team can review and reject non-compliant workflow changes

**Automation: applying CODEOWNERS across all repos:**

```bash
# Script to add CODEOWNERS to every repo that doesn't have one
for repo in $(gh repo list my-org --limit 1000 --json name -q '.[].name'); do
    # Check if CODEOWNERS exists
    if ! gh api "repos/my-org/$repo/contents/.github/CODEOWNERS" &>/dev/null; then
        # Create CODEOWNERS via API
        content=$(echo ".github/workflows/  @my-org/platform-team" | base64)
        gh api --method PUT "repos/my-org/$repo/contents/.github/CODEOWNERS" \
            -f message="Add CODEOWNERS for workflow files" \
            -f content="$content" \
            -f branch="main"
    fi
done
```

**Limitation:** CODEOWNERS only works when branch protection requires code review. And it's reactive — it gates changes, but doesn't prevent initial non-compliant creation.

---

## 6. Branch Protection Rules Requiring Status Checks from the Reusable Workflow

**What it is:** Branch protection rules on `main` (or other key branches) that require specific status checks to pass. If your reusable workflow provides a named check, you can require it.

**How it works:**

1. Your reusable workflow at `my-org/reusable-workflows/.github/workflows/ci.yml` defines a job:
   ```yaml
   jobs:
     build:
       runs-on: ubuntu-latest
       steps: [...]
   ```

2. When a calling workflow uses it:
   ```yaml
   jobs:
     call-ci:
       uses: my-org/reusable-workflows/.github/workflows/ci.yml@main
   ```

3. The status check name in GitHub UI is: `call-ci / build`

4. You add `call-ci / build` as a required status check in branch protection.

**Setting branch protection via API:**

```bash
curl -X PUT \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/my-org/my-repo/branches/main/protection" \
  -d '{
    "required_status_checks": {
      "strict": true,
      "checks": [
        { "context": "call-ci / build", "app_id": null }
      ]
    },
    "enforce_admins": true,
    "required_pull_request_reviews": {
      "required_approving_review_count": 1
    },
    "restrictions": null
  }'
```

**Apply to all repos in an org (automation):**

```bash
for repo in $(gh repo list my-org --limit 1000 --json name -q '.[].name'); do
    curl -sX PUT \
        -H "Authorization: Bearer $GITHUB_TOKEN" \
        -H "Accept: application/vnd.github+json" \
        "https://api.github.com/repos/my-org/$repo/branches/main/protection" \
        -d '{"required_status_checks": {"strict": false, "checks": [{"context": "call-ci / build"}]}, "enforce_admins": false, "required_pull_request_reviews": null, "restrictions": null}'
    echo "Updated $repo"
done
```

**Limitation:** You need the exact status check name. This name comes from the calling workflow's job name, not the reusable workflow. Standardize your calling job names (e.g., always `call-ci`) so the check name is predictable.

---

## Recommended Combination Strategy

Use these mechanisms together for defense in depth:

| Layer | Mechanism | Enforces | Blocks Merge | Effort |
|---|---|---|---|---|
| 1 (Proactive) | Starter Workflows | Guides new workflows toward reusable pattern | No | Low |
| 2 (Detection) | gh-pipeline-compliance | Identifies non-compliant repos | No | None (automated) |
| 3 (Soft gate) | CODEOWNERS | Requires review of workflow changes | Yes (review only) | Medium |
| 4 (Hard gate) | Required Workflows (Org setting) | Runs org workflow on all PRs | Yes | Low |
| 5 (Hard gate) | Rulesets + Status Checks | Requires reusable workflow check to pass | Yes | Medium |
| 6 (Reactive) | GitHub App + Webhooks | Custom logic, post check result | Yes | High |

**Start with:** Layer 1 (starter workflows) + Layer 4 (required workflows org setting). This is the quickest win with the least disruption to existing repos.

**Then add:** Layer 2 (this tool, scheduled weekly via Lambda + EventBridge). Gives you visibility.

**Finally:** Layer 5 (rulesets) for repos where you need strict enforcement. Layer 3 (CODEOWNERS) for change management.

---

## Scheduling This Tool as a Lambda (Weekly Report)

Set up an EventBridge rule to run the compliance checker weekly:

```json
// EventBridge rule (Terraform):
resource "aws_cloudwatch_event_rule" "weekly_compliance" {
    name                = "gh-pipeline-compliance-weekly"
    description         = "Run pipeline compliance check every Monday at 8am UTC"
    schedule_expression = "cron(0 8 ? * MON *)"
}

resource "aws_cloudwatch_event_target" "compliance_lambda" {
    rule      = aws_cloudwatch_event_rule.weekly_compliance.name
    target_id = "ComplianceLambda"
    arn       = aws_lambda_function.gh_pipeline_compliance.arn
    input     = jsonencode({
        org         = "my-org"
        workflow    = "my-org/reusable-workflows/.github/workflows/ci.yml@main"
        s3_bucket   = "my-compliance-reports"
        s3_prefix   = "pipeline-compliance/"
        format      = "json"
    })
}
```

Then send the results to Slack or email via an SNS trigger on the S3 upload event.

---

## Glossary

| Term | Definition |
|---|---|
| Reusable workflow | A workflow in one repo that other repos can call with `uses: owner/repo/.github/workflows/file.yml@ref` |
| Required workflow | An org-level setting that forces a specific workflow to run on all repos |
| Ruleset | A GitHub feature that defines merge conditions at org or repo level |
| CODEOWNERS | A file that maps file paths to required reviewers |
| Status check | A named pass/fail result reported to a commit via the Checks API |
| Branch protection | Rules on a branch (like `main`) that control what can be merged |

---

*Written by h3nryza*
