"""
conftest.py — Shared pytest fixtures for gh-new-resource-detector tests
Written by h3nryza
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ─────────────────────────────────────────────
# Datetime helpers
# ─────────────────────────────────────────────
def utc(dt_str: str) -> datetime:
    """Parse an ISO string into a UTC-aware datetime."""
    return datetime.fromisoformat(dt_str).replace(tzinfo=timezone.utc)


SEVEN_DAYS_AGO = datetime.now(timezone.utc).replace(
    microsecond=0
) - __import__("datetime").timedelta(days=7)


# ─────────────────────────────────────────────
# Fake API response builders
# ─────────────────────────────────────────────
def make_repo(
    name: str,
    org: str,
    days_ago: int = 1,
    visibility: str = "private",
) -> dict:
    ts = (
        datetime.now(timezone.utc) - __import__("datetime").timedelta(days=days_ago)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "name": name,
        "full_name": f"{org}/{name}",
        "html_url": f"https://github.com/{org}/{name}",
        "created_at": ts,
        "visibility": visibility,
        "private": visibility == "private",
        "owner": {"login": org},
    }


def make_org(login: str, days_ago: int = 1) -> dict:
    ts = (
        datetime.now(timezone.utc) - __import__("datetime").timedelta(days=days_ago)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "login": login,
        "name": login.title(),
        "url": f"https://github.com/{login}",
        "created_at": ts,
    }


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────
@pytest.fixture
def mock_client():
    """A MagicMock GitHubClient instance."""
    from gh_new_resource_detector import GitHubClient

    client = MagicMock(spec=GitHubClient)
    return client


@pytest.fixture
def tmp_state(tmp_path: Path) -> Path:
    """Path to a temporary state file (does not exist yet)."""
    return tmp_path / ".gh_detector_state.json"


@pytest.fixture
def existing_state(tmp_path: Path) -> Path:
    """State file pre-populated with a known org list."""
    state = tmp_path / ".gh_detector_state.json"
    state.write_text(json.dumps(["existing-org-1", "existing-org-2"]))
    return state


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Prevent any real HTTP calls during tests."""
    import requests

    monkeypatch.setattr(
        requests.Session,
        "request",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("Real HTTP call attempted in test")),
    )
