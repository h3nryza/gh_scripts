"""
test_detector.py — Unit tests for gh-new-resource-detector
Written by h3nryza
"""

from __future__ import annotations

import csv
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from gh_new_resource_detector import (
    CSV_COLUMNS,
    GitHubClient,
    _compute_since,
    _default_output_path,
    _parse_iso,
    detect_new_orgs,
    detect_new_repos,
    enumerate_enterprise,
    enumerate_user,
    export_results,
    main,
    run_detection,
)

from tests.conftest import make_org, make_repo, utc


# ─────────────────────────────────────────────
# _parse_iso
# ─────────────────────────────────────────────
class TestParseIso:
    def test_z_suffix(self):
        dt = _parse_iso("2026-01-15T12:00:00Z")
        assert dt is not None
        assert dt.tzinfo is not None
        assert dt.year == 2026

    def test_offset_suffix(self):
        dt = _parse_iso("2026-01-15T12:00:00+00:00")
        assert dt is not None

    def test_none_input(self):
        assert _parse_iso(None) is None

    def test_empty_string(self):
        assert _parse_iso("") is None

    def test_invalid_string(self):
        assert _parse_iso("not-a-date") is None


# ─────────────────────────────────────────────
# _compute_since
# ─────────────────────────────────────────────
class TestComputeSince:
    def test_days_default(self):
        config = {}
        since = _compute_since(config)
        expected = datetime.now(timezone.utc) - timedelta(days=7)
        assert abs((since - expected).total_seconds()) < 5

    def test_days_custom(self):
        config = {"days": 14}
        since = _compute_since(config)
        expected = datetime.now(timezone.utc) - timedelta(days=14)
        assert abs((since - expected).total_seconds()) < 5

    def test_since_string_overrides_days(self):
        config = {"since": "2026-01-01", "days": 99}
        since = _compute_since(config)
        assert since.year == 2026
        assert since.month == 1
        assert since.day == 1


# ─────────────────────────────────────────────
# detect_new_repos
# ─────────────────────────────────────────────
class TestDetectNewRepos:
    def _since(self, days: int = 7) -> datetime:
        return datetime.now(timezone.utc) - timedelta(days=days)

    def test_returns_recent_repos(self, mock_client):
        repos = [
            make_repo("new-repo", "my-org", days_ago=1),
            make_repo("old-repo", "my-org", days_ago=10),
        ]
        mock_client.paginate.return_value = iter(repos)

        since = self._since(7)
        results = detect_new_repos(mock_client, "my-org", since, enterprise="my-ent")

        # Only the 1-day-old repo should pass
        assert len(results) == 1
        assert results[0]["Name"] == "my-org/new-repo"
        assert results[0]["Enterprise"] == "my-ent"
        assert results[0]["ResourceType"] == "repo"

    def test_stops_at_old_repo(self, mock_client):
        """Once a repo older than `since` is encountered, iteration stops."""
        repos = [
            make_repo("repo-a", "org", days_ago=1),
            make_repo("repo-b", "org", days_ago=3),
            make_repo("repo-c", "org", days_ago=30),  # older than window
        ]
        mock_client.paginate.return_value = iter(repos)

        results = detect_new_repos(mock_client, "org", self._since(7))
        assert len(results) == 2

    def test_empty_org(self, mock_client):
        mock_client.paginate.return_value = iter([])
        results = detect_new_repos(mock_client, "empty-org", self._since(7))
        assert results == []

    def test_visibility_field(self, mock_client):
        repos = [make_repo("pub-repo", "org", days_ago=1, visibility="public")]
        mock_client.paginate.return_value = iter(repos)

        results = detect_new_repos(mock_client, "org", self._since(7))
        assert results[0]["Visibility"] == "public"

    def test_url_field(self, mock_client):
        repos = [make_repo("my-repo", "org", days_ago=1)]
        mock_client.paginate.return_value = iter(repos)

        results = detect_new_repos(mock_client, "org", self._since(7))
        assert "github.com/org/my-repo" in results[0]["URL"]


