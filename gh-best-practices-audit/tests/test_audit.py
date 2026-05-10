"""
Tests for gh-best-practices-audit.
Written by h3nryza

Run with: pytest tests/ -v
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gh_best_practices_audit import (
    Rule,
    AuditResult,
    GitHubClient,
    load_rules,
    load_custom_rules,
    filter_rules,
    get_nested_value,
    evaluate_expected,
    check_rule,
    audit_repo,
    audit_org,
    audit_local_path,
    generate_scorecard,
    export_csv,
    export_json,
    export_html,
    build_parser,
)


# ──────────────────────────────────────────────
# Rule loading tests
# ──────────────────────────────────────────────
class TestLoadRules:
    """Tests for loading rules from JSON files."""

    def test_load_all_benchmarks(self, rules_dir):
        """All three benchmark files should load successfully."""
        rules = load_rules(rules_dir, {"cis", "owasp", "sans"})
        assert len(rules) > 0
        benchmarks = {r.benchmark for r in rules}
        assert "CIS" in benchmarks
        assert "OWASP" in benchmarks
        assert "SANS" in benchmarks

    def test_load_cis_only(self, rules_dir):
        """Loading CIS only should not include OWASP or SANS rules."""
        rules = load_rules(rules_dir, {"cis"})
        assert len(rules) > 0
        benchmarks = {r.benchmark for r in rules}
        assert "CIS" in benchmarks
        assert "OWASP" not in benchmarks
        assert "SANS" not in benchmarks

    def test_load_owasp_only(self, rules_dir):
        """Loading OWASP only should not include CIS or SANS rules."""
        rules = load_rules(rules_dir, {"owasp"})
        assert len(rules) > 0
        benchmarks = {r.benchmark for r in rules}
        assert "OWASP" in benchmarks
        assert "CIS" not in benchmarks

    def test_load_sans_only(self, rules_dir):
        """Loading SANS only should not include CIS or OWASP rules."""
        rules = load_rules(rules_dir, {"sans"})
        assert len(rules) > 0
        benchmarks = {r.benchmark for r in rules}
        assert "SANS" in benchmarks
        assert "CIS" not in benchmarks

    def test_load_nonexistent_benchmark(self, rules_dir):
        """Loading a nonexistent benchmark should return empty list."""
        rules = load_rules(rules_dir, {"nonexistent"})
        assert len(rules) == 0

    def test_rules_have_required_fields(self, rules_dir):
        """All rules should have required fields populated."""
        rules = load_rules(rules_dir, {"cis", "owasp", "sans"})
        for rule in rules:
            assert rule.id, f"Rule missing id: {rule}"
            assert rule.name, f"Rule {rule.id} missing name"
            assert rule.severity in ("critical", "high", "medium", "low", "info"), \
                f"Rule {rule.id} has invalid severity: {rule.severity}"
            assert rule.level in ("enterprise", "organization", "repository"), \
                f"Rule {rule.id} has invalid level: {rule.level}"
            assert rule.check_type, f"Rule {rule.id} missing check_type"

    def test_cis_rule_counts(self, rules_dir):
        """CIS should have enterprise, org, and repo rules."""
        rules = load_rules(rules_dir, {"cis"})
        levels = {r.level for r in rules}
        assert "enterprise" in levels
        assert "organization" in levels
        assert "repository" in levels
        # Minimum counts per spec
        enterprise_rules = [r for r in rules if r.level == "enterprise"]
        org_rules = [r for r in rules if r.level == "organization"]
        repo_rules = [r for r in rules if r.level == "repository"]
        assert len(enterprise_rules) >= 5
        assert len(org_rules) >= 14
        assert len(repo_rules) >= 20


class TestLoadCustomRules:
    """Tests for loading custom rules from CSV."""

    def test_load_csv_rules(self, custom_rules_csv):
        """Custom CSV rules should load correctly."""
        rules = load_custom_rules(custom_rules_csv)
        assert len(rules) == 1
        assert rules[0].id == "CUSTOM-TEST-01"
        assert rules[0].severity == "medium"
        assert rules[0].expected_value is False

    def test_load_nonexistent_file(self):
        """Loading from nonexistent file should return empty list."""
        rules = load_custom_rules("/nonexistent/file.csv")
        assert len(rules) == 0

    def test_load_custom_template(self, rules_dir):
        """The included custom template should load."""
        template = rules_dir / "custom_template.csv"
        rules = load_custom_rules(str(template))
        assert len(rules) > 0


class TestFilterRules:
    """Tests for filtering rules by severity and category."""

    def test_filter_by_severity_critical(self, rules_dir):
        """Filtering by critical should only return critical rules."""
        rules = load_rules(rules_dir, {"cis"})
        filtered = filter_rules(rules, severity="critical")
        assert all(r.severity == "critical" for r in filtered)
        assert len(filtered) > 0

    def test_filter_by_severity_low(self, rules_dir):
        """Filtering by low should include all severities except info."""
        rules = load_rules(rules_dir, {"cis"})
        filtered = filter_rules(rules, severity="low")
        severities = {r.severity for r in filtered}
        assert "critical" in severities or "high" in severities
        assert len(filtered) >= len(filter_rules(rules, severity="critical"))

    def test_filter_by_category(self, rules_dir):
        """Filtering by category should only return matching rules."""
        rules = load_rules(rules_dir, {"cis"})
        filtered = filter_rules(rules, category="auth")
        assert all(r.category == "auth" for r in filtered)

    def test_filter_by_severity_and_category(self, rules_dir):
        """Filtering by both severity and category should intersect."""
        rules = load_rules(rules_dir, {"cis"})
        filtered = filter_rules(rules, severity="critical", category="branch-protection")
        assert all(r.severity == "critical" and r.category == "branch-protection"
                   for r in filtered)


# ──────────────────────────────────────────────
# Value extraction and evaluation tests
# ──────────────────────────────────────────────
class TestGetNestedValue:
    """Tests for nested value extraction from dicts."""

    def test_simple_key(self):
        assert get_nested_value({"a": 1}, "a") == 1

    def test_nested_key(self):
        assert get_nested_value({"a": {"b": {"c": 3}}}, "a.b.c") == 3

    def test_missing_key(self):
        assert get_nested_value({"a": 1}, "b") is None

    def test_none_data(self):
        assert get_nested_value(None, "a") is None

    def test_deep_nested(self):
        data = {"security_and_analysis": {"secret_scanning": {"status": "enabled"}}}
        assert get_nested_value(data, "security_and_analysis.secret_scanning.status") == "enabled"


class TestEvaluateExpected:
    """Tests for expected value evaluation."""

    def test_bool_true(self):
        assert evaluate_expected(True, True) is True
        assert evaluate_expected(False, True) is False

    def test_bool_false(self):
        assert evaluate_expected(False, False) is True
        assert evaluate_expected(True, False) is False

    def test_string_match(self):
        assert evaluate_expected("read", "read") is True
        assert evaluate_expected("write", "read") is False

    def test_not_null(self):
        assert evaluate_expected("something", "not_null") is True
        assert evaluate_expected(None, "not_null") is False

    def test_gte_operator(self):
        assert evaluate_expected(2, ">=1") is True
        assert evaluate_expected(1, ">=1") is True
        assert evaluate_expected(0, ">=1") is False

    def test_gt_operator(self):
        assert evaluate_expected(1, ">0") is True
        assert evaluate_expected(0, ">0") is False

    def test_list_of_values(self):
        assert evaluate_expected("read", ["none", "read"]) is True
        assert evaluate_expected("write", ["none", "read"]) is False

    def test_int_comparison(self):
        assert evaluate_expected(0, 0) is True
        assert evaluate_expected(5, 0) is False

    def test_string_enabled(self):
        assert evaluate_expected("enabled", "enabled") is True
        assert evaluate_expected("disabled", "enabled") is False


# ──────────────────────────────────────────────
# Rule checking tests
# ──────────────────────────────────────────────
class TestCheckRule:
    """Tests for individual rule checking."""

    def test_api_check_pass(self, mock_client, sample_org_response):
        """API check should pass when field matches expected value."""
        mock_client.api_call.return_value = sample_org_response
        rule = Rule(
            id="TEST-01", name="Test 2FA", description="",
            benchmark="TEST", category="auth", severity="critical",
            level="organization", check_type="api",
            api_endpoint="/orgs/{org}", field="two_factor_requirement_enabled",
            expected_value=True, remediation="Enable 2FA",
        )
        result = check_rule(mock_client, rule, {"org": "test-org", "target_name": "test-org"})
        assert result.status == "PASS"

    def test_api_check_fail(self, mock_client):
        """API check should fail when field does not match expected value."""
        mock_client.api_call.return_value = {"two_factor_requirement_enabled": False}
        rule = Rule(
            id="TEST-02", name="Test 2FA", description="",
            benchmark="TEST", category="auth", severity="critical",
            level="organization", check_type="api",
            api_endpoint="/orgs/{org}", field="two_factor_requirement_enabled",
            expected_value=True, remediation="Enable 2FA",
        )
        result = check_rule(mock_client, rule, {"org": "test-org", "target_name": "test-org"})
        assert result.status == "FAIL"

    def test_api_check_permission_denied(self, mock_client):
        """API check should skip when permission is denied."""
        mock_client.api_call.return_value = {"_error": "permission_denied", "_message": "Forbidden"}
        rule = Rule(
            id="TEST-03", name="Test", description="",
            benchmark="TEST", category="auth", severity="high",
            level="organization", check_type="api",
            api_endpoint="/orgs/{org}", field="some_field",
            expected_value=True, remediation="Fix it",
        )
        result = check_rule(mock_client, rule, {"org": "test-org", "target_name": "test-org"})
        assert result.status == "SKIP"

    def test_branch_protection_pass(self, mock_client, sample_branch_protection_response):
        """Branch protection check should pass when protection exists."""
        mock_client.api_call.return_value = sample_branch_protection_response
        rule = Rule(
            id="TEST-04", name="Branch protection", description="",
            benchmark="TEST", category="branch-protection", severity="critical",
            level="repository", check_type="branch_protection",
            api_endpoint="/repos/{owner}/{repo}/branches/{branch}/protection",
            field="protected", expected_value=True, remediation="Enable BP",
        )
        result = check_rule(
            mock_client, rule,
            {"owner": "test-org", "repo": "test-repo", "branch": "main", "target_name": "test-org/test-repo"},
        )
        assert result.status == "PASS"

    def test_branch_protection_no_protection(self, mock_client):
        """Branch protection check should fail when no protection exists."""
        mock_client.api_call.return_value = None
        rule = Rule(
            id="TEST-05", name="Branch protection", description="",
            benchmark="TEST", category="branch-protection", severity="critical",
            level="repository", check_type="branch_protection",
            api_endpoint="/repos/{owner}/{repo}/branches/{branch}/protection",
            field="protected", expected_value=True, remediation="Enable BP",
        )
        result = check_rule(
            mock_client, rule,
            {"owner": "test-org", "repo": "test-repo", "branch": "main", "target_name": "test-org/test-repo"},
        )
        assert result.status == "FAIL"

    def test_branch_protection_nested_field(self, mock_client, sample_branch_protection_response):
        """Branch protection check for nested fields should work."""
        mock_client.api_call.return_value = sample_branch_protection_response
        rule = Rule(
            id="TEST-06", name="Dismiss stale reviews", description="",
            benchmark="TEST", category="branch-protection", severity="high",
            level="repository", check_type="branch_protection",
            api_endpoint="/repos/{owner}/{repo}/branches/{branch}/protection",
            field="required_pull_request_reviews.dismiss_stale_reviews",
            expected_value=True, remediation="Enable stale review dismissal",
        )
        result = check_rule(
            mock_client, rule,
            {"owner": "test-org", "repo": "test-repo", "branch": "main", "target_name": "test-org/test-repo"},
        )
        assert result.status == "PASS"

    def test_file_exists_local_pass(self, tmp_local_repo):
        """File exists check should pass when file exists locally."""
        rule = Rule(
            id="TEST-07", name="README exists", description="",
            benchmark="TEST", category="repo-settings", severity="low",
            level="repository", check_type="file_exists",
            api_endpoint="/repos/{owner}/{repo}/readme",
            field="name", expected_value="not_null", remediation="Add README",
        )
        # For local file check, the endpoint last segment is used
        rule.api_endpoint = "/repos/local/test-repo/contents/README.md"
        result = check_rule(
            None, rule,
            {"owner": "local", "repo": "test-repo", "branch": "local", "target_name": "local/test-repo"},
            local_path=tmp_local_repo,
        )
        assert result.status == "PASS"

    def test_file_exists_local_fail(self, tmp_local_repo_minimal):
        """File exists check should fail when file is missing locally."""
        rule = Rule(
            id="TEST-08", name="README exists", description="",
            benchmark="TEST", category="repo-settings", severity="low",
            level="repository", check_type="file_exists",
            api_endpoint="/repos/local/test-repo/contents/README.md",
            field="name", expected_value="not_null", remediation="Add README",
        )
        result = check_rule(
            None, rule,
            {"owner": "local", "repo": "test-repo", "branch": "local", "target_name": "local/test-repo"},
            local_path=tmp_local_repo_minimal,
        )
        assert result.status == "FAIL"

    def test_file_exists_multi_local_pass(self, tmp_local_repo):
        """Multi-path file exists check should pass when file exists in any path."""
        rule = Rule(
            id="TEST-09", name="CODEOWNERS exists", description="",
            benchmark="TEST", category="access", severity="medium",
            level="repository", check_type="file_exists_multi",
            api_endpoint="/repos/{owner}/{repo}/contents/{path}",
            field="name", expected_value="not_null", remediation="Add CODEOWNERS",
            check_paths=["CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"],
        )
        result = check_rule(
            None, rule,
            {"owner": "local", "repo": "test-repo", "branch": "local", "target_name": "local/test-repo"},
            local_path=tmp_local_repo,
        )
        assert result.status == "PASS"

    def test_nested_security_analysis(self, mock_client, sample_repo_response):
        """Nested security_and_analysis field should be correctly evaluated."""
        mock_client.api_call.return_value = sample_repo_response
        rule = Rule(
            id="TEST-10", name="Secret scanning", description="",
            benchmark="TEST", category="secrets", severity="critical",
            level="repository", check_type="api",
            api_endpoint="/repos/{owner}/{repo}",
            field="security_and_analysis.secret_scanning.status",
            expected_value="enabled", remediation="Enable secret scanning",
        )
        result = check_rule(
            mock_client, rule,
            {"owner": "test-org", "repo": "test-repo", "target_name": "test-org/test-repo"},
        )
        assert result.status == "PASS"


# ──────────────────────────────────────────────
# Local path audit tests
# ──────────────────────────────────────────────
class TestAuditLocalPath:
    """Tests for auditing local repository paths."""

    def test_audit_local_complete_repo(self, tmp_local_repo, rules_dir):
        """Auditing a complete local repo should find all files."""
        rules = load_rules(rules_dir, {"cis"})
        file_rules = [
            r for r in rules
            if r.level == "repository" and r.check_type in ("file_exists", "file_exists_multi")
        ]
        results = audit_local_path(file_rules, tmp_local_repo)
        assert len(results) > 0
        # Should pass for README, LICENSE, .gitignore, CODEOWNERS
        passed = [r for r in results if r.status == "PASS"]
        assert len(passed) >= 3

    def test_audit_local_minimal_repo(self, tmp_local_repo_minimal, rules_dir):
        """Auditing a minimal repo should find missing files."""
        rules = load_rules(rules_dir, {"cis"})
        file_rules = [
            r for r in rules
            if r.level == "repository" and r.check_type in ("file_exists", "file_exists_multi")
        ]
        results = audit_local_path(file_rules, tmp_local_repo_minimal)
        assert len(results) > 0
        failed = [r for r in results if r.status == "FAIL"]
        assert len(failed) >= 3  # Missing README, LICENSE, .gitignore, CODEOWNERS

    def test_audit_nonexistent_path(self, rules_dir):
        """Auditing a nonexistent path should return empty results."""
        rules = load_rules(rules_dir, {"cis"})
        results = audit_local_path(rules, "/nonexistent/path")
        assert len(results) == 0


# ──────────────────────────────────────────────
# Report generation tests
# ──────────────────────────────────────────────
class TestReportGeneration:
    """Tests for report generation and export."""

    @pytest.fixture
    def sample_results(self):
        """Create a set of sample audit results."""
        return [
            AuditResult("org1", "organization", "CIS-O1", "2FA required", "CIS",
                         "auth", "critical", "PASS", "True", "True", ""),
            AuditResult("org1", "organization", "CIS-O3", "Default perms", "CIS",
                         "access", "high", "FAIL", "admin", "read", "Set to read"),
            AuditResult("org1/repo1", "repository", "CIS-R1", "Branch protection", "CIS",
                         "branch-protection", "critical", "PASS", "protected", "True", ""),
            AuditResult("org1/repo1", "repository", "CIS-R9", "Secret scanning", "CIS",
                         "secrets", "critical", "FAIL", "disabled", "enabled", "Enable it"),
            AuditResult("org1/repo1", "repository", "OWASP-SEC1-01", "Flow control", "OWASP",
                         "branch-protection", "critical", "PASS", "protected", "True", ""),
            AuditResult("org1/repo1", "repository", "SANS-798-01", "Secrets", "SANS",
                         "secrets", "critical", "SKIP", "insufficient permissions", "enabled", ""),
        ]

    def test_generate_scorecard(self, sample_results):
        """Scorecard should contain key information."""
        scorecard = generate_scorecard(sample_results, "org1")
        assert "org1" in scorecard
        assert "CIS" in scorecard
        assert "OWASP" in scorecard
        assert "SANS" in scorecard

    def test_export_csv(self, sample_results, tmp_path):
        """CSV export should create a valid CSV file."""
        filepath = str(tmp_path / "test_report.csv")
        result = export_csv(sample_results, filepath)
        assert os.path.isfile(result)

        import csv
        with open(result, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == len(sample_results)
        assert "Target" in rows[0]
        assert "RuleID" in rows[0]

    def test_export_json(self, sample_results, tmp_path):
        """JSON export should create a valid JSON file."""
        filepath = str(tmp_path / "test_report.json")
        result = export_json(sample_results, filepath)
        assert os.path.isfile(result)

        with open(result, "r") as f:
            data = json.load(f)
        assert "results" in data
        assert len(data["results"]) == len(sample_results)
        assert data["total_rules"] == len(sample_results)

    def test_export_html(self, sample_results, tmp_path):
        """HTML export should create a valid HTML file."""
        filepath = str(tmp_path / "test_report.html")
        result = export_html(sample_results, filepath, "org1")
        assert os.path.isfile(result)

        with open(result, "r") as f:
            content = f.read()
        assert "<html" in content
        assert "org1" in content
        assert "h3nryza" in content
        assert "CIS-O1" in content


# ──────────────────────────────────────────────
# CLI argument parser tests
# ──────────────────────────────────────────────
class TestBuildParser:
    """Tests for CLI argument parsing."""

    def test_org_argument(self):
        """Parser should accept -o/--org argument."""
        parser = build_parser()
        args = parser.parse_args(["-o", "my-org"])
        assert args.org == "my-org"

    def test_enterprise_argument(self):
        """Parser should accept -e/--enterprise argument."""
        parser = build_parser()
        args = parser.parse_args(["-e", "my-enterprise"])
        assert args.enterprise == "my-enterprise"

    def test_repo_argument(self):
        """Parser should accept -r/--repo argument."""
        parser = build_parser()
        args = parser.parse_args(["-r", "owner/repo"])
        assert args.repo == "owner/repo"

    def test_benchmarks_argument(self):
        """Parser should accept --benchmarks argument."""
        parser = build_parser()
        args = parser.parse_args(["-o", "org", "--benchmarks", "cis,owasp"])
        assert args.benchmarks == "cis,owasp"

    def test_severity_argument(self):
        """Parser should accept --severity argument."""
        parser = build_parser()
        args = parser.parse_args(["-o", "org", "--severity", "high"])
        assert args.severity == "high"

    def test_format_argument(self):
        """Parser should accept --format argument."""
        parser = build_parser()
        args = parser.parse_args(["-o", "org", "--format", "json"])
        assert args.output_format == "json"

    def test_verbose_flag(self):
        """Parser should accept -v/--verbose flag."""
        parser = build_parser()
        args = parser.parse_args(["-o", "org", "-v"])
        assert args.verbose is True

    def test_summary_flag(self):
        """Parser should accept --summary flag."""
        parser = build_parser()
        args = parser.parse_args(["-o", "org", "--summary"])
        assert args.summary is True

    def test_interactive_flag(self):
        """Parser should accept -i/--interactive flag."""
        parser = build_parser()
        args = parser.parse_args(["-i"])
        assert args.interactive is True

    def test_default_values(self):
        """Default values should be set correctly."""
        parser = build_parser()
        args = parser.parse_args(["-o", "org"])
        assert args.benchmarks == "all"
        assert args.severity == "low"
        assert args.output_format == "csv"
        assert args.auth == "gh"
        assert args.verbose is False
        assert args.summary is False


# ──────────────────────────────────────────────
# Integration-style tests with mock API
# ──────────────────────────────────────────────
class TestAuditOrgMocked:
    """Integration tests for org audit with mocked API calls."""

    def test_audit_org_with_no_repos(self, mock_client, rules_dir):
        """Org audit with no repos should still check org-level rules."""
        # Mock org response
        mock_client.api_call.side_effect = lambda endpoint, **kwargs: {
            "/orgs/test-org": {
                "login": "test-org",
                "two_factor_requirement_enabled": True,
                "default_repository_permission": "read",
                "members_can_create_repositories": False,
                "members_can_fork_private_repositories": False,
                "members_can_invite_outside_collaborators": False,
                "members_can_create_pages": False,
                "members_can_create_public_packages": False,
                "dependency_graph_enabled_for_new_repositories": True,
                "dependabot_alerts_enabled_for_new_repositories": True,
                "dependabot_security_updates_enabled_for_new_repositories": True,
                "secret_scanning_enabled_for_new_repositories": True,
                "code_scanning_default_setup_enabled": True,
                "security_advisories_enabled": True,
                "members_allowed_repository_creation_type": "none",
            },
        }.get(endpoint.split("?")[0])

        rules = load_rules(rules_dir, {"cis"})
        org_rules = [r for r in rules if r.level == "organization"]

        # Only test org-level rules (no repos)
        results = []
        for rule in org_rules:
            result = check_rule(
                mock_client, rule,
                {"org": "test-org", "target_name": "test-org"},
            )
            results.append(result)

        assert len(results) > 0
        # With a well-configured org, most should pass
        passed = [r for r in results if r.status == "PASS"]
        assert len(passed) > 0


class TestAuditResultDataClass:
    """Tests for the AuditResult data class."""

    def test_audit_result_creation(self):
        """AuditResult should be created with all fields."""
        result = AuditResult(
            target="test", level="org", rule_id="R1", rule_name="Test",
            benchmark="CIS", category="auth", severity="high",
            status="PASS", current_value="True", expected_value="True",
            remediation="None needed",
        )
        assert result.target == "test"
        assert result.status == "PASS"
        assert result.severity == "high"


class TestRuleDataClass:
    """Tests for the Rule data class."""

    def test_rule_creation(self):
        """Rule should be created with all fields."""
        rule = Rule(
            id="TEST-01", name="Test rule", description="A test",
            benchmark="TEST", category="auth", severity="high",
            level="organization", check_type="api",
            api_endpoint="/orgs/{org}", field="field",
            expected_value=True, remediation="Fix it",
        )
        assert rule.id == "TEST-01"
        assert rule.check_paths == []

    def test_rule_with_check_paths(self):
        """Rule should support custom check_paths."""
        rule = Rule(
            id="TEST-02", name="Test rule", description="",
            benchmark="TEST", category="access", severity="medium",
            level="repository", check_type="file_exists_multi",
            api_endpoint="/repos/{owner}/{repo}/contents/{path}",
            field="name", expected_value="not_null",
            remediation="Create file",
            check_paths=["CODEOWNERS", ".github/CODEOWNERS"],
        )
        assert len(rule.check_paths) == 2
