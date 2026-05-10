# Valid Patterns

## Pattern: Self-Contained Tool Directories
Each tool has its own directory with all needed files (script, tests, docs, requirements).
Enables independent curl-based remote execution without cloning the whole repo.

## Pattern: Triple Auth Strategy
Support GH CLI (interactive), PAT (automation/CI), and GitHub OAuth App (enterprise).
Covers all user personas: developer, CI pipeline, enterprise admin.

## Pattern: Timestamped CSV Output
Default output format with ISO timestamp prevents overwrites and enables audit trails.
Format: `YYYY-MM-DD_HHMMSS_Github_visibility.csv`

## Pattern: Interactive Fallback
`-i/--interactive` mode asks questions when user doesn't know the CLI flags.
Lowers barrier to entry for new users.

## Pattern: Remote Execution First
Scripts designed to run via `curl | bash` or `gh` without cloning.
Install script handles dependencies automatically.

## Pattern: Venv Sandwich (Python tools)
`setup.sh` creates venv + installs deps, script runs, `teardown.sh` cleans up.
Prevents polluting system Python.
