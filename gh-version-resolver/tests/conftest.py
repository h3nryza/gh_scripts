"""
conftest.py - pytest fixtures for gh-version-resolver tests
Written by h3nryza
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ─────────────────────────────────────────────
# Fixture: mock GitHubClient
# ─────────────────────────────────────────────
@pytest.fixture
def mock_client():
    """Return a MagicMock that mimics GitHubClient."""
    client = MagicMock()
    return client


# ─────────────────────────────────────────────
# Fixture: sample tag list (GitHub API format)
# ─────────────────────────────────────────────
SAMPLE_TAGS = [
    {
        "name": "v4.1.1",
        "commit": {"sha": "b4ffde65f46336ab88eb53be808477a3936bae11"},
    },
    {
        "name": "v4.1.0",
        "commit": {"sha": "a6604474cbf51e6e2b5a069b08cdb7a81dd5c24e"},
    },
    {
        "name": "v4.0.0",
        "commit": {"sha": "2e0e94e1f14605d2fb869c7c4dce12f76d0eb8a1"},
    },
    {
        "name": "v3.6.5",
        "commit": {"sha": "c32ab3021d3b6f9824a6b2e55cc3e8fc47c9d08a"},
    },
]


@pytest.fixture
def sample_tags():
    return SAMPLE_TAGS


# ─────────────────────────────────────────────
# Fixture: sample workflow file
# ─────────────────────────────────────────────
SAMPLE_WORKFLOW = """\
name: CI

on: [push]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11  # v4.1.1
      - uses: actions/setup-python@v4.7.0
      - uses: docker/build-push-action@4f58ea79222b3b9dc2c8bbdd6debcef730109a75  # v6.9.0
"""


@pytest.fixture
def workflow_file(tmp_path) -> Path:
    f = tmp_path / "ci.yml"
    f.write_text(SAMPLE_WORKFLOW)
    return f


# ─────────────────────────────────────────────
# Fixture: sample Terraform file
# ─────────────────────────────────────────────
SAMPLE_TF_GIT = '''\
module "vpc" {
  source = "git::https://github.com/terraform-aws-modules/terraform-aws-vpc.git?ref=a6604474cbf51e6e2b5a069b08cdb7a81dd5c24e"
}

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"
}
'''

SAMPLE_TF_REGISTRY = '''\
module "rds" {
  source  = "terraform-aws-modules/rds/aws"
  version = "6.9.0"
}
'''


@pytest.fixture
def terraform_file_git(tmp_path) -> Path:
    f = tmp_path / "main.tf"
    f.write_text(SAMPLE_TF_GIT)
    return f


@pytest.fixture
def terraform_file_registry(tmp_path) -> Path:
    f = tmp_path / "main.tf"
    f.write_text(SAMPLE_TF_REGISTRY)
    return f


# ─────────────────────────────────────────────
# Fixture: sample bulk import CSV
# ─────────────────────────────────────────────
SAMPLE_CSV = """\
repository,hash,type
actions/checkout,b4ffde65f46336ab88eb53be808477a3936bae11,github-action
actions/setup-python,v4.7.0,github-action
"""


@pytest.fixture
def import_csv(tmp_path) -> Path:
    f = tmp_path / "hashes.csv"
    f.write_text(SAMPLE_CSV)
    return f


# ─────────────────────────────────────────────
# Fixture: sample bulk import JSON
# ─────────────────────────────────────────────
SAMPLE_JSON = [
    {
        "repository": "actions/checkout",
        "hash": "b4ffde65f46336ab88eb53be808477a3936bae11",
        "type": "github-action",
    },
    {
        "repository": "actions/setup-python",
        "version": "v4.7.0",
        "type": "github-action",
    },
]


@pytest.fixture
def import_json(tmp_path) -> Path:
    f = tmp_path / "hashes.json"
    f.write_text(json.dumps(SAMPLE_JSON, indent=2))
    return f
