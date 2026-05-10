#!/usr/bin/env python3
"""
gh_version_resolver.py - GitHub Version Resolver
Written by h3nryza

Resolves between git commit hashes and release/tag versions.
Supports GitHub Actions, Terraform modules/providers, and general git repos.
Reports version currency (up-to-date, patch-behind, N-1, M-1, or older).
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

import requests

try:
    import semver as semver_lib
    _HAS_SEMVER = True
except ImportError:
    _HAS_SEMVER = False

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────
VERSION = "1.0.0"
SCRIPT_NAME = "gh-version-resolver"
AUTHOR = "h3nryza"
GITHUB_API = "https://api.github.com"
TF_REGISTRY_API = "https://registry.terraform.io/v1"

CSV_COLUMNS = [
    "Repository",
    "Reference",
    "Type",
    "InputHash",
    "ResolvedVersion",
    "LatestVersion",
    "Currency",
    "VersionsBehind",
]

# Minimum hash length for partial matching
MIN_HASH_LEN = 7

# Rate-limit / retry config
MAX_RETRIES = 5
INITIAL_BACKOFF = 1.0

# Ecosystem types
ECOSYSTEM_GITHUB_ACTION = "github-action"
ECOSYSTEM_TF_MODULE = "terraform-module"
ECOSYSTEM_TF_PROVIDER = "terraform-provider"
ECOSYSTEM_NPM = "npm"
ECOSYSTEM_PYPI = "pypi"
ECOSYSTEM_GENERAL = "general"

VALID_ECOSYSTEMS = [
    ECOSYSTEM_GITHUB_ACTION,
    ECOSYSTEM_TF_MODULE,
    ECOSYSTEM_TF_PROVIDER,
    ECOSYSTEM_NPM,
    ECOSYSTEM_PYPI,
    ECOSYSTEM_GENERAL,
]

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
    logging.basicConfig(level=level, handlers=[handler], force=True)


# ─────────────────────────────────────────────
# Auth helpers
# ─────────────────────────────────────────────
def get_token_from_gh_cli() -> str:
    """Retrieve the current GH CLI token via `gh auth token`."""
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

    # Use a temporary client with the JWT to get an installation token
    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    )
    resp = session.get(f"{GITHUB_API}/app/installations", timeout=30)
    resp.raise_for_status()
    installations = resp.json()
    if not installations:
        raise RuntimeError("No installations found for GitHub App")
    installation_id = installations[0]["id"]

    resp = session.post(
        f"{GITHUB_API}/app/installations/{installation_id}/access_tokens", timeout=30
    )
    resp.raise_for_status()
    return resp.json()["token"]


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
    """Resolve a GitHub auth token from the configured method."""
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
        raise ValueError(
            "--app-key or GH_APP_SECRET_NAME env var is required when --auth app is used"
        )
    raise ValueError(f"Unknown auth method: {auth_method}")


# ─────────────────────────────────────────────
# GitHub API client
# ─────────────────────────────────────────────
class GitHubClient:
    """Thin wrapper around the GitHub REST API with rate-limit backoff."""

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
                log.debug("404 Not Found: %s", url)
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
            items = data if isinstance(data, list) else []
            if not items:
                break
            yield from items
            if len(items) < page_params["per_page"]:
                break
            page_params["page"] += 1


# ─────────────────────────────────────────────
# Semver / version helpers
# ─────────────────────────────────────────────
_RE_SEMVER_LOOSE = re.compile(
    r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:[-.]?(alpha|beta|rc|pre)[.\-]?\d*)?$",
    re.IGNORECASE,
)


def parse_semver(version_str: str) -> tuple[int, int, int, str] | None:
    """
    Parse a version string into (major, minor, patch, pre_release).

    Handles semver, vX, vX.Y, vX.Y.Z, and loose pre-release tags.
    Returns None for non-parseable strings.
    """
    v = version_str.strip().lstrip("v")
    if _HAS_SEMVER:
        try:
            sv = semver_lib.VersionInfo.parse(v)
            return (sv.major, sv.minor, sv.patch, sv.prerelease or "")
        except ValueError:
            pass
    # Fallback loose parser
    m = _RE_SEMVER_LOOSE.match(version_str.strip())
    if not m:
        return None
    major = int(m.group(1))
    minor = int(m.group(2) or 0)
    patch = int(m.group(3) or 0)
    pre = m.group(4) or ""
    return (major, minor, patch, pre.lower())


def is_stable_release(version_str: str) -> bool:
    """Return True if the version string is not a pre-release / RC / alpha / beta."""
    lower = version_str.lower()
    for kw in ("alpha", "beta", "rc", "pre", "dev", "nightly", "snapshot"):
        if kw in lower:
            return False
    parsed = parse_semver(version_str)
    if parsed and parsed[3]:
        return False
    return True


def compare_versions(a: str, b: str) -> int:
    """
    Compare two version strings.

    Returns: -1 if a < b, 0 if a == b, 1 if a > b
    """
    pa = parse_semver(a)
    pb = parse_semver(b)
    if pa is None or pb is None:
        # Fall back to string comparison
        return (a > b) - (a < b)
    # Compare (major, minor, patch) tuples; pre-release is lower than release
    va = (pa[0], pa[1], pa[2])
    vb = (pb[0], pb[1], pb[2])
    if va < vb:
        return -1
    if va > vb:
        return 1
    # Same (major, minor, patch): pre-release < release
    if pa[3] and not pb[3]:
        return -1
    if not pa[3] and pb[3]:
        return 1
    return 0


# ─────────────────────────────────────────────
# Version currency logic
# ─────────────────────────────────────────────
CURRENCY_UP_TO_DATE = "up-to-date"
CURRENCY_PATCH_BEHIND = "patch-behind"
CURRENCY_N1 = "N-1"
CURRENCY_M1 = "M-1"
CURRENCY_OLDER = "older"
CURRENCY_UNKNOWN = "unknown"


def check_version_currency(
    resolved_version: str,
    latest_version: str,
) -> tuple[str, str]:
    """
    Determine how current `resolved_version` is relative to `latest_version`.

    Returns (currency_label, versions_behind_description).

    Currency labels:
      up-to-date    - exact match with latest
      patch-behind  - same major.minor, older patch
      N-1           - one minor version behind (same major)
      M-1           - one major version behind
      older         - more than one major behind
      unknown       - cannot parse versions
    """
    if not resolved_version or not latest_version:
        return CURRENCY_UNKNOWN, ""

    pr = parse_semver(resolved_version)
    pl = parse_semver(latest_version)

    if pr is None or pl is None:
        # Non-semver: equality check only
        if resolved_version == latest_version:
            return CURRENCY_UP_TO_DATE, ""
        return CURRENCY_UNKNOWN, ""

    if compare_versions(resolved_version, latest_version) == 0:
        return CURRENCY_UP_TO_DATE, ""

    major_diff = pl[0] - pr[0]
    minor_diff = pl[1] - pr[1]
    patch_diff = pl[2] - pr[2]

    if major_diff == 0 and minor_diff == 0 and patch_diff > 0:
        return CURRENCY_PATCH_BEHIND, f"{patch_diff} patch(es)"

    if major_diff == 0 and minor_diff == 1:
        return CURRENCY_N1, f"{minor_diff} minor version(s)"

    if major_diff == 0 and minor_diff > 1:
        return CURRENCY_OLDER, f"{minor_diff} minor version(s)"

    if major_diff == 1:
        return CURRENCY_M1, f"{major_diff} major version(s)"

    if major_diff > 1:
        return CURRENCY_OLDER, f"{major_diff} major version(s)"

    # resolved is somehow newer than latest (pre-release edge case)
    return CURRENCY_UP_TO_DATE, ""


# ─────────────────────────────────────────────
# GitHub tag/release resolution
# ─────────────────────────────────────────────
def get_latest_release(client: GitHubClient, repo: str) -> str | None:
    """
    Return the tag name of the latest stable release for a GitHub repo.

    First tries the /releases/latest endpoint (skips pre-releases and drafts).
    Falls back to listing all tags and picking the highest semver.
    """
    data = client.get(f"/repos/{repo}/releases/latest")
    if data and isinstance(data, dict):
        tag = data.get("tag_name", "")
        if tag and is_stable_release(tag):
            log.debug("Latest release for %s: %s", repo, tag)
            return tag

    # Fallback: scan all tags
    log.debug("Falling back to tag scan for latest version of %s", repo)
    best: str | None = None
    for tag in client.paginate(f"/repos/{repo}/tags"):
        name = tag.get("name", "")
        if not is_stable_release(name):
            continue
        if best is None or compare_versions(name, best) > 0:
            best = name

    log.debug("Best tag found for %s: %s", repo, best)
    return best


def resolve_hash_to_version(
    client: GitHubClient,
    commit_hash: str,
    repo: str,
) -> str | None:
    """
    Resolve a (possibly partial) commit hash to a release version tag.

    Iterates through all tags in the repo and matches by SHA prefix.
    Returns the tag name, or None if no match is found.
    """
    if len(commit_hash) < MIN_HASH_LEN:
        raise ValueError(
            f"Hash must be at least {MIN_HASH_LEN} characters, got: {commit_hash!r}"
        )

    prefix = commit_hash.lower()
    log.debug("Resolving hash %s in repo %s", prefix, repo)

    for tag in client.paginate(f"/repos/{repo}/tags"):
        tag_name = tag.get("name", "")
        tag_sha = (tag.get("commit") or {}).get("sha", "")

        if not tag_sha:
            continue

        # Direct match on tag commit SHA
        if tag_sha.lower().startswith(prefix):
            log.debug("Matched tag %s via commit SHA %s", tag_name, tag_sha)
            return tag_name

        # For annotated tags, the tag object SHA differs from the commit SHA.
        # Dereference the tag object to get the underlying commit SHA.
        tag_obj = client.get(f"/repos/{repo}/git/tags/{tag_sha}")
        if tag_obj and isinstance(tag_obj, dict):
            obj_type = tag_obj.get("object", {}).get("type", "")
            obj_sha = tag_obj.get("object", {}).get("sha", "")
            if obj_type == "commit" and obj_sha.lower().startswith(prefix):
                log.debug(
                    "Matched annotated tag %s via dereferenced commit SHA %s",
                    tag_name,
                    obj_sha,
                )
                return tag_name

    log.debug("No tag found for hash %s in repo %s", prefix, repo)
    return None


def resolve_version_to_hash(
    client: GitHubClient,
    version: str,
    repo: str,
) -> str | None:
    """
    Resolve a release version/tag to a commit SHA.

    Supports lightweight and annotated tags.
    Returns the full commit SHA, or None if the tag does not exist.
    """
    log.debug("Resolving version %s in repo %s", version, repo)

    # Get the tag ref
    ref_data = client.get(f"/repos/{repo}/git/ref/tags/{version}")
    if not ref_data:
        # Try without leading 'v' or with it
        alt = version.lstrip("v") if version.startswith("v") else f"v{version}"
        ref_data = client.get(f"/repos/{repo}/git/ref/tags/{alt}")
        if not ref_data:
            log.debug("Tag ref not found for version %s in repo %s", version, repo)
            return None

    obj_type = ref_data.get("object", {}).get("type", "")
    obj_sha = ref_data.get("object", {}).get("sha", "")

    if not obj_sha:
        return None

    if obj_type == "tag":
        # Annotated tag: dereference to get the commit SHA
        tag_obj = client.get(f"/repos/{repo}/git/tags/{obj_sha}")
        if tag_obj and isinstance(tag_obj, dict):
            commit_sha = tag_obj.get("object", {}).get("sha", "")
            if commit_sha:
                log.debug(
                    "Resolved annotated tag %s to commit %s", version, commit_sha
                )
                return commit_sha

    # Lightweight tag points directly at a commit
    log.debug("Resolved lightweight tag %s to commit %s", version, obj_sha)
    return obj_sha


# ─────────────────────────────────────────────
# Scan: GitHub Actions workflow files
# ─────────────────────────────────────────────

# Matches: uses: owner/repo@<ref>
# ref may be a hash, a tag (v1.2.3), or a branch name
_RE_ACTION_USES = re.compile(
    r"""uses:\s+['"]?(?P<repo>[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.\-]+)@(?P<ref>[a-zA-Z0-9_.\/\-]+)['"]?"""
)