# ─────────────────────────────────────────────
# detect_new_orgs
# ─────────────────────────────────────────────
class TestDetectNewOrgs:
    def _since(self, days: int = 7) -> datetime:
        return datetime.now(timezone.utc) - timedelta(days=days)

    def test_detects_new_org_via_created_at(self, mock_client, tmp_state):
        orgs = [make_org("new-org", days_ago=1)]
        results = detect_new_orgs(
            mock_client, orgs, self._since(7), enterprise="ent", state_file=tmp_state
        )
        assert len(results) == 1
        assert results[0]["Organization"] == "new-org"
        assert results[0]["ResourceType"] == "org"

    def test_ignores_old_org_without_state(self, mock_client, tmp_state):
        orgs = [make_org("old-org", days_ago=30)]
        results = detect_new_orgs(
            mock_client, orgs, self._since(7), state_file=tmp_state
        )
        assert results == []

    def test_uses_state_file_to_detect_new_org(self, mock_client, existing_state):
        orgs = [
            make_org("existing-org-1"),
            make_org("existing-org-2"),
            make_org("brand-new-org"),
        ]
        results = detect_new_orgs(
            mock_client, orgs, self._since(7), enterprise="ent", state_file=existing_state
        )
        assert len(results) == 1
        assert results[0]["Organization"] == "brand-new-org"

    def test_state_file_written_after_run(self, mock_client, tmp_state):
        orgs = [make_org("org-a"), make_org("org-b")]
        detect_new_orgs(mock_client, orgs, self._since(7), state_file=tmp_state)
        assert tmp_state.exists()
        saved = json.loads(tmp_state.read_text())
        assert "org-a" in saved
        assert "org-b" in saved

    def test_no_state_file_no_crash(self, mock_client):
        orgs = [make_org("org-a", days_ago=1)]
        results = detect_new_orgs(mock_client, orgs, self._since(7))
        assert len(results) == 1


# ─────────────────────────────────────────────
# enumerate_enterprise
# ─────────────────────────────────────────────
class TestEnumerateEnterprise:
    def test_returns_orgs_from_rest(self, mock_client):
        mock_client.paginate.return_value = iter(
            [make_org("org-a"), make_org("org-b")]
        )
        orgs = enumerate_enterprise(mock_client, "my-ent")
        assert len(orgs) == 2
        mock_client.paginate.assert_called_once_with("/enterprises/my-ent/organizations")

    def test_falls_back_to_graphql(self, mock_client):
        mock_client.paginate.return_value = iter([])  # REST returns nothing
        mock_client.graphql.return_value = {
            "data": {
                "enterprise": {
                    "organizations": {
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": [
                            {"login": "gql-org", "name": "GQL Org", "url": "https://github.com/gql-org", "createdAt": "2026-01-01T00:00:00Z"},
                        ],
                    }
                }
            }
        }
        orgs = enumerate_enterprise(mock_client, "my-ent")
        assert len(orgs) == 1
        assert orgs[0]["login"] == "gql-org"

    def test_graphql_error_returns_empty(self, mock_client):
        mock_client.paginate.return_value = iter([])
        mock_client.graphql.return_value = {"errors": [{"message": "Unauthorized"}]}
        orgs = enumerate_enterprise(mock_client, "bad-ent")
        assert orgs == []


# ─────────────────────────────────────────────
# enumerate_user
# ─────────────────────────────────────────────
class TestEnumerateUser:
    def test_returns_user_repos(self, mock_client):
        mock_client.paginate.return_value = iter(
            [make_repo("user-repo", "octocat")]
        )
        repos = enumerate_user(mock_client, "octocat")
        assert len(repos) == 1
        mock_client.paginate.assert_called_once()


# ─────────────────────────────────────────────
# export_results
# ─────────────────────────────────────────────
class TestExportResults:
    def _sample_results(self) -> list[dict]:
        return [
            {
                "Enterprise": "ent",
                "Organization": "org",
                "ResourceType": "repo",
                "Name": "org/repo",
                "CreatedAt": "2026-01-01T00:00:00Z",
                "CreatedBy": "octocat",
                "Visibility": "private",
                "URL": "https://github.com/org/repo",
            }
        ]

    def test_csv_output(self, tmp_path):
        out = tmp_path / "results.csv"
        export_results(self._sample_results(), out, fmt="csv")
        assert out.exists()
        rows = list(csv.DictReader(out.open()))
        assert len(rows) == 1
        assert rows[0]["Name"] == "org/repo"
        assert rows[0]["ResourceType"] == "repo"

    def test_csv_columns_match_spec(self, tmp_path):
        out = tmp_path / "results.csv"
        export_results(self._sample_results(), out, fmt="csv")
        with out.open() as f:
            reader = csv.reader(f)
            headers = next(reader)
        assert headers == CSV_COLUMNS

    def test_json_output(self, tmp_path):
        out = tmp_path / "results.json"
        export_results(self._sample_results(), out, fmt="json")
        assert out.exists()
        data = json.loads(out.read_text())
        assert isinstance(data, list)
        assert data[0]["Name"] == "org/repo"

    def test_creates_parent_dirs(self, tmp_path):
        out = tmp_path / "nested" / "deep" / "results.csv"
        export_results(self._sample_results(), out)
        assert out.exists()

    def test_empty_results(self, tmp_path):
        out = tmp_path / "empty.csv"
        export_results([], out)
        rows = list(csv.DictReader(out.open()))
        assert rows == []


