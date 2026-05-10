"""
conftest.py - pytest fixtures for gh-pipeline-compliance tests
Written by h3nryza
"""

from __future__ import annotations

import base64
import json
import sys
import os
from typing import Any

import pytest
import responses as resp_lib

# Ensure the parent directory is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ---------------------------------------------------------------------------
# Mock data helpers
# ---------------------------------------------------------------------------

def encode_content(text: str) -> str:
    """Base64-encode a string to mimic the GitHub Contents API."""
    return base64.b64encode(text.encode()).decode()


# ---------------------------------------------------------------------------
# Sample workflow YAML snippets
# ---------------------------------------------------------------------------

WORKFLOW_WITH_REUSABLE = """\
name: CI

on: [push, pull_request]

jobs:
  call-reusable:
    uses: my-org/reusable-workflows/.github/workflows/ci.yml@main
    secrets: inherit
"""

WORKFLOW_WITHOUT_REUSABLE = """\
name: CI

on: [push, pull_request]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: echo "hello"
"""

WORKFLOW_WITH_CHECKOUT_ONLY = """\
name: Lint

on: [push]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install ruff && ruff check .
"""

WORKFLOW_CALLING_MULTIPLE = """\
name: Release Pipeline

on:
  push:
    branches: [main]

jobs:
  security:
    uses: my-org/reusable-workflows/.github/workflows/security.yml@v2
    secrets: inherit
  deploy:
    uses: my-org/reusable-workflows/.github/workflows/deploy.yml@v2
    needs: security
    secrets: inherit
"""


# ---------------------------------------------------------------------------
# Fixtures: repos
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_repo_compliant() -> dict:
    return {
        "name": "api-service",
        "full_name": "my-org/api-service",
        "updated_at": "2026-05-01T10:00:00Z",
        "owner": {"login": "my-org"},
    }


@pytest.fixture
def mock_repo_non_compliant() -> dict:
    return {
        "name": "legacy-app",
        "full_name": "my-org/legacy-app",
        "updated_at": "2026-04-15T08:00:00Z",
        "owner": {"login": "my-org"},
    }


@pytest.fixture
def mock_repo_no_pipeline() -> dict:
    return {
        "name": "docs-site",
        "full_name": "my-org/docs-site",
        "updated_at": "2026-03-20T12:00:00Z",
        "owner": {"login": "my-org"},
    }


@pytest.fixture
def mock_repos(
    mock_repo_compliant, mock_repo_non_compliant, mock_repo_no_pipeline
) -> list[dict]:
    return [mock_repo_compliant, mock_repo_non_compliant, mock_repo_no_pipeline]


# ---------------------------------------------------------------------------
# Fixtures: workflow file listings
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_workflows_dir_compliant() -> list[dict]:
    return [
        {
            "name": "ci.yml",
            "path": ".github/workflows/ci.yml",
            "type": "file",
            "encoding": "base64",
            "content": encode_content(WORKFLOW_WITH_REUSABLE),
        }
    ]


@pytest.fixture
def mock_workflows_dir_non_compliant() -> list[dict]:
    return [
        {
            "name": "build.yml",
            "path": ".github/workflows/build.yml",
            "type": "file",
            "encoding": "base64",
            "content": encode_content(WORKFLOW_WITHOUT_REUSABLE),
        }
    ]


# ---------------------------------------------------------------------------
# Fixtures: argparse namespace
# ---------------------------------------------------------------------------

@pytest.fixture
def base_args():
    """Minimal args namespace for testing."""
    import argparse
    return argparse.Namespace(
        enterprise=None,
        org="my-org",
        user=None,
        workflow="my-org/reusable-workflows/.github/workflows/ci.yml",
        workflows_file=None,
        pattern=None,
        search=None,
        auth="pat",
        token="ghp_test_token_123",
        app_id=None,
        app_key=None,
        output=None,
        format="csv",
        s3_bucket=None,
        s3_prefix="pipeline-compliance/",
        summary=False,
        mode="local",
        verbose=False,
        interactive=False,
    )


# ---------------------------------------------------------------------------
# Fixtures: responses mock
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_api(mock_repos):
    """
    Activate responses mock and register common GitHub API endpoints.
    Tests can add more registrations on top.
    """
    with resp_lib.RequestsMock() as rsps:
        yield rsps
