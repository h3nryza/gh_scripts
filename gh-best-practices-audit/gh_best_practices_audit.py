#!/usr/bin/env python3
"""
gh-best-practices-audit - GitHub Best Practices Auditor
Written by h3nryza

Comprehensive automated audit of GitHub Enterprise, Organization, and Repository
settings against security best practices from CIS GitHub Benchmark, OWASP CI/CD
Top 10, and SANS Top 25.

Supports custom rules via Excel/CSV. Runs locally or as AWS Lambda.
"""

import argparse
import csv
import datetime
import io
import json
import logging
import os
import subprocess
import sys
import textwrap
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional, Union

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
VERSION = "1.0.0"
AUTHOR = "h3nryza"
SCRIPT_NAME = "gh-best-practices-audit"
TIMESTAMP = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
RULES_DIR = Path(__file__).resolve().parent / "rules"

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
VALID_CATEGORIES = {
    "auth", "branch-protection", "secrets", "ci-cd",
    "access", "repo-settings", "audit",
}
VALID_BENCHMARKS = {"cis", "owasp", "sans"}
VALID_FORMATS = {"csv", "json", "html"}

# ANSI colors
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
BLUE = "\033[0;34m"
CYAN = "\033[0;36m"
BOLD = "\033[1m"
RESET = "\033[0m"
DIM = "\033[2m"

logger = logging.getLogger(SCRIPT_NAME)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class Rule:
    """Represents a single audit rule."""
    id: str
    name: str
    description: str
    benchmark: str
    category: str
    severity: str
    level: str
    check_type: str
    api_endpoint: str
    field: str
    expected_value: Any
    remediation: str
    check_paths: list = field(default_factory=list)


@dataclass
class AuditResult:
    """Represents the result of a single rule check."""
    target: str
    level: str
    rule_id: str
    rule_name: str
    benchmark: str
    category: str
    severity: str
    status: str  # PASS, FAIL, SKIP, ERROR
    current_value: str
    expected_value: str
    remediation: str


# ---------------------------------------------------------------------------
# GitHub API client
# ---------------------------------------------------------------------------
class GitHubClient:
    """Handles GitHub API authentication and requests."""

    def __init__(self, auth_method: str = "gh", token: str = "",
                 app_id: str = "", app_key_file: str = ""):
        self.auth_method = auth_method
        self.token = token
        self.app_id = app_id
        self.app_key_file = app_key_file
        self._validate_auth()

    def _validate_auth(self) -> None:
        """Validate that the chosen authentication method is available."""
        if self.auth_method == "gh":
            try:
                result = subprocess.run(
                    ["gh", "auth", "status"],
                    capture_output=True, text=True, timeout=15,
                )
                if result.returncode != 0:
                    raise RuntimeError(
                        "GitHub CLI is not authenticated. "
                        "Run 'gh auth login' or use --auth pat --token <TOKEN>."
                    )
            except FileNotFoundError:
                raise RuntimeError(
                    "GitHub CLI (gh) is not installed. "
                    "Install from https://cli.github.com or use --auth pat --token <TOKEN>."
                )
        elif self.auth_method == "pat":
            if not self.token:
                raise RuntimeError("PAT auth requires --token <TOKEN>.")
        elif self.auth_method == "app":
            if not self.app_id or not self.app_key_file:
                raise RuntimeError("App auth requires --app-id and --app-key.")
            if not os.path.isfile(self.app_key_file):
                raise RuntimeError(f"App key file not found: {self.app_key_file}")

    def api_call(self, endpoint: str, method: str = "GET",
                 accept: str = "application/vnd.github+json",
                 paginate: bool = False) -> Any:
        """Make a GitHub API call using the configured auth method."""
        if self.auth_method == "gh":
            return self._gh_cli_call(endpoint, method, accept, paginate)
        elif self.auth_method == "pat":
            return self._pat_call(endpoint, method, accept, paginate)
        elif self.auth_method == "app":
            return self._pat_call(endpoint, method, accept, paginate)
        return None

    def _gh_cli_call(self, endpoint: str, method: str, accept: str,
                     paginate: bool) -> Any:
        """Make API call via gh CLI."""
        cmd = ["gh", "api", endpoint, "-H", f"Accept: {accept}"]
        if method != "GET":
            cmd.extend(["--method", method])
        if paginate:
            cmd.append("--paginate")
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                stderr = result.stderr.strip()
                if "404" in stderr or "Not Found" in stderr:
                    return None
                if "403" in stderr or "forbidden" in stderr.lower():
                    logger.debug("Permission denied for %s: %s", endpoint, stderr)
                    return {"_error": "permission_denied", "_message": stderr}
                logger.debug("API error for %s: %s", endpoint, stderr)
                return {"_error": "api_error", "_message": stderr}
            if not result.stdout.strip():
                return None
            return json.loads(result.stdout)
        except subprocess.TimeoutExpired:
            logger.warning("API call timed out: %s", endpoint)
            return {"_error": "timeout", "_message": "Request timed out"}
        except json.JSONDecodeError:
            return result.stdout.strip() if result.stdout.strip() else None

    def _pat_call(self, endpoint: str, method: str, accept: str,
                  paginate: bool) -> Any:
        """Make API call via curl with PAT."""
        base_url = "https://api.github.com"
        if endpoint.startswith("http"):
            url = endpoint
        else:
            url = f"{base_url}{endpoint}"

        all_results: list = []
        while url:
            cmd = [
                "curl", "-sS", "-X", method,
                "-H", f"Accept: {accept}",
                "-H", f"Authorization: Bearer {self.token}",
                "-H", "X-GitHub-Api-Version: 2022-11-28",
                "-w", "\n%{http_code}\n%{header_json}",
                url,
            ]
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=30,
                )
                lines = result.stdout.rsplit("\n", 3)
                if len(lines) >= 3:
                    body = "\n".join(lines[:-2])
                    status_code = lines[-2].strip()
                else:
                    body = result.stdout
                    status_code = "200"

                if status_code.startswith("4") or status_code.startswith("5"):
                    if status_code == "404":
                        return None
                    if status_code == "403":
                        return {"_error": "permission_denied", "_message": body}
                    return {"_error": "api_error", "_message": body}

                if not body.strip():
                    return None

                data = json.loads(body)
                if not paginate:
                    return data

                if isinstance(data, list):
                    all_results.extend(data)
                else:
                    return data

                # Simple link header parsing for pagination
                url = None
                try:
                    headers_json = lines[-1].strip()
                    if headers_json:
                        headers = json.loads(headers_json)
                        link = headers.get("link", [""])[0] if isinstance(headers.get("link"), list) else headers.get("link", "")
                        if 'rel="next"' in str(link):
                            for part in str(link).split(","):
                                if 'rel="next"' in part:
                                    url = part.split("<")[1].split(">")[0]
                                    break
                except (json.JSONDecodeError, IndexError, KeyError):
                    url = None

            except subprocess.TimeoutExpired:
                return {"_error": "timeout", "_message": "Request timed out"}
            except json.JSONDecodeError:
                return body if body else None

        return all_results if all_results else None


