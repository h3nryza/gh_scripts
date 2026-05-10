#!/usr/bin/env python3
"""
gh_new_resource_detector.py - GitHub New Resource Detector
Written by h3nryza

Detects newly created repositories and organizations across a GitHub Enterprise,
organization, or user account. Supports local and AWS Lambda runtimes.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

import requests

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────
VERSION = "1.0.0"
SCRIPT_NAME = "gh-new-resource-detector"
AUTHOR = "h3nryza"
GITHUB_API = "https://api.github.com"
GITHUB_GRAPHQL = "https://api.github.com/graphql"
CSV_COLUMNS = [
    "Enterprise",
    "Organization",
    "ResourceType",
    "Name",
    "CreatedAt",
    "CreatedBy",
    "Visibility",
    "URL",
]
DEFAULT_DAYS = 7
MAX_RETRIES = 5
INITIAL_BACKOFF = 1.0  # seconds

log = logging.getLogger(SCRIPT_NAME)


# ─────────────────────────────────────────────
# Logging helpers
# ─────────────────────────────────────────────
class ColorFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG: "\033[0;36m",
        logging.INFO: "\033[0;32m",
        logging.WARNING: "\033[1;33m",
        logging.ERROR: "\033[0;31m",
        logging.CRITICAL: "\033[1;31m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelno, self.RESET)
        prefix = {
            logging.DEBUG: "DEBUG",
            logging.INFO: "INFO ",
            logging.WARNING: "WARN ",
            logging.ERROR: "ERROR",
            logging.CRITICAL: "CRIT ",
        }.get(record.levelno, "     ")
        return f"{color}[{prefix}]{self.RESET} {record.getMessage()}"


def setup_logging(verbose: bool = False) -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(ColorFormatter())
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, handlers=[handler])


# ─────────────────────────────────────────────
# GitHub API client
# ─────────────────────────────────────────────
class GitHubClient:
    """Thin wrapper around the GitHub REST and GraphQL APIs with rate-limit backoff."""

    def __init__(self, token: str, base_url: str = GITHUB_API) -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        """Execute a request with exponential backoff on rate-limit or server errors."""
        backoff = INITIAL_BACKOFF
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.request(
                    method, url, params=params, json=json_body, timeout=30
                )
            except requests.RequestException as exc:
                if attempt == MAX_RETRIES:
                    raise
                log.warning("Network error (attempt %d/%d): %s", attempt, MAX_RETRIES, exc)
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue

            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 204:
                return {}
            if resp.status_code == 403 and "rate limit" in resp.text.lower():
                reset_ts = int(resp.headers.get("X-RateLimit-Reset", time.time() + 60))
                wait = max(reset_ts - int(time.time()), 1)
                log.warning("Rate limit hit — sleeping %ds", wait)
                time.sleep(wait)
                continue
            if resp.status_code in (500, 502, 503, 504) and attempt < MAX_RETRIES:
                log.warning(
                    "Server error %d (attempt %d/%d), retrying in %ds",
                    resp.status_code,
                    attempt,
                    MAX_RETRIES,
                    backoff,
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue
            if resp.status_code == 404:
                log.warning("404 Not Found: %s", url)
                return None
            resp.raise_for_status()
        return None

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        return self._request("GET", url, params=params)

    def paginate(self, path: str, params: dict[str, Any] | None = None) -> Iterator[dict]:
        """Yield items from a paginated REST endpoint."""
        page_params = dict(params or {})
        page_params.setdefault("per_page", 100)
        page_params["page"] = 1

        url = path if path.startswith("http") else f"{self.base_url}{path}"

        while True:
            data = self._request("GET", url, params=page_params)
            if not data:
                break
            items = data if isinstance(data, list) else data.get("repositories", [])
            if not items:
                break
            yield from items
            if len(items) < page_params["per_page"]:
                break
            page_params["page"] += 1

    def graphql(self, query: str, variables: dict[str, Any] | None = None) -> Any:
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        return self._request("POST", GITHUB_GRAPHQL, json_body=payload)


# ─────────────────────────────────────────────
# Auth helpers
# ─────────────────────────────────────────────
def get_token_from_gh_cli() -> str:
    """Retrieve the current GH CLI token via `gh auth token`."""
    import subprocess

    result = subprocess.run(
        ["gh", "auth", "token"], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(
            "gh CLI auth failed. Run `gh auth login` first.\n" + result.stderr.strip()
        )
    token = result.stdout.strip()
    if not token:
        raise RuntimeError("gh CLI returned an empty token.")
    return token


def get_app_token(app_id: str, key_file: str) -> str:
    """Generate a GitHub App installation token using JWT."""
    try:
        import jwt  # PyJWT
    except ImportError:
        raise ImportError("PyJWT is required for App auth: pip install PyJWT cryptography")

    private_key = Path(key_file).read_text()
    now = int(time.time())
    payload = {"iat": now - 60, "exp": now + 600, "iss": app_id}
    jwt_token = jwt.encode(payload, private_key, algorithm="RS256")

    client = GitHubClient(jwt_token)
    installations = client.get("/app/installations")
    if not installations:
        raise RuntimeError("No installations found for GitHub App")
    installation_id = installations[0]["id"]

    resp = client._request(
        "POST", f"{GITHUB_API}/app/installations/{installation_id}/access_tokens"
    )
    return resp["token"]


def get_app_token_from_secrets_manager(app_id: str, secret_name: str) -> str:
    """Retrieve App private key from AWS Secrets Manager and mint a token."""
    import boto3

    sm = boto3.client("secretsmanager")
    secret = sm.get_secret_value(SecretId=secret_name)
    key_content = secret.get("SecretString", "")

    tmp_path = Path("/tmp/gh_app_key.pem")
    tmp_path.write_text(key_content)
    try:
        return get_app_token(app_id, str(tmp_path))
    finally:
        tmp_path.unlink(missing_ok=True)


def resolve_token(
    auth_method: str,
    pat_token: str | None = None,
    app_id: str | None = None,
    app_key_file: str | None = None,
    app_secret_name: str | None = None,
) -> str:
    if auth_method == "gh":
        return get_token_from_gh_cli()
    if auth_method == "pat":
        if not pat_token:
            raise ValueError("--token is required when --auth pat is used")
        return pat_token
    if auth_method == "app":
        if not app_id:
            raise ValueError("--app-id is required when --auth app is used")
        if app_secret_name:
            return get_app_token_from_secrets_manager(app_id, app_secret_name)
        if app_key_file:
            return get_app_token(app_id, app_key_file)
        raise ValueError("--app-key or AWS_SECRET_NAME env var is required when --auth app is used")
    raise ValueError(f"Unknown auth method: {auth_method}")


# ─────────────────────────────────────────────
# Resource detection
# ─────────────────────────────────────────────
def _parse_iso(dt_str: str | None) -> datetime | None:
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except ValueError:
        return None


def detect_new_repos(
    client: GitHubClient,
    org: str,
    since: datetime,
    enterprise: str = "",
) -> list[dict[str, str]]:
    """
    Fetch repositories for an org created after `since`.

    Returns a list of resource dicts suitable for CSV export.
    """
    log.debug("Scanning repos for org: %s (since %s)", org, since.date())
    results: list[dict[str, str]] = []

    for repo in client.paginate(
        f"/orgs/{org}/repos",
        params={"sort": "created", "direction": "desc", "type": "all"},
    ):
        created_at = _parse_iso(repo.get("created_at"))
        if created_at is None:
            continue
        # Repos are sorted newest-first; stop once we're past the window
        if created_at < since:
            break
        results.append(
            {
                "Enterprise": enterprise,
                "Organization": org,
                "ResourceType": "repo",
                "Name": repo.get("full_name", repo.get("name", "")),
                "CreatedAt": repo.get("created_at", ""),
                "CreatedBy": repo.get("owner", {}).get("login", ""),
                "Visibility": repo.get("visibility", repo.get("private") and "private" or "public"),
                "URL": repo.get("html_url", ""),
            }
        )

    log.info("Found %d new repo(s) in org %s", len(results), org)
    return results


def detect_new_orgs(
    client: GitHubClient,
    orgs: list[dict[str, Any]],
    since: datetime,
    enterprise: str = "",
    state_file: Path | None = None,
) -> list[dict[str, str]]:
    """
    Detect new organizations by comparing current org list against a previous state.

    If `state_file` is provided and exists, it is used as the reference. Otherwise
    falls back to checking `created_at` where available.

    Returns a list of resource dicts suitable for CSV export.
    """
    known_logins: set[str] = set()

    if state_file and state_file.exists():
        try:
            known_logins = set(json.loads(state_file.read_text()))
            log.debug("Loaded %d known orgs from state file", len(known_logins))
        except json.JSONDecodeError:
            log.warning("Could not parse state file %s — using created_at fallback", state_file)

    results: list[dict[str, str]] = []
    current_logins: list[str] = []

    for org in orgs:
        login = org.get("login", "")
        current_logins.append(login)

        if known_logins:
            if login not in known_logins:
                results.append(
                    {
                        "Enterprise": enterprise,
                        "Organization": login,
                        "ResourceType": "org",
                        "Name": login,
                        "CreatedAt": org.get("created_at", ""),
                        "CreatedBy": "",
                        "Visibility": "internal",
                        "URL": org.get("url", f"https://github.com/{login}"),
                    }
                )
        else:
            created_at = _parse_iso(org.get("created_at"))
            if created_at and created_at >= since:
                results.append(
                    {
                        "Enterprise": enterprise,
                        "Organization": login,
                        "ResourceType": "org",
                        "Name": login,
                        "CreatedAt": org.get("created_at", ""),
                        "CreatedBy": "",
                        "Visibility": "internal",
                        "URL": org.get("url", f"https://github.com/{login}"),
                    }
                )

    # Persist current state
    if state_file is not None:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(current_logins, indent=2))
        log.debug("State file updated: %s", state_file)

    log.info("Found %d new org(s) in enterprise %s", len(results), enterprise)
    return results


def enumerate_enterprise(
    client: GitHubClient,
    enterprise: str,
) -> list[dict[str, Any]]:
    """
    Return all organizations for a GitHub Enterprise using the REST API.
    Falls back to GraphQL if the REST endpoint is unavailable.
    """
    log.debug("Enumerating orgs for enterprise: %s", enterprise)

    # Try REST first (requires enterprise:admin or admin:org scope)
    orgs: list[dict[str, Any]] = list(
        client.paginate(f"/enterprises/{enterprise}/organizations")
    )
    if orgs:
        log.info("Enumerated %d org(s) via REST for enterprise %s", len(orgs), enterprise)
        return orgs

    # GraphQL fallback
    log.debug("REST returned empty; attempting GraphQL for enterprise %s", enterprise)
    query = """
    query($slug: String!, $cursor: String) {
      enterprise(slug: $slug) {
        organizations(first: 100, after: $cursor) {
          pageInfo { hasNextPage endCursor }
          nodes {
            login
            name
            url
            createdAt
          }
        }
      }
    }
    """
    cursor: str | None = None
    while True:
        resp = client.graphql(query, {"slug": enterprise, "cursor": cursor})
        if not resp or "errors" in resp:
            log.warning("GraphQL error for enterprise %s: %s", enterprise, resp)
            break
        connection = resp["data"]["enterprise"]["organizations"]
        for node in connection["nodes"]:
            orgs.append(
                {
                    "login": node["login"],
                    "name": node.get("name", node["login"]),
                    "url": node.get("url", ""),
                    "created_at": node.get("createdAt", ""),
                }
            )
        if not connection["pageInfo"]["hasNextPage"]:
            break
        cursor = connection["pageInfo"]["endCursor"]

    log.info("Enumerated %d org(s) via GraphQL for enterprise %s", len(orgs), enterprise)
    return orgs


def enumerate_user(
    client: GitHubClient,
    username: str,
) -> list[dict[str, Any]]:
    """Return all repositories for a user account."""
    log.debug("Enumerating repos for user: %s", username)
    return list(client.paginate(f"/users/{username}/repos", params={"type": "all"}))


# ─────────────────────────────────────────────
# Output
# ─────────────────────────────────────────────
def export_results(
    results: list[dict[str, str]],
    output_path: Path,
    fmt: str = "csv",
) -> None:
    """Write detection results to a CSV or JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "json":
        output_path.write_text(json.dumps(results, indent=2))
        log.info("Results written to %s (JSON, %d records)", output_path, len(results))
        return

    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)
    log.info("Results written to %s (CSV, %d records)", output_path, len(results))


