"""
test_compliance.py - Unit tests for gh-pipeline-compliance
Written by h3nryza

Run: pytest tests/ -v
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import sys
import tempfile
import unittest
from io import StringIO
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from gh_pipeline_compliance import (
    STATUS_COMPLIANT,
    STATUS_NON_COMPLIANT,
    STATUS_NO_PIPELINE,
    calculate_summary,
    check_repo_compliance,
    default_output_path,
    generate_report,
    parse_workflow_uses,
    print_summary,
    scan_workflows,
    CSV_COLUMNS,
)
from conftest import (
    WORKFLOW_CALLING_MULTIPLE,
    WORKFLOW_WITH_CHECKOUT_ONLY,
    WORKFLOW_WITH_REUSABLE,
    WORKFLOW_WITHOUT_REUSABLE,
    encode_content,
)


# ===========================================================================
# parse_workflow_uses
# ===========================================================================


class TestParseWorkflowUses:
    def test_finds_reusable_workflow_job(self):
        uses = parse_workflow_uses(WORKFLOW_WITH_REUSABLE)
        assert "my-org/reusable-workflows/.github/workflows/ci.yml@main" in uses

    def test_finds_step_level_uses(self):
        uses = parse_workflow_uses(WORKFLOW_WITH_CHECKOUT_ONLY)
        assert any("actions/checkout" in u for u in uses)
        assert any("actions/setup-python" in u for u in uses)

    def test_finds_multiple_uses(self):
        uses = parse_workflow_uses(WORKFLOW_CALLING_MULTIPLE)
        assert len(uses) >= 2
        assert any("security.yml" in u for u in uses)
        assert any("deploy.yml" in u for u in uses)

    def test_empty_workflow(self):
        uses = parse_workflow_uses("name: Empty\non: [push]\njobs: {}")
        assert uses == []

    def test_handles_quoted_uses(self):
        content = "      uses: 'my-org/rw/.github/workflows/ci.yml@main'"
        uses = parse_workflow_uses(content)
        assert "my-org/rw/.github/workflows/ci.yml@main" in uses

    def test_handles_double_quoted_uses(self):
        content = '      uses: "my-org/rw/.github/workflows/ci.yml@main"'
        uses = parse_workflow_uses(content)
        assert "my-org/rw/.github/workflows/ci.yml@main" in uses

    def test_no_false_positives_from_comments(self):
        content = "# uses: some/action@v1\nname: Test"
        uses = parse_workflow_uses(content)
        # comments should not be picked up — they don't start with whitespace+uses:
        # Our pattern requires `uses:` at start of line (possibly after whitespace),
        # a commented line starts with `#` so should not match
        assert "some/action@v1" not in uses


# ===========================================================================
# scan_workflows
# ===========================================================================


class TestScanWorkflows:
    def _make_contents_response(self, files: list[dict]) -> list[dict]:
        return [
            {
                "name": f["name"],
                "path": f".github/workflows/{f['name']}",
                "type": "file",
            }
            for f in files
        ]

    def _make_file_content(self, content: str) -> dict:
        return {
            "encoding": "base64",
            "content": encode_content(content),
        }

    @patch("gh_pipeline_compliance.github_request")
    def test_compliant_repo(self, mock_req):
        """Repo with reusable workflow ref is COMPLIANT."""
        workflow_list = [{"name": "ci.yml", "path": ".github/workflows/ci.yml", "type": "file"}]
        file_content = {
            "encoding": "base64",
            "content": encode_content(WORKFLOW_WITH_REUSABLE),
        }
        mock_req.side_effect = [workflow_list, file_content]

        result = scan_workflows(
            owner="my-org",
            repo="api-service",
            token="ghp_test",
            required_workflows=["my-org/reusable-workflows/.github/workflows/ci.yml"],
            content_search=None,
        )

        assert result["has_workflows"] is True
        assert result["uses_required_workflow"] is True
        assert "ci.yml" in result["workflow_files"]

    @patch("gh_pipeline_compliance.github_request")
    def test_non_compliant_repo(self, mock_req):
        """Repo with workflows but not the required one is NON_COMPLIANT."""
        workflow_list = [{"name": "build.yml", "path": ".github/workflows/build.yml", "type": "file"}]
        file_content = {
            "encoding": "base64",
            "content": encode_content(WORKFLOW_WITHOUT_REUSABLE),
        }
        mock_req.side_effect = [workflow_list, file_content]

        result = scan_workflows(
            owner="my-org",
            repo="legacy-app",
            token="ghp_test",
            required_workflows=["my-org/reusable-workflows/.github/workflows/ci.yml"],
            content_search=None,
        )

        assert result["has_workflows"] is True
        assert result["uses_required_workflow"] is False

    @patch("gh_pipeline_compliance.github_request")
    def test_no_pipeline_repo(self, mock_req):
        """Repo without .github/workflows/ dir returns NO_PIPELINE."""
        mock_req.return_value = None  # 404 from GitHub

        result = scan_workflows(
            owner="my-org",
            repo="docs-site",
            token="ghp_test",
            required_workflows=["my-org/reusable-workflows/.github/workflows/ci.yml"],
            content_search=None,
        )

        assert result["has_workflows"] is False
        assert result["uses_required_workflow"] is False
        assert result["workflow_files"] == []

    @patch("gh_pipeline_compliance.github_request")
    def test_content_search_match(self, mock_req):
        """Content search finds matching files."""
        workflow_list = [{"name": "ci.yml", "path": ".github/workflows/ci.yml", "type": "file"}]
        file_content = {
            "encoding": "base64",
            "content": encode_content(WORKFLOW_WITH_CHECKOUT_ONLY),
        }
        mock_req.side_effect = [workflow_list, file_content]

        result = scan_workflows(
            owner="my-org",
            repo="api-service",
            token="ghp_test",
            required_workflows=[],
            content_search=r"uses:\s+actions/checkout",
        )

        assert "ci.yml" in result["search_matches"]

    @patch("gh_pipeline_compliance.github_request")
    def test_content_search_no_match(self, mock_req):
        """Content search returns empty when pattern not found."""
        workflow_list = [{"name": "ci.yml", "path": ".github/workflows/ci.yml", "type": "file"}]
        file_content = {
            "encoding": "base64",
            "content": encode_content(WORKFLOW_WITHOUT_REUSABLE),
        }
        mock_req.side_effect = [workflow_list, file_content]

        result = scan_workflows(
            owner="my-org",
            repo="api-service",
            token="ghp_test",
            required_workflows=[],
            content_search=r"uses:\s+some/nonexistent",
        )

        assert result["search_matches"] == []

    @patch("gh_pipeline_compliance.github_request")
    def test_workflow_ref_version_agnostic(self, mock_req):
        """Workflow matching ignores @ref suffix when comparing base paths."""
        workflow_list = [{"name": "ci.yml", "path": ".github/workflows/ci.yml", "type": "file"}]
        # File uses @v2, required is specified without @ref
        content_v2 = WORKFLOW_WITH_REUSABLE.replace("@main", "@v2")
        file_content = {
            "encoding": "base64",
            "content": encode_content(content_v2),
        }
        mock_req.side_effect = [workflow_list, file_content]

        result = scan_workflows(
            owner="my-org",
            repo="api-service",
            token="ghp_test",
            required_workflows=["my-org/reusable-workflows/.github/workflows/ci.yml"],
            content_search=None,
        )

        assert result["uses_required_workflow"] is True


# ===========================================================================
# check_repo_compliance
# ===========================================================================


class TestCheckRepoCompliance:
    @patch("gh_pipeline_compliance.scan_workflows")
    def test_returns_compliant_status(self, mock_scan):
        mock_scan.return_value = {
            "has_workflows": True,
            "uses_required_workflow": True,
            "workflow_files": ["ci.yml"],
            "all_uses": ["my-org/rw/.github/workflows/ci.yml@main"],
            "search_matches": [],
        }

        repo = {"name": "api-service", "owner": {"login": "my-org"}, "updated_at": "2026-05-01T00:00:00Z"}
        result = check_repo_compliance(
            enterprise="",
            org="my-org",
            repo=repo,
            token="ghp_test",
            required_workflows=["my-org/rw/.github/workflows/ci.yml"],
            content_search=None,
        )

        assert result["ComplianceStatus"] == STATUS_COMPLIANT
        assert result["HasWorkflows"] is True
        assert result["UsesRequiredWorkflow"] is True
        assert result["Repository"] == "api-service"
        assert result["Organization"] == "my-org"

    @patch("gh_pipeline_compliance.scan_workflows")
    def test_returns_non_compliant_status(self, mock_scan):
        mock_scan.return_value = {
            "has_workflows": True,
            "uses_required_workflow": False,
            "workflow_files": ["build.yml"],
            "all_uses": ["actions/checkout@v4"],
            "search_matches": [],
        }

        repo = {"name": "legacy-app", "owner": {"login": "my-org"}, "updated_at": "2026-04-01T00:00:00Z"}
        result = check_repo_compliance(
            enterprise="",
            org="my-org",
            repo=repo,
            token="ghp_test",
            required_workflows=["my-org/rw/.github/workflows/ci.yml"],
            content_search=None,
        )

        assert result["ComplianceStatus"] == STATUS_NON_COMPLIANT

    @patch("gh_pipeline_compliance.scan_workflows")
    def test_returns_no_pipeline_status(self, mock_scan):
        mock_scan.return_value = {
            "has_workflows": False,
            "uses_required_workflow": False,
            "workflow_files": [],
            "all_uses": [],
            "search_matches": [],
        }

        repo = {"name": "docs-site", "owner": {"login": "my-org"}, "updated_at": "2026-03-01T00:00:00Z"}
        result = check_repo_compliance(
            enterprise="",
            org="my-org",
            repo=repo,
            token="ghp_test",
            required_workflows=["my-org/rw/.github/workflows/ci.yml"],
            content_search=None,
        )

        assert result["ComplianceStatus"] == STATUS_NO_PIPELINE

    @patch("gh_pipeline_compliance.scan_workflows")
    def test_no_required_workflow_with_workflows_is_compliant(self, mock_scan):
        """When no required workflow is specified, having any workflow = COMPLIANT."""
        mock_scan.return_value = {
            "has_workflows": True,
            "uses_required_workflow": False,
            "workflow_files": ["ci.yml"],
            "all_uses": ["actions/checkout@v4"],
            "search_matches": [],
        }

        repo = {"name": "api-service", "owner": {"login": "my-org"}, "updated_at": "2026-05-01T00:00:00Z"}
        result = check_repo_compliance(
            enterprise="",
            org="my-org",
            repo=repo,
            token="ghp_test",
            required_workflows=[],  # no required workflow
            content_search=None,
        )

        assert result["ComplianceStatus"] == STATUS_COMPLIANT

    def test_csv_columns_present(self):
        """Output dict must contain all CSV_COLUMNS keys."""
        with patch("gh_pipeline_compliance.scan_workflows") as mock_scan:
            mock_scan.return_value = {
                "has_workflows": False,
                "uses_required_workflow": False,
                "workflow_files": [],
                "all_uses": [],
                "search_matches": [],
            }
            repo = {"name": "test", "owner": {"login": "org"}, "updated_at": ""}
            result = check_repo_compliance("", "org", repo, "tok", [], None)
            for col in CSV_COLUMNS:
                assert col in result, f"Missing column: {col}"


# ===========================================================================
# calculate_summary
# ===========================================================================


class TestCalculateSummary:
    def _make_results(self, compliant: int, non_compliant: int, no_pipeline: int) -> list[dict]:
        results = []
        for _ in range(compliant):
            results.append({"ComplianceStatus": STATUS_COMPLIANT})
        for _ in range(non_compliant):
            results.append({"ComplianceStatus": STATUS_NON_COMPLIANT})
        for _ in range(no_pipeline):
            results.append({"ComplianceStatus": STATUS_NO_PIPELINE})
        return results

    def test_basic_counts(self):
        results = self._make_results(89, 41, 20)
        summary = calculate_summary(results)

        assert summary["total"] == 150
        assert summary["compliant"] == 89
        assert summary["non_compliant"] == 41
        assert summary["no_pipeline"] == 20

    def test_percentages(self):
        results = self._make_results(89, 41, 20)
        summary = calculate_summary(results)

        assert summary["compliant_pct"] == 59.3
        assert summary["non_compliant_pct"] == 27.3
        assert summary["no_pipeline_pct"] == 13.3

    def test_empty_results(self):
        summary = calculate_summary([])
        assert summary["total"] == 0
        assert summary["compliant_pct"] == 0.0

    def test_all_compliant(self):
        results = self._make_results(10, 0, 0)
        summary = calculate_summary(results)
        assert summary["compliant_pct"] == 100.0
        assert summary["non_compliant_pct"] == 0.0
        assert summary["no_pipeline_pct"] == 0.0

    def test_all_no_pipeline(self):
        results = self._make_results(0, 0, 5)
        summary = calculate_summary(results)
        assert summary["compliant"] == 0
        assert summary["no_pipeline"] == 5
        assert summary["no_pipeline_pct"] == 100.0


# ===========================================================================
# generate_report
# ===========================================================================


class TestGenerateReport:
    def _sample_results(self) -> list[dict]:
        return [
            {
                "Enterprise": "",
                "Organization": "my-org",
                "Repository": "api-service",
                "HasWorkflows": True,
                "UsesRequiredWorkflow": True,
                "WorkflowFiles": "ci.yml",
                "ComplianceStatus": STATUS_COMPLIANT,
                "LastUpdated": "2026-05-01T10:00:00Z",
            },
            {
                "Enterprise": "",
                "Organization": "my-org",
                "Repository": "legacy-app",
                "HasWorkflows": True,
                "UsesRequiredWorkflow": False,
                "WorkflowFiles": "build.yml",
                "ComplianceStatus": STATUS_NON_COMPLIANT,
                "LastUpdated": "2026-04-15T08:00:00Z",
            },
            {
                "Enterprise": "",
                "Organization": "my-org",
                "Repository": "docs-site",
                "HasWorkflows": False,
                "UsesRequiredWorkflow": False,
                "WorkflowFiles": "",
                "ComplianceStatus": STATUS_NO_PIPELINE,
                "LastUpdated": "2026-03-20T12:00:00Z",
            },
        ]

    def test_csv_output(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as f:
            tmp_path = f.name
        try:
            generate_report(self._sample_results(), tmp_path, fmt="csv")
            with open(tmp_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            assert len(rows) == 3
            assert rows[0]["Repository"] == "api-service"
            assert rows[0]["ComplianceStatus"] == STATUS_COMPLIANT
            assert rows[2]["ComplianceStatus"] == STATUS_NO_PIPELINE
        finally:
            os.unlink(tmp_path)

    def test_json_output(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            tmp_path = f.name
        try:
            generate_report(self._sample_results(), tmp_path, fmt="json")
            with open(tmp_path, encoding="utf-8") as f:
                data = json.load(f)
            assert "summary" in data
            assert "results" in data
            assert data["summary"]["total"] == 3
            assert len(data["results"]) == 3
        finally:
            os.unlink(tmp_path)

    def test_csv_has_all_columns(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as f:
            tmp_path = f.name
        try:
            generate_report(self._sample_results(), tmp_path, fmt="csv")
            with open(tmp_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                headers = reader.fieldnames or []
            for col in CSV_COLUMNS:
                assert col in headers, f"Missing column: {col}"
        finally:
            os.unlink(tmp_path)

    def test_csv_injection_sanitised(self):
        """Values starting with = should be prefixed with single quote."""
        results = [
            {
                "Enterprise": "",
                "Organization": "=cmd|' /C calc",
                "Repository": "test",
                "HasWorkflows": False,
                "UsesRequiredWorkflow": False,
                "WorkflowFiles": "",
                "ComplianceStatus": STATUS_NO_PIPELINE,
                "LastUpdated": "",
            }
        ]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as f:
            tmp_path = f.name
        try:
            generate_report(results, tmp_path, fmt="csv")
            with open(tmp_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            assert rows[0]["Organization"].startswith("'")
        finally:
            os.unlink(tmp_path)

    def test_creates_parent_directories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            nested_path = os.path.join(tmpdir, "a", "b", "c", "report.csv")
            generate_report(self._sample_results(), nested_path, fmt="csv")
            assert os.path.exists(nested_path)


# ===========================================================================
# default_output_path
# ===========================================================================


class TestDefaultOutputPath:
    def test_csv_extension(self):
        path = default_output_path("csv")
        assert path.endswith(".csv")

    def test_json_extension(self):
        path = default_output_path("json")
        assert path.endswith(".json")

    def test_contains_timestamp(self):
        path = default_output_path("csv")
        # Should contain something that looks like a timestamp YYYYMMDD_HHMMSS
        import re
        assert re.match(r"\d{8}_\d{6}_pipeline_compliance\.(csv|json)", path)


# ===========================================================================
# print_summary
# ===========================================================================


class TestPrintSummary:
    def test_output_format(self, capsys):
        summary = {
            "total": 150,
            "compliant": 89,
            "non_compliant": 41,
            "no_pipeline": 20,
            "compliant_pct": 59.3,
            "non_compliant_pct": 27.3,
            "no_pipeline_pct": 13.3,
        }
        print_summary(summary, "org: my-org")
        captured = capsys.readouterr()

        assert "Pipeline Compliance Summary" in captured.out
        assert "org: my-org" in captured.out
        assert "150" in captured.out
        assert "89" in captured.out
        assert "59.3%" in captured.out


# ===========================================================================
# load_required_workflows
# ===========================================================================


class TestLoadRequiredWorkflows:
    def test_single_workflow_from_args(self, base_args):
        from gh_pipeline_compliance import load_required_workflows
        workflows = load_required_workflows(base_args)
        assert "my-org/reusable-workflows/.github/workflows/ci.yml" in workflows

    def test_workflows_from_file(self, tmp_path, base_args):
        from gh_pipeline_compliance import load_required_workflows
        wf_file = tmp_path / "workflows.txt"
        wf_file.write_text(
            "my-org/rw/.github/workflows/ci.yml@main\n"
            "# comment line\n"
            "my-org/rw/.github/workflows/security.yml@main\n"
            "\n"
        )
        base_args.workflow = None
        base_args.workflows_file = str(wf_file)
        workflows = load_required_workflows(base_args)
        assert len(workflows) == 2
        assert "my-org/rw/.github/workflows/ci.yml@main" in workflows
        assert "my-org/rw/.github/workflows/security.yml@main" in workflows

    def test_no_workflows_specified(self, base_args):
        from gh_pipeline_compliance import load_required_workflows
        base_args.workflow = None
        base_args.workflows_file = None
        workflows = load_required_workflows(base_args)
        assert workflows == []


# ===========================================================================
# lambda_handler
# ===========================================================================


class TestLambdaHandler:
    @patch("lambda_handler.upload_to_s3")
    @patch("lambda_handler.generate_report")
    @patch("lambda_handler.run_scan")
    def test_successful_invocation(self, mock_scan, mock_report, mock_s3):
        from lambda_handler import handler

        mock_scan.return_value = [
            {
                "Enterprise": "",
                "Organization": "my-org",
                "Repository": "api-service",
                "HasWorkflows": True,
                "UsesRequiredWorkflow": True,
                "WorkflowFiles": "ci.yml",
                "ComplianceStatus": STATUS_COMPLIANT,
                "LastUpdated": "2026-05-01T10:00:00Z",
            }
        ]
        mock_report.return_value = "/tmp/test.csv"
        mock_s3.return_value = "s3://my-bucket/pipeline-compliance/test.csv"

        event = {
            "org": "my-org",
            "workflow": "my-org/rw/.github/workflows/ci.yml",
            "auth": "pat",
            "token": "ghp_test",
            "s3_bucket": "my-bucket",
            "format": "csv",
        }

        response = handler(event, context=MagicMock())

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert "summary" in body
        assert body["summary"]["total"] == 1
        assert body["summary"]["compliant"] == 1

    def test_missing_s3_bucket_returns_500(self):
        from lambda_handler import handler

        event = {
            "org": "my-org",
            "token": "ghp_test",
            # no s3_bucket
        }

        with patch("lambda_handler.run_scan") as mock_scan, \
             patch("lambda_handler.generate_report"):
            mock_scan.return_value = []
            response = handler(event, context=MagicMock())

        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert "error" in body

    def test_exception_returns_500(self):
        from lambda_handler import handler

        with patch("lambda_handler.run_scan", side_effect=RuntimeError("API down")):
            response = handler({"org": "my-org", "token": "tok"}, context=MagicMock())

        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert "API down" in body["error"]


# ===========================================================================
# Integration-style: full scan with mocked API
# ===========================================================================


class TestRunScanIntegration:
    @patch("gh_pipeline_compliance.list_org_repos")
    @patch("gh_pipeline_compliance.check_repo_compliance")
    @patch("gh_pipeline_compliance.resolve_token")
    def test_org_scan_returns_all_repos(self, mock_token, mock_check, mock_list):
        from gh_pipeline_compliance import run_scan

        mock_token.return_value = "ghp_test"
        mock_list.return_value = [
            {"name": "api-service", "owner": {"login": "my-org"}, "updated_at": ""},
            {"name": "legacy-app", "owner": {"login": "my-org"}, "updated_at": ""},
            {"name": "docs-site", "owner": {"login": "my-org"}, "updated_at": ""},
        ]
        mock_check.side_effect = [
            {"ComplianceStatus": STATUS_COMPLIANT, **{c: "" for c in CSV_COLUMNS if c != "ComplianceStatus"}},
            {"ComplianceStatus": STATUS_NON_COMPLIANT, **{c: "" for c in CSV_COLUMNS if c != "ComplianceStatus"}},
            {"ComplianceStatus": STATUS_NO_PIPELINE, **{c: "" for c in CSV_COLUMNS if c != "ComplianceStatus"}},
        ]

        args = argparse.Namespace(
            enterprise=None,
            org="my-org",
            user=None,
            workflow="my-org/rw/.github/workflows/ci.yml",
            workflows_file=None,
            pattern=None,
            search=None,
            auth="pat",
            token="ghp_test",
            app_id=None,
            app_key=None,
            verbose=False,
        )

        results = run_scan(args)
        assert len(results) == 3

    def test_no_target_raises(self):
        from gh_pipeline_compliance import run_scan

        args = argparse.Namespace(
            enterprise=None,
            org=None,
            user=None,
            workflow=None,
            workflows_file=None,
            pattern=None,
            search=None,
            auth="pat",
            token="ghp_test",
            app_id=None,
            app_key=None,
            verbose=False,
        )

        with pytest.raises(RuntimeError, match="No target specified"):
            run_scan(args)