# ---------------------------------------------------------------------------
# Rule loading
# ---------------------------------------------------------------------------
def load_rules(rules_dir: Path, benchmarks: set[str]) -> list[Rule]:
    """Load rules from JSON files based on selected benchmarks."""
    rules: list[Rule] = []
    benchmark_files = {
        "cis": "cis_benchmark.json",
        "owasp": "owasp_cicd.json",
        "sans": "sans_top25.json",
    }

    for bm, filename in benchmark_files.items():
        if bm not in benchmarks:
            continue
        filepath = rules_dir / filename
        if not filepath.exists():
            logger.warning("Rules file not found: %s", filepath)
            continue
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            for r in data.get("rules", []):
                rules.append(Rule(
                    id=r["id"],
                    name=r["name"],
                    description=r.get("description", ""),
                    benchmark=r.get("benchmark", bm.upper()),
                    category=r.get("category", ""),
                    severity=r.get("severity", "info"),
                    level=r.get("level", "repository"),
                    check_type=r.get("check_type", "api"),
                    api_endpoint=r.get("api_endpoint", ""),
                    field=r.get("field", ""),
                    expected_value=r.get("expected_value"),
                    remediation=r.get("remediation", ""),
                    check_paths=r.get("check_paths", []),
                ))
            logger.info("Loaded %d rules from %s", len(data.get("rules", [])), filename)
        except (json.JSONDecodeError, KeyError) as exc:
            logger.error("Error loading rules from %s: %s", filepath, exc)

    return rules


def load_custom_rules(filepath: str) -> list[Rule]:
    """Load custom rules from a CSV or Excel file."""
    rules: list[Rule] = []
    path = Path(filepath)

    if not path.exists():
        logger.error("Custom rules file not found: %s", filepath)
        return rules

    if path.suffix.lower() in (".xlsx", ".xls"):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(str(path), read_only=True)
            ws = wb.active
            headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
            for row in ws.iter_rows(min_row=2, values_only=True):
                row_dict = dict(zip(headers, row))
                if row_dict.get("id"):
                    rules.append(_dict_to_rule(row_dict))
            wb.close()
        except ImportError:
            logger.error("openpyxl is required for Excel files. Install with: pip install openpyxl")
        except Exception as exc:
            logger.error("Error loading Excel rules: %s", exc)
    elif path.suffix.lower() == ".csv":
        try:
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("id"):
                        rules.append(_dict_to_rule(row))
        except Exception as exc:
            logger.error("Error loading CSV rules: %s", exc)
    else:
        logger.error("Unsupported custom rules file format: %s (use .csv or .xlsx)", path.suffix)

    if rules:
        logger.info("Loaded %d custom rules from %s", len(rules), filepath)
    return rules


def _dict_to_rule(d: dict) -> Rule:
    """Convert a dictionary row to a Rule object."""
    expected = d.get("expected_value", "")
    if isinstance(expected, str):
        if expected.lower() == "true":
            expected = True
        elif expected.lower() == "false":
            expected = False
        elif expected.isdigit():
            expected = int(expected)
    return Rule(
        id=d.get("id", ""),
        name=d.get("name", ""),
        description=d.get("description", ""),
        benchmark=d.get("benchmark", "CUSTOM"),
        category=d.get("category", ""),
        severity=d.get("severity", "info"),
        level=d.get("level", "repository"),
        check_type=d.get("check_type", "api"),
        api_endpoint=d.get("api_endpoint", ""),
        field=d.get("field", ""),
        expected_value=expected,
        remediation=d.get("remediation", ""),
        check_paths=d.get("check_paths", "").split(";") if isinstance(d.get("check_paths"), str) and d.get("check_paths") else [],
    )


def filter_rules(rules: list[Rule], severity: str = "low",
                 category: str = "") -> list[Rule]:
    """Filter rules by minimum severity and optional category."""
    min_sev = SEVERITY_ORDER.get(severity, 3)
    filtered = [r for r in rules if SEVERITY_ORDER.get(r.severity, 4) <= min_sev]
    if category:
        filtered = [r for r in filtered if r.category == category]
    return filtered


# ---------------------------------------------------------------------------
# Rule checking engine
# ---------------------------------------------------------------------------
def get_nested_value(data: Any, field_path: str) -> Any:
    """Retrieve a nested value from a dict using dot notation."""
    if data is None:
        return None
    parts = field_path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
        if current is None:
            return None
    return current


def evaluate_expected(actual: Any, expected: Any) -> bool:
    """Compare actual value against expected, supporting various match types."""
    if expected is None:
        return actual is not None

    # String comparison operators
    if isinstance(expected, str):
        if expected == "not_null":
            return actual is not None
        if expected == "review_required":
            # This is an informational check - always pass, but log the value
            return True
        if expected.startswith(">="):
            try:
                threshold = int(expected[2:])
                return int(actual) >= threshold if actual is not None else False
            except (ValueError, TypeError):
                return False
        if expected.startswith(">"):
            try:
                threshold = int(expected[1:])
                return int(actual) > threshold if actual is not None else False
            except (ValueError, TypeError):
                return False
        if expected.startswith("<="):
            try:
                threshold = int(expected[2:])
                return int(actual) <= threshold if actual is not None else False
            except (ValueError, TypeError):
                return False

    # List of acceptable values
    if isinstance(expected, list):
        return actual in expected

    # Direct comparison
    if isinstance(expected, bool):
        if isinstance(actual, bool):
            return actual == expected
        if isinstance(actual, str):
            return actual.lower() == str(expected).lower()
        return bool(actual) == expected

    if isinstance(expected, int):
        try:
            return int(actual) == expected if actual is not None else False
        except (ValueError, TypeError):
            return False

    return str(actual).lower() == str(expected).lower()


def check_rule(client: GitHubClient, rule: Rule,
               target_vars: dict[str, str],
               local_path: str = "") -> AuditResult:
    """Check a single rule and return the result."""
    target_name = target_vars.get("target_name", "unknown")

    # Build the API endpoint with variable substitution
    endpoint = rule.api_endpoint
    for key, val in target_vars.items():
        endpoint = endpoint.replace(f"{{{key}}}", val)

    result = AuditResult(
        target=target_name,
        level=rule.level,
        rule_id=rule.id,
        rule_name=rule.name,
        benchmark=rule.benchmark,
        category=rule.category,
        severity=rule.severity,
        status="SKIP",
        current_value="",
        expected_value=str(rule.expected_value),
        remediation=rule.remediation,
    )

    try:
        if rule.check_type == "file_exists":
            result = _check_file_exists(client, rule, endpoint, target_name, local_path, result)
        elif rule.check_type == "file_exists_multi":
            result = _check_file_exists_multi(client, rule, target_vars, target_name, local_path, result)
        elif rule.check_type == "branch_protection":
            result = _check_branch_protection(client, rule, endpoint, target_name, result)
        elif rule.check_type == "api":
            result = _check_api(client, rule, endpoint, target_name, result)
        else:
            result.status = "SKIP"
            result.current_value = f"Unknown check_type: {rule.check_type}"
    except Exception as exc:
        result.status = "ERROR"
        result.current_value = f"Error: {exc}"
        logger.debug("Rule %s check error: %s", rule.id, exc)

    return result


