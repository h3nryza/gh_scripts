"""
test_resolver.py - Tests for gh_version_resolver
Written by h3nryza
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest
import responses as responses_lib

from gh_version_resolver import (
    CURRENCY_M1,
    CURRENCY_N1,
    CURRENCY_OLDER,
    CURRENCY_PATCH_BEHIND,
    CURRENCY_UNKNOWN,
    CURRENCY_UP_TO_DATE,
    ECOSYSTEM_GITHUB_ACTION,
    ECOSYSTEM_TF_MODULE,
    CSV_COLUMNS,
    check_version_currency,
    compare_versions,
    export_results,
    get_latest_release,
    is_stable_release,
    load_import_file,
    parse_semver,
    process_bulk_items,
    resolve_hash_to_version,
    resolve_version_to_hash,
    scan_terraform_file,
    scan_workflow_file,
    _is_commit_hash,
    _resolve_ref,
)


# ─────────────────────────────────────────────
# parse_semver
# ─────────────────────────────────────────────
class TestParseSemver:
    def test_full_semver(self):
        assert parse_semver("v4.1.1") == (4, 1, 1, "")

    def test_major_minor_only(self):
        result = parse_semver("v4.1")
        assert result is not None
        assert result[:2] == (4, 1)

    def test_major_only(self):
        result = parse_semver("v4")
        assert result is not None
        assert result[0] == 4

    def test_no_v_prefix(self):
        assert parse_semver("3.6.5") == (3, 6, 5, "")

    def test_pre_release_rc(self):
        result = parse_semver("v4.2.0-rc1")
        assert result is not None
        # pre-release field should be non-empty
        assert result[3]

    def test_invalid_returns_none(self):
        assert parse_semver("not-a-version") is None

    def test_empty_returns_none(self):
        assert parse_semver("") is None


# ─────────────────────────────────────────────
# is_stable_release
# ─────────────────────────────────────────────
class TestIsStableRelease:
    @pytest.mark.parametrize(
        "tag,expected",
        [
            ("v4.1.1", True),
            ("v3.0.0", True),
            ("v4.2.0-rc1", False),
            ("v4.2.0-alpha", False),
            ("v4.2.0-beta.1", False),
            ("v4.2.0-dev", False),
        ],
    )
    def test_stability(self, tag, expected):
        assert is_stable_release(tag) == expected


# ─────────────────────────────────────────────
# compare_versions
# ─────────────────────────────────────────────
class TestCompareVersions:
    def test_equal(self):
        assert compare_versions("v4.1.1", "v4.1.1") == 0

    def test_less_than(self):
        assert compare_versions("v4.0.0", "v4.1.0") == -1

    def test_greater_than(self):
        assert compare_versions("v4.1.0", "v4.0.0") == 1

    def test_major_difference(self):
        assert compare_versions("v3.6.5", "v4.1.1") == -1

    def test_pre_release_lower_than_release(self):
        assert compare_versions("v4.1.0-rc1", "v4.1.0") == -1


# ─────────────────────────────────────────────
# check_version_currency
# ─────────────────────────────────────────────
class TestCheckVersionCurrency:
    def test_up_to_date(self):
        currency, _ = check_version_currency("v4.1.1", "v4.1.1")
        assert currency == CURRENCY_UP_TO_DATE

    def test_patch_behind(self):
        currency, behind = check_version_currency("v4.1.0", "v4.1.1")
        assert currency == CURRENCY_PATCH_BEHIND
        assert "patch" in behind.lower()

    def test_n1_minor_behind(self):
        currency, behind = check_version_currency("v4.0.0", "v4.1.0")
        assert currency == CURRENCY_N1
        assert "minor" in behind.lower()

    def test_m1_major_behind(self):
        currency, behind = check_version_currency("v3.6.5", "v4.1.1")
        assert currency == CURRENCY_M1
        assert "major" in behind.lower()

    def test_older_multiple_major(self):
        currency, _ = check_version_currency("v2.0.0", "v4.1.1")
        assert currency == CURRENCY_OLDER

    def test_older_multiple_minor(self):
        currency, _ = check_version_currency("v4.0.0", "v4.3.0")
        assert currency == CURRENCY_OLDER

    def test_unknown_empty_version(self):
        currency, _ = check_version_currency("", "v4.1.1")
        assert currency == CURRENCY_UNKNOWN

    def test_unknown_non_semver(self):
        currency, _ = check_version_currency("sha-abc123", "v4.1.1")
        assert currency == CURRENCY_UNKNOWN


# ─────────────────────────────────────────────
# _is_commit_hash
# ─────────────────────────────────────────────
class TestIsCommitHash:
    @pytest.mark.parametrize(
        "ref,expected",
        [
            ("b4ffde65f46336ab88eb53be808477a3936bae11", True),
            ("abc123f", True),
            ("v4.1.1", False),
            ("main", False),
            ("abc12", False),  # too short
        ],
    )
    def test_detection(self, ref, expected):
        assert _is_commit_hash(ref) == expected


# ─────────────────────────────────────────────
# resolve_hash_to_version
# ─────────────────────────────────────────────
class TestResolveHashToVersion:
    def test_resolves_lightweight_tag(self, mock_client, sample_tags):
        mock_client.paginate.return_value = iter(sample_tags)
        result = resolve_hash_to_version(
            mock_client, "b4ffde65f46336ab88eb53be808477a3936bae11", "actions/checkout"
        )
        assert result == "v4.1.1"

    def test_partial_hash(self, mock_client, sample_tags):
        mock_client.paginate.return_value = iter(sample_tags)
        result = resolve_hash_to_version(
            mock_client, "b4ffde6", "actions/checkout"
        )
        assert result == "v4.1.1"

    def test_annotated_tag_dereference(self, mock_client):
        # Tag object SHA differs from commit SHA (annotated tag)
        tag_obj_sha = "aaabbbccc0001"
        commit_sha = "b4ffde65f46336ab88eb53be808477a3936bae11"
        tags = [
            {"name": "v4.1.1", "commit": {"sha": tag_obj_sha}},
        ]
        mock_client.paginate.return_value = iter(tags)
        mock_client.get.return_value = {
            "object": {"type": "commit", "sha": commit_sha}
        }
        result = resolve_hash_to_version(
            mock_client, "b4ffde6", "actions/checkout"
        )
        assert result == "v4.1.1"

    def test_no_match_returns_none(self, mock_client, sample_tags):
        mock_client.paginate.return_value = iter(sample_tags)
        mock_client.get.return_value = None
        result = resolve_hash_to_version(
            mock_client, "0000000", "actions/checkout"
        )
        assert result is None

    def test_short_hash_raises(self, mock_client):
        with pytest.raises(ValueError, match="at least"):
            resolve_hash_to_version(mock_client, "abc", "actions/checkout")


# ─────────────────────────────────────────────
# resolve_version_to_hash
# ─────────────────────────────────────────────
class TestResolveVersionToHash:
    def test_lightweight_tag(self, mock_client):
        mock_client.get.return_value = {
            "object": {
                "type": "commit",
                "sha": "b4ffde65f46336ab88eb53be808477a3936bae11",
            }
        }
        result = resolve_version_to_hash(mock_client, "v4.1.1", "actions/checkout")
        assert result == "b4ffde65f46336ab88eb53be808477a3936bae11"

    def test_annotated_tag(self, mock_client):
        tag_obj_sha = "aaabbbccc0001"
        commit_sha = "b4ffde65f46336ab88eb53be808477a3936bae11"

        def get_side_effect(path, **kwargs):
            if "ref/tags" in path:
                return {"object": {"type": "tag", "sha": tag_obj_sha}}
            if f"git/tags/{tag_obj_sha}" in path:
                return {"object": {"type": "commit", "sha": commit_sha}}
            return None

        mock_client.get.side_effect = get_side_effect
        result = resolve_version_to_hash(mock_client, "v4.1.1", "actions/checkout")
        assert result == commit_sha

    def test_not_found_returns_none(self, mock_client):
        mock_client.get.return_value = None
        result = resolve_version_to_hash(mock_client, "v99.0.0", "actions/checkout")
        assert result is None


# ─────────────────────────────────────────────
# get_latest_release
# ─────────────────────────────────────────────
class TestGetLatestRelease:
    def test_uses_releases_endpoint(self, mock_client):
        mock_client.get.return_value = {"tag_name": "v4.1.1"}
        result = get_latest_release(mock_client, "actions/checkout")
        assert result == "v4.1.1"

    def test_skips_prerelease_fallback_to_tags(self, mock_client, sample_tags):
        mock_client.get.return_value = {"tag_name": "v5.0.0-rc1"}
        mock_client.paginate.return_value = iter(sample_tags)
        result = get_latest_release(mock_client, "actions/checkout")
        # Should fall back to tag scanning and pick v4.1.1
        assert result == "v4.1.1"

    def test_fallback_to_tags_when_no_release(self, mock_client, sample_tags):
        mock_client.get.return_value = None
        mock_client.paginate.return_value = iter(sample_tags)
        result = get_latest_release(mock_client, "actions/checkout")
        assert result == "v4.1.1"


# ─────────────────────────────────────────────
# scan_workflow_file
# ─────────────────────────────────────────────
class TestScanWorkflowFile:
    def test_finds_pinned_hashes(self, mock_client, workflow_file):
        mock_client.paginate.return_value = iter([
            {
                "name": "v4.1.1",
                "commit": {"sha": "b4ffde65f46336ab88eb53be808477a3936bae11"},
            }
        ])
        mock_client.get.return_value = None
        results = scan_workflow_file(mock_client, workflow_file, check_currency=False)
        # Should find at least one hash-pinned action
        assert len(results) >= 1
        hashed = [r for r in results if r["InputHash"]]
        assert any(
            r["InputHash"].startswith("b4ffde6") for r in hashed
        )

    def test_finds_version_pinned_actions(self, mock_client, workflow_file):
        mock_client.get.return_value = {
            "object": {
                "type": "commit",
                "sha": "a6604474cbf51e6e2b5a069b08cdb7a81dd5c24e",
            }
        }
        results = scan_workflow_file(mock_client, workflow_file, check_currency=False)
        version_pinned = [r for r in results if r["ResolvedVersion"] == "v4.7.0"]
        assert len(version_pinned) >= 1

    def test_check_currency_adds_latest(self, mock_client, workflow_file):
        # Hash-pinned checkout action
        mock_client.paginate.return_value = iter([
            {
                "name": "v4.1.1",
                "commit": {"sha": "b4ffde65f46336ab88eb53be808477a3936bae11"},
            }
        ])
        mock_client.get.return_value = {"tag_name": "v4.1.1"}
        results = scan_workflow_file(mock_client, workflow_file, check_currency=True)
        resolved = [r for r in results if r["ResolvedVersion"] == "v4.1.1"]
        if resolved:
            assert resolved[0]["LatestVersion"] != ""


# ─────────────────────────────────────────────
# scan_terraform_file
# ─────────────────────────────────────────────
class TestScanTerraformFile:
    def test_finds_git_ref_hash(self, mock_client, terraform_file_git):
        mock_client.paginate.return_value = iter([
            {
                "name": "v5.0.0",
                "commit": {"sha": "a6604474cbf51e6e2b5a069b08cdb7a81dd5c24e"},
            }
        ])
        mock_client.get.return_value = None
        results = scan_terraform_file(
            mock_client, terraform_file_git, ecosystem=ECOSYSTEM_TF_MODULE
        )
        git_rows = [r for r in results if r["Type"] == ECOSYSTEM_TF_MODULE]
        assert len(git_rows) >= 1

    def test_finds_registry_module(self, mock_client, terraform_file_git):
        results = scan_terraform_file(
            mock_client, terraform_file_git, ecosystem=ECOSYSTEM_TF_MODULE
        )
        registry_rows = [r for r in results if "terraform-aws-modules" in r.get("Repository", "")]
        assert len(registry_rows) >= 1


# ─────────────────────────────────────────────
# load_import_file
# ─────────────────────────────────────────────
class TestLoadImportFile:
    def test_loads_csv(self, import_csv):
        items = load_import_file(import_csv)
        assert len(items) == 2
        assert items[0]["repository"] == "actions/checkout"

    def test_loads_json(self, import_json):
        items = load_import_file(import_json)
        assert len(items) == 2
        assert items[0]["repository"] == "actions/checkout"


# ─────────────────────────────────────────────
# process_bulk_items
# ─────────────────────────────────────────────
class TestProcessBulkItems:
    def test_processes_hash_items(self, mock_client, sample_tags):
        mock_client.paginate.return_value = iter(sample_tags)
        mock_client.get.return_value = None
        items = [
            {
                "repository": "actions/checkout",
                "hash": "b4ffde65f46336ab88eb53be808477a3936bae11",
                "type": "github-action",
            }
        ]
        results = process_bulk_items(mock_client, items, check_currency=False)
        assert len(results) == 1
        assert results[0]["Repository"] == "actions/checkout"
        assert results[0]["ResolvedVersion"] == "v4.1.1"

    def test_skips_items_missing_repo(self, mock_client):
        items = [{"hash": "abc123f"}]
        results = process_bulk_items(mock_client, items)
        assert len(results) == 0

    def test_skips_items_missing_ref(self, mock_client):
        items = [{"repository": "actions/checkout"}]
        results = process_bulk_items(mock_client, items)
        assert len(results) == 0


# ─────────────────────────────────────────────
# export_results
# ─────────────────────────────────────────────
class TestExportResults:
    def test_csv_output(self, tmp_path):
        rows = [
            {
                "Repository": "actions/checkout",
                "Reference": "ci.yml:42",
                "Type": "github-action",
                "InputHash": "b4ffde65f46336ab88eb53be808477a3936bae11",
                "ResolvedVersion": "v4.1.1",
                "LatestVersion": "v4.1.1",
                "Currency": "up-to-date",
                "VersionsBehind": "",
            }
        ]
        out = tmp_path / "output.csv"
        export_results(rows, out, fmt="csv")
        assert out.exists()
        with out.open() as f:
            reader = csv.DictReader(f)
            written = list(reader)
        assert len(written) == 1
        assert written[0]["Repository"] == "actions/checkout"
        assert written[0]["ResolvedVersion"] == "v4.1.1"

    def test_json_output(self, tmp_path):
        rows = [
            {
                "Repository": "actions/checkout",
                "Reference": "ci.yml",
                "Type": "github-action",
                "InputHash": "b4ffde65f46336ab88eb53be808477a3936bae11",
                "ResolvedVersion": "v4.1.1",
                "LatestVersion": "v4.1.1",
                "Currency": "up-to-date",
                "VersionsBehind": "",
            }
        ]
        out = tmp_path / "output.json"
        export_results(rows, out, fmt="json")
        assert out.exists()
        data = json.loads(out.read_text())
        assert len(data) == 1
        assert data[0]["ResolvedVersion"] == "v4.1.1"

    def test_creates_parent_dirs(self, tmp_path):
        rows = [
            {k: "" for k in CSV_COLUMNS}
        ]
        deep_out = tmp_path / "deep" / "nested" / "output.csv"
        export_results(rows, deep_out, fmt="csv")
        assert deep_out.exists()


# ─────────────────────────────────────────────
# _resolve_ref (integration-style unit tests)
# ─────────────────────────────────────────────
class TestResolveRef:
    def test_hash_ref_triggers_hash_to_version(self, mock_client, sample_tags):
        mock_client.paginate.return_value = iter(sample_tags)
        mock_client.get.return_value = None
        row = _resolve_ref(
            client=mock_client,
            repo="actions/checkout",
            ref="b4ffde65f46336ab88eb53be808477a3936bae11",
            ecosystem=ECOSYSTEM_GITHUB_ACTION,
        )
        assert row["InputHash"] == "b4ffde65f46336ab88eb53be808477a3936bae11"
        assert row["ResolvedVersion"] == "v4.1.1"

    def test_version_ref_triggers_version_to_hash(self, mock_client):
        mock_client.get.return_value = {
            "object": {
                "type": "commit",
                "sha": "b4ffde65f46336ab88eb53be808477a3936bae11",
            }
        }
        row = _resolve_ref(
            client=mock_client,
            repo="actions/checkout",
            ref="v4.1.1",
            ecosystem=ECOSYSTEM_GITHUB_ACTION,
        )
        assert row["ResolvedVersion"] == "v4.1.1"
        assert row["InputHash"] == "b4ffde65f46336ab88eb53be808477a3936bae11"

    def test_check_currency_populates_fields(self, mock_client, sample_tags):
        mock_client.paginate.return_value = iter(sample_tags)
        mock_client.get.return_value = {"tag_name": "v4.1.1"}
        row = _resolve_ref(
            client=mock_client,
            repo="actions/checkout",
            ref="b4ffde65f46336ab88eb53be808477a3936bae11",
            ecosystem=ECOSYSTEM_GITHUB_ACTION,
            check_currency=True,
        )
        assert row["LatestVersion"] == "v4.1.1"
        assert row["Currency"] == CURRENCY_UP_TO_DATE

    def test_check_currency_m1(self, mock_client, sample_tags):
        """Resolves hash to v3.6.5 when latest is v4.1.1 → should be M-1."""
        mock_client.paginate.return_value = iter(sample_tags)

        # First call to get (releases/latest) returns v4.1.1
        mock_client.get.return_value = {"tag_name": "v4.1.1"}

        row = _resolve_ref(
            client=mock_client,
            repo="actions/checkout",
            ref="c32ab3021d3b6f9824a6b2e55cc3e8fc47c9d08a",
            ecosystem=ECOSYSTEM_GITHUB_ACTION,
            check_currency=True,
        )
        if row["ResolvedVersion"]:
            assert row["Currency"] in (CURRENCY_M1, CURRENCY_OLDER)
