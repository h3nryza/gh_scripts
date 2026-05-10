"""
test_audit.py — Pytest unit tests for gh-best-practices-audit.
Written by h3nryza

Run with:
    pytest tests/ -v
    pytest tests/ -v --cov=gh_best_practices_audit
"""

import csv
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure parent directory is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gh_best_practices_audit import (
    AuditResult,
    GitHubClient,
    Rule,
    audit_local_path,
    audit_org,
    audit_repo,
    build_parser,
    check_rule,
    evaluate_expected,
    export_csv,
    export_html,
    export_json,
    filter_rules,
    generate_scorecard,
    get_nested_value,
    load_custom_rules,
    load_rules,
)


# ===========================================================================
# 1. CLI argument parser
# ===========================================================================

class TestBuildParser:
    """Tests for CLI argument parsing."""

    def test_org_short_flag(self):
        parser = build_parser()
        args = parser.parse_args(["-o", "my-org"])
        assert args.org == "my-org"

    def test_org_long_flag(self):
        parser = build_parser()
        args = parser.parse_args(["--org", "my-org"])
        assert args.org == "my-org"

    def test_enterprise_short_flag(self):
        parser = build_parser()
        args = parser.parse_args(["-e", "my-enterprise"])
        assert args.enterprise == "my-enterprise"

    def test_enterprise_long_flag(self):
        parser = build_parser()
        args = parser.parse_args(["--enterprise", "my-enterprise"])
        assert args.enterprise == "my-enterprise"

    def test_repo_short_flag(self):
        parser = build_parser()
        args = parser.parse_args(["-r", "owner/repo"])
        assert args.repo == "owner/repo"

    def test_repo_long_flag(self):
        parser = build_parser()
        args = parser.parse_args(["--repo", "owner/repo"])
        assert args.repo == "owner/repo"

    def test_local_path_flag(self):
        parser = build_parser()
        args = parser.parse_args(["--local-path", "/some/path"])
        assert args.local_path == "/some/path"

    def test_benchmarks_default(self):
        parser = build_parser()
        args = parser.parse_args(["-o", "org"])
        assert args.benchmarks == "all"

    def test_benchmarks_custom(self):
        parser = build_parser()
        args = parser.parse_args(["-o", "org", "--benchmarks", "cis,owasp"])
        assert args.benchmarks == "cis,owasp"

    def test_severity_default(self):
        parser = build_parser()
        args = parser.parse_args(["-o", "org"])
        assert args.severity == "low"

    def test_severity_high(self):
        parser = build_parser()
        args = parser.parse_args(["-o", "org", "--severity", "high"])
        assert args.severity == "high"

    def test_severity_invalid(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["-o", "org", "--severity", "extreme"])

    def test_format_default(self):
        parser = build_parser()
        args = parser.parse_args(["-o", "org"])
        assert args.output_format == "csv"

    def test_format_json(self):
        parser = build_parser()
        args = parser.parse_args(["-o", "org", "--format", "json"])
        assert args.output_format == "json"

    def test_format_html(self):
        parser = build_parser()
        args = parser.parse_args(["-o", "org", "--format", "html"])
        assert args.output_format == "html"

    def test_format_invalid(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["-o", "org", "--format", "xml"])

    def test_auth_default(self):
        parser = build_parser()
        args = parser.parse_args(["-o", "org"])
        assert args.auth == "gh"

    def test_auth_pat(self):
        parser = build_parser()
        args = parser.parse_args(["-o", "org", "--auth", "pat", "--token", "ghp_abc123"])
        assert args.auth == "pat"
        assert args.token == "ghp_abc123"

    def test_auth_app(self):
        parser = build_parser()
        args = parser.parse_args(
            ["-o", "org", "--auth", "app", "--app-id", "123", "--app-key", "key.pem"]
        )
        assert args.auth == "app"
        assert args.app_id == "123"
        assert args.app_key == "key.pem"

    def test_verbose_flag_short(self):
        parser = build_parser()
        args = parser.parse_args(["-o", "org", "-v"])
        assert args.verbose is True

    def test_verbose_flag_long(self):
        parser = build_parser()
        args = parser.parse_args(["-o", "org", "--verbose"])
        assert args.verbose is True

    def test_summary_flag(self):
        parser = build_parser()
        args = parser.parse_args(["-o", "org", "--summary"])
        assert args.summary is True

    def test_interactive_flag_short(self):
        parser = build_parser()
        args = parser.parse_args(["-i"])
        assert args.interactive is True

    def test_interactive_flag_long(self):
        parser = build_parser()
        args = parser.parse_args(["--interactive"])
        assert args.interactive is True

    def test_s3_flags(self):
        parser = build_parser()
        args = parser.parse_args(["-o", "org", "--s3-bucket", "my-bucket", "--s3-prefix", "audits"])
        assert args.s3_bucket == "my-bucket"
        assert args.s3_prefix == "audits"

    def test_category_flag(self):
        parser = build_parser()
        args = parser.parse_args(["-o", "org", "--category", "auth"])
        assert args.category == "auth"

    def test_custom_rules_flag(self):
        parser = build_parser()
        args = parser.parse_args(["-o", "org", "--custom-rules", "rules.csv"])
        assert args.custom_rules == "rules.csv"

    def test_output_flag(self):
        parser = build_parser()
        args = parser.parse_args(["-o", "org", "--output", "report.csv"])
        assert args.output == "report.csv"

    def test_all_defaults_together(self):
        parser = build_parser()
        args = parser.parse_args(["-o", "org"])
        assert args.benchmarks == "all"
        assert args.severity == "low"
        assert args.output_format == "csv"
        assert args.auth == "gh"
        assert args.verbose is False
        assert args.summary is False
        assert args.interactive is False
        assert args.output == ""
        assert args.s3_bucket == ""
        assert args.category == ""