# Detect if ref looks like a commit hash (hex, len >= MIN_HASH_LEN)
_RE_COMMIT_HASH = re.compile(r"^[0-9a-f]{7,40}$", re.IGNORECASE)


def _is_commit_hash(ref: str) -> bool:
    return bool(_RE_COMMIT_HASH.match(ref))


def scan_workflow_file(
    client: GitHubClient,
    file_path: Path,
    check_currency: bool = False,
) -> list[dict[str, str]]:
    """
    Scan a GitHub Actions workflow YAML file for pinned action references.

    Extracts `uses: owner/repo@<ref>` entries and resolves hashes to versions
    (or versions to their canonical commit SHAs).

    Returns a list of result dicts matching CSV_COLUMNS.
    """
    log.info("Scanning workflow file: %s", file_path)
    content = file_path.read_text(encoding="utf-8", errors="replace")
    results: list[dict[str, str]] = []

    for match in _RE_ACTION_USES.finditer(content):
        repo = match.group("repo")
        ref = match.group("ref")
        row = _resolve_ref(
            client=client,
            repo=repo,
            ref=ref,
            ecosystem=ECOSYSTEM_GITHUB_ACTION,
            check_currency=check_currency,
        )
        row["Reference"] = f"{file_path.name}:{match.start()}"
        results.append(row)

    log.info("Found %d action reference(s) in %s", len(results), file_path)
    return results