def upload_to_s3(local_path: Path, bucket: str, prefix: str = "") -> str:
    """Upload a file to S3 and return the S3 URI."""
    try:
        import boto3
    except ImportError:
        raise ImportError("boto3 is required for S3 upload: pip install boto3")

    key = f"{prefix.rstrip('/')}/{local_path.name}" if prefix else local_path.name
    s3 = boto3.client("s3")
    s3.upload_file(str(local_path), bucket, key)
    uri = f"s3://{bucket}/{key}"
    log.info("Uploaded to %s", uri)
    return uri


# ─────────────────────────────────────────────
# Orchestration
# ─────────────────────────────────────────────
def run_detection(config: dict[str, Any]) -> list[dict[str, str]]:
    """
    Main detection orchestrator. Accepts a flat config dict (same keys as CLI args).
    Returns the combined list of new resource records.
    """
    token = resolve_token(
        auth_method=config.get("auth", "gh"),
        pat_token=config.get("token"),
        app_id=config.get("app_id"),
        app_key_file=config.get("app_key"),
        app_secret_name=config.get("app_secret_name"),
    )
    client = GitHubClient(token)

    since = _compute_since(config)
    resource_type = config.get("type", "all")
    enterprise = config.get("enterprise", "")
    org = config.get("org", "")
    user = config.get("user", "")
    state_file = Path(config.get("state_file", ".gh_detector_state.json"))

    results: list[dict[str, str]] = []

    if enterprise:
        orgs = enumerate_enterprise(client, enterprise)

        if resource_type in ("all", "orgs"):
            results.extend(
                detect_new_orgs(client, orgs, since, enterprise=enterprise, state_file=state_file)
            )

        if resource_type in ("all", "repos"):
            for org_item in orgs:
                org_login = org_item.get("login", "")
                if not org_login:
                    continue
                results.extend(
                    detect_new_repos(client, org_login, since, enterprise=enterprise)
                )

    elif org:
        if resource_type in ("all", "repos"):
            results.extend(detect_new_repos(client, org, since))

    elif user:
        if resource_type in ("all", "repos"):
            user_repos = enumerate_user(client, user)
            for repo in user_repos:
                created_at = _parse_iso(repo.get("created_at"))
                if created_at and created_at >= since:
                    results.append(
                        {
                            "Enterprise": "",
                            "Organization": "",
                            "ResourceType": "repo",
                            "Name": repo.get("full_name", repo.get("name", "")),
                            "CreatedAt": repo.get("created_at", ""),
                            "CreatedBy": repo.get("owner", {}).get("login", ""),
                            "Visibility": repo.get("visibility", ""),
                            "URL": repo.get("html_url", ""),
                        }
                    )

    log.info("Detection complete. Total new resources: %d", len(results))
    return results