# ===========================================================================
# 2. Rule loading from JSON files
# ===========================================================================

class TestLoadRules:
    """Tests for loading rules from JSON benchmark files."""

    def test_load_all_benchmarks(self, rules_dir):
        rules = load_rules(rules_dir, {"cis", "owasp", "sans"})
        assert len(rules) > 0
        benchmarks = {r.benchmark for r in rules}
        assert "CIS" in benchmarks
        assert "OWASP" in benchmarks
        assert "SANS" in benchmarks

    def test_load_cis_only(self, rules_dir):
        rules = load_rules(rules_dir, {"cis"})
        assert len(rules) > 0
        assert all(r.benchmark == "CIS" for r in rules)

    def test_load_owasp_only(self, rules_dir):
        rules = load_rules(rules_dir, {"owasp"})
        assert len(rules) > 0
        assert all(r.benchmark == "OWASP" for r in rules)

    def test_load_sans_only(self, rules_dir):
        rules = load_rules(rules_dir, {"sans"})
        assert len(rules) > 0
        assert all(r.benchmark == "SANS" for r in rules)

    def test_load_nonexistent_benchmark_returns_empty(self, rules_dir):
        rules = load_rules(rules_dir, {"foobar"})
        assert len(rules) == 0

    def test_load_empty_benchmark_set(self, rules_dir):
        rules = load_rules(rules_dir, set())
        assert len(rules) == 0

    def test_load_from_nonexistent_directory(self, tmp_path):
        rules = load_rules(tmp_path / "no_such_dir", {"cis"})
        assert len(rules) == 0

    def test_rules_have_required_fields(self, rules_dir):
        rules = load_rules(rules_dir, {"cis", "owasp", "sans"})
        valid_severities = {"critical", "high", "medium", "low", "info"}
        valid_levels = {"enterprise", "organization", "repository"}
        for rule in rules:
            assert rule.id, f"Rule missing id"
            assert rule.name, f"Rule {rule.id} missing name"
            assert rule.severity in valid_severities, \
                f"Rule {rule.id} has invalid severity: {rule.severity}"
            assert rule.level in valid_levels, \
                f"Rule {rule.id} has invalid level: {rule.level}"
            assert rule.check_type, f"Rule {rule.id} missing check_type"

    def test_cis_has_all_three_levels(self, rules_dir):
        rules = load_rules(rules_dir, {"cis"})
        levels = {r.level for r in rules}
        assert "enterprise" in levels
        assert "organization" in levels
        assert "repository" in levels

    def test_cis_minimum_rule_counts(self, rules_dir):
        rules = load_rules(rules_dir, {"cis"})
        enterprise_rules = [r for r in rules if r.level == "enterprise"]
        org_rules = [r for r in rules if r.level == "organization"]
        repo_rules = [r for r in rules if r.level == "repository"]
        assert len(enterprise_rules) >= 5
        assert len(org_rules) >= 14
        assert len(repo_rules) >= 20

    def test_rule_is_rule_object(self, rules_dir):
        rules = load_rules(rules_dir, {"cis"})
        for rule in rules:
            assert isinstance(rule, Rule)
            assert isinstance(rule.check_paths, list)

    def test_invalid_json_file(self, tmp_path):
        r_dir = tmp_path / "rules"
        r_dir.mkdir()
        (r_dir / "cis_benchmark.json").write_text("not valid json{{", encoding="utf-8")
        rules = load_rules(r_dir, {"cis"})
        assert len(rules) == 0

    def test_json_missing_rules_key(self, tmp_path):
        r_dir = tmp_path / "rules"
        r_dir.mkdir()
        (r_dir / "cis_benchmark.json").write_text(
            json.dumps({"benchmark": "CIS", "version": "1.0"}), encoding="utf-8"
        )
        rules = load_rules(r_dir, {"cis"})
        assert len(rules) == 0


# ===========================================================================
# 3. Custom rules loading from CSV
# ===========================================================================

