"""
conftest.py — Pytest fixtures for gh-best-practices-audit tests.
Written by h3nryza
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure the package root is importable regardless of how pytest is invoked
PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))


# ---------------------------------------------------------------------------
# Shared API response payloads
# ---------------------------------------------------------------------------

REPO_API_RESPONSE = {
    "id": 123456,
    "full_name": "test-org/test-repo",
    "name": "test-repo",
    "owner": {"login": "test-org"},
    "default_branch": "main",
    "private": True,
    "archived": False,
    "has_wiki": False,
    "has_projects": False,
    "security_and_analysis": {
        "secret_scanning": {"status": "enabled"},
        "secret_scanning_push_protection": {"status": "enabled"},
        "dependabot_security_updates": {"status": "enabled"},
        "advanced_security": {"status": "enabled"},
    },
    "delete_branch_on_merge": True,
    "allow_force_pushes": False,
    "allow_merge_commit": False,
    "allow_squash_merge": True,
    "allow_rebase_merge": False,
}

ORG_API_RESPONSE = {
    "login": "test-org",
    "id": 111,
    "two_factor_requirement_enabled": True,
    "members_can_create_repositories": False,
    "members_can_create_public_repositories": False,
    "members_can_fork_private_repositories": False,
    "members_can_invite_outside_collaborators": False,
    "members_can_create_pages": False,
    "members_can_create_public_packages": False,
    "default_repository_permission": "read",
    "members_allowed_repository_creation_type": "none",
    "dependency_graph_enabled_for_new_repositories": True,
    "dependabot_alerts_enabled_for_new_repositories": True,
    "dependabot_security_updates_enabled_for_new_repositories": True,
    "secret_scanning_enabled_for_new_repositories": True,
    "code_scanning_default_setup_enabled": True,
    "security_advisories_enabled": True,
}

BRANCH_PROTECTION_RESPONSE = {
    "url": "https://api.github.com/repos/test-org/test-repo/branches/main/protection",
    "required_status_checks": {
        "strict": True,
        "contexts": ["ci/test"],
    },
    "enforce_admins": {"url": "...", "enabled": True},
    "required_pull_request_reviews": {
        "dismissal_restrictions": {},
        "dismiss_stale_reviews": True,
        "require_code_owner_reviews": True,
        "required_approving_review_count": 2,
        "require_last_push_approval": True,
    },
    "restrictions": None,
    "required_linear_history": {"enabled": True},
    "allow_force_pushes": {"enabled": False},
    "allow_deletions": {"enabled": False},
    "block_creations": {"enabled": True},
    "required_conversation_resolution": {"enabled": True},
}

WEBHOOKS_RESPONSE = [
    {
        "id": 1,
        "config": {
            "url": "https://example.com/webhook",
            "content_type": "json",
            "insecure_ssl": "0",
        },
        "active": True,
    }
]

REPOS_LIST_RESPONSE = [
    {
        "full_name": "test-org/test-repo",
        "name": "test-repo",
        "default_branch": "main",
        "archived": False,
    },
    {
        "full_name": "test-org/archived-repo",
        "name": "archived-repo",
        "default_branch": "main",
        "archived": True,
    },
]


# ---------------------------------------------------------------------------
# Core fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def rules_dir() -> Path:
    """Return the path to the real rules directory bundled with the tool."""
    return Path(__file__).resolve().parent.parent / "rules"


@pytest.fixture
def mock_client() -> MagicMock:
    """
    A MagicMock GitHubClient with api_call returning None by default.
    Individual tests override api_call.return_value or .side_effect.
    """
    client = MagicMock()
    client.auth_method = "gh"
    client.api_call = MagicMock(return_value=None)
    return client


@pytest.fixture
def smart_mock_client() -> MagicMock:
    """
    A MagicMock GitHubClient whose api_call routes to realistic stub responses
    based on the endpoint pattern. Useful for integration-style tests.
    """
    client = MagicMock()

    def _side_effect(endpoint: str, **kwargs):
        e = endpoint.split("?")[0]
        if "/branches/" in e and "/protection" in e:
            if "/required_signatures" in e:
                return {"enabled": True}
            return BRANCH_PROTECTION_RESPONSE
        if e.endswith("/repos/test-org/test-repo") or e == "/repos/test-org/test-repo":
            return REPO_API_RESPONSE
        if "/orgs/test-org" in e and "repos" not in e:
            return ORG_API_RESPONSE
        if "orgs/test-org/repos" in e:
            return REPOS_LIST_RESPONSE
        if "hooks" in e or "webhooks" in e:
            return WEBHOOKS_RESPONSE
        if "code-scanning/alerts" in e or "secret-scanning/alerts" in e:
            return []
        if "audit-log" in e:
            return [{"action": "repo.create", "created_at": 1234567890}]
        if "enterprises/" in e:
            return {"saml_enabled": True, "advanced_security_enabled": True}
        if "organizations" in e:
            return [{"login": "test-org", "id": 111}]
        return None

    client.api_call.side_effect = _side_effect
    client.auth_method = "gh"
    return client


@pytest.fixture
def sample_org_response() -> dict:
    """Sample GitHub organization API response."""
    return ORG_API_RESPONSE.copy()


@pytest.fixture
def sample_repo_response() -> dict:
    """Sample GitHub repository API response."""
    return REPO_API_RESPONSE.copy()


@pytest.fixture
def sample_branch_protection_response() -> dict:
    """Sample GitHub branch protection API response."""
    return BRANCH_PROTECTION_RESPONSE.copy()


@pytest.fixture
def sample_actions_permissions_response() -> dict:
    """Sample GitHub Actions permissions API response."""
    return {
        "enabled": True,
        "allowed_actions": "selected",
        "selected_actions_url": (
            "https://api.github.com/repos/test-org/test-repo"
            "/actions/permissions/selected-actions"
        ),
    }


@pytest.fixture
def sample_workflow_permissions_response() -> dict:
    """Sample GitHub workflow permissions API response."""
    return {
        "default_workflow_permissions": "read",
        "can_approve_pull_request_reviews": False,
    }


# ---------------------------------------------------------------------------
# Local filesystem fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_local_repo(tmp_path: Path) -> str:
    """
    Create a temporary local repository with common security hygiene files:
    .gitignore, README, LICENSE, CODEOWNERS, a workflow file.
    """
    repo_dir = tmp_path / "test-repo"
    repo_dir.mkdir()
    (repo_dir / ".git").mkdir()
    (repo_dir / ".gitignore").write_text("*.pyc\n__pycache__/\n.env\n", encoding="utf-8")
    (repo_dir / "README.md").write_text("# Test Repo\n", encoding="utf-8")
    (repo_dir / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    (repo_dir / "SECURITY.md").write_text("# Security Policy\n", encoding="utf-8")
    github_dir = repo_dir / ".github"
    github_dir.mkdir()
    (github_dir / "CODEOWNERS").write_text("* @test-org/admins\n", encoding="utf-8")
    workflows_dir = github_dir / "workflows"
    workflows_dir.mkdir()
    (workflows_dir / "ci.yml").write_text("name: CI\n", encoding="utf-8")
    (workflows_dir / "dependency-review.yml").write_text(
        "name: Dependency Review\n", encoding="utf-8"
    )
    return str(repo_dir)


@pytest.fixture
def tmp_local_repo_minimal(tmp_path: Path) -> str:
    """Create a minimal local repository — only a .git directory, nothing else."""
    repo_dir = tmp_path / "minimal-repo"
    repo_dir.mkdir()
    (repo_dir / ".git").mkdir()
    return str(repo_dir)


# ---------------------------------------------------------------------------
# CSV custom rules fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def custom_rules_csv(tmp_path: Path) -> str:
    """Create a temporary custom rules CSV file with one rule."""
    csv_file = tmp_path / "custom_rules.csv"
    csv_file.write_text(
        "id,name,description,category,severity,level,check_type,"
        "api_endpoint,field,expected_value,remediation\n"
        "CUSTOM-TEST-01,Test custom rule,A test rule,repo-settings,medium,repository,api,"
        "/repos/{owner}/{repo},has_wiki,false,Disable wiki\n",
        encoding="utf-8",
    )
    return str(csv_file)
