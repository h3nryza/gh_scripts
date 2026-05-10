"""
Test fixtures for gh-best-practices-audit.
Written by h3nryza
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def rules_dir():
    """Return the path to the rules directory."""
    return Path(__file__).resolve().parent.parent / "rules"


@pytest.fixture
def mock_client():
    """Create a mock GitHubClient that returns configurable responses."""
    client = MagicMock()
    client.auth_method = "gh"
    client.api_call = MagicMock(return_value=None)
    return client


@pytest.fixture
def sample_org_response():
    """Sample GitHub organization API response."""
    return {
        "login": "test-org",
        "id": 12345,
        "two_factor_requirement_enabled": True,
        "default_repository_permission": "read",
        "members_can_create_repositories": False,
        "members_can_fork_private_repositories": False,
        "members_can_invite_outside_collaborators": False,
        "members_can_create_pages": False,
        "members_can_create_public_packages": False,
        "members_allowed_repository_creation_type": "none",
        "dependency_graph_enabled_for_new_repositories": True,
        "dependabot_alerts_enabled_for_new_repositories": True,
        "dependabot_security_updates_enabled_for_new_repositories": True,
        "secret_scanning_enabled_for_new_repositories": True,
        "code_scanning_default_setup_enabled": True,
        "security_advisories_enabled": True,
    }


@pytest.fixture
def sample_repo_response():
    """Sample GitHub repository API response."""
    return {
        "full_name": "test-org/test-repo",
        "name": "test-repo",
        "default_branch": "main",
        "visibility": "private",
        "has_wiki": False,
        "has_projects": False,
        "archived": False,
        "security_and_analysis": {
            "secret_scanning": {"status": "enabled"},
            "secret_scanning_push_protection": {"status": "enabled"},
        },
    }


@pytest.fixture
def sample_branch_protection_response():
    """Sample GitHub branch protection API response."""
    return {
        "url": "https://api.github.com/repos/test-org/test-repo/branches/main/protection",
        "required_pull_request_reviews": {
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": True,
            "required_approving_review_count": 2,
        },
        "required_status_checks": {
            "strict": True,
            "contexts": ["ci/test"],
        },
        "enforce_admins": {
            "enabled": True,
        },
        "required_linear_history": {
            "enabled": False,
        },
        "allow_force_pushes": {
            "enabled": False,
        },
        "allow_deletions": {
            "enabled": False,
        },
        "required_conversation_resolution": {
            "enabled": True,
        },
    }


@pytest.fixture
def sample_actions_permissions_response():
    """Sample GitHub Actions permissions API response."""
    return {
        "enabled": True,
        "allowed_actions": "selected",
        "selected_actions_url": "https://api.github.com/repos/test-org/test-repo/actions/permissions/selected-actions",
    }


@pytest.fixture
def sample_workflow_permissions_response():
    """Sample GitHub workflow permissions API response."""
    return {
        "default_workflow_permissions": "read",
        "can_approve_pull_request_reviews": False,
    }


@pytest.fixture
def tmp_local_repo(tmp_path):
    """Create a temporary local repository with common files."""
    repo_dir = tmp_path / "test-repo"
    repo_dir.mkdir()
    (repo_dir / ".git").mkdir()
    (repo_dir / ".gitignore").write_text("*.pyc\n__pycache__/\n.env\n")
    (repo_dir / "README.md").write_text("# Test Repo\n")
    (repo_dir / "LICENSE").write_text("MIT License\n")
    (repo_dir / ".github").mkdir()
    (repo_dir / ".github" / "CODEOWNERS").write_text("* @test-org/admins\n")
    return str(repo_dir)


@pytest.fixture
def tmp_local_repo_minimal(tmp_path):
    """Create a temporary local repository with only .git directory."""
    repo_dir = tmp_path / "minimal-repo"
    repo_dir.mkdir()
    (repo_dir / ".git").mkdir()
    return str(repo_dir)


@pytest.fixture
def custom_rules_csv(tmp_path):
    """Create a temporary custom rules CSV file."""
    csv_file = tmp_path / "custom_rules.csv"
    csv_file.write_text(
        "id,name,description,category,severity,level,check_type,api_endpoint,field,expected_value,remediation\n"
        "CUSTOM-TEST-01,Test custom rule,A test rule,repo-settings,medium,repository,api,"
        "/repos/{owner}/{repo},has_wiki,false,Disable wiki\n"
    )
    return str(csv_file)