class TestLoadCustomRules:
    """Tests for loading custom rules from CSV files."""

    def test_load_csv_basic(self, custom_rules_csv):
        rules = load_custom_rules(custom_rules_csv)
        assert len(rules) == 1
        r = rules[0]
        assert r.id == "CUSTOM-TEST-01"
        assert r.name == "Test custom rule"
        assert r.severity == "medium"
        assert r.level == "repository"
        assert r.check_type == "api"

    def test_load_csv_bool_false(self, custom_rules_csv):
        rules = load_custom_rules(custom_rules_csv)
        assert rules[0].expected_value is False

    def test_load_nonexistent_file(self):
        rules = load_custom_rules("/nonexistent/path/rules.csv")
        assert rules == []

    def test_load_unsupported_extension(self, tmp_path):
        f = tmp_path / "rules.txt"
        f.write_text("id,name\nR1,Test\n", encoding="utf-8")
        rules = load_custom_rules(str(f))
        assert rules == []

    def test_load_bundled_custom_template(self, rules_dir):
        template = rules_dir / "custom_template.csv"
        if template.exists():
            rules = load_custom_rules(str(template))
            assert len(rules) > 0
            for r in rules:
                assert isinstance(r, Rule)

    def test_csv_bool_true_conversion(self, tmp_path):
        f = tmp_path / "rules.csv"
        f.write_text(
            "id,name,description,category,severity,level,check_type,"
            "api_endpoint,field,expected_value,remediation\n"
            "R1,Name,Desc,auth,high,organization,api,/orgs/{org},field,true,Fix it\n",
            encoding="utf-8",
        )
        rules = load_custom_rules(str(f))
        assert rules[0].expected_value is True

    def test_csv_integer_conversion(self, tmp_path):
        f = tmp_path / "rules.csv"
        f.write_text(
            "id,name,description,category,severity,level,check_type,"
            "api_endpoint,field,expected_value,remediation\n"
            "R1,Name,Desc,auth,high,organization,api,/orgs/{org},field,2,Fix it\n",
            encoding="utf-8",
        )
        rules = load_custom_rules(str(f))
        assert rules[0].expected_value == 2

    def test_csv_check_paths_parsed(self, tmp_path):
        f = tmp_path / "rules.csv"
        f.write_text(
            "id,name,description,category,severity,level,check_type,"
            "api_endpoint,field,expected_value,remediation,check_paths\n"
            "R1,Name,Desc,access,medium,repository,file_exists_multi,"
            "/repos/{owner}/{repo}/contents/{path},name,not_null,Add it,"
            "CODEOWNERS;.github/CODEOWNERS\n",
            encoding="utf-8",
        )
        rules = load_custom_rules(str(f))
        assert rules[0].check_paths == ["CODEOWNERS", ".github/CODEOWNERS"]

    def test_csv_rows_without_id_are_skipped(self, tmp_path):
        f = tmp_path / "rules.csv"
        f.write_text(
            "id,name,description,category,severity,level,check_type,"
            "api_endpoint,field,expected_value,remediation\n"
            ",Empty ID row,Desc,auth,high,org,api,/orgs/{org},field,true,Fix\n"
            "R1,Valid row,Desc,auth,high,organization,api,/orgs/{org},field,true,Fix\n",
            encoding="utf-8",
        )
        rules = load_custom_rules(str(f))
        assert len(rules) == 1
        assert rules[0].id == "R1"


# ===========================================================================
# 4. Rule filtering
# ===========================================================================

class TestFilterRules:
    """Tests for filtering rules by severity and category."""

    def test_filter_critical_only(self, rules_dir):
        rules = load_rules(rules_dir, {"cis"})
        filtered = filter_rules(rules, severity="critical")
        assert len(filtered) > 0
        assert all(r.severity == "critical" for r in filtered)

    def test_filter_low_includes_higher_severities(self, rules_dir):
        rules = load_rules(rules_dir, {"cis"})
        filtered = filter_rules(rules, severity="low")
        severities = {r.severity for r in filtered}
        assert "critical" in severities
        assert "high" in severities

    def test_filter_low_excludes_info(self, rules_dir):
        rules = load_rules(rules_dir, {"cis"})
        filtered = filter_rules(rules, severity="low")
        assert all(r.severity != "info" for r in filtered)

    def test_filter_by_category_auth(self, rules_dir):
        rules = load_rules(rules_dir, {"cis"})
        filtered = filter_rules(rules, category="auth")
        assert all(r.category == "auth" for r in filtered)
        assert len(filtered) > 0

    def test_filter_by_category_branch_protection(self, rules_dir):
        rules = load_rules(rules_dir, {"cis", "owasp"})
        filtered = filter_rules(rules, category="branch-protection")
        assert all(r.category == "branch-protection" for r in filtered)
        assert len(filtered) > 0

    def test_filter_severity_and_category_combined(self, rules_dir):
        rules = load_rules(rules_dir, {"cis"})
        filtered = filter_rules(rules, severity="high", category="secrets")
        for r in filtered:
            assert r.category == "secrets"
            assert r.severity in ("critical", "high")

    def test_filter_keeps_rule_objects(self, rules_dir):
        rules = load_rules(rules_dir, {"cis"})
        filtered = filter_rules(rules, severity="high")
        for r in filtered:
            assert isinstance(r, Rule)

    def test_filter_no_category_returns_all_severities(self, rules_dir):
        rules = load_rules(rules_dir, {"cis"})
        filtered = filter_rules(rules, severity="info")
        assert len(filtered) == len(rules)


# ===========================================================================
# 5. get_nested_value helper
# ===========================================================================

class TestGetNestedValue:
    """Tests for get_nested_value dot-notation extraction."""

    def test_simple_key(self):
        assert get_nested_value({"a": 1}, "a") == 1

    def test_nested_two_levels(self):
        assert get_nested_value({"a": {"b": 2}}, "a.b") == 2

    def test_nested_three_levels(self):
        data = {"a": {"b": {"c": 3}}}
        assert get_nested_value(data, "a.b.c") == 3

    def test_missing_top_key_returns_none(self):
        assert get_nested_value({"a": 1}, "b") is None

    def test_missing_nested_key_returns_none(self):
        assert get_nested_value({"a": {"b": 1}}, "a.c") is None

    def test_none_data_returns_none(self):
        assert get_nested_value(None, "a") is None

    def test_security_analysis_path(self):
        data = {"security_and_analysis": {"secret_scanning": {"status": "enabled"}}}
        result = get_nested_value(data, "security_and_analysis.secret_scanning.status")
        assert result == "enabled"

    def test_non_dict_intermediate_returns_none(self):
        data = {"a": "string_not_dict"}
        assert get_nested_value(data, "a.b") is None

    def test_boolean_value(self):
        assert get_nested_value({"enabled": True}, "enabled") is True

    def test_integer_value(self):
        assert get_nested_value({"count": 5}, "count") == 5


# ===========================================================================
# 6. evaluate_expected comparator
# ===========================================================================