def _check_file_exists(client: GitHubClient, rule: Rule, endpoint: str,
                       target_name: str, local_path: str,
                       result: AuditResult) -> AuditResult:
    """Check if a file exists in a repository."""
    if local_path:
        # Check local filesystem
        file_name = endpoint.rsplit("/", 1)[-1] if "/" in endpoint else ""
        candidates = [
            os.path.join(local_path, file_name),
            os.path.join(local_path, file_name.upper()),
            os.path.join(local_path, file_name.lower()),
        ]
        for candidate in candidates:
            if os.path.isfile(candidate):
                size = os.path.getsize(candidate)
                result.current_value = f"exists (size={size})"
                if rule.expected_value == ">0":
                    result.status = "PASS" if size > 0 else "FAIL"
                else:
                    result.status = "PASS"
                return result
        result.current_value = "not found"
        result.status = "FAIL"
        return result

    data = client.api_call(endpoint)
    if data is None:
        result.current_value = "not found"
        result.status = "FAIL"
        return result
    if isinstance(data, dict) and data.get("_error"):
        result.status = "SKIP"
        result.current_value = f"API error: {data.get('_message', 'unknown')}"
        return result

    actual = get_nested_value(data, rule.field) if rule.field else data
    result.current_value = str(actual) if actual is not None else "not found"

    if rule.expected_value == ">0":
        try:
            result.status = "PASS" if actual is not None and int(actual) > 0 else "FAIL"
        except (ValueError, TypeError):
            result.status = "PASS" if actual is not None else "FAIL"
    elif rule.expected_value == "not_null":
        result.status = "PASS" if actual is not None else "FAIL"
    else:
        result.status = "PASS" if actual is not None else "FAIL"
    return result


def _check_file_exists_multi(client: GitHubClient, rule: Rule,
                             target_vars: dict[str, str],
                             target_name: str, local_path: str,
                             result: AuditResult) -> AuditResult:
    """Check if a file exists in any of several possible paths."""
    paths = rule.check_paths or ["CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"]

    for check_path in paths:
        if local_path:
            candidate = os.path.join(local_path, check_path)
            if os.path.isfile(candidate):
                result.current_value = f"found at {check_path}"
                result.status = "PASS"
                return result
        else:
            endpoint = rule.api_endpoint
            for key, val in target_vars.items():
                endpoint = endpoint.replace(f"{{{key}}}", val)
            endpoint = endpoint.replace("{path}", check_path)
            data = client.api_call(endpoint)
            if data is not None and not (isinstance(data, dict) and data.get("_error")):
                result.current_value = f"found at {check_path}"
                result.status = "PASS"
                return result

    result.current_value = "not found in any location"
    result.status = "FAIL"
    return result


def _check_branch_protection(client: GitHubClient, rule: Rule,
                             endpoint: str, target_name: str,
                             result: AuditResult) -> AuditResult:
    """Check a branch protection rule."""
    data = client.api_call(endpoint)

    if data is None:
        result.current_value = "no branch protection"
        result.status = "FAIL"
        return result
    if isinstance(data, dict) and data.get("_error"):
        if data.get("_error") == "permission_denied":
            result.status = "SKIP"
            result.current_value = "insufficient permissions to check branch protection"
        else:
            result.status = "SKIP"
            result.current_value = f"API error: {data.get('_message', 'unknown')}"
        return result

    # For the basic "protected" field check
    if rule.field == "protected":
        result.current_value = "protected"
        result.status = "PASS"
        return result

    # Check for required_signatures via separate endpoint
    if rule.field == "required_signatures.enabled":
        sig_endpoint = endpoint.replace("/protection", "/protection/required_signatures")
        sig_data = client.api_call(
            sig_endpoint,
            accept="application/vnd.github.zzzax-preview+json",
        )
        if sig_data is None or (isinstance(sig_data, dict) and sig_data.get("_error")):
            result.current_value = str(False)
            result.status = "FAIL"
        else:
            enabled = sig_data.get("enabled", False) if isinstance(sig_data, dict) else False
            result.current_value = str(enabled)
            result.status = "PASS" if evaluate_expected(enabled, rule.expected_value) else "FAIL"
        return result

    actual = get_nested_value(data, rule.field)
    result.current_value = str(actual) if actual is not None else "not configured"
    result.status = "PASS" if evaluate_expected(actual, rule.expected_value) else "FAIL"
    return result


def _check_api(client: GitHubClient, rule: Rule, endpoint: str,
               target_name: str, result: AuditResult) -> AuditResult:
    """Check a generic API-based rule."""
    # Special handling for alert count checks
    if rule.field in ("open_alerts_count",):
        return _check_alert_count(client, rule, endpoint, result)

    # Special handling for webhook security
    if rule.field == "webhook_security":
        return _check_webhook_security(client, endpoint, result)

    # Special handling for audit log accessibility
    if rule.field == "audit_log_accessible":
        return _check_audit_log(client, endpoint, result)

    # Special handling for stream_configured
    if rule.field == "stream_configured":
        return _check_stream_configured(client, endpoint, result)

    data = client.api_call(endpoint)

    if data is None:
        result.current_value = "not found / not accessible"
        result.status = "SKIP"
        return result
    if isinstance(data, dict) and data.get("_error"):
        if data.get("_error") == "permission_denied":
            result.status = "SKIP"
            result.current_value = "insufficient permissions"
        else:
            result.status = "SKIP"
            result.current_value = f"API error: {data.get('_message', 'unknown')}"
        return result

    actual = get_nested_value(data, rule.field)
    result.current_value = str(actual) if actual is not None else "not set"

    if rule.expected_value == "review_required":
        # Informational check - report the value
        if isinstance(data, dict) and "total_count" in data:
            result.current_value = f"{data['total_count']} apps installed"
        result.status = "PASS"
        return result

    result.status = "PASS" if evaluate_expected(actual, rule.expected_value) else "FAIL"
    return result


def _check_alert_count(client: GitHubClient, rule: Rule,
                       endpoint: str, result: AuditResult) -> AuditResult:
    """Check the count of open alerts for a repository."""
    # Add state filter for open alerts
    separator = "&" if "?" in endpoint else "?"
    filtered_endpoint = f"{endpoint}{separator}state=open&per_page=1"
    data = client.api_call(filtered_endpoint)

    if data is None:
        # No alerts endpoint or no alerts = good
        result.current_value = "0"
        result.status = "PASS"
        return result
    if isinstance(data, dict) and data.get("_error"):
        if data.get("_error") == "permission_denied":
            result.status = "SKIP"
            result.current_value = "insufficient permissions"
        else:
            # Feature not enabled - treat as skip
            result.status = "SKIP"
            result.current_value = "feature not enabled or not accessible"
        return result

    if isinstance(data, list):
        count = len(data)
        # If we got results with per_page=1, there are open alerts
        # Get actual count with a broader request
        if count > 0:
            full_data = client.api_call(f"{endpoint}{separator}state=open&per_page=100")
            if isinstance(full_data, list):
                count = len(full_data)
        result.current_value = str(count)
        result.status = "PASS" if count == 0 else "FAIL"
    else:
        result.current_value = "0"
        result.status = "PASS"
    return result