# ─────────────────────────────────────────────
# Scan: Terraform files
# ─────────────────────────────────────────────

# Module source with git ref: source = "git::https://github.com/org/repo.git?ref=<ref>"
_RE_TF_GIT_REF = re.compile(
    r"""source\s*=\s*['"].*?github\.com[/:](?P<repo>[a-zA-Z0-9_.\-]+/[a-zA-Z0-9_.\-]+?)(?:\.git)?\?ref=(?P<ref>[a-zA-Z0-9_.\/\-]+)['"]"""
)

# Module version constraint: version = "~> 3.0" or "= 1.2.3"
_RE_TF_VERSION = re.compile(
    r"""version\s*=\s*['"](?P<constraint>[^'"]+)['"]"""
)

# Registry module source: source = "hashicorp/consul/aws"  (namespace/name/provider)
_RE_TF_REGISTRY = re.compile(
    r"""source\s*=\s*['"](?P<namespace>[a-zA-Z0-9_-]+)/(?P<name>[a-zA-Z0-9_-]+)/(?P<provider>[a-zA-Z0-9_-]+)['"]"""
)

# Provider version in required_providers block
_RE_TF_PROVIDER_VERSION = re.compile(
    r"""(?P<provider>[a-zA-Z0-9_\-/]+)\s*=\s*\{[^}]*?version\s*=\s*['"](?P<constraint>[^'"]+)['"]""",
    re.DOTALL,
)


