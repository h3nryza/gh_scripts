#!/usr/bin/env python3
"""
gh-pipeline-compliance - GitHub Pipeline Compliance Checker
Written by h3nryza

Checks which repos across an org/enterprise are using the organization's
reusable GitHub Actions workflows vs custom pipelines. Shows security posture
of pipeline adoption. Can also search for arbitrary file patterns.
Runs locally or as Lambda.
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional

__version__ = "1.0.0"
__author__ = "h3nryza"

# ---------------------------------------------------------------------------
# Compliance status constants
# ---------------------------------------------------------------------------
STATUS_COMPLIANT = "COMPLIANT"
STATUS_NON_COMPLIANT = "NON_COMPLIANT"
STATUS_NO_PIPELINE = "NO_PIPELINE"

CSV_COLUMNS = [
    "Enterprise",
    "Organization",
    "Repository",
    "HasWorkflows",
    "UsesRequiredWorkflow",
    "WorkflowFiles",
    "ComplianceStatus",
    "LastUpdated",
]

HELP_TEXT = """
gh-pipeline-compliance - GitHub Pipeline Compliance Checker
Written by h3nryza

USAGE:
  python gh_pipeline_compliance.py [OPTIONS]

TARGET:
  -e, --enterprise <name>    Target enterprise
  -o, --org <name>           Target organization
  -u, --user <name>          Target user

PIPELINE CHECK:
  --workflow <name>          Reusable workflow to check for
                             (e.g., "my-org/workflows/.github/workflows/ci.yml")
  --workflows-file <file>    File with list of required workflows (one per line)
  --pattern <glob>           Search for file pattern in repos
                             (e.g., ".github/workflows/*.yml")
  --search <regex>           Search file contents for pattern

AUTH:
  -a, --auth <method>        Auth: gh|pat|app (default: gh)
  -t, --token <token>        PAT token
  --app-id <id>              GitHub App ID
  --app-key <file>           App private key

OUTPUT:
  --output <file>            Output file (default: timestamped CSV)
  --format <fmt>             csv|json (default: csv)
  --s3-bucket <bucket>       S3 bucket for Lambda
  --s3-prefix <prefix>       S3 key prefix
  --summary                  Print summary stats only

RUNTIME:
  --mode <mode>              local|lambda (default: local)
  -i, --interactive          Interactive mode
  -h, --help                 Show help
  -v, --verbose              Verbose
  --version                  Version

EXAMPLES:
  # Check if org uses reusable workflow
  python gh_pipeline_compliance.py -o my-org \\
      --workflow "my-org/reusable-workflows/.github/workflows/ci.yml"

  # Check multiple required workflows from file
  python gh_pipeline_compliance.py -o my-org --workflows-file required.txt

  # Search for any workflow files
  python gh_pipeline_compliance.py -o my-org --pattern ".github/workflows/*.yml"

  # Find repos using a specific action
  python gh_pipeline_compliance.py -o my-org --search "uses: actions/checkout@v4"

  # Enterprise-wide check
  python gh_pipeline_compliance.py -e my-enterprise \\
      --workflow "my-org/reusable-workflows/.github/workflows/ci.yml"

  # JSON output to S3 (Lambda mode)
  python gh_pipeline_compliance.py -o my-org \\
      --workflow "my-org/rw/.github/workflows/ci.yml" \\
      --mode lambda --s3-bucket my-bucket --format json

  # Interactive
  python gh_pipeline_compliance.py -i
