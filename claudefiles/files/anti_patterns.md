# Anti-Patterns to Avoid

## Anti-Pattern: Monolithic CLI
Don't combine all 7 tools into one giant CLI. Each tool is independent.
Why: Makes remote execution harder, increases blast radius of changes, harder to test.

## Anti-Pattern: Hardcoded Auth
Don't hardcode PAT tokens or assume GH CLI is always available.
Why: Breaks in CI, Lambda, and remote execution scenarios.

## Anti-Pattern: Flat Output Directory
Don't dump all output files in one directory.
Why: When backing up GitHub, the directory structure must mirror GitHub's hierarchy (enterprise/org/repo).

## Anti-Pattern: Silent Failures
Don't swallow API errors or rate limit responses.
Why: User needs to know what failed, especially in bulk operations across hundreds of repos.

## Anti-Pattern: Full Clone for Backup
Don't `git clone` every repo for backup unless explicitly asked.
Why: API metadata + archive download is faster and uses less disk. Clone only when needed.

## Anti-Pattern: Unbounded API Calls
Don't enumerate all repos without pagination handling and rate limit awareness.
Why: Enterprise accounts can have 10,000+ repos. Will hit rate limits and timeout.