def _resolve_tf_registry_module(
    namespace: str,
    module_name: str,
    provider: str,
    version_constraint: str,
) -> dict[str, str]:
    """Query the Terraform Registry for module version info."""
    try:
        url = f"{TF_REGISTRY_API}/modules/{namespace}/{module_name}/{provider}"
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200:
            latest = ""
        else:
            data = resp.json()
            latest = data.get("version", "")
    except requests.RequestException:
        latest = ""

    repo_id = f"{namespace}/{module_name}/{provider}"
    resolved = version_constraint  # constraint IS the reference for registry modules
    currency, behind = (
        check_version_currency(resolved, latest)
        if latest
        else (CURRENCY_UNKNOWN, "")
    )

    return {
        "Repository": repo_id,
        "Reference": "terraform-registry",
        "Type": ECOSYSTEM_TF_MODULE,
        "InputHash": version_constraint,
        "ResolvedVersion": resolved,
        "LatestVersion": latest,
        "Currency": currency,
        "VersionsBehind": behind,
    }


def scan_terraform_file(
    client: GitHubClient,
    file_path: Path,
    ecosystem: str = ECOSYSTEM_TF_MODULE,
    check_currency: bool = False,
) -> list[dict[str, str]]:
    """
    Scan a Terraform (.tf) file for module sources and provider version constraints.

    Handles:
    - git::https://github.com/... ?ref=<hash/tag>
    - Terraform Registry sources (namespace/name/provider)
    - version = "~> X.Y" constraints

    Returns a list of result dicts matching CSV_COLUMNS.
    """
    log.info("Scanning Terraform file: %s", file_path)
    content = file_path.read_text(encoding="utf-8", errors="replace")
    results: list[dict[str, str]] = []

    # Git-ref module sources (GitHub)
    for match in _RE_TF_GIT_REF.finditer(content):
        repo = match.group("repo")
        ref = match.group("ref")
        row = _resolve_ref(
            client=client,
            repo=repo,
            ref=ref,
            ecosystem=ecosystem,
            check_currency=check_currency,
        )
        row["Reference"] = f"{file_path.name}:{match.start()}"
        results.append(row)

    # Terraform Registry module sources
    for match in _RE_TF_REGISTRY.finditer(content):
        ns = match.group("namespace")
        name = match.group("name")
        provider = match.group("provider")

        # Try to find associated version constraint
        version_constraint = ""
        snippet = content[match.start(): match.start() + 400]
        vm = _RE_TF_VERSION.search(snippet)
        if vm:
            version_constraint = vm.group("constraint")

        row = _resolve_tf_registry_module(ns, name, provider, version_constraint)
        row["Reference"] = f"{file_path.name}:{match.start()}"
        results.append(row)

    log.info("Found %d Terraform reference(s) in %s", len(results), file_path)
    return results