# ─────────────────────────────────────────────
# _default_output_path
# ─────────────────────────────────────────────
class TestDefaultOutputPath:
    def test_csv_extension(self):
        p = _default_output_path("csv")
        assert p.suffix == ".csv"
        assert "new_resources" in p.name

    def test_json_extension(self):
        p = _default_output_path("json")
        assert p.suffix == ".json"

    def test_includes_timestamp(self):
        p = _default_output_path("csv")
        # Name should start with a date-like pattern
        assert p.name[0].isdigit()


# ─────────────────────────────────────────────
# run_detection (integration-style with mocks)
# ─────────────────────────────────────────────
class TestRunDetection:
    def _base_config(self, **kwargs) -> dict:
        return {
            "auth": "pat",
            "token": "fake-token",
            "days": 7,
            "type": "all",
            "format": "csv",
            **kwargs,
        }

    def test_org_mode_calls_detect_repos(self, tmp_path):
        config = self._base_config(org="my-org")

        with (
            patch("gh_new_resource_detector.GitHubClient") as MockClient,
            patch("gh_new_resource_detector.detect_new_repos") as mock_detect,
        ):
            MockClient.return_value = MagicMock()
            mock_detect.return_value = [{"ResourceType": "repo", "Name": "my-org/repo"}]
            results = run_detection(config)

        mock_detect.assert_called_once()
        assert len(results) == 1

    def test_enterprise_mode_calls_both(self, tmp_path):
        config = self._base_config(enterprise="my-ent")

        with (
            patch("gh_new_resource_detector.GitHubClient") as MockClient,
            patch("gh_new_resource_detector.enumerate_enterprise") as mock_enum,
            patch("gh_new_resource_detector.detect_new_orgs") as mock_orgs,
            patch("gh_new_resource_detector.detect_new_repos") as mock_repos,
        ):
            MockClient.return_value = MagicMock()
            mock_enum.return_value = [{"login": "org-a"}, {"login": "org-b"}]
            mock_orgs.return_value = [{"ResourceType": "org", "Name": "org-c"}]
            mock_repos.return_value = [{"ResourceType": "repo", "Name": "org-a/repo-x"}]

            results = run_detection(config)

        mock_enum.assert_called_once()
        mock_orgs.assert_called_once()
        # Should be called for each org
        assert mock_repos.call_count == 2

    def test_user_mode(self):
        config = self._base_config(user="octocat")

        with (
            patch("gh_new_resource_detector.GitHubClient") as MockClient,
            patch("gh_new_resource_detector.enumerate_user") as mock_enum,
        ):
            MockClient.return_value = MagicMock()
            mock_enum.return_value = [
                make_repo("repo", "octocat", days_ago=1)
            ]
            results = run_detection(config)

        assert len(results) == 1
        assert results[0]["ResourceType"] == "repo"

    def test_type_repos_skips_org_detection(self):
        config = self._base_config(enterprise="my-ent", type="repos")

        with (
            patch("gh_new_resource_detector.GitHubClient") as MockClient,
            patch("gh_new_resource_detector.enumerate_enterprise") as mock_enum,
            patch("gh_new_resource_detector.detect_new_orgs") as mock_orgs,
            patch("gh_new_resource_detector.detect_new_repos") as mock_repos,
        ):
            MockClient.return_value = MagicMock()
            mock_enum.return_value = [{"login": "org-a"}]
            mock_repos.return_value = []

            run_detection(config)

        mock_orgs.assert_not_called()

    def test_type_orgs_skips_repo_detection(self):
        config = self._base_config(enterprise="my-ent", type="orgs")

        with (
            patch("gh_new_resource_detector.GitHubClient") as MockClient,
            patch("gh_new_resource_detector.enumerate_enterprise") as mock_enum,
            patch("gh_new_resource_detector.detect_new_orgs") as mock_orgs,
            patch("gh_new_resource_detector.detect_new_repos") as mock_repos,
        ):
            MockClient.return_value = MagicMock()
            mock_enum.return_value = [{"login": "org-a"}]
            mock_orgs.return_value = []

            run_detection(config)

        mock_repos.assert_not_called()