def _check_webhook_security(client: GitHubClient, endpoint: str,
                            result: AuditResult) -> AuditResult:
    """Check that all webhooks use HTTPS and have secrets configured."""
    data = client.api_call(endpoint)
    if data is None or (isinstance(data, dict) and data.get("_error")):
        result.status = "SKIP"
        result.current_value = "no webhooks or insufficient permissions"
        return result

    if not isinstance(data, list) or len(data) == 0:
        result.current_value = "no webhooks configured"
        result.status = "PASS"
        return result

    insecure = []
    for hook in data:
        config = hook.get("config", {})
        url = config.get("url", "")
        # Check insecure_ssl setting
        insecure_ssl = config.get("insecure_ssl", "0")
        if not url.startswith("https://") or str(insecure_ssl) == "1":
            insecure.append(hook.get("id", "unknown"))

    if insecure:
        result.current_value = f"{len(insecure)} insecure webhooks"
        result.status = "FAIL"
    else:
        result.current_value = f"{len(data)} webhooks, all secure"
        result.status = "PASS"
    return result


def _check_audit_log(client: GitHubClient, endpoint: str,
                     result: AuditResult) -> AuditResult:
    """Check that the audit log is accessible."""
    # Try to access audit log with minimal results
    separator = "&" if "?" in endpoint else "?"
    data = client.api_call(f"{endpoint}{separator}per_page=1")
    if data is None:
        result.status = "SKIP"
        result.current_value = "audit log not accessible"
        return result
    if isinstance(data, dict) and data.get("_error"):
        result.status = "SKIP"
        result.current_value = "insufficient permissions for audit log"
        return result
    result.current_value = "accessible"
    result.status = "PASS"
    return result


def _check_stream_configured(client: GitHubClient, endpoint: str,
                             result: AuditResult) -> AuditResult:
    """Check if audit log streaming is configured (enterprise only)."""
    # Enterprise audit log streaming is configured via settings, not easily
    # checkable via API. We check if the audit log endpoint is accessible.
    data = client.api_call(endpoint)
    if data is None:
        result.status = "SKIP"
        result.current_value = "not accessible (enterprise feature)"
        return result
    if isinstance(data, dict) and data.get("_error"):
        result.status = "SKIP"
        result.current_value = "insufficient permissions"
        return result
    result.current_value = "audit log accessible (streaming config requires manual verification)"
    result.status = "SKIP"
    return result


# ---------------------------------------------------------------------------
# Audit orchestration
# ---------------------------------------------------------------------------
def audit_enterprise(client: GitHubClient, enterprise: str,
                     rules: list[Rule], verbose: bool = False) -> list[AuditResult]:
    """Audit an enterprise and all its organizations."""
    results: list[AuditResult] = []
    enterprise_rules = [r for r in rules if r.level == "enterprise"]
    target_vars = {"enterprise": enterprise, "target_name": enterprise}

    log_info(f"Auditing enterprise: {enterprise}")
    log_info(f"Checking {len(enterprise_rules)} enterprise-level rules...")

    for rule in enterprise_rules:
        if verbose:
            log_verbose(f"Checking {rule.id}: {rule.name}")
        result = check_rule(client, rule, target_vars)
        results.append(result)
        _log_result(result, verbose)

    # Discover organizations in the enterprise
    log_info("Discovering organizations in enterprise...")
    orgs_data = client.api_call(f"/organizations?per_page=100", paginate=True)

    # For enterprise, try the enterprise-specific endpoint
    enterprise_orgs = client.api_call(
        f"/enterprises/{enterprise}/organizations",
        paginate=True,
    )

    org_names: list[str] = []
    if isinstance(enterprise_orgs, list):
        org_names = [o.get("login", "") for o in enterprise_orgs if o.get("login")]
    elif isinstance(orgs_data, list):
        org_names = [o.get("login", "") for o in orgs_data if o.get("login")]

    if org_names:
        log_info(f"Found {len(org_names)} organizations")
        for org_name in org_names:
            org_results = audit_org(client, org_name, rules, verbose=verbose)
            results.extend(org_results)
    else:
        log_warn("No organizations found or insufficient permissions to list enterprise orgs")

    return results


def audit_org(client: GitHubClient, org: str, rules: list[Rule],
              verbose: bool = False) -> list[AuditResult]:
    """Audit an organization and all its repositories."""
    results: list[AuditResult] = []
    org_rules = [r for r in rules if r.level == "organization"]
    target_vars = {"org": org, "target_name": org}

    log_info(f"Auditing organization: {org}")
    log_info(f"Checking {len(org_rules)} organization-level rules...")

    for rule in org_rules:
        if verbose:
            log_verbose(f"Checking {rule.id}: {rule.name}")
        result = check_rule(client, rule, target_vars)
        results.append(result)
        _log_result(result, verbose)

    # Discover repositories in the organization
    log_info("Discovering repositories in organization...")
    repos_data = client.api_call(f"/orgs/{org}/repos?per_page=100&type=all", paginate=True)

    repo_list: list[dict] = []
    if isinstance(repos_data, list):
        repo_list = repos_data
    elif repos_data is None or (isinstance(repos_data, dict) and repos_data.get("_error")):
        log_warn(f"Could not list repositories for {org}")

    if repo_list:
        log_info(f"Found {len(repo_list)} repositories")
        for repo_info in repo_list:
            repo_full_name = repo_info.get("full_name", "")
            if not repo_full_name:
                continue
            # Skip archived repos
            if repo_info.get("archived", False):
                if verbose:
                    log_verbose(f"Skipping archived repo: {repo_full_name}")
                continue
            default_branch = repo_info.get("default_branch", "main")
            repo_results = audit_repo(
                client, repo_full_name, rules,
                default_branch=default_branch, verbose=verbose,
            )
            results.extend(repo_results)
    else:
        log_warn("No repositories found or insufficient permissions")

    return results


def audit_repo(client: GitHubClient, repo: str, rules: list[Rule],
               default_branch: str = "", local_path: str = "",
               verbose: bool = False) -> list[AuditResult]:
    """Audit a single repository."""
    results: list[AuditResult] = []
    repo_rules = [r for r in rules if r.level == "repository"]

    if not default_branch and not local_path:
        # Fetch repo info to get default branch
        repo_data = client.api_call(f"/repos/{repo}")
        if isinstance(repo_data, dict) and not repo_data.get("_error"):
            default_branch = repo_data.get("default_branch", "main")
        else:
            default_branch = "main"

    parts = repo.split("/")
    owner = parts[0] if len(parts) >= 2 else repo
    repo_name = parts[1] if len(parts) >= 2 else repo

    target_vars = {
        "owner": owner,
        "repo": repo_name,
        "branch": default_branch,
        "target_name": repo,
        "org": owner,
    }

    log_info(f"Auditing repository: {repo} (branch: {default_branch})")
    log_info(f"Checking {len(repo_rules)} repository-level rules...")

    for rule in repo_rules:
        if verbose:
            log_verbose(f"Checking {rule.id}: {rule.name}")
        result = check_rule(client, rule, target_vars, local_path=local_path)
        results.append(result)
        _log_result(result, verbose)

    return results