class TestEvaluateExpected:
    """Tests for the evaluate_expected comparison function."""

    def test_bool_true_match(self):
        assert evaluate_expected(True, True) is True

    def test_bool_false_no_match(self):
        assert evaluate_expected(False, True) is False

    def test_bool_false_match(self):
        assert evaluate_expected(False, False) is True

    def test_bool_true_no_match(self):
        assert evaluate_expected(True, False) is False

    def test_string_equals(self):
        assert evaluate_expected("enabled", "enabled") is True

    def test_string_not_equals(self):
        assert evaluate_expected("disabled", "enabled") is False

    def test_not_null_with_value(self):
        assert evaluate_expected("something", "not_null") is True

    def test_not_null_with_none(self):
        assert evaluate_expected(None, "not_null") is False

    def test_gte_pass(self):
        assert evaluate_expected(2, ">=1") is True

    def test_gte_equal(self):
        assert evaluate_expected(1, ">=1") is True

    def test_gte_fail(self):
        assert evaluate_expected(0, ">=1") is False

    def test_gt_pass(self):
        assert evaluate_expected(1, ">0") is True

    def test_gt_fail_zero(self):
        assert evaluate_expected(0, ">0") is False

    def test_lte_pass(self):
        assert evaluate_expected(3, "<=5") is True

    def test_lte_fail(self):
        assert evaluate_expected(10, "<=5") is False

    def test_list_in(self):
        assert evaluate_expected("read", ["none", "read"]) is True

    def test_list_not_in(self):
        assert evaluate_expected("write", ["none", "read"]) is False

    def test_int_match(self):
        assert evaluate_expected(0, 0) is True

    def test_int_no_match(self):
        assert evaluate_expected(5, 0) is False

    def test_review_required_always_passes(self):
        assert evaluate_expected("anything", "review_required") is True

    def test_none_expected_nonnull_actual(self):
        assert evaluate_expected("value", None) is True

    def test_bool_from_string_actual(self):
        # actual string "true" against expected bool True
        assert evaluate_expected("true", True) is True

    def test_int_from_string_actual(self):
        # actual "5" against expected int 5
        assert evaluate_expected("5", 5) is True


# ===========================================================================
# 7. API check execution (mocked)
# ===========================================================================

class TestCheckRuleApi:
    """Tests for API-based rule checks."""

    def test_api_pass_bool(self, mock_client, sample_org_response):
        mock_client.api_call.return_value = sample_org_response
        rule = Rule(
            id="T-01", name="2FA", description="", benchmark="TEST",
            category="auth", severity="critical", level="organization",
            check_type="api", api_endpoint="/orgs/{org}",
            field="two_factor_requirement_enabled", expected_value=True,
            remediation="Enable 2FA",
        )
        result = check_rule(mock_client, rule, {"org": "test-org", "target_name": "test-org"})
        assert result.status == "PASS"
        assert result.rule_id == "T-01"

    def test_api_fail_bool(self, mock_client):
        mock_client.api_call.return_value = {"two_factor_requirement_enabled": False}
        rule = Rule(
            id="T-02", name="2FA", description="", benchmark="TEST",
            category="auth", severity="critical", level="organization",
            check_type="api", api_endpoint="/orgs/{org}",
            field="two_factor_requirement_enabled", expected_value=True,
            remediation="Enable 2FA",
        )
        result = check_rule(mock_client, rule, {"org": "test-org", "target_name": "test-org"})
        assert result.status == "FAIL"

    def test_api_skip_on_permission_denied(self, mock_client):
        mock_client.api_call.return_value = {"_error": "permission_denied", "_message": "403"}
        rule = Rule(
            id="T-03", name="Test", description="", benchmark="TEST",
            category="auth", severity="high", level="organization",
            check_type="api", api_endpoint="/orgs/{org}",
            field="field", expected_value=True, remediation="Fix it",
        )
        result = check_rule(mock_client, rule, {"org": "test-org", "target_name": "test-org"})
        assert result.status == "SKIP"

    def test_api_skip_on_api_error(self, mock_client):
        mock_client.api_call.return_value = {"_error": "api_error", "_message": "500"}
        rule = Rule(
            id="T-04", name="Test", description="", benchmark="TEST",
            category="auth", severity="high", level="organization",
            check_type="api", api_endpoint="/orgs/{org}",
            field="field", expected_value=True, remediation="Fix it",
        )
        result = check_rule(mock_client, rule, {"org": "test-org", "target_name": "test-org"})
        assert result.status == "SKIP"

    def test_api_skip_on_none_response(self, mock_client):
        mock_client.api_call.return_value = None
        rule = Rule(
            id="T-05", name="Test", description="", benchmark="TEST",
            category="secrets", severity="high", level="repository",
            check_type="api", api_endpoint="/repos/{owner}/{repo}",
            field="some_field", expected_value=True, remediation="Fix it",
        )
        result = check_rule(
            mock_client, rule,
            {"owner": "org", "repo": "repo", "target_name": "org/repo"},
        )
        assert result.status == "SKIP"

    def test_api_nested_field_pass(self, mock_client, sample_repo_response):
        mock_client.api_call.return_value = sample_repo_response
        rule = Rule(
            id="T-06", name="Secret scanning", description="", benchmark="TEST",
            category="secrets", severity="critical", level="repository",
            check_type="api", api_endpoint="/repos/{owner}/{repo}",
            field="security_and_analysis.secret_scanning.status",
            expected_value="enabled", remediation="Enable secret scanning",
        )
        result = check_rule(
            mock_client, rule,
            {"owner": "test-org", "repo": "test-repo", "target_name": "test-org/test-repo"},
        )
        assert result.status == "PASS"

    def test_api_endpoint_variable_substitution(self, mock_client):
        mock_client.api_call.return_value = {"two_factor_requirement_enabled": True}
        rule = Rule(
            id="T-07", name="2FA", description="", benchmark="TEST",
            category="auth", severity="high", level="organization",
            check_type="api", api_endpoint="/orgs/{org}",
            field="two_factor_requirement_enabled", expected_value=True,
            remediation="Enable 2FA",
        )
        check_rule(mock_client, rule, {"org": "my-org", "target_name": "my-org"})
        called_endpoint = mock_client.api_call.call_args[0][0]
        assert "{org}" not in called_endpoint
        assert "my-org" in called_endpoint

    def test_api_webhook_security_all_secure(self, mock_client):
        mock_client.api_call.return_value = [
            {"id": 1, "config": {"url": "https://example.com", "insecure_ssl": "0"}},
        ]
        rule = Rule(
            id="T-08", name="Webhook security", description="", benchmark="TEST",
            category="repo-settings", severity="high", level="repository",
            check_type="api", api_endpoint="/repos/{owner}/{repo}/hooks",
            field="webhook_security", expected_value=True, remediation="Use HTTPS",
        )
        result = check_rule(
            mock_client, rule,
            {"owner": "org", "repo": "repo", "target_name": "org/repo"},
        )
        assert result.status == "PASS"

    def test_api_webhook_security_insecure(self, mock_client):
        mock_client.api_call.return_value = [
            {"id": 1, "config": {"url": "http://example.com", "insecure_ssl": "1"}},
        ]
        rule = Rule(
            id="T-09", name="Webhook security", description="", benchmark="TEST",
            category="repo-settings", severity="high", level="repository",
            check_type="api", api_endpoint="/repos/{owner}/{repo}/hooks",
            field="webhook_security", expected_value=True, remediation="Use HTTPS",
        )
        result = check_rule(
            mock_client, rule,
            {"owner": "org", "repo": "repo", "target_name": "org/repo"},
        )
        assert result.status == "FAIL"

    def test_unknown_check_type_returns_skip(self, mock_client):
        rule = Rule(
            id="T-10", name="Unknown", description="", benchmark="TEST",
            category="auth", severity="low", level="repository",
            check_type="unknown_type", api_endpoint="/repos/{owner}/{repo}",
            field="field", expected_value=True, remediation="Fix it",
        )
        result = check_rule(
            mock_client, rule,
            {"owner": "org", "repo": "repo", "target_name": "org/repo"},
        )
        assert result.status == "SKIP"

    def test_result_carries_target_name(self, mock_client):
        mock_client.api_call.return_value = {"field": True}
        rule = Rule(
            id="T-11", name="Test", description="", benchmark="TEST",
            category="auth", severity="low", level="repository",
            check_type="api", api_endpoint="/repos/{owner}/{repo}",
            field="field", expected_value=True, remediation="Fix it",
        )
        result = check_rule(
            mock_client, rule,
            {"owner": "org", "repo": "repo", "target_name": "org/repo"},
        )
        assert result.target == "org/repo"