"""


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def get_token_gh_cli() -> str:
    """Retrieve token from the gh CLI."""
    import subprocess
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        token = result.stdout.strip()
        if not token:
            raise RuntimeError("gh CLI returned an empty token. Run: gh auth login")
        return token
    except FileNotFoundError:
        raise RuntimeError(
            "gh CLI not found. Install from https://cli.github.com or use --auth pat"
        )


def generate_app_jwt(app_id: str, private_key_path: str) -> str:
    """Generate a GitHub App JWT (RS256, 10-minute TTL)."""
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        import struct
    except ImportError:
        raise RuntimeError(
            "cryptography package required for App auth. "
            "Install: pip install cryptography"
        )

    with open(private_key_path, "rb") as f:
        private_key = serialization.load_pem_private_key(f.read(), password=None)

    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + (10 * 60),
        "iss": app_id,
    }

    def _b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    body = _b64url(json.dumps(payload).encode())
    signing_input = f"{header}.{body}".encode()
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{header}.{body}.{_b64url(signature)}"


def get_installation_token(jwt: str, org: str) -> str:
    """Exchange a GitHub App JWT for an installation token scoped to an org."""
    installations = github_request(
        "GET", "/app/installations", token=jwt
    )
    for inst in installations:
        acct = inst.get("account", {})
        if acct.get("login", "").lower() == org.lower():
            inst_id = inst["id"]
            resp = github_request(
                "POST",
                f"/app/installations/{inst_id}/access_tokens",
                token=jwt,
            )
            return resp["token"]
    raise RuntimeError(
        f"GitHub App not installed on org '{org}'. "
        "Install the app at https://github.com/organizations/{org}/settings/installations"
    )


def resolve_token(args: argparse.Namespace, org: Optional[str] = None) -> str:
    """Resolve a usable GitHub API token from CLI args / env."""
    method = getattr(args, "auth", "gh") or "gh"

    if method == "app":
        app_id = getattr(args, "app_id", None) or os.environ.get("GH_APP_ID")
        app_key = getattr(args, "app_key", None) or os.environ.get("GH_APP_KEY_FILE")
        if not app_id or not app_key:
            raise RuntimeError(
                "App auth requires --app-id and --app-key (or GH_APP_ID / GH_APP_KEY_FILE)"
            )
        jwt = generate_app_jwt(app_id, app_key)
        target_org = org or getattr(args, "org", None)
        if not target_org:
            raise RuntimeError("App auth requires --org to derive an installation token")
        return get_installation_token(jwt, target_org)

    if method == "pat":
        token = (
            getattr(args, "token", None)
            or os.environ.get("GITHUB_TOKEN")
            or os.environ.get("GH_TOKEN")
        )
        if not token:
            raise RuntimeError(
                "PAT auth requires --token or GITHUB_TOKEN env var"
            )
        return token

    # default: gh CLI
    token = (
        getattr(args, "token", None)
        or os.environ.get("GITHUB_TOKEN")
        or os.environ.get("GH_TOKEN")
    )
    if token:
        return token
    return get_token_gh_cli()


# ---------------------------------------------------------------------------
# GitHub API client
# ---------------------------------------------------------------------------

API_BASE = "https://api.github.com"
_rate_limit_remaining = 5000
_rate_limit_reset = 0


def github_request(
    method: str,
    path: str,
    token: str = "",
    params: Optional[dict] = None,
    body: Optional[dict] = None,
    accept: str = "application/vnd.github+json",
    retries: int = 3,
) -> Any:
    """Make a single GitHub API request with retry/backoff."""
    global _rate_limit_remaining, _rate_limit_reset

    url = f"{API_BASE}{path}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"

    data = json.dumps(body).encode() if body else None
    headers = {
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": f"gh-pipeline-compliance/{__version__}",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=30) as resp:
                _rate_limit_remaining = int(
                    resp.headers.get("X-RateLimit-Remaining", _rate_limit_remaining)
                )
                _rate_limit_reset = int(
                    resp.headers.get("X-RateLimit-Reset", _rate_limit_reset)
                )
                raw = resp.read()
                if not raw:
                    return {}
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            if exc.code == 403:
                retry_after = int(exc.headers.get("Retry-After", 0))
                reset_in = max(0, _rate_limit_reset - int(time.time()))
                wait = retry_after or reset_in or (2 ** attempt * 5)
                if attempt < retries - 1:
                    print(
                        f"  [rate-limit] waiting {wait}s before retry...",
                        file=sys.stderr,
                    )
                    time.sleep(wait)
                    continue
            if exc.code == 404:
                return None
            raise
        except urllib.error.URLError as exc:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"Network error calling {url}: {exc}") from exc
    return None


def paginate(
    path: str,
    token: str,
    params: Optional[dict] = None,
    verbose: bool = False,
) -> list[Any]:
    """Iterate through all pages of a GitHub list endpoint."""
    results: list[Any] = []
    page = 1
    per_page = 100
    base_params = dict(params or {})
    base_params["per_page"] = per_page

    while True:
        base_params["page"] = page
        data = github_request("GET", path, token=token, params=base_params)
        if not data:
            break
        if isinstance(data, dict):
            # Some endpoints wrap in a key (search results)
            items = data.get("items") or data.get("repositories") or []
        else:
            items = data
        if not items:
            break
        results.extend(items)
        if verbose:
            print(f"  [paginate] {path} page {page}: +{len(items)} items", file=sys.stderr)
        if len(items) < per_page:
            break
        page += 1
    return results


# ---------------------------------------------------------------------------
# Core compliance logic
# ---------------------------------------------------------------------------

def list_org_repos(org: str, token: str, verbose: bool = False) -> list[dict]:
    """Return all repos in an org."""
    if verbose:
        print(f"[info] Listing repos for org: {org}", file=sys.stderr)
    return paginate(f"/orgs/{org}/repos", token, verbose=verbose)


def list_enterprise_orgs(enterprise: str, token: str, verbose: bool = False) -> list[dict]:
    """Return all orgs in an enterprise (requires enterprise admin token)."""
    if verbose:
        print(f"[info] Listing orgs for enterprise: {enterprise}", file=sys.stderr)
    return paginate(f"/enterprises/{enterprise}/organizations", token, verbose=verbose)


def list_user_repos(user: str, token: str, verbose: bool = False) -> list[dict]:
    """Return all repos for a user."""
    if verbose:
        print(f"[info] Listing repos for user: {user}", file=sys.stderr)
    return paginate(f"/users/{user}/repos", token, verbose=verbose)


def get_repo_workflows_dir(
    owner: str, repo: str, token: str
) -> list[dict] | None:
    """
    List the contents of .github/workflows/ in a repo.
    Returns None if the directory does not exist (no pipeline).
    Returns [] if the directory exists but is empty.
    Returns list of file dicts on success.
    """
    result = github_request(
        "GET",
        f"/repos/{owner}/{repo}/contents/.github/workflows",
        token=token,
    )
    if result is None:
        return None
    if isinstance(result, dict) and result.get("message") == "Not Found":
        return None
    if isinstance(result, list):
        return [f for f in result if f.get("type") == "file" and f.get("name", "").endswith((".yml", ".yaml"))]
    return []


def get_file_content(owner: str, repo: str, path: str, token: str) -> str | None:
    """Fetch and decode a file's content from the GitHub Contents API."""
    result = github_request(
        "GET",
        f"/repos/{owner}/{repo}/contents/{path}",
        token=token,
    )
    if not result or not isinstance(result, dict):
        return None
    encoding = result.get("encoding", "")
    content = result.get("content", "")
    if encoding == "base64":
        return base64.b64decode(content).decode("utf-8", errors="replace")
    return content