# ─────────────────────────────────────────────
# Core ref resolver (shared)
# ─────────────────────────────────────────────
def _resolve_ref(
    client: GitHubClient,
    repo: str,
    ref: str,
    ecosystem: str,
    check_currency: bool = False,
    current_version: str | None = None,
) -> dict[str, str]:
    """
    Resolve a single repo + ref combination.

    If ref looks like a commit hash, resolve to version.
    If ref looks like a version tag, resolve to commit hash and back to canonical version.
    """
    row: dict[str, str] = {
        "Repository": repo,
        "Reference": ref,
        "Type": ecosystem,
        "InputHash": "",
        "ResolvedVersion": "",
        "LatestVersion": "",
        "Currency": CURRENCY_UNKNOWN,
        "VersionsBehind": "",
    }

    if _is_commit_hash(ref):
        row["InputHash"] = ref
        resolved_version = resolve_hash_to_version(client, ref, repo)
        row["ResolvedVersion"] = resolved_version or ""
        if not resolved_version:
            log.warning("Could not resolve hash %s in repo %s", ref, repo)
    else:
        # ref is a version tag or branch
        row["ResolvedVersion"] = ref
        commit_sha = resolve_version_to_hash(client, ref, repo)
        row["InputHash"] = commit_sha or ""
        if not commit_sha:
            log.warning("Could not resolve version %s in repo %s", ref, repo)

    if check_currency:
        latest = current_version or get_latest_release(client, repo)
        row["LatestVersion"] = latest or ""
        if latest and row["ResolvedVersion"]:
            currency, behind = check_version_currency(row["ResolvedVersion"], latest)
            row["Currency"] = currency
            row["VersionsBehind"] = behind

    return row


# ─────────────────────────────────────────────
# Directory scanner
# ─────────────────────────────────────────────
_WORKFLOW_EXTENSIONS = {".yml", ".yaml"}
_TF_EXTENSIONS = {".tf"}


def scan_directory(
    client: GitHubClient,
    directory: Path,
    ecosystem: str = ECOSYSTEM_GENERAL,
    check_currency: bool = False,
    recursive: bool = True,
) -> list[dict[str, str]]:
    """
    Scan a directory for workflow or Terraform files and resolve all pinned refs.

    Auto-detects file type based on extension and directory patterns.
    """
    log.info("Scanning directory: %s (ecosystem=%s)", directory, ecosystem)
    results: list[dict[str, str]] = []
    pattern = "**/*" if recursive else "*"

    for file_path in sorted(directory.glob(pattern)):
        if not file_path.is_file():
            continue

        suffix = file_path.suffix.lower()
        if suffix in _WORKFLOW_EXTENSIONS and ecosystem in (
            ECOSYSTEM_GITHUB_ACTION,
            ECOSYSTEM_GENERAL,
        ):
            results.extend(
                scan_workflow_file(client, file_path, check_currency=check_currency)
            )
        elif suffix in _TF_EXTENSIONS and ecosystem in (
            ECOSYSTEM_TF_MODULE,
            ECOSYSTEM_TF_PROVIDER,
            ECOSYSTEM_GENERAL,
        ):
            results.extend(
                scan_terraform_file(
                    client, file_path, ecosystem=ecosystem, check_currency=check_currency
                )
            )

    log.info("Directory scan complete. Total references found: %d", len(results))
    return results