# ─────────────────────────────────────────────
# GitHubClient
# ─────────────────────────────────────────────
class TestGitHubClientInit:
    def test_sets_auth_header(self, monkeypatch):
        # Patch Session.request so no real call is made
        import requests

        monkeypatch.setattr(
            requests.Session,
            "request",
            MagicMock(
                return_value=MagicMock(status_code=200, json=lambda: [], text="")
            ),
        )
        client = GitHubClient("my-token")
        assert "Bearer my-token" in client.session.headers.get("Authorization", "")

    def test_paginate_stops_on_empty(self, monkeypatch):
        import requests

        call_count = 0

        def fake_request(self, method, url, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = "[]"
            mock_resp.json.return_value = []
            return mock_resp

        monkeypatch.setattr(requests.Session, "request", fake_request)
        client = GitHubClient("token")
        results = list(client.paginate("/orgs/my-org/repos"))
        assert results == []
        assert call_count == 1  # only one page attempted


# ─────────────────────────────────────────────
# CLI (main)
# ─────────────────────────────────────────────
class TestCLIMain:
    def test_help_flag(self, capsys):
        rc = main(["-h"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "gh-new-resource-detector" in captured.out

    def test_version_flag(self, capsys):
        rc = main(["--version"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "h3nryza" in captured.out

    def test_no_target_exits_nonzero(self, capsys):
        rc = main([])
        assert rc == 1

    def test_org_mode_end_to_end(self, tmp_path):
        output_file = str(tmp_path / "out.csv")

        with (
            patch("gh_new_resource_detector.run_detection") as mock_run,
            patch("gh_new_resource_detector.export_results") as mock_export,
        ):
            mock_run.return_value = [
                {
                    "Enterprise": "",
                    "Organization": "test-org",
                    "ResourceType": "repo",
                    "Name": "test-org/repo-1",
                    "CreatedAt": "2026-05-01T00:00:00Z",
                    "CreatedBy": "octocat",
                    "Visibility": "private",
                    "URL": "https://github.com/test-org/repo-1",
                }
            ]
            rc = main(["-o", "test-org", "--output", output_file, "--auth", "pat", "--token", "tok"])

        assert rc == 0
        mock_run.assert_called_once()
        mock_export.assert_called_once()

    def test_enterprise_mode_passes_config(self):
        with (
            patch("gh_new_resource_detector.run_detection") as mock_run,
            patch("gh_new_resource_detector.export_results"),
        ):
            mock_run.return_value = []
            main(["-e", "my-ent", "--days", "14", "--type", "repos", "--auth", "pat", "--token", "t"])

        call_config = mock_run.call_args[0][0]
        assert call_config["enterprise"] == "my-ent"
        assert call_config["days"] == 14
        assert call_config["type"] == "repos"


# ─────────────────────────────────────────────
# upload_to_s3
# ─────────────────────────────────────────────
class TestUploadToS3:
    """boto3 is an optional dep; inject a fake module via sys.modules so tests
    don't require the real package to be installed."""

    @pytest.fixture(autouse=True)
    def _fake_boto3(self, monkeypatch):
        import sys
        import types

        mock_s3_client = MagicMock()
        fake_boto3 = types.ModuleType("boto3")
        fake_boto3.client = MagicMock(return_value=mock_s3_client)
        monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
        self._mock_s3 = mock_s3_client
        self._fake_boto3 = fake_boto3

    def test_upload_called_with_correct_args(self, tmp_path):
        from gh_new_resource_detector import upload_to_s3

        test_file = tmp_path / "results.csv"
        test_file.write_text("header\nvalue")

        uri = upload_to_s3(test_file, "my-bucket", prefix="audit/")

        self._mock_s3.upload_file.assert_called_once_with(
            str(test_file), "my-bucket", "audit/results.csv"
        )
        assert uri == "s3://my-bucket/audit/results.csv"

    def test_upload_no_prefix(self, tmp_path):
        from gh_new_resource_detector import upload_to_s3

        test_file = tmp_path / "out.csv"
        test_file.write_text("data")

        uri = upload_to_s3(test_file, "bucket")

        self._mock_s3.upload_file.assert_called_once_with(str(test_file), "bucket", "out.csv")
        assert uri == "s3://bucket/out.csv"