def parse_workflow_uses(content: str) -> list[str]:
    """
    Extract all `uses:` references from a workflow YAML file.
    Handles both job-level and step-level `uses:`.
    Returns a list of reference strings.
    """
    # Match all forms of `uses:` in GitHub Actions YAML:
    #   Job-level:   uses: owner/repo/.github/workflows/name.yml@ref
    #   Step-level:  - uses: actions/checkout@v4
    #   Quoted:      uses: 'owner/repo/...'
    pattern = re.compile(
        r"""^\s*(?:-\s+)?uses\s*:\s*['"]?([^\s'"#]+)['"]?""",
        re.MULTILINE,
    )
    return pattern.findall(content)


def scan_workflows(
    owner: str,
    repo: str,
    token: str,
    required_workflows: list[str],
    content_search: Optional[str],
    verbose: bool = False,
) -> dict:
    """
    Scan a single repo's .github/workflows/ directory.

    Returns a dict with:
        has_workflows: bool
        uses_required_workflow: bool
        workflow_files: list[str]
        all_uses: list[str]
        search_matches: list[str]  (file names that matched content_search)
    """
    workflow_files_meta = get_repo_workflows_dir(owner, repo, token)

    if workflow_files_meta is None:
        return {
            "has_workflows": False,
            "uses_required_workflow": False,
            "workflow_files": [],
            "all_uses": [],
            "search_matches": [],
        }

    file_names = [f["name"] for f in workflow_files_meta]

    if not file_names:
        return {
            "has_workflows": False,
            "uses_required_workflow": False,
            "workflow_files": [],
            "all_uses": [],
            "search_matches": [],
        }

    all_uses: list[str] = []
    search_matches: list[str] = []
    search_pattern = re.compile(content_search, re.MULTILINE) if content_search else None

    for file_meta in workflow_files_meta:
        file_path = file_meta.get("path", f".github/workflows/{file_meta['name']}")
        if verbose:
            print(f"    [scan] {owner}/{repo} -> {file_path}", file=sys.stderr)

        content = get_file_content(owner, repo, file_path, token)
        if content is None:
            continue

        uses_refs = parse_workflow_uses(content)
        all_uses.extend(uses_refs)

        if search_pattern and search_pattern.search(content):
            search_matches.append(file_meta["name"])

    uses_required = False
    if required_workflows:
        for ref in all_uses:
            ref_norm = ref.split("@")[0].strip()
            for req in required_workflows:
                req_norm = req.split("@")[0].strip()
                if ref_norm == req_norm or ref == req:
                    uses_required = True
                    break
            if uses_required:
                break

    return {
        "has_workflows": True,
        "uses_required_workflow": uses_required,
        "workflow_files": file_names,
        "all_uses": all_uses,
        "search_matches": search_matches,
    }