# ─────────────────────────────────────────────
# Bulk import (CSV / JSON)
# ─────────────────────────────────────────────
def load_import_file(file_path: Path) -> list[dict[str, str]]:
    """
    Load items to resolve from a CSV or JSON file.

    Expected CSV columns: repository, hash (or version), type
    Expected JSON: list of {repository, hash, type} objects
    """
    suffix = file_path.suffix.lower()
    items: list[dict[str, str]] = []

    if suffix == ".json":
        raw = json.loads(file_path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            items = raw
        else:
            items = raw.get("items", [])
    else:
        with file_path.open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            items = [dict(row) for row in reader]

    log.info("Loaded %d item(s) from %s", len(items), file_path)
    return items


def process_bulk_items(
    client: GitHubClient,
    items: list[dict[str, str]],
    check_currency: bool = False,
    current_version: str | None = None,
) -> list[dict[str, str]]:
    """
    Process a list of bulk items (from CSV/JSON import).

    Each item must have at least:
    - 'repository' (owner/repo)
    - 'hash' or 'version' or 'ref' — the reference to resolve
    - 'type' (optional, defaults to 'general')
    """
    results: list[dict[str, str]] = []

    for i, item in enumerate(items, 1):
        repo = item.get("repository") or item.get("repo") or ""
        ref = (
            item.get("hash")
            or item.get("version")
            or item.get("ref")
            or ""
        )
        ecosystem = item.get("type", ECOSYSTEM_GENERAL)

        if not repo or not ref:
            log.warning("Item %d missing repository or ref — skipping: %s", i, item)
            continue

        log.debug("Processing item %d: %s @ %s", i, repo, ref)
        row = _resolve_ref(
            client=client,
            repo=repo,
            ref=ref,
            ecosystem=ecosystem,
            check_currency=check_currency,
            current_version=current_version,
        )
        results.append(row)

    return results


# ─────────────────────────────────────────────
# Output
# ─────────────────────────────────────────────
def export_results(
    results: list[dict[str, str]],
    output_path: Path,
    fmt: str = "csv",
) -> None:
    """Write resolution results to a CSV or JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "json":
        output_path.write_text(
            json.dumps(results, indent=2), encoding="utf-8"
        )
        log.info(
            "Results written to %s (JSON, %d records)", output_path, len(results)
        )
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


def _default_output_path(fmt: str) -> Path:
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    ext = "json" if fmt == "json" else "csv"
    return Path(f"{ts}_version_resolver.{ext}")


# ─────────────────────────────────────────────
# Orchestration
# ─────────────────────────────────────────────
def run_resolver(config: dict[str, Any]) -> list[dict[str, str]]:
    """
    Main orchestrator. Accepts a flat config dict (same keys as CLI args).
    Returns the combined list of resolved records.
    """
    token = resolve_token(
        auth_method=config.get("auth", "gh"),
        pat_token=config.get("token"),
        app_id=config.get("app_id"),
        app_key_file=config.get("app_key"),
        app_secret_name=config.get("app_secret_name"),
    )
    client = GitHubClient(token)
    check_currency = config.get("check_currency", False)
    current_version = config.get("current_version")
    ecosystem = config.get("type", ECOSYSTEM_GENERAL)
    results: list[dict[str, str]] = []

    # Single hash-to-version
    if config.get("hash_to_version"):
        repo = config.get("repo", "")
        if not repo:
            raise ValueError("--repo is required with --hash-to-version")
        row = _resolve_ref(
            client=client,
            repo=repo,
            ref=config["hash_to_version"],
            ecosystem=ecosystem,
            check_currency=check_currency,
            current_version=current_version,
        )
        results.append(row)

    # Single version-to-hash
    elif config.get("version_to_hash"):
        repo = config.get("repo", "")
        if not repo:
            raise ValueError("--repo is required with --version-to-hash")
        row = _resolve_ref(
            client=client,
            repo=repo,
            ref=config["version_to_hash"],
            ecosystem=ecosystem,
            check_currency=check_currency,
            current_version=current_version,
        )
        results.append(row)

    # Scan a single file
    elif config.get("scan_file"):
        scan_path = Path(config["scan_file"])
        suffix = scan_path.suffix.lower()
        if suffix in _WORKFLOW_EXTENSIONS:
            results.extend(
                scan_workflow_file(client, scan_path, check_currency=check_currency)
            )
        elif suffix in _TF_EXTENSIONS:
            results.extend(
                scan_terraform_file(
                    client, scan_path, ecosystem=ecosystem, check_currency=check_currency
                )
            )
        else:
            log.warning(
                "Unsupported file type for scanning: %s. "
                "Supported: %s, %s",
                suffix,
                ", ".join(_WORKFLOW_EXTENSIONS),
                ", ".join(_TF_EXTENSIONS),
            )

    # Scan a directory
    elif config.get("scan_dir"):
        results.extend(
            scan_directory(
                client,
                Path(config["scan_dir"]),
                ecosystem=ecosystem,
                check_currency=check_currency,
            )
        )

    # Bulk import
    elif config.get("import_file"):
        items = load_import_file(Path(config["import_file"]))
        results.extend(
            process_bulk_items(
                client,
                items,
                check_currency=check_currency,
                current_version=current_version,
            )
        )

    log.info("Resolution complete. Total records: %d", len(results))
    return results


# ─────────────────────────────────────────────
# Interactive mode
# ─────────────────────────────────────────────
def interactive_mode() -> dict[str, Any]:
    """Prompt the user for configuration parameters interactively."""
    print("\n\033[1m\033[0;36mgh-version-resolver — Interactive Mode\033[0m")
    print("─" * 48)

    def prompt(msg: str, default: str = "") -> str:
        suffix = f" [{default}]" if default else ""
        val = input(f"  {msg}{suffix}: ").strip()
        return val if val else default

    mode = prompt(
        "Mode (hash-to-version / version-to-hash / scan-file / scan-dir / import)",
        "hash-to-version",
    )
    config: dict[str, Any] = {}

    if mode == "hash-to-version":
        config["hash_to_version"] = prompt("Commit hash")
        config["repo"] = prompt("Repository (owner/repo)")
    elif mode == "version-to-hash":
        config["version_to_hash"] = prompt("Version/tag (e.g. v4.1.0)")
        config["repo"] = prompt("Repository (owner/repo)")
    elif mode == "scan-file":
        config["scan_file"] = prompt("File path to scan")
    elif mode == "scan-dir":
        config["scan_dir"] = prompt("Directory path to scan")
    elif mode == "import":
        config["import_file"] = prompt("Import file path (CSV or JSON)")

    config["type"] = prompt(
        "Ecosystem type (github-action/terraform-module/terraform-provider/npm/pypi/general)",
        ECOSYSTEM_GENERAL,
    )

    do_currency = prompt("Check version currency? (y/n)", "n")
    config["check_currency"] = do_currency.lower() in ("y", "yes")
    if config["check_currency"]:
        cv = prompt("Current/latest version (leave blank to auto-detect)", "")
        if cv:
            config["current_version"] = cv

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
\033[1m\033[0;36mgh-version-resolver\033[0m — GitHub Version Resolver
Written by {AUTHOR}

\033[1mUSAGE:\033[0m
  python gh_version_resolver.py [OPTIONS]

\033[1mRESOLVE MODE:\033[0m
  --hash-to-version <hash>   Convert commit hash to release version
  --version-to-hash <ver>    Convert release version to commit hash
  --repo <owner/repo>        Target repository

\033[1mBULK MODE:\033[0m
  --import <file>            Import CSV/JSON with items to resolve
  --scan-file <file>         Scan a file for pinned hashes (workflows, .tf files)
  --scan-dir <dir>           Scan directory for all pinned hashes

\033[1mVERSION CURRENCY:\033[0m
  --check-currency           Check if version is current, M-1, N-1, patch-behind, or older
  --current-version <ver>    Specify what "current" is (auto-detects from GitHub if omitted)

\033[1mECOSYSTEM:\033[0m
  --type <type>              Type: github-action|terraform-module|terraform-provider|
                             npm|pypi|general (default: general)

\033[1mAUTH:\033[0m
  -a, --auth <method>        Auth method: gh|pat|app (default: gh)
  -t, --token <token>        PAT token
  --app-id <id>              GitHub App ID
  --app-key <file>           App private key file path

\033[1mOUTPUT:\033[0m
  --output <file>            Output file (default: timestamped CSV)
  --format <fmt>             csv|json (default: csv)
  --s3-bucket <bucket>       S3 bucket for Lambda output
  --s3-prefix <prefix>       S3 key prefix

\033[1mRUNTIME:\033[0m
  --mode <mode>              local|lambda (default: local)
  -i, --interactive          Interactive mode
  -h, --help                 Show this help message
  -v, --verbose              Verbose output
  --version                  Show script version

\033[1mEXAMPLES:\033[0m
  # Hash to version
  python gh_version_resolver.py --hash-to-version abc123f --repo actions/checkout

  # Version to hash
  python gh_version_resolver.py --version-to-hash v4.1.0 --repo actions/checkout

  # Scan a workflow file and check currency
  python gh_version_resolver.py --scan-file .github/workflows/ci.yml \\
      --type github-action --check-currency

  # Scan terraform directory
  python gh_version_resolver.py --scan-dir ./terraform/ \\
      --type terraform-module --check-currency

  # Bulk resolve from CSV
  python gh_version_resolver.py --import hashes.csv --check-currency

  # Interactive mode
  python gh_version_resolver.py -i
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gh_version_resolver",
        add_help=False,
    )
    # Resolve mode
    resolve = parser.add_argument_group("Resolve")
    resolve.add_argument("--hash-to-version", metavar="HASH")
    resolve.add_argument("--version-to-hash", metavar="VERSION")
    resolve.add_argument("--repo", metavar="OWNER/REPO")
    # Bulk mode
    bulk = parser.add_argument_group("Bulk")
    bulk.add_argument("--import", dest="import_file", metavar="FILE")
    bulk.add_argument("--scan-file", metavar="FILE")
    bulk.add_argument("--scan-dir", metavar="DIR")
    # Currency
    currency = parser.add_argument_group("Currency")
    currency.add_argument("--check-currency", action="store_true")
    currency.add_argument("--current-version", metavar="VERSION")
    # Ecosystem
    eco = parser.add_argument_group("Ecosystem")
    eco.add_argument(
        "--type",
        dest="type",
        default=ECOSYSTEM_GENERAL,
        choices=VALID_ECOSYSTEMS,
    )
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
    log.info("\033[1m%s v%s — written by %s\033[0m", SCRIPT_NAME, VERSION, AUTHOR)

    config: dict[str, Any]

    if args.interactive:
        config = interactive_mode()
    else:
        has_action = any(
            [
                args.hash_to_version,
                args.version_to_hash,
                args.import_file,
                args.scan_file,
                args.scan_dir,
            ]
        )
        if not has_action:
            print(HELP_TEXT)
            log.error(
                "Specify an action: --hash-to-version, --version-to-hash, "
                "--import, --scan-file, or --scan-dir"
            )
            return 1

        config = {
            "hash_to_version": args.hash_to_version,
            "version_to_hash": args.version_to_hash,
            "repo": args.repo,
            "import_file": args.import_file,
            "scan_file": args.scan_file,
            "scan_dir": args.scan_dir,
            "check_currency": args.check_currency,
            "current_version": args.current_version,
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

    results = run_resolver(config)

    output_path = Path(config["output"])
    fmt = config.get("format", "csv")
    export_results(results, output_path, fmt=fmt)

    s3_bucket = config.get("s3_bucket")
    if s3_bucket:
        upload_to_s3(output_path, s3_bucket, prefix=config.get("s3_prefix", ""))

    if not results:
        log.info("No references found or resolved.")
    else:
        log.info("Summary: %d reference(s) resolved.", len(results))
        _print_summary_table(results)

    return 0


def _print_summary_table(results: list[dict[str, str]]) -> None:
    """Print a concise summary table to stdout."""
    print(f"\n\033[1m{'Repository':<40} {'ResolvedVersion':<20} {'Currency':<14} {'VersionsBehind'}\033[0m")
    print("─" * 100)
    for row in results:
        repo = (row.get("Repository") or "")[:38]
        ver = (row.get("ResolvedVersion") or "—")[:18]
        currency = row.get("Currency") or "—"
        behind = row.get("VersionsBehind") or ""
        # Colour-code currency
        colour = {
            CURRENCY_UP_TO_DATE: "\033[0;32m",
            CURRENCY_PATCH_BEHIND: "\033[1;33m",
            CURRENCY_N1: "\033[1;33m",
            CURRENCY_M1: "\033[0;31m",
            CURRENCY_OLDER: "\033[1;31m",
        }.get(currency, "\033[0m")
        reset = "\033[0m"
        print(f"{repo:<40} {ver:<20} {colour}{currency:<14}{reset} {behind}")
    print()


if __name__ == "__main__":
    sys.exit(main())
