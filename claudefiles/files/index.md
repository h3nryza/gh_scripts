# Project Index — gh_scripts

## Repository Map

| Path | Type | Description | Context Source |
|------|------|-------------|----------------|
| `gh-visibility-audit/` | Bash Tool | Repo visibility auditor & bulk updater | GitHub REST API (repos endpoint) |
| `gh-backup/` | Bash Tool | Enterprise/Org/User backup tool | GitHub REST + GraphQL API (repos, gists, orgs) |
| `gh-repo-migrator/` | Bash Tool | Cross-org repository migration | GitHub REST API (transfer endpoint) |
| `gh-new-resource-detector/` | Python Tool | New resource detection | GitHub REST + GraphQL API (enterprise, orgs, repos) |
| `gh-pipeline-compliance/` | Python Tool | Pipeline compliance checker | GitHub REST API (contents, search) |
| `gh-best-practices-audit/` | Python Tool | Best practices auditor | GitHub REST API (all settings endpoints) |
| `gh-version-resolver/` | Python Tool | Hash/version resolver | GitHub REST API (tags, releases) |

## Context Gathering Locations

### Where Context is Collected From
| Source | API/Method | Used By |
|--------|-----------|---------|
| Enterprise Settings | `GET /enterprises/{enterprise}` | Scripts 1,2,4,5,6 |
| Enterprise Orgs | `GET /enterprises/{enterprise}/organizations` or GraphQL | Scripts 1,2,4,5,6 |
| Organization Settings | `GET /orgs/{org}` | All scripts |
| Org Repos | `GET /orgs/{org}/repos` | All scripts |
| Repo Settings | `GET /repos/{owner}/{repo}` | Scripts 1,3,5,6,7 |
| Repo Contents | `GET /repos/{owner}/{repo}/contents/{path}` | Scripts 5,6,7 |
| Branch Protection | `GET /repos/{owner}/{repo}/branches/{branch}/protection` | Script 6 |
| Tags/Releases | `GET /repos/{owner}/{repo}/tags` and `/releases` | Script 7 |
| Gists | `GET /users/{user}/gists` | Script 2 |
| User Repos | `GET /users/{user}/repos` | Scripts 1,2 |
| Search API | `GET /search/code` | Scripts 5,7 |
| GitHub App Installations | `GET /app/installations` | All scripts (app auth) |

### Where Context is Saved
| Location | Purpose |
|----------|---------|
| `claudefiles/prompts/` | Raw user prompts and critiques |
| `claudefiles/files/thinkLikeMe.md` | Architecture reasoning with mermaid diagrams |
| `claudefiles/files/taskflows.md` | Task flow diagrams per script |
| `claudefiles/files/decision_records.csv` | Architecture decisions |
| `claudefiles/files/changelog.md` | Append-only changelog |
| `claudefiles/files/valid_patterns.md` | Validated patterns to reuse |
| `claudefiles/files/anti_patterns.md` | Anti-patterns to avoid |
| `claudefiles/learnt/agents.md` | Agent roles, skills, slash commands |
| `CLAUDE.md` | Project config for AI assistants |
| Each tool's `docs/USAGE.md` | Per-tool documentation |
| Each tool's `tests/` | Unit and mock tests |