def audit_local_path(rules: list[Rule], local_path: str,
                     verbose: bool = False) -> list[AuditResult]:
    """Audit a local directory for file-based rules only."""
    results: list[AuditResult] = []
    file_rules = [
        r for r in rules
        if r.level == "repository" and r.check_type in ("file_exists", "file_exists_multi")
    ]

    log_info(f"Auditing local path: {local_path}")
    log_info(f"Checking {len(file_rules)} file-based rules...")

    if not os.path.isdir(local_path):
        log_error(f"Local path does not exist: {local_path}")
        return results

    # Check if it's a single repo or multiple repos
    dirs = [d for d in os.listdir(local_path)
            if os.path.isdir(os.path.join(local_path, d)) and not d.startswith(".")]

    # Heuristic: if .git exists, treat as single repo
    if os.path.isdir(os.path.join(local_path, ".git")):
        dirs = ["."]

    if not dirs:
        dirs = ["."]

    for d in dirs:
        dir_path = os.path.join(local_path, d) if d != "." else local_path
        target_name = os.path.basename(os.path.abspath(dir_path))
        target_vars = {
            "owner": "local",
            "repo": target_name,
            "branch": "local",
            "target_name": f"local/{target_name}",
        }

        for rule in file_rules:
            if verbose:
                log_verbose(f"Checking {rule.id}: {rule.name} in {target_name}")
            result = check_rule(None, rule, target_vars, local_path=dir_path)
            results.append(result)
            _log_result(result, verbose)

    return results


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------
def generate_scorecard(results: list[AuditResult], target: str) -> str:
    """Generate a text summary scorecard from audit results."""
    lines: list[str] = []
    lines.append("")
    lines.append(f"{BOLD}GitHub Best Practices Audit - {target}{RESET}")
    lines.append(f"{BOLD}{'=' * 55}{RESET}")

    # Overall counts
    total = len(results)
    passed = sum(1 for r in results if r.status == "PASS")
    failed = sum(1 for r in results if r.status == "FAIL")
    skipped = sum(1 for r in results if r.status in ("SKIP", "ERROR"))
    score = int((passed / (passed + failed)) * 100) if (passed + failed) > 0 else 0

    # Score color
    if score >= 80:
        score_color = GREEN
    elif score >= 60:
        score_color = YELLOW
    else:
        score_color = RED

    lines.append(f"Overall Score: {score_color}{BOLD}{score}/100{RESET}")
    lines.append(f"Total Rules: {total}  |  Passed: {GREEN}{passed}{RESET}  |  "
                 f"Failed: {RED}{failed}{RESET}  |  Skipped: {DIM}{skipped}{RESET}")
    lines.append("")

    # By Benchmark
    lines.append(f"{BOLD}By Benchmark:{RESET}")
    benchmarks_seen: dict[str, dict] = {}
    for r in results:
        bm = r.benchmark
        if bm not in benchmarks_seen:
            benchmarks_seen[bm] = {"pass": 0, "fail": 0, "skip": 0}
        if r.status == "PASS":
            benchmarks_seen[bm]["pass"] += 1
        elif r.status == "FAIL":
            benchmarks_seen[bm]["fail"] += 1
        else:
            benchmarks_seen[bm]["skip"] += 1

    for bm, counts in sorted(benchmarks_seen.items()):
        p, f = counts["pass"], counts["fail"]
        pct = int((p / (p + f)) * 100) if (p + f) > 0 else 0
        if pct >= 80:
            pct_color = GREEN
        elif pct >= 60:
            pct_color = YELLOW
        else:
            pct_color = RED
        bm_label = f"{bm:15s}"
        lines.append(f"  {bm_label} {pct_color}{pct:3d}%{RESET} ({p}/{p + f} rules passing)")

    lines.append("")

    # By Severity
    lines.append(f"{BOLD}By Severity:{RESET}")
    for sev in ("critical", "high", "medium", "low", "info"):
        sev_results = [r for r in results if r.severity == sev]
        if not sev_results:
            continue
        p = sum(1 for r in sev_results if r.status == "PASS")
        f = sum(1 for r in sev_results if r.status == "FAIL")
        s = sum(1 for r in sev_results if r.status in ("SKIP", "ERROR"))
        sev_label = f"{sev.upper():12s}"
        fail_str = f"{RED}{f} FAIL{RESET}" if f > 0 else f"{GREEN}0 FAIL{RESET}"
        lines.append(f"  {sev_label} {fail_str}, {GREEN}{p} PASS{RESET}"
                     + (f", {DIM}{s} SKIP{RESET}" if s > 0 else ""))

    lines.append("")

    # Top Issues (failures sorted by severity)
    failures = [r for r in results if r.status == "FAIL"]
    failures.sort(key=lambda r: SEVERITY_ORDER.get(r.severity, 4))

    if failures:
        lines.append(f"{BOLD}Top Issues:{RESET}")
        for i, r in enumerate(failures[:10], 1):
            sev_label = r.severity.upper()
            if sev_label == "CRITICAL":
                sev_color = RED
            elif sev_label == "HIGH":
                sev_color = YELLOW
            else:
                sev_color = BLUE
            lines.append(f"  {i:2d}. [{sev_color}{sev_label}{RESET}] "
                         f"{r.rule_id}: {r.rule_name} ({r.target})")
        if len(failures) > 10:
            lines.append(f"  ... and {len(failures) - 10} more issues")
    else:
        lines.append(f"{GREEN}{BOLD}No issues found! All checks passed.{RESET}")

    lines.append(f"{BOLD}{'=' * 55}{RESET}")
    lines.append("")

    return "\n".join(lines)


def export_csv(results: list[AuditResult], filepath: str) -> str:
    """Export audit results to CSV file."""
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Target", "Level", "RuleID", "RuleName", "Benchmark",
            "Category", "Severity", "Status", "CurrentValue",
            "ExpectedValue", "Remediation",
        ])
        for r in results:
            writer.writerow([
                r.target, r.level, r.rule_id, r.rule_name, r.benchmark,
                r.category, r.severity, r.status, r.current_value,
                r.expected_value, r.remediation,
            ])
    return filepath