def check_file_pattern(
    org: str, pattern: str, token: str, verbose: bool = False
) -> dict[str, list[str]]:
    """
    Use GitHub Code Search to find repos in an org matching a file pattern.
    Returns {repo_full_name: [matched_paths]}.
    """
    filename = os.path.basename(pattern)
    query = f"org:{org} filename:{filename}"
    if verbose:
        print(f"[info] Code search: {query}", file=sys.stderr)

    results: dict[str, list[str]] = {}
    page = 1
    per_page = 100

    while True:
        data = github_request(
            "GET",
            "/search/code",
            token=token,
            params={"q": query, "per_page": per_page, "page": page},
        )
        if not data or not isinstance(data, dict):
            break
        items = data.get("items", [])
        if not items:
            break
        for item in items:
            repo_name = item.get("repository", {}).get("full_name", "")
            path = item.get("path", "")
            results.setdefault(repo_name, []).append(path)
        if len(items) < per_page:
            break
        page += 1
        # Search API secondary rate limit: 1 req/sec
        time.sleep(1.0)

    return results


def check_repo_compliance(
    enterprise: str,
    org: str,
    repo: dict,
    token: str,
    required_workflows: list[str],
    content_search: Optional[str],
    verbose: bool = False,
) -> dict:
    """
    Check a single repo for pipeline compliance.
    Returns a dict matching CSV_COLUMNS.
    """
    repo_name = repo.get("name", "")
    owner = repo.get("owner", {}).get("login", org)
    updated_at = repo.get("updated_at", "")

    if verbose:
        print(f"  [check] {owner}/{repo_name}", file=sys.stderr)

    scan = scan_workflows(
        owner=owner,
        repo=repo_name,
        token=token,
        required_workflows=required_workflows,
        content_search=content_search,
        verbose=verbose,
    )

    if not scan["has_workflows"]:
        status = STATUS_NO_PIPELINE
    elif required_workflows and not scan["uses_required_workflow"]:
        status = STATUS_NON_COMPLIANT
    elif required_workflows and scan["uses_required_workflow"]:
        status = STATUS_COMPLIANT
    else:
        # No specific workflow required — just checking for presence
        status = STATUS_COMPLIANT

    return {
        "Enterprise": enterprise,
        "Organization": org,
        "Repository": repo_name,
        "HasWorkflows": scan["has_workflows"],
        "UsesRequiredWorkflow": scan["uses_required_workflow"],
        "WorkflowFiles": "|".join(scan["workflow_files"]),
        "ComplianceStatus": status,
        "LastUpdated": updated_at,
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def calculate_summary(results: list[dict]) -> dict:
    """Calculate summary statistics from a list of compliance results."""
    total = len(results)
    if total == 0:
        return {
            "total": 0,
            "compliant": 0,
            "non_compliant": 0,
            "no_pipeline": 0,
            "compliant_pct": 0.0,
            "non_compliant_pct": 0.0,
            "no_pipeline_pct": 0.0,
        }

    compliant = sum(1 for r in results if r["ComplianceStatus"] == STATUS_COMPLIANT)
    non_compliant = sum(1 for r in results if r["ComplianceStatus"] == STATUS_NON_COMPLIANT)
    no_pipeline = sum(1 for r in results if r["ComplianceStatus"] == STATUS_NO_PIPELINE)

    return {
        "total": total,
        "compliant": compliant,
        "non_compliant": non_compliant,
        "no_pipeline": no_pipeline,
        "compliant_pct": round(compliant / total * 100, 1),
        "non_compliant_pct": round(non_compliant / total * 100, 1),
        "no_pipeline_pct": round(no_pipeline / total * 100, 1),
    }


def print_summary(summary: dict, target_label: str) -> None:
    """Print a formatted summary block to stdout."""
    width = 41
    bar = "\u2501" * width
    print(f"\nPipeline Compliance Summary for {target_label}")
    print(bar)
    print(f"Total Repos:        {summary['total']}")
    print(f"Compliant:          {summary['compliant']} ({summary['compliant_pct']}%)")
    print(f"Non-Compliant:      {summary['non_compliant']} ({summary['non_compliant_pct']}%)")
    print(f"No Pipeline:        {summary['no_pipeline']} ({summary['no_pipeline_pct']}%)")
    print(bar)


def generate_report(
    results: list[dict],
    output_path: str,
    fmt: str = "csv",
) -> str:
    """Write results to a CSV or JSON file. Returns the output path."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    if fmt == "json":
        summary = calculate_summary(results)
        payload = {"summary": summary, "results": results}
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
    else:
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            for row in results:
                # Sanitise against CSV injection
                safe_row = {
                    k: (f"'{v}" if str(v).startswith(("=", "+", "-", "@")) else v)
                    for k, v in row.items()
                }
                writer.writerow(safe_row)

    return output_path


# ---------------------------------------------------------------------------
# S3 upload (Lambda mode)
# ---------------------------------------------------------------------------

def upload_to_s3(local_path: str, bucket: str, key: str) -> str:
    """Upload a file to S3 and return the s3:// URI."""
    try:
        import boto3
    except ImportError:
        raise RuntimeError("boto3 required for S3 upload. Install: pip install boto3")

    s3 = boto3.client("s3")
    s3.upload_file(local_path, bucket, key)
    return f"s3://{bucket}/{key}"


# ---------------------------------------------------------------------------
# Default output filename
# ---------------------------------------------------------------------------

def default_output_path(fmt: str = "csv") -> str:
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{ts}_pipeline_compliance.{fmt}"


# ---------------------------------------------------------------------------
# Interactive mode
# ---------------------------------------------------------------------------

def _prompt(question: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{question}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    return answer or default


def _choose(question: str, choices: list[str]) -> str:
    print(question)
    for i, c in enumerate(choices, 1):
        print(f"  {i}. {c}")
    while True:
        raw = _prompt("Enter number").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(choices):
            return choices[int(raw) - 1]
        print(f"  Please enter 1-{len(choices)}")


def interactive_mode() -> argparse.Namespace:
    """Guided interactive mode. Returns a populated Namespace."""
    print("\ngh-pipeline-compliance - Interactive Mode")
    print("Written by h3nryza\n")

    scope = _choose("Select target scope:", ["org", "enterprise", "user"])

    ns = argparse.Namespace(
        enterprise=None,
        org=None,
        user=None,
        workflow=None,
        workflows_file=None,
        pattern=None,
        search=None,
        auth="gh",
        token=None,
        app_id=None,
        app_key=None,
        output=None,
        format="csv",
        s3_bucket=None,
        s3_prefix="pipeline-compliance/",
        summary=False,
        mode="local",
        verbose=False,
        interactive=True,
    )

    if scope == "enterprise":
        ns.enterprise = _prompt("Enterprise name")
    elif scope == "org":
        ns.org = _prompt("Organization name")
    else:
        ns.user = _prompt("Username")

    check_type = _choose(
        "What do you want to check?",
        [
            "Specific reusable workflow",
            "File with list of required workflows",
            "File pattern search",
            "Content search (regex)",
            "Just list workflow files",
        ],
    )

    if check_type == "Specific reusable workflow":
        ns.workflow = _prompt(
            "Workflow ref",
            "my-org/reusable-workflows/.github/workflows/ci.yml@main",
        )
    elif check_type == "File with list of required workflows":
        ns.workflows_file = _prompt("Path to workflows file")
    elif check_type == "File pattern search":
        ns.pattern = _prompt("File pattern", ".github/workflows/*.yml")
    elif check_type == "Content search (regex)":
        ns.search = _prompt("Regex pattern", r"uses:\s+actions/checkout")

    auth = _choose("Auth method:", ["gh (GH CLI)", "pat (Personal Access Token)", "app (GitHub App)"])
    ns.auth = auth.split()[0]
    if ns.auth == "pat":
        ns.token = _prompt("PAT token (or set GITHUB_TOKEN env var)", "")
    elif ns.auth == "app":
        ns.app_id = _prompt("App ID")
        ns.app_key = _prompt("Private key file path")

    fmt = _choose("Output format:", ["csv", "json"])
    ns.format = fmt

    mode = _choose("Runtime mode:", ["local", "lambda"])
    ns.mode = mode
    if mode == "lambda":
        ns.s3_bucket = _prompt("S3 bucket")
        ns.s3_prefix = _prompt("S3 key prefix", "pipeline-compliance/")

    print(f"\n[info] Starting compliance check...")
    return ns


# ---------------------------------------------------------------------------
# Main scan orchestration
# ---------------------------------------------------------------------------

def load_required_workflows(args: argparse.Namespace) -> list[str]:
    """Collect the list of required workflows from CLI args."""
    workflows: list[str] = []
    if getattr(args, "workflow", None):
        workflows.append(args.workflow)
    if getattr(args, "workflows_file", None):
        with open(args.workflows_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    workflows.append(line)
    return workflows


def run_scan(args: argparse.Namespace) -> list[dict]:
    """
    Main scan loop. Returns a list of per-repo compliance dicts.
    """
    verbose: bool = getattr(args, "verbose", False)
    enterprise: str = getattr(args, "enterprise", None) or ""
    org_name: str = getattr(args, "org", None) or ""
    user_name: str = getattr(args, "user", None) or ""

    required_workflows = load_required_workflows(args)
    content_search: Optional[str] = getattr(args, "search", None)
    file_pattern: Optional[str] = getattr(args, "pattern", None)

    # Resolve token
    primary_org = org_name or ""
    token = resolve_token(args, org=primary_org)

    all_results: list[dict] = []

    if enterprise:
        orgs = list_enterprise_orgs(enterprise, token, verbose=verbose)
        for org in orgs:
            org_login = org.get("login", "")
            if not org_login:
                continue
            # For App auth we may need a per-org token
            org_token = token
            if getattr(args, "auth", "gh") == "app":
                try:
                    org_token = resolve_token(args, org=org_login)
                except Exception as exc:
                    print(f"  [warn] Skipping org {org_login}: {exc}", file=sys.stderr)
                    continue

            repos = list_org_repos(org_login, org_token, verbose=verbose)
            for repo in repos:
                result = check_repo_compliance(
                    enterprise=enterprise,
                    org=org_login,
                    repo=repo,
                    token=org_token,
                    required_workflows=required_workflows,
                    content_search=content_search,
                    verbose=verbose,
                )
                all_results.append(result)

    elif org_name:
        if file_pattern:
            # Use code search for pattern
            pattern_results = check_file_pattern(
                org=org_name, pattern=file_pattern, token=token, verbose=verbose
            )
            repos = list_org_repos(org_name, token, verbose=verbose)
            matched_repos = set(pattern_results.keys())
            for repo in repos:
                full_name = repo.get("full_name", f"{org_name}/{repo.get('name', '')}")
                files = pattern_results.get(full_name, [])
                result = {
                    "Enterprise": enterprise,
                    "Organization": org_name,
                    "Repository": repo.get("name", ""),
                    "HasWorkflows": bool(files),
                    "UsesRequiredWorkflow": False,
                    "WorkflowFiles": "|".join(files),
                    "ComplianceStatus": STATUS_COMPLIANT if files else STATUS_NO_PIPELINE,
                    "LastUpdated": repo.get("updated_at", ""),
                }
                all_results.append(result)
        else:
            repos = list_org_repos(org_name, token, verbose=verbose)
            for repo in repos:
                result = check_repo_compliance(
                    enterprise=enterprise,
                    org=org_name,
                    repo=repo,
                    token=token,
                    required_workflows=required_workflows,
                    content_search=content_search,
                    verbose=verbose,
                )
                all_results.append(result)

    elif user_name:
        repos = list_user_repos(user_name, token, verbose=verbose)
        for repo in repos:
            result = check_repo_compliance(
                enterprise=enterprise,
                org=user_name,
                repo=repo,
                token=token,
                required_workflows=required_workflows,
                content_search=content_search,
                verbose=verbose,
            )
            all_results.append(result)

    else:
        raise RuntimeError(
            "No target specified. Use --enterprise, --org, or --user. "
            "Run with -h for help."
        )

    return all_results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gh_pipeline_compliance",
        description="GitHub Pipeline Compliance Checker — written by h3nryza",
        add_help=False,
    )

    # Target
    tgt = parser.add_argument_group("TARGET")
    tgt.add_argument("-e", "--enterprise", metavar="<name>", help="Target enterprise")
    tgt.add_argument("-o", "--org", metavar="<name>", help="Target organization")
    tgt.add_argument("-u", "--user", metavar="<name>", help="Target user")

    # Pipeline check
    pc = parser.add_argument_group("PIPELINE CHECK")
    pc.add_argument("--workflow", metavar="<ref>", help="Reusable workflow to check for")
    pc.add_argument("--workflows-file", metavar="<file>", help="File with required workflows")
    pc.add_argument("--pattern", metavar="<glob>", help="File pattern to search for")
    pc.add_argument("--search", metavar="<regex>", help="Regex to search file contents")

    # Auth
    auth_grp = parser.add_argument_group("AUTH")
    auth_grp.add_argument("-a", "--auth", default="gh", metavar="<method>",
                          choices=["gh", "pat", "app"],
                          help="Auth method: gh|pat|app (default: gh)")
    auth_grp.add_argument("-t", "--token", metavar="<token>", help="PAT token")
    auth_grp.add_argument("--app-id", metavar="<id>", help="GitHub App ID")
    auth_grp.add_argument("--app-key", metavar="<file>", help="App private key file")

    # Output
    out = parser.add_argument_group("OUTPUT")
    out.add_argument("--output", metavar="<file>", help="Output file")
    out.add_argument("--format", default="csv", choices=["csv", "json"],
                     metavar="<fmt>", help="csv|json (default: csv)")
    out.add_argument("--s3-bucket", metavar="<bucket>", help="S3 bucket for Lambda output")
    out.add_argument("--s3-prefix", default="pipeline-compliance/", metavar="<prefix>",
                     help="S3 key prefix")
    out.add_argument("--summary", action="store_true",
                     help="Print summary stats to stdout")

    # Runtime
    rt = parser.add_argument_group("RUNTIME")
    rt.add_argument("--mode", default="local", choices=["local", "lambda"],
                    metavar="<mode>", help="local|lambda (default: local)")
    rt.add_argument("-i", "--interactive", action="store_true", help="Interactive mode")
    rt.add_argument("-h", "--help", action="store_true", help="Show help")
    rt.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    rt.add_argument("--version", action="store_true", help="Show version")

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"gh-pipeline-compliance v{__version__} — written by {__author__}")
        return 0

    if args.help:
        print(HELP_TEXT)
        return 0

    if args.interactive:
        args = interactive_mode()

    # Determine output path
    fmt = getattr(args, "format", "csv")
    output_path = getattr(args, "output", None) or default_output_path(fmt)

    try:
        results = run_scan(args)
    except RuntimeError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n[interrupted]", file=sys.stderr)
        return 130

    # Write report
    generate_report(results, output_path, fmt=fmt)

    # Upload to S3 if lambda mode
    mode = getattr(args, "mode", "local")
    s3_bucket = getattr(args, "s3_bucket", None)
    if mode == "lambda" and s3_bucket:
        s3_prefix = getattr(args, "s3_prefix", "pipeline-compliance/")
        s3_key = f"{s3_prefix}{os.path.basename(output_path)}"
        s3_uri = upload_to_s3(output_path, s3_bucket, s3_key)
        print(f"[output] Uploaded to {s3_uri}")
    else:
        print(f"[output] Report written to: {output_path}")

    # Summary
    summary = calculate_summary(results)
    if getattr(args, "summary", False) or True:
        target_label = (
            f"enterprise: {args.enterprise}" if getattr(args, "enterprise", None)
            else f"org: {args.org}" if getattr(args, "org", None)
            else f"user: {args.user}" if getattr(args, "user", None)
            else "unknown"
        )
        print_summary(summary, target_label)

    return 0


if __name__ == "__main__":
    sys.exit(main())