# ===========================================================================
# 8. Branch protection checks (mocked)
# ===========================================================================

class TestCheckRuleBranchProtection:
    """Tests for branch_protection check type."""

    def _bp_rule(self, field: str, expected) -> Rule:
        return Rule(
            id="BP-01", name="BP test", description="", benchmark="TEST",
            category="branch-protection", severity="critical", level="repository",
            check_type="branch_protection",
            api_endpoint="/repos/{owner}/{repo}/branches/{branch}/protection",
            field=field, expected_value=expected, remediation="Enable it",
        )

    def _vars(self) -> dict:
        return {"owner": "org", "repo": "repo", "branch": "main", "target_name": "org/repo"}

    def test_protected_field_pass(self, mock_client, sample_branch_protection_response):
        mock_client.api_call.return_value = sample_branch_protection_response
        result = check_rule(mock_client, self._bp_rule("protected", True), self._vars())
        assert result.status == "PASS"

    def test_no_protection_returns_fail(self, mock_client):
        mock_client.api_call.return_value = None
        result = check_rule(mock_client, self._bp_rule("protected", True), self._vars())
        assert result.status == "FAIL"
        assert "no branch protection" in result.current_value.lower()

    def test_permission_denied_returns_skip(self, mock_client):
        mock_client.api_call.return_value = {"_error": "permission_denied", "_message": "403"}
        result = check_rule(mock_client, self._bp_rule("protected", True), self._vars())
        assert result.status == "SKIP"

    def test_dismiss_stale_reviews_pass(self, mock_client, sample_branch_protection_response):
        mock_client.api_call.return_value = sample_branch_protection_response
        rule = self._bp_rule("required_pull_request_reviews.dismiss_stale_reviews", True)
        result = check_rule(mock_client, rule, self._vars())
        assert result.status == "PASS"

    def test_review_count_gte_pass(self, mock_client, sample_branch_protection_response):
        mock_client.api_call.return_value = sample_branch_protection_response
        rule = self._bp_rule(
            "required_pull_request_reviews.required_approving_review_count", ">=1"
        )
        result = check_rule(mock_client, rule, self._vars())
        assert result.status == "PASS"

    def test_required_signatures_enabled(self, mock_client, sample_branch_protection_response):
        def _side(endpoint, **kwargs):
            if "required_signatures" in endpoint:
                return {"enabled": True}
            return sample_branch_protection_response
        mock_client.api_call.side_effect = _side
        rule = self._bp_rule("required_signatures.enabled", True)
        result = check_rule(mock_client, rule, self._vars())
        assert result.status == "PASS"

    def test_required_signatures_disabled(self, mock_client, sample_branch_protection_response):
        def _side(endpoint, **kwargs):
            if "required_signatures" in endpoint:
                return {"enabled": False}
            return sample_branch_protection_response
        mock_client.api_call.side_effect = _side
        rule = self._bp_rule("required_signatures.enabled", True)
        result = check_rule(mock_client, rule, self._vars())
        assert result.status == "FAIL"


# ===========================================================================
# 9. File check execution (mocked / local)
# ===========================================================================