def _compute_since(config: dict[str, Any]) -> datetime:
    if config.get("since"):
        dt = datetime.fromisoformat(config["since"])
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    days = int(config.get("days", DEFAULT_DAYS))
    return datetime.now(timezone.utc) - timedelta(days=days)


def _default_output_path(fmt: str) -> Path:
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    ext = "json" if fmt == "json" else "csv"
    return Path(f"{ts}_new_resources.{ext}")


# ─────────────────────────────────────────────
# Interactive mode
# ─────────────────────────────────────────────
def interactive_mode() -> dict[str, Any]:
    """Prompt the user for configuration parameters interactively."""
    print("\n\033[1m\033[0;36mgh-new-resource-detector — Interactive Mode\033[0m")
    print("─" * 48)

    def prompt(msg: str, default: str = "") -> str:
        suffix = f" [{default}]" if default else ""
        val = input(f"  {msg}{suffix}: ").strip()
        return val if val else default

    target = prompt("Target type (enterprise/org/user)", "org")
    config: dict[str, Any] = {}

    if target == "enterprise":
        config["enterprise"] = prompt("Enterprise name")
    elif target == "org":
        config["org"] = prompt("Organization name")
    else:
        config["user"] = prompt("Username")

    config["days"] = int(prompt("Days to look back", str(DEFAULT_DAYS)))
    config["type"] = prompt("Resource type (all/repos/orgs)", "all")
    config["auth"] = prompt("Auth method (gh/pat/app)", "gh")

    if config["auth"] == "pat":
        config["token"] = prompt("PAT token")
    elif config["auth"] == "app":
        config["app_id"] = prompt("GitHub App ID")
        config["app_key"] = prompt("Path to private key file")

    fmt = prompt("Output format (csv/json)", "csv")
    config["format"] = fmt
    config["output"] = prompt("Output file", str(_default_output_path(fmt)))

    s3_bucket = prompt("S3 bucket (leave blank to skip)", "")
    if s3_bucket:
        config["s3_bucket"] = s3_bucket
        config["s3_prefix"] = prompt("S3 prefix", "github-audit/")

    print()
    return config


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────
HELP_TEXT = f"""
\033[1m\033[0;36mgh-new-resource-detector\033[0m — GitHub New Resource Detector
Written by {AUTHOR}

\033[1mUSAGE:\033[0m
  python gh_new_resource_detector.py [OPTIONS]

\033[1mTARGET:\033[0m
  -e, --enterprise <name>    Target enterprise (enumerates orgs and repos)
  -o, --org <name>           Target organization
  -u, --user <name>          Target user

\033[1mFILTERS:\033[0m
  --since <date>             Only show resources created after this date (ISO format)
  --days <n>                 Show resources created in last N days (default: {DEFAULT_DAYS})
  --type <type>              Filter by: repos|orgs|all (default: all)

\033[1mAUTH:\033[0m
  -a, --auth <method>        Auth method: gh|pat|app (default: gh)
  -t, --token <token>        PAT token
  --app-id <id>              GitHub App ID
  --app-key <file>           GitHub App private key file

\033[1mOUTPUT:\033[0m
  --output <file>            Output file (default: YYYY-MM-DD_HHMMSS_new_resources.csv)
  --format <fmt>             Output format: csv|json (default: csv)
  --s3-bucket <bucket>       S3 bucket for output
  --s3-prefix <prefix>       S3 key prefix

\033[1mRUNTIME:\033[0m
  --mode <mode>              Runtime mode: local|lambda (default: local)
  -i, --interactive          Interactive mode
  -h, --help                 Show this help
  -v, --verbose              Verbose output
  --version                  Show version

\033[1mEXAMPLES:\033[0m
  python gh_new_resource_detector.py -e my-enterprise --days 7
  python gh_new_resource_detector.py -o my-org --since 2026-01-01
  python gh_new_resource_detector.py -u octocat --type repos
  python gh_new_resource_detector.py -e my-enterprise --format json --s3-bucket my-bucket
  python gh_new_resource_detector.py -i
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gh_new_resource_detector",
        add_help=False,
    )
    # Target
    target = parser.add_argument_group("Target")
    target.add_argument("-e", "--enterprise")
    target.add_argument("-o", "--org")
    target.add_argument("-u", "--user")
    # Filters
    filters = parser.add_argument_group("Filters")
    filters.add_argument("--since")
    filters.add_argument("--days", type=int, default=DEFAULT_DAYS)
    filters.add_argument("--type", dest="type", default="all", choices=["repos", "orgs", "all"])
    # Auth
    auth = parser.add_argument_group("Auth")
    auth.add_argument("-a", "--auth", default="gh", choices=["gh", "pat", "app"])
    auth.add_argument("-t", "--token")
    auth.add_argument("--app-id")
    auth.add_argument("--app-key")
    # Output
    output = parser.add_argument_group("Output")
    output.add_argument("--output")
    output.add_argument("--format", dest="format", default="csv", choices=["csv", "json"])
    output.add_argument("--s3-bucket")
    output.add_argument("--s3-prefix", default="github-audit/")
    # Runtime
    runtime = parser.add_argument_group("Runtime")
    runtime.add_argument("--mode", default="local", choices=["local", "lambda"])
    runtime.add_argument("-i", "--interactive", action="store_true")
    runtime.add_argument("-h", "--help", action="store_true")
    runtime.add_argument("-v", "--verbose", action="store_true")
    runtime.add_argument("--version", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"{SCRIPT_NAME} v{VERSION} — written by {AUTHOR}")
        return 0

    if args.help:
        print(HELP_TEXT)
        return 0

    setup_logging(args.verbose)

    # Print banner
    log.info("\033[1m%s v%s — written by %s\033[0m", SCRIPT_NAME, VERSION, AUTHOR)

    config: dict[str, Any]
    if args.interactive:
        config = interactive_mode()
    else:
        if not any([args.enterprise, args.org, args.user]):
            print(HELP_TEXT)
            log.error("Specify a target: --enterprise, --org, or --user")
            return 1

        config = {
            "enterprise": args.enterprise or "",
            "org": args.org or "",
            "user": args.user or "",
            "since": args.since,
            "days": args.days,
            "type": args.type,
            "auth": args.auth,
            "token": args.token,
            "app_id": args.app_id,
            "app_key": args.app_key,
            "format": args.format,
            "output": args.output or str(_default_output_path(args.format)),
            "s3_bucket": args.s3_bucket,
            "s3_prefix": args.s3_prefix,
            "mode": args.mode,
        }

    results = run_detection(config)

    output_path = Path(config["output"])
    fmt = config.get("format", "csv")
    export_results(results, output_path, fmt=fmt)

    s3_bucket = config.get("s3_bucket")
    if s3_bucket:
        upload_to_s3(output_path, s3_bucket, prefix=config.get("s3_prefix", ""))

    if not results:
        log.info("No new resources found in the specified window.")
    else:
        log.info("Summary: %d new resource(s) detected.", len(results))

    return 0


if __name__ == "__main__":
    sys.exit(main())
