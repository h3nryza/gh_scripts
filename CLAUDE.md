# CLAUDE.md

## Project Overview
- Suite of 7 independent GitHub management CLI tools
- Each tool is self-contained in its own directory
- Tools work with GitHub Enterprise, Organizations, and User accounts
- Auth: GH CLI, PAT, GitHub OAuth App

## Repository Structure
```
gh_scripts/
├── gh-visibility-audit/    # Script 1: Repo visibility checker & bulk updater (Bash)
├── gh-backup/              # Script 2: Enterprise/Org/User backup tool (Bash)
├── gh-repo-migrator/       # Script 3: Cross-org repo migration (Bash)
├── gh-new-resource-detector/ # Script 4: New repo/org detection (Python, Lambda+local)
├── gh-pipeline-compliance/ # Script 5: Reusable pipeline adoption checker (Python, Lambda+local)
├── gh-best-practices-audit/ # Script 6: GitHub best practices audit (Python, Lambda+local)
├── gh-version-resolver/    # Script 7: Hash/release version resolver (Python, Lambda+local)
├── claudefiles/            # Project meta: prompts, thinking, learnings
└── README.md
```

## Development Rules
- Every tool must have comprehensive --help with examples
- Every tool must support -i/--interactive mode
- Default output: timestamped CSV in current directory
- All tools must work remotely via curl without cloning
- Python tools must include venv setup/teardown scripts
- TDD: write tests before implementation
- Each tool stamped "written by h3nryza"
- Bash tools: shellcheck clean
- Python tools: ruff/black formatted

## Agent Roles
- Architect (Opus): Breaks down phases, tasks, subtasks
- Reporter (Haiku): Changelog entries, status updates
- Product Owner (Opus): Requirements validation
- Sub-agents (Sonnet): Implementation tasks

## Conventions
- Tool names: kebab-case
- Function names: snake_case, descriptive
- Branch naming: feature/{tool-name}/{description}
- Commits: conventional commits format