class TestCheckRuleFileExists:
    """Tests for file_exists and file_exists_multi check types."""

    def _file_rule(self, filename: str) -> Rule:
        return Rule(
            id="F-01", name="File check", description="", benchmark="TEST",
            category="repo-settings", severity="low", level="repository",
            check_type="file_exists",
            api_endpoint=f"/repos/{{owner}}/{{repo}}/contents/{filename}",
            field="name", expected_value="not_null", remediation="Add the file",
        )

    def _multi_rule(self, paths: list) -> Rule:
        return Rule(
            id="F-02", name="Multi-path check", description="", benchmark="TEST",
            category="access", severity="medium", level="repository",
            check_type="file_exists_multi",
            api_endpoint="/repos/{owner}/{repo}/contents/{path}",
            field="name", expected_value="not_null", remediation="Add CODEOWNERS",
            check_paths=paths,
        )

    def _vars(self) -> dict:
        return {"owner": "org", "repo": "repo", "branch": "main", "target_name": "org/repo"}

    def test_file_exists_local_pass(self, tmp_local_repo):
        rule = self._file_rule("README.md")
        result = check_rule(None, rule, self._vars(), local_path=tmp_local_repo)
        assert result.status == "PASS"

    def test_file_exists_local_fail(self, tmp_local_repo_minimal):
        rule = self._file_rule("README.md")
        result = check_rule(None, rule, self._vars(), local_path=tmp_local_repo_minimal)
        assert result.status == "FAIL"

    def test_file_exists_local_case_variants(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".git").mkdir()
        (repo / "license").write_text("MIT\n", encoding="utf-8")
        rule = self._file_rule("LICENSE")
        result = check_rule(None, rule, self._vars(), local_path=str(repo))
        assert result.status == "PASS"

    def test_file_exists_api_pass(self, mock_client):
        mock_client.api_call.return_value = {"name": "README.md", "size": 512}
        rule = self._file_rule("README.md")
        result = check_rule(mock_client, rule, self._vars())
        assert result.status == "PASS"

    def test_file_exists_api_not_found(self, mock_client):
        mock_client.api_call.return_value = None
        rule = self._file_rule("README.md")
        result = check_rule(mock_client, rule, self._vars())
        assert result.status == "FAIL"

    def test_file_exists_multi_local_any_path_passes(self, tmp_local_repo):
        rule = self._multi_rule(["CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"])
        result = check_rule(None, rule, self._vars(), local_path=tmp_local_repo)
        assert result.status == "PASS"

    def test_file_exists_multi_local_none_found(self, tmp_local_repo_minimal):
        rule = self._multi_rule(["CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"])
        result = check_rule(None, rule, self._vars(), local_path=tmp_local_repo_minimal)
        assert result.status == "FAIL"
        assert "not found" in result.current_value.lower()

    def test_file_exists_multi_api_first_path(self, mock_client):
        mock_client.api_call.return_value = {"name": "CODEOWNERS", "size": 20}
        rule = self._multi_rule(["CODEOWNERS", ".github/CODEOWNERS"])
        result = check_rule(mock_client, rule, self._vars())
        assert result.status == "PASS"

    def test_file_exists_multi_api_second_path(self, mock_client):
        call_count = {"n": 0}
        def _side(endpoint, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return None  # first path not found
            return {"name": "CODEOWNERS", "size": 20}
        mock_client.api_call.side_effect = _side
        rule = self._multi_rule(["CODEOWNERS", ".github/CODEOWNERS"])
        result = check_rule(mock_client, rule, self._vars())
        assert result.status == "PASS"


# ===========================================================================
# 10. Local path audit
# ===========================================================================

class TestAuditLocalPath:
    """Tests for the audit_local_path function."""

    def test_complete_repo_has_passes(self, rules_dir, tmp_local_repo):
        rules = load_rules(rules_dir, {"cis"})
        file_rules = [
            r for r in rules
            if r.level == "repository" and r.check_type in ("file_exists", "file_exists_multi")
        ]
        results = audit_local_path(file_rules, tmp_local_repo)
        assert len(results) > 0
        passed = [r for r in results if r.status == "PASS"]
        assert len(passed) >= 3

    def test_minimal_repo_has_failures(self, rules_dir, tmp_local_repo_minimal):
        rules = load_rules(rules_dir, {"cis"})
        file_rules = [
            r for r in rules
            if r.level == "repository" and r.check_type in ("file_exists", "file_exists_multi")
        ]
        results = audit_local_path(file_rules, tmp_local_repo_minimal)
        assert len(results) > 0
        failed = [r for r in results if r.status == "FAIL"]
        assert len(failed) >= 3

    def test_nonexistent_path_returns_empty(self, rules_dir):
        rules = load_rules(rules_dir, {"cis"})
        results = audit_local_path(rules, "/path/does/not/exist")
        assert results == []

    def test_targets_contain_local_prefix(self, rules_dir, tmp_local_repo):
        rules = load_rules(rules_dir, {"cis"})
        file_rules = [
            r for r in rules
            if r.level == "repository" and r.check_type in ("file_exists", "file_exists_multi")
        ]
        results = audit_local_path(file_rules, tmp_local_repo)
        for r in results:
            assert "local" in r.target or "test-repo" in r.target


# ===========================================================================
# 11. Scorecard generation
# ===========================================================================

class TestGenerateScorecard:
    """Tests for the scorecard generation function."""

    @pytest.fixture
    def mixed_results(self):
        return [
            AuditResult("t", "repository", "R1", "Pass rule", "CIS",
                        "auth", "critical", "PASS", "True", "True", ""),
            AuditResult("t", "repository", "R2", "Fail rule", "CIS",
                        "secrets", "high", "FAIL", "disabled", "enabled", "Enable it"),
            AuditResult("t", "repository", "R3", "Skip rule", "OWASP",
                        "branch-protection", "critical", "SKIP", "no perms", "True", ""),
            AuditResult("t", "repository", "R4", "Fail 2", "SANS",
                        "ci-cd", "high", "FAIL", "missing", "present", "Add it"),
        ]

    def test_scorecard_contains_target(self, mixed_results):
        scorecard = generate_scorecard(mixed_results, "my-org")
        assert "my-org" in scorecard

    def test_scorecard_contains_benchmark_names(self, mixed_results):
        scorecard = generate_scorecard(mixed_results, "my-org")
        assert "CIS" in scorecard
        assert "OWASP" in scorecard
        assert "SANS" in scorecard

    def test_scorecard_contains_severity_levels(self, mixed_results):
        scorecard = generate_scorecard(mixed_results, "my-org")
        assert "CRITICAL" in scorecard or "critical" in scorecard.lower()
        assert "HIGH" in scorecard or "high" in scorecard.lower()

    def test_scorecard_all_pass(self):
        results = [
            AuditResult("t", "repo", f"R{i}", f"Rule {i}", "CIS",
                        "auth", "critical", "PASS", "True", "True", "")
            for i in range(5)
        ]
        scorecard = generate_scorecard(results, "target")
        assert "100" in scorecard

    def test_scorecard_all_fail(self):
        results = [
            AuditResult("t", "repo", f"R{i}", f"Rule {i}", "CIS",
                        "auth", "critical", "FAIL", "False", "True", "Fix it")
            for i in range(5)
        ]
        scorecard = generate_scorecard(mixed_results := results, "target")
        assert "0" in scorecard

    def test_scorecard_empty_results(self):
        scorecard = generate_scorecard([], "target")
        assert isinstance(scorecard, str)

    def test_scorecard_top_issues_listed(self, mixed_results):
        scorecard = generate_scorecard(mixed_results, "my-org")
        assert "R2" in scorecard or "Fail rule" in scorecard

    def test_scorecard_returns_string(self, mixed_results):
        scorecard = generate_scorecard(mixed_results, "target")
        assert isinstance(scorecard, str)
        assert len(scorecard) > 0


# ===========================================================================
# 12. CSV export
# ===========================================================================

class TestExportCsv:
    """Tests for CSV export."""

    @pytest.fixture
    def results(self):
        return [
            AuditResult("org/repo", "repository", "R1", "Rule 1", "CIS",
                        "auth", "critical", "PASS", "True", "True", ""),
            AuditResult("org/repo", "repository", "R2", "Rule 2", "OWASP",
                        "secrets", "high", "FAIL", "disabled", "enabled", "Enable it"),
        ]

    def test_csv_file_created(self, results, tmp_path):
        filepath = str(tmp_path / "report.csv")
        export_csv(results, filepath)
        assert os.path.isfile(filepath)

    def test_csv_returns_filepath(self, results, tmp_path):
        filepath = str(tmp_path / "report.csv")
        returned = export_csv(results, filepath)
        assert returned == filepath

    def test_csv_row_count(self, results, tmp_path):
        filepath = str(tmp_path / "report.csv")
        export_csv(results, filepath)
        with open(filepath, "r", newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        # header + data rows
        assert len(rows) == len(results) + 1

    def test_csv_header_fields(self, results, tmp_path):
        filepath = str(tmp_path / "report.csv")
        export_csv(results, filepath)
        with open(filepath, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
        assert "Target" in headers
        assert "RuleID" in headers
        assert "Status" in headers
        assert "Severity" in headers
        assert "Remediation" in headers

    def test_csv_data_values(self, results, tmp_path):
        filepath = str(tmp_path / "report.csv")
        export_csv(results, filepath)
        with open(filepath, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert rows[0]["RuleID"] == "R1"
        assert rows[0]["Status"] == "PASS"
        assert rows[1]["RuleID"] == "R2"
        assert rows[1]["Status"] == "FAIL"


# ===========================================================================
# 13. JSON export
# ===========================================================================

class TestExportJson:
    """Tests for JSON export."""

    @pytest.fixture
    def results(self):
        return [
            AuditResult("org/repo", "repository", "R1", "Rule 1", "CIS",
                        "auth", "critical", "PASS", "True", "True", ""),
            AuditResult("org/repo", "repository", "R2", "Rule 2", "OWASP",
                        "secrets", "high", "FAIL", "disabled", "enabled", "Enable it"),
            AuditResult("org/repo", "repository", "R3", "Rule 3", "SANS",
                        "ci-cd", "medium", "SKIP", "no perms", "present", ""),
        ]

    def test_json_file_created(self, results, tmp_path):
        filepath = str(tmp_path / "report.json")
        export_json(results, filepath)
        assert os.path.isfile(filepath)

    def test_json_returns_filepath(self, results, tmp_path):
        filepath = str(tmp_path / "report.json")
        returned = export_json(results, filepath)
        assert returned == filepath

    def test_json_valid_structure(self, results, tmp_path):
        filepath = str(tmp_path / "report.json")
        export_json(results, filepath)
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "results" in data
        assert "total_rules" in data
        assert "passed" in data
        assert "failed" in data
        assert "skipped" in data
        assert "tool" in data
        assert "version" in data

    def test_json_result_counts(self, results, tmp_path):
        filepath = str(tmp_path / "report.json")
        export_json(results, filepath)
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["total_rules"] == 3
        assert data["passed"] == 1
        assert data["failed"] == 1
        assert data["skipped"] == 1

    def test_json_results_array_length(self, results, tmp_path):
        filepath = str(tmp_path / "report.json")
        export_json(results, filepath)
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data["results"]) == 3

    def test_json_result_fields(self, results, tmp_path):
        filepath = str(tmp_path / "report.json")
        export_json(results, filepath)
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        r = data["results"][0]
        assert "rule_id" in r
        assert "status" in r
        assert "severity" in r
        assert "remediation" in r


# ===========================================================================
# 14. HTML export
# ===========================================================================

class TestExportHtml:
    """Tests for HTML export."""

    @pytest.fixture
    def results(self):
        return [
            AuditResult("org/repo", "repository", "R1", "Rule 1", "CIS",
                        "auth", "critical", "PASS", "True", "True", ""),
            AuditResult("org/repo", "repository", "R2", "Rule 2", "OWASP",
                        "secrets", "high", "FAIL", "disabled", "enabled", "Enable secret scanning"),
        ]

    def test_html_file_created(self, results, tmp_path):
        filepath = str(tmp_path / "report.html")
        export_html(results, filepath, "org/repo")
        assert os.path.isfile(filepath)

    def test_html_returns_filepath(self, results, tmp_path):
        filepath = str(tmp_path / "report.html")
        returned = export_html(results, filepath, "org/repo")
        assert returned == filepath

    def test_html_contains_doctype(self, results, tmp_path):
        filepath = str(tmp_path / "report.html")
        export_html(results, filepath, "org/repo")
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        assert "<!DOCTYPE html>" in content or "<!doctype html" in content.lower()

    def test_html_contains_target(self, results, tmp_path):
        filepath = str(tmp_path / "report.html")
        export_html(results, filepath, "org/repo")
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        assert "org/repo" in content

    def test_html_contains_author(self, results, tmp_path):
        filepath = str(tmp_path / "report.html")
        export_html(results, filepath, "org/repo")
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        assert "h3nryza" in content

    def test_html_contains_rule_ids(self, results, tmp_path):
        filepath = str(tmp_path / "report.html")
        export_html(results, filepath, "org/repo")
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        assert "R1" in content
        assert "R2" in content

    def test_html_contains_pass_fail_badges(self, results, tmp_path):
        filepath = str(tmp_path / "report.html")
        export_html(results, filepath, "org/repo")
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        assert "PASS" in content
        assert "FAIL" in content


# ===========================================================================
# 15. Authentication methods
# ===========================================================================

class TestGitHubClientAuth:
    """Tests for GitHubClient authentication validation."""

    def test_gh_auth_validates_cli(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="Logged in", stderr="")
            client = GitHubClient(auth_method="gh")
            assert client.auth_method == "gh"

    def test_gh_auth_raises_when_cli_not_authenticated(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not logged in")
            with pytest.raises(RuntimeError, match="not authenticated"):
                GitHubClient(auth_method="gh")

    def test_gh_auth_raises_when_cli_not_installed(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeError, match="not installed"):
                GitHubClient(auth_method="gh")

    def test_pat_auth_valid_token(self):
        client = GitHubClient(auth_method="pat", token="ghp_abc123")
        assert client.auth_method == "pat"
        assert client.token == "ghp_abc123"

    def test_pat_auth_raises_without_token(self):
        with pytest.raises(RuntimeError, match="PAT auth requires"):
            GitHubClient(auth_method="pat", token="")

    def test_app_auth_requires_app_id_and_key(self):
        with pytest.raises(RuntimeError, match="App auth requires"):
            GitHubClient(auth_method="app", app_id="", app_key_file="")

    def test_app_auth_raises_when_key_file_missing(self, tmp_path):
        with pytest.raises(RuntimeError, match="App key file not found"):
            GitHubClient(
                auth_method="app",
                app_id="123",
                app_key_file=str(tmp_path / "nonexistent.pem"),
            )

    def test_app_auth_valid_when_key_file_exists(self, tmp_path):
        key_file = tmp_path / "app.pem"
        key_file.write_text("-----BEGIN RSA PRIVATE KEY-----\n", encoding="utf-8")
        client = GitHubClient(
            auth_method="app",
            app_id="123",
            app_key_file=str(key_file),
        )
        assert client.auth_method == "app"
        assert client.app_id == "123"


# ===========================================================================
# 16. Data class sanity checks
# ===========================================================================

class TestDataClasses:
    """Tests for the Rule and AuditResult data classes."""

    def test_rule_default_check_paths(self):
        rule = Rule(
            id="R1", name="n", description="d", benchmark="B",
            category="c", severity="low", level="repository",
            check_type="api", api_endpoint="/ep", field="f",
            expected_value=True, remediation="r",
        )
        assert rule.check_paths == []

    def test_rule_with_check_paths(self):
        rule = Rule(
            id="R1", name="n", description="d", benchmark="B",
            category="c", severity="low", level="repository",
            check_type="file_exists_multi", api_endpoint="/ep", field="f",
            expected_value="not_null", remediation="r",
            check_paths=["A", "B", "C"],
        )
        assert len(rule.check_paths) == 3

    def test_audit_result_all_fields(self):
        r = AuditResult(
            target="t", level="repository", rule_id="R1", rule_name="Name",
            benchmark="CIS", category="auth", severity="critical",
            status="PASS", current_value="True", expected_value="True",
            remediation="",
        )
        assert r.target == "t"
        assert r.rule_id == "R1"
        assert r.status == "PASS"
        assert r.severity == "critical"

    def test_audit_result_status_values(self):
        for status in ("PASS", "FAIL", "SKIP", "ERROR"):
            r = AuditResult(
                target="t", level="repository", rule_id="R1", rule_name="N",
                benchmark="B", category="c", severity="low",
                status=status, current_value="v", expected_value="e",
                remediation="",
            )
            assert r.status == status