def export_json(results: list[AuditResult], filepath: str) -> str:
    """Export audit results to JSON file."""
    data = {
        "audit_timestamp": TIMESTAMP,
        "tool": SCRIPT_NAME,
        "version": VERSION,
        "total_rules": len(results),
        "passed": sum(1 for r in results if r.status == "PASS"),
        "failed": sum(1 for r in results if r.status == "FAIL"),
        "skipped": sum(1 for r in results if r.status in ("SKIP", "ERROR")),
        "results": [asdict(r) for r in results],
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    return filepath


def export_html(results: list[AuditResult], filepath: str, target: str) -> str:
    """Export audit results to an HTML report."""
    total = len(results)
    passed = sum(1 for r in results if r.status == "PASS")
    failed = sum(1 for r in results if r.status == "FAIL")
    skipped = sum(1 for r in results if r.status in ("SKIP", "ERROR"))
    score = int((passed / (passed + failed)) * 100) if (passed + failed) > 0 else 0

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GitHub Best Practices Audit - {target}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         margin: 20px; background: #0d1117; color: #c9d1d9; }}
  h1 {{ color: #58a6ff; border-bottom: 1px solid #30363d; padding-bottom: 10px; }}
  h2 {{ color: #8b949e; }}
  .score {{ font-size: 2em; font-weight: bold; }}
  .score.high {{ color: #3fb950; }}
  .score.medium {{ color: #d29922; }}
  .score.low {{ color: #f85149; }}
  .summary {{ display: flex; gap: 20px; margin: 20px 0; }}
  .summary-card {{ background: #161b22; padding: 15px 20px; border-radius: 6px;
                   border: 1px solid #30363d; text-align: center; }}
  .summary-card .number {{ font-size: 1.5em; font-weight: bold; }}
  .pass {{ color: #3fb950; }}
  .fail {{ color: #f85149; }}
  .skip {{ color: #8b949e; }}
  table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
  th {{ background: #161b22; color: #8b949e; text-align: left; padding: 10px;
       border: 1px solid #30363d; }}
  td {{ padding: 8px 10px; border: 1px solid #30363d; }}
  tr:nth-child(even) {{ background: #161b22; }}
  .badge {{ padding: 2px 8px; border-radius: 12px; font-size: 0.8em; font-weight: bold; }}
  .badge-pass {{ background: #238636; color: #fff; }}
  .badge-fail {{ background: #da3633; color: #fff; }}
  .badge-skip {{ background: #30363d; color: #8b949e; }}
  .badge-critical {{ background: #da3633; color: #fff; }}
  .badge-high {{ background: #d29922; color: #000; }}
  .badge-medium {{ background: #2ea043; color: #fff; }}
  .badge-low {{ background: #388bfd; color: #fff; }}
  .badge-info {{ background: #30363d; color: #8b949e; }}
  footer {{ margin-top: 40px; padding-top: 10px; border-top: 1px solid #30363d;
           color: #8b949e; font-size: 0.9em; }}
</style>
</head>
<body>
<h1>GitHub Best Practices Audit</h1>
<p>Target: <strong>{target}</strong> | Generated: {TIMESTAMP} | Tool: {SCRIPT_NAME} v{VERSION}</p>

<div class="score {'high' if score >= 80 else 'medium' if score >= 60 else 'low'}">
  Score: {score}/100
</div>

<div class="summary">
  <div class="summary-card"><div class="number">{total}</div>Total Rules</div>
  <div class="summary-card"><div class="number pass">{passed}</div>Passed</div>
  <div class="summary-card"><div class="number fail">{failed}</div>Failed</div>
  <div class="summary-card"><div class="number skip">{skipped}</div>Skipped</div>
</div>

<h2>Detailed Results</h2>
<table>
<thead>
<tr><th>Target</th><th>Rule ID</th><th>Rule Name</th><th>Benchmark</th>
<th>Severity</th><th>Status</th><th>Current Value</th><th>Remediation</th></tr>
</thead>
<tbody>
"""
    for r in results:
        sev_class = f"badge-{r.severity}"
        status_class = f"badge-{'pass' if r.status == 'PASS' else 'fail' if r.status == 'FAIL' else 'skip'}"
        html += f"""<tr>
<td>{r.target}</td><td>{r.rule_id}</td><td>{r.rule_name}</td>
<td>{r.benchmark}</td>
<td><span class="badge {sev_class}">{r.severity.upper()}</span></td>
<td><span class="badge {status_class}">{r.status}</span></td>
<td>{r.current_value}</td>
<td>{r.remediation if r.status == 'FAIL' else ''}</td>
</tr>
"""

    html += f"""</tbody>
</table>
<footer>Written by {AUTHOR} | {SCRIPT_NAME} v{VERSION}</footer>
</body>
</html>"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)
    return filepath


def upload_to_s3(filepath: str, bucket: str, prefix: str = "") -> str:
    """Upload a file to S3 (requires boto3 or aws cli)."""
    filename = os.path.basename(filepath)
    s3_key = f"{prefix}/{filename}" if prefix else filename

    try:
        import boto3
        s3 = boto3.client("s3")
        s3.upload_file(filepath, bucket, s3_key)
        log_success(f"Uploaded to s3://{bucket}/{s3_key}")
        return f"s3://{bucket}/{s3_key}"
    except ImportError:
        # Fall back to AWS CLI
        try:
            result = subprocess.run(
                ["aws", "s3", "cp", filepath, f"s3://{bucket}/{s3_key}"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                log_success(f"Uploaded to s3://{bucket}/{s3_key}")
                return f"s3://{bucket}/{s3_key}"
            else:
                log_error(f"S3 upload failed: {result.stderr}")
                return ""
        except FileNotFoundError:
            log_error("Neither boto3 nor AWS CLI available for S3 upload")
            return ""


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------
def log_info(msg: str) -> None:
    print(f"{BLUE}[INFO]{RESET} {msg}")


def log_success(msg: str) -> None:
    print(f"{GREEN}[OK]{RESET} {msg}")


def log_warn(msg: str) -> None:
    print(f"{YELLOW}[WARN]{RESET} {msg}", file=sys.stderr)


def log_error(msg: str) -> None:
    print(f"{RED}[ERROR]{RESET} {msg}", file=sys.stderr)


def log_verbose(msg: str) -> None:
    print(f"{CYAN}[VERBOSE]{RESET} {msg}")


def _log_result(result: AuditResult, verbose: bool) -> None:
    """Log a single audit result."""
    if result.status == "PASS":
        if verbose:
            print(f"  {GREEN}PASS{RESET} {result.rule_id}: {result.rule_name}")
    elif result.status == "FAIL":
        sev = result.severity.upper()
        if sev == "CRITICAL":
            sev_color = RED
        elif sev == "HIGH":
            sev_color = YELLOW
        else:
            sev_color = BLUE
        print(f"  {RED}FAIL{RESET} [{sev_color}{sev}{RESET}] "
              f"{result.rule_id}: {result.rule_name} "
              f"(current: {result.current_value})")
    elif result.status == "SKIP" and verbose:
        print(f"  {DIM}SKIP{RESET} {result.rule_id}: {result.rule_name} "
              f"({result.current_value})")
    elif result.status == "ERROR" and verbose:
        print(f"  {RED}ERROR{RESET} {result.rule_id}: {result.current_value}")


# ---------------------------------------------------------------------------
# Interactive mode
# ---------------------------------------------------------------------------
def run_interactive() -> dict[str, Any]:
    """Run the tool in interactive mode, prompting for all options."""
    print(f"\n{BOLD}{CYAN}{'=' * 55}{RESET}")
    print(f"{BOLD}{CYAN}  gh-best-practices-audit - Interactive Mode{RESET}")
    print(f"{BOLD}{CYAN}  Written by {AUTHOR}{RESET}")
    print(f"{BOLD}{CYAN}{'=' * 55}{RESET}\n")

    opts: dict[str, Any] = {}

    # Target selection
    print(f"{BOLD}Select audit target:{RESET}")
    print("  1) Enterprise (audit enterprise + all orgs + repos)")
    print("  2) Organization (audit org + all repos)")
    print("  3) Single Repository")
    print("  4) Local Path (file-based checks only)")
    print()

    choice = input(f"{CYAN}Enter choice [1-4]: {RESET}").strip()

    if choice == "1":
        name = input(f"{CYAN}Enterprise name: {RESET}").strip()
        if not name:
            log_error("Enterprise name is required.")
            sys.exit(1)
        opts["enterprise"] = name
    elif choice == "2":
        name = input(f"{CYAN}Organization name: {RESET}").strip()
        if not name:
            log_error("Organization name is required.")
            sys.exit(1)
        opts["org"] = name
    elif choice == "3":
        name = input(f"{CYAN}Repository (owner/repo): {RESET}").strip()
        if not name or "/" not in name:
            log_error("Repository must be in owner/repo format.")
            sys.exit(1)
        opts["repo"] = name
    elif choice == "4":
        path = input(f"{CYAN}Local path: {RESET}").strip()
        if not path or not os.path.isdir(path):
            log_error("Valid local path is required.")
            sys.exit(1)
        opts["local_path"] = path
    else:
        log_error("Invalid choice.")
        sys.exit(1)

    # Benchmarks
    print(f"\n{BOLD}Select benchmarks:{RESET}")
    print("  1) All (CIS + OWASP + SANS)")
    print("  2) CIS GitHub Benchmark only")
    print("  3) OWASP CI/CD Top 10 only")
    print("  4) SANS Top 25 only")
    print("  5) Custom selection")
    bm_choice = input(f"{CYAN}Enter choice [1-5] (default: 1): {RESET}").strip() or "1"

    if bm_choice == "1":
        opts["benchmarks"] = "all"
    elif bm_choice == "2":
        opts["benchmarks"] = "cis"
    elif bm_choice == "3":
        opts["benchmarks"] = "owasp"
    elif bm_choice == "4":
        opts["benchmarks"] = "sans"
    elif bm_choice == "5":
        sel = input(f"{CYAN}Enter benchmarks (comma-separated: cis,owasp,sans): {RESET}").strip()
        opts["benchmarks"] = sel or "all"

    # Severity
    print(f"\n{BOLD}Minimum severity level:{RESET}")
    print("  1) Critical only")
    print("  2) High and above")
    print("  3) Medium and above")
    print("  4) Low and above (default)")
    print("  5) Info (all)")
    sev_choice = input(f"{CYAN}Enter choice [1-5] (default: 4): {RESET}").strip() or "4"
    sev_map = {"1": "critical", "2": "high", "3": "medium", "4": "low", "5": "info"}
    opts["severity"] = sev_map.get(sev_choice, "low")

    # Custom rules
    custom = input(f"\n{CYAN}Custom rules file (CSV/Excel, or press Enter to skip): {RESET}").strip()
    if custom:
        opts["custom_rules"] = custom

    # Output format
    print(f"\n{BOLD}Output format:{RESET}")
    print("  1) CSV (default)")
    print("  2) JSON")
    print("  3) HTML")
    fmt_choice = input(f"{CYAN}Enter choice [1-3] (default: 1): {RESET}").strip() or "1"
    fmt_map = {"1": "csv", "2": "json", "3": "html"}
    opts["format"] = fmt_map.get(fmt_choice, "csv")

    # Output file
    out = input(f"\n{CYAN}Output file (press Enter for default): {RESET}").strip()
    if out:
        opts["output"] = out

    # Summary only
    summary = input(f"\n{CYAN}Show summary scorecard only? [y/N]: {RESET}").strip().lower()
    opts["summary"] = summary in ("y", "yes")

    # Verbose
    verbose = input(f"{CYAN}Verbose output? [y/N]: {RESET}").strip().lower()
    opts["verbose"] = verbose in ("y", "yes")

    # Auth
    print(f"\n{BOLD}Authentication:{RESET}")
    print("  1) GitHub CLI (default)")
    print("  2) Personal Access Token")
    print("  3) GitHub App")
    auth_choice = input(f"{CYAN}Enter choice [1-3] (default: 1): {RESET}").strip() or "1"
    if auth_choice == "1":
        opts["auth"] = "gh"
    elif auth_choice == "2":
        opts["auth"] = "pat"
        opts["token"] = input(f"{CYAN}PAT token: {RESET}").strip()
    elif auth_choice == "3":
        opts["auth"] = "app"
        opts["app_id"] = input(f"{CYAN}App ID: {RESET}").strip()
        opts["app_key"] = input(f"{CYAN}App private key file: {RESET}").strip()

    return opts


# ---------------------------------------------------------------------------
# CLI argument parser
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog=SCRIPT_NAME,
        description=f"{SCRIPT_NAME} - GitHub Best Practices Auditor\nWritten by {AUTHOR}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(f"""\
            examples:
              python gh_best_practices_audit.py -o my-org --benchmarks cis
              python gh_best_practices_audit.py -e my-enterprise --severity high
              python gh_best_practices_audit.py -r my-org/my-repo --custom-rules my_rules.csv
              python gh_best_practices_audit.py --local-path ./downloaded-repos --benchmarks all
              python gh_best_practices_audit.py -i

            Written by {AUTHOR} | {SCRIPT_NAME} v{VERSION}
        """),
    )

    # Target
    target = parser.add_argument_group("target")
    target.add_argument("-e", "--enterprise", metavar="<name>",
                        help="Audit enterprise settings + all orgs")
    target.add_argument("-o", "--org", metavar="<name>",
                        help="Audit organization + all repos")
    target.add_argument("-r", "--repo", metavar="<owner/repo>",
                        help="Audit single repository")
    target.add_argument("--local-path", metavar="<dir>",
                        help="Audit local repo files (downloaded state)")

    # Rules
    rules_group = parser.add_argument_group("rules")
    rules_group.add_argument("--benchmarks", metavar="<list>", default="all",
                             help="Benchmarks to check: cis,owasp,sans,all (default: all)")
    rules_group.add_argument("--custom-rules", metavar="<file>",
                             help="Custom rules file (CSV or Excel)")
    rules_group.add_argument("--severity", metavar="<level>", default="low",
                             choices=["critical", "high", "medium", "low", "info"],
                             help="Min severity: critical,high,medium,low,info (default: low)")
    rules_group.add_argument("--category", metavar="<cat>", default="",
                             help="Filter by category: auth,branch-protection,secrets,"
                                  "ci-cd,access,repo-settings")

    # Auth
    auth_group = parser.add_argument_group("auth")
    auth_group.add_argument("-a", "--auth", metavar="<method>", default="gh",
                            choices=["gh", "pat", "app"],
                            help="Auth: gh|pat|app (default: gh)")
    auth_group.add_argument("-t", "--token", metavar="<token>", default="",
                            help="PAT token")
    auth_group.add_argument("--app-id", metavar="<id>", default="",
                            help="GitHub App ID")
    auth_group.add_argument("--app-key", metavar="<file>", default="",
                            help="App private key file")

    # Output
    output = parser.add_argument_group("output")
    output.add_argument("--output", metavar="<file>", default="",
                        help="Output file (default: timestamped CSV)")
    output.add_argument("--format", metavar="<fmt>", default="csv",
                        choices=["csv", "json", "html"], dest="output_format",
                        help="csv|json|html (default: csv)")
    output.add_argument("--s3-bucket", metavar="<bucket>", default="",
                        help="S3 bucket for Lambda output")
    output.add_argument("--s3-prefix", metavar="<prefix>", default="",
                        help="S3 key prefix")
    output.add_argument("--summary", action="store_true",
                        help="Print summary scorecard only")

    # Runtime
    runtime = parser.add_argument_group("runtime")
    runtime.add_argument("--mode", metavar="<mode>", default="local",
                         choices=["local", "lambda"],
                         help="local|lambda (default: local)")
    runtime.add_argument("-i", "--interactive", action="store_true",
                         help="Interactive mode")
    runtime.add_argument("-v", "--verbose", action="store_true",
                         help="Verbose output")
    runtime.add_argument("--version", action="version",
                         version=f"{SCRIPT_NAME} v{VERSION} - Written by {AUTHOR}")

    return parser


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
def show_banner() -> None:
    """Display the tool banner."""
    print(f"{BOLD}{CYAN}")
    print("=" * 55)
    print(f"  {SCRIPT_NAME} - GitHub Best Practices Auditor")
    print(f"  Written by {AUTHOR}")
    print("=" * 55)
    print(f"{RESET}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def main(event: Optional[dict] = None) -> dict[str, Any]:
    """
    Main entry point. Can be called from CLI or from Lambda handler.

    Args:
        event: Optional dict of parameters (used by Lambda handler).
               If None, parses CLI arguments.

    Returns:
        Dict with audit summary and output file location.
    """
    # Determine parameters from CLI args or event dict
    if event:
        # Lambda / programmatic invocation
        enterprise = event.get("enterprise", "")
        org = event.get("org", "")
        repo = event.get("repo", "")
        local_path = event.get("local_path", "")
        benchmarks_str = event.get("benchmarks", "all")
        custom_rules_file = event.get("custom_rules", "")
        severity = event.get("severity", "low")
        category = event.get("category", "")
        auth_method = event.get("auth", "gh")
        token = event.get("token", "")
        app_id = event.get("app_id", "")
        app_key = event.get("app_key", "")
        output_file = event.get("output", "")
        output_format = event.get("format", "csv")
        s3_bucket = event.get("s3_bucket", "")
        s3_prefix = event.get("s3_prefix", "")
        summary_only = event.get("summary", False)
        verbose = event.get("verbose", False)
    else:
        parser = build_parser()
        args = parser.parse_args()

        if args.interactive:
            opts = run_interactive()
            enterprise = opts.get("enterprise", "")
            org = opts.get("org", "")
            repo = opts.get("repo", "")
            local_path = opts.get("local_path", "")
            benchmarks_str = opts.get("benchmarks", "all")
            custom_rules_file = opts.get("custom_rules", "")
            severity = opts.get("severity", "low")
            category = opts.get("category", "")
            auth_method = opts.get("auth", "gh")
            token = opts.get("token", "")
            app_id = opts.get("app_id", "")
            app_key = opts.get("app_key", "")
            output_file = opts.get("output", "")
            output_format = opts.get("format", "csv")
            s3_bucket = opts.get("s3_bucket", "")
            s3_prefix = opts.get("s3_prefix", "")
            summary_only = opts.get("summary", False)
            verbose = opts.get("verbose", False)
        else:
            enterprise = args.enterprise or ""
            org = args.org or ""
            repo = args.repo or ""
            local_path = args.local_path or ""
            benchmarks_str = args.benchmarks
            custom_rules_file = args.custom_rules or ""
            severity = args.severity
            category = args.category
            auth_method = args.auth
            token = args.token
            app_id = args.app_id
            app_key = args.app_key
            output_file = args.output
            output_format = args.output_format
            s3_bucket = args.s3_bucket
            s3_prefix = args.s3_prefix
            summary_only = args.summary
            verbose = args.verbose

        if not any([enterprise, org, repo, local_path]):
            show_banner()
            parser.print_help()
            sys.exit(1)

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    if not event:
        show_banner()

    # Parse benchmarks
    if benchmarks_str == "all":
        benchmarks = {"cis", "owasp", "sans"}
    else:
        benchmarks = {b.strip().lower() for b in benchmarks_str.split(",")}
        invalid = benchmarks - VALID_BENCHMARKS
        if invalid:
            log_error(f"Invalid benchmarks: {invalid}. Valid: {VALID_BENCHMARKS}")
            sys.exit(1)

    # Load rules
    log_info("Loading audit rules...")
    rules = load_rules(RULES_DIR, benchmarks)

    if custom_rules_file:
        custom_rules = load_custom_rules(custom_rules_file)
        rules.extend(custom_rules)

    if not rules:
        log_error("No rules loaded. Check rules directory and benchmark selection.")
        sys.exit(1)

    # Filter rules
    rules = filter_rules(rules, severity=severity, category=category)
    log_info(f"Total rules to check: {len(rules)}")

    # Initialize GitHub client (not needed for local-only checks)
    client = None
    if not local_path or any([enterprise, org, repo]):
        try:
            client = GitHubClient(
                auth_method=auth_method,
                token=token,
                app_id=app_id,
                app_key_file=app_key,
            )
            log_success("GitHub authentication verified")
        except RuntimeError as exc:
            log_error(str(exc))
            sys.exit(1)

    # Run audit
    results: list[AuditResult] = []
    target_name = ""

    if enterprise:
        target_name = enterprise
        results = audit_enterprise(client, enterprise, rules, verbose=verbose)
    elif org:
        target_name = org
        results = audit_org(client, org, rules, verbose=verbose)
    elif repo:
        target_name = repo
        results = audit_repo(client, repo, rules, verbose=verbose)
    elif local_path:
        target_name = os.path.basename(os.path.abspath(local_path))
        if client:
            # If we have API access, run all checks
            results = audit_local_path(rules, local_path, verbose=verbose)
        else:
            # Local only - file checks
            results = audit_local_path(rules, local_path, verbose=verbose)

    if not results:
        log_warn("No audit results generated. Check target and permissions.")
        return {"status": "no_results", "results": []}

    # Generate scorecard
    scorecard = generate_scorecard(results, target_name)
    print(scorecard)

    if summary_only:
        return {
            "status": "ok",
            "target": target_name,
            "total": len(results),
            "passed": sum(1 for r in results if r.status == "PASS"),
            "failed": sum(1 for r in results if r.status == "FAIL"),
        }

    # Export results
    if not output_file:
        output_file = f"audit_{target_name.replace('/', '_')}_{TIMESTAMP}.{output_format}"

    if output_format == "csv":
        export_csv(results, output_file)
    elif output_format == "json":
        export_json(results, output_file)
    elif output_format == "html":
        export_html(results, output_file, target_name)

    log_success(f"Report saved to: {output_file}")

    # S3 upload if configured
    s3_url = ""
    if s3_bucket:
        s3_url = upload_to_s3(output_file, s3_bucket, s3_prefix)

    return {
        "status": "ok",
        "target": target_name,
        "total": len(results),
        "passed": sum(1 for r in results if r.status == "PASS"),
        "failed": sum(1 for r in results if r.status == "FAIL"),
        "skipped": sum(1 for r in results if r.status in ("SKIP", "ERROR")),
        "output_file": output_file,
        "s3_url": s3_url,
    }


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Interrupted by user.{RESET}")
        sys.exit(130)
