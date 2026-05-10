# Prompt Critique and Learning Guide

## Score: 3.5/10

This prompt has ambitious goals and clear intentions, but significant structural and clarity issues prevent effective execution. The combination of spelling errors, unclear specifications, conflicting instructions, and organizational chaos makes it difficult for an LLM to prioritize, scope, or execute reliably.

---

## What You Did Well

1. **Ambitious Vision** - You have a clear end-state goal: build multiple GitHub automation scripts with proper documentation and peer review processes.

2. **Recognition of Complexity** - You identified that this needs orchestration, phase breaking, and agent delegation. That's sophisticated thinking.

3. **Good Intent on Documentation** - You want to capture learning, decision records, and changelogs. This shows maturity.

4. **Specific User Requirements** - The 7 scripts are described with actual use cases (even if confusingly).

5. **Security & Best Practices Focus** - Golden rules include help documentation, testing, and GitHub App support.

---

## Critical Issues Found

1. **Pervasive Spelling Errors** - "acccess", "repoter" (should be "reporter"), "hauku" (should be "Haiku"), "direcory" (should be "directory"), "uupdating", "uuploading", "sscript", "labda" (should be "lambda"), "henrysexlaination" - these accumulate and cause confusion about which terms are intentional.

2. **Inconsistent Agent Names** - "repoter (hauku)" vs "reporter (Haiku)" - which is correct? This ambiguity cascades through the entire prompt.

3. **Circular/Conflicting Instructions** - You ask to run critique on "haiku" (reporter agent) but the reporter agent is supposed to append findings. Is the reporter running critique on itself, or is a separate critique process happening?

4. **Vague Agent Responsibilities** - What exactly does the "Architect" do vs "Product Owner" vs "Orchestrator"? No clear role definitions. Who makes final decisions? Who coordinates?

5. **Missing Core Information** - No GitHub App details provided, no OAuth setup instructions, no mention of which token type (PAT vs App vs OAuth) for which script.

6. **Scope Creep and Mixed Concerns** - Scripts 1-7 mix multiple concerns: backup, migration, monitoring, compliance checking, version tracking. Should these be separate streams or coordinated?

7. **Ambiguous "Golden Rules"** - Rule 3 is unintelligible: "Unless other save it to the direcory is it queries from with a date time stamp and Github_visibility.csv" - what does this mean?

8. **Conflicting Output Locations** - Script output goes to multiple places (local, S3, index.md, Claude files) with no unified strategy. Where is the source of truth?

9. **Unclear Token Optimization Strategy** - You mention SQLite for token savings but don't specify schema, query patterns, or when to query vs cache.

10. **Incomplete Requirements for Each Script** - Scripts lack clarity on:
    - Input validation rules
    - Error handling strategy
    - Rate limiting approach
    - Partial failure handling (what if one org fails?)

11. **Testing Strategy Undefined** - "write mock and unit tests incase needed" - when IS it needed? For which scripts? What test frameworks?

12. **Peer Review Process Unclear** - "2 peers need to review... 1 needs to test" - but you're working with agents. How do agents peer-review each other? What's the workflow?

13. **Mixed Language Specification** - "Use the apropriate language" but don't specify: Python for which? Bash for which? Lambda for which? Creates ambiguity.

14. **Unclear Learning Capture** - "valid patterns or anti valid should be named as such" - what's an "anti valid" pattern? How structured should these be?

15. **Documentation Placement Inconsistency** - Files scattered across: /claudefiles/prompts/, /claudefiles/files/, /claudefiles/learnt/ with unclear hierarchy or purpose.

---

## How to Fix Each Issue

### Issue 1: Pervasive Spelling Errors
**Problematic:** "acccess", "repoter (hauku)", "direcory", "uupdating", "labda", "henrysexlaination"

**Corrected:**
- "acccess" → "access"
- "repoter (hauku)" → "reporter (Haiku)"
- "direcory" → "directory"
- "uupdating" → "updating"
- "labda" → "lambda"
- "henrysexlaination" → "henry_explanation"

**Impact:** Removes 30+ instances of ambiguity that force LLMs to guess your intent.

---

### Issue 2: Inconsistent Agent Names
**Problematic:** Mix of "Architect", "repoter", "product owner", "Sub agents (sonnet6)" with varying capitalization

**Corrected:** Establish clear names at the start:
```
AGENT ROLES:
- Architect (Claude Opus) - Plans phases, tasks, subtasks
- Reporter (Claude Haiku) - Documents findings, critique, learns
- Product Owner (Claude Opus) - Validates requirements, approves scope
- Implementation (Claude Sonnet 3.5) - Executes defined tasks
```

**Impact:** Eliminates confusion about who does what.

---

### Issue 3: Circular Critique Instructions
**Problematic:** "help teach and me and adjust how I prompt by running his though haiku... giving me critical critique"

**Corrected:** Separate concerns into distinct outputs:
```
EACH PROMPT GENERATES:
1. /claudefiles/prompts/rawprompts.md - stores your original prompt
2. /claudefiles/prompts/LearnToPrompts.md - Haiku critiques it
3. Separate agents work on implementation (no self-critique)
4. Final report to user
```

**Impact:** Clear signal flow, no circular dependencies.

---

### Issue 4: Vague Agent Responsibilities
**Problematic:** "Each agent should have enough information and context though to do their piece of work" - what IS their piece? No role matrix.

**Corrected:** Create explicit responsibility matrix:
```
| Role | Input | Output | Decision Authority |
|------|-------|--------|-------------------|
| Architect | Requirements | Phases, tasks, subtasks, dependencies | Technical approach |
| Reporter | Any completed work | Changelog, critique, learnings | Learning capture |
| Product Owner | Implementation status | Approval/rejection, scope adjustments | User intent |
| Implementation | Defined tasks | Code, tests, documentation | Execution details |
```

**Impact:** Agents know exactly what they own.

---

### Issue 5: Missing GitHub Configuration
**Problematic:** No details on: which GitHub App? Which token for which script? OAuth setup steps?

**Corrected:**
```
GITHUB AUTHENTICATION STRATEGY:
- Script 1 (Visibility Check): GitHub App with org:read, repo:read permissions
- Script 2 (Backup): PAT with repo:read, gist:read, user:read scopes
- Script 3 (Migration): GitHub App with admin permissions
- Scripts 4-7: Similar explicit specifications
- All scripts must support: local PAT, GitHub App, GitHub CLI auth
```

**Impact:** No ambiguity on authentication.

---

### Issue 6: Scope Creep Across Scripts
**Problematic:** Scripts mix backup (2), migration (3), monitoring (4), compliance (5-6), versioning (7). Unclear if sequential or parallel.

**Corrected:**
```
SCRIPT GROUPS:
Group A - Foundation (Scripts 1-2): Visibility, backup
Group B - Operations (Script 3): Migration
Group C - Monitoring (Script 4): Change detection
Group D - Compliance (Scripts 5-6): Policy enforcement
Group E - Versioning (Script 7): Release tracking

EXECUTION STRATEGY: Build Group A first (foundation), then Groups B-E in parallel
DEPENDENCIES: Group B depends on Group A outputs
```

**Impact:** Clear execution sequence, parallel work identified.

---

### Issue 7: Unintelligible Golden Rule 3
**Problematic:** "Unless other save it to the direcory is it queries from with a date time stamp and Github_visibility.csv"

**Corrected:**
```
DEFAULT OUTPUT BEHAVIOR:
- Save results to the same directory the script queries from
- Filename format: {script_name}_{timestamp}_{visibility_level}.csv
- Example: github_visibility_20260510_141500_enterprise.csv
- Exception: If user specifies --output-dir, use that location instead
```

**Impact:** Clear, testable requirement.

---

### Issue 8: Conflicting Output Locations
**Problematic:** Script outputs go to "local", "S3", "index.md", various /claudefiles/ subdirectories with no unified strategy.

**Corrected:**
```
OUTPUT STRATEGY:
LOCAL MODE: Save to ./{script_name}/output/{date}/ directory
LAMBDA MODE: Save to S3://{bucket}/{script_name}/output/{date}/
UNIFIED INDEX: /claudefiles/output_index.md lists all outputs with timestamps
DECISION RECORD: /claudefiles/files/decision_records.csv tracks why each format chosen
```

**Impact:** Single source of truth for outputs.

---

### Issue 9: Undefined Token Optimization
**Problematic:** "minimize tokens by saving this in an SQL light store" - but no schema, no query strategy.

**Corrected:**
```
TOKEN OPTIMIZATION STRATEGY:
CACHE LAYER: SQLite database at /claudefiles/cache/context.db
SCHEMA:
  - Tasks table: id, phase, agent, status, context_key, context_value, created_at
  - Query pattern: SELECT context_value WHERE task_id = ? AND key = ?
  - Retention: Keep for current session, archive monthly
USAGE: Agents query cache before requesting full context from user
REFRESH: Update on task completion, agent-to-agent handoff
```

**Impact:** Concrete implementation strategy reduces back-and-forth.

---

### Issue 10: Incomplete Script Requirements
**Problematic:** No specifications for: input validation, error handling, rate limiting, partial failure recovery.

**Corrected:**
```
SCRIPT REQUIREMENTS (for all scripts):
INPUT VALIDATION:
  - Validate GitHub enterprise/org/user names against GitHub API
  - Reject invalid characters, log rejection reason
  - Support --dry-run to preview without making changes

ERROR HANDLING:
  - Retry failed API calls 3x with exponential backoff
  - Log all errors to {script}/logs/{date}.log
  - Partial failures: continue processing other items, report summary

RATE LIMITING:
  - Respect GitHub API rate limits (5000 req/hr for PAT)
  - Implement 100ms delay between API calls
  - Queue requests if approaching limit

PARTIAL FAILURE:
  - Process all targets, report which succeeded/failed
  - Example output: "Processed 50 repos: 48 success, 2 failed"
  - Failed items saved to {script}/failed_{date}.csv for retry
```

**Impact:** Scripts behave predictably under edge cases.

---

### Issue 11: Vague Testing Requirements
**Problematic:** "write mock and unit tests incase needed" - when? for what?

**Corrected:**
```
TESTING STRATEGY:
UNIT TESTS REQUIRED FOR:
  - Script 1 (Visibility): Test CSV parsing, API response mocking
  - Script 2 (Backup): Test structure preservation, index generation
  - Script 3 (Migration): Test dry-run mode, decision recording
  - Scripts 4-7: Similar per-script specifications

MOCK SETUP:
  - Mock GitHub API responses with realistic data
  - Mock S3 for lambda tests
  - Fixtures in /tests/fixtures/ per script

TEST COVERAGE:
  - Minimum 80% coverage for API-critical logic
  - 100% coverage for CSV parsing/output logic
  - All error paths tested

RUN ON:
  - Every commit (pre-commit hook)
  - In PR checks
  - In lambda deployment pipeline
```

**Impact:** Tests become executable requirements, not suggestions.

---

### Issue 12: Unclear Peer Review Process
**Problematic:** "2 peers need to review... 1 needs to test" - how do agents peer-review each other?

**Corrected:**
```
PEER REVIEW WORKFLOW:
IMPLEMENTATION PHASE:
  1. Implementation agent completes task, logs to changelog
  2. Reporter agent reviews code against golden rules
  3. Architect agent validates task completion and dependencies

SIGN-OFF:
  - Reporter: "Critique passed" entry in changelog
  - Architect: "Task dependencies satisfied" in changelog
  - Both logged with timestamp and reasoning

FOR HUMAN REVIEW (user):
  - Before initial deployment: Create PR with all scripts
  - User review checklist: Help text, tests, documentation
  - User sign-off required before merge to main

FOR ONGOING REVIEWS:
  - Monthly: Reporter audits all scripts against golden rules
  - Quarterly: Architect reviews architecture decisions
```

**Impact:** Clear workflow, practical for agent execution.

---

### Issue 13: Unclear Language Specification
**Problematic:** "Use the apropriate language" with no mapping of script to language.

**Corrected:**
```
LANGUAGE SELECTION:
Script 1 (Visibility Check): Python (CSV manipulation, API calls)
Script 2 (Backup): Python (JSON structure handling, git integration)
Script 3 (Migration): Bash (parallelizable repo operations)
Script 4 (Monitoring): Python + Lambda (cron-friendly)
Script 5 (Pipeline Check): Python + Lambda (file pattern matching)
Script 6 (Best Practices Check): Python (complex rule engine, SANS/OWASP/CIS mapping)
Script 7 (Version Tracking): Python + Lambda (lookup service, multi-repo querying)

RATIONALE: Python for data manipulation, Bash for git operations, Lambda for scheduled monitoring
```

**Impact:** No guessing about language choices.

---

### Issue 14: Undefined Learning Capture
**Problematic:** "valid patterns or anti valid should be named as such" - what's an "anti valid" pattern?

**Corrected:**
```
LEARNING CAPTURE FORMAT:
FILE: /claudefiles/learnt/{pattern_name}.md
STRUCTURE:
  - Pattern Name: Clear, descriptive title
  - Category: Valid Pattern | Anti-Pattern | Skill | Agent | Workflow
  - Description: What is it? Why does it matter?
  - Context: Where did we learn this? Which script/task?
  - Example: Concrete code or workflow example
  - When to Use: Specific conditions this applies
  - When NOT to Use: Common mistakes
  - Contributed By: Which agent or human

EXAMPLES:
  - /claudefiles/learnt/github_api_retry_strategy.md (Valid Pattern)
  - /claudefiles/learnt/monolithic_script_mistake.md (Anti-Pattern)
  - /claudefiles/learnt/csv_output_skill.md (Skill)
```

**Impact:** Learning becomes structured, reusable.

---

### Issue 15: Documentation Directory Chaos
**Problematic:** Files scattered: /claudefiles/prompts/, /claudefiles/files/, /claudefiles/learnt/ with unclear purpose.

**Corrected:**
```
DIRECTORY STRUCTURE:
/claudefiles/
  /prompts/
    rawprompts.md - Your original prompts (append-only)
    LearnToPrompts.md - Critique and learning
  /files/
    changelog.md - Append-only execution log
    decision_records.csv - Architecture decisions
    taskflows.md - Mermaid diagrams of workflows
    thinkLikeMe.md - Reasoning and thinking process
  /learnt/
    *.md - Pattern libraries (one per pattern)
  /cache/
    context.db - SQLite context cache
  /output_index.md - Master index of all script outputs

PURPOSE:
- /prompts/ = Meta: How you prompt, learning to improve
- /files/ = Execution: What was done, decisions made, workflows
- /learnt/ = Knowledge: Patterns, skills, agents discovered
- /cache/ = Runtime: Shared context between agents
```

**Impact:** Clear navigation, clear purpose for each file.

---

## Corrected Prompt

Below is how this entire prompt should be structured for an LLM:

```
# GitHub Automation Suite - Complete Specifications

## PROJECT OVERVIEW
Build a suite of 7 independent GitHub automation scripts to manage enterprise visibility,
backup, migration, monitoring, and compliance across GitHub organizations. Each script
runs locally, via Lambda, or via GitHub CLI, with comprehensive documentation and peer
review workflow.

## EXECUTION FRAMEWORK

### Agent Roles (with Model Assignment)
- **Architect** (Claude Opus) - Breaks requirements into phases, tasks, subtasks; owns technical approach
- **Reporter** (Claude Haiku) - Documents findings, captures learning, critiques prompts
- **Product Owner** (Claude Opus) - Validates requirements, approves scope changes
- **Implementation** (Claude Sonnet 3.5) - Executes defined tasks with high quality standards

### Communication Pattern
1. Architect receives requirements → breaks into phases/tasks with dependency graph
2. Implementation teams execute against defined tasks (non-blocking where possible)
3. Completion → logged to Reporter for changelog entry
4. Learning → captured in /claudefiles/learnt/ with pattern name and context
5. Orchestrator (user) reviews changelog and approves progress

### Token Optimization
**SQLite Context Cache**: /claudefiles/cache/context.db
```sql
CREATE TABLE tasks (
  id TEXT PRIMARY KEY,
  phase TEXT,
  agent TEXT,
  status TEXT (pending|in_progress|completed),
  context_key TEXT,
  context_value TEXT,
  created_at TIMESTAMP
);
```
Agents query cache before requesting full context. Updated on task completion.

---

## GOLDEN RULES (NON-NEGOTIABLE)

1. **GitHub Structure Preservation** - When downloading GitHub resources, maintain exact directory hierarchy
2. **Help Documentation** - Every script must have:
   - `-h / --help` output explaining what it does
   - `-i / --interactive` mode for guided setup
   - Usage examples for each feature
   - Written by h3nryza signature
3. **Output Format** - Default: save to query directory with timestamp and visibility level
   - Format: `{script_name}_{YYYYMMDD_HHMMSS}_{visibility}.csv`
   - Override: `--output-dir` parameter
4. **CLI Notation** - Support `-` and `--` flags for all options; documented in help
5. **Timestamping** - All outputs timestamped YYYYMMDD_HHMMSS
6. **Language Selection** - Use appropriate language per script (detailed below)
7. **Python Environment** - For Python scripts: provide venv setup and teardown
8. **Remote Execution** - All scripts must run remotely: curl, GitHub CLI, or GitHub App (no clone required)
9. **Script Organization** - One directory per script containing all related files
10. **Function Naming** - Clear, descriptive, snake_case function names
11. **Code Simplicity** - Follow DDD (Domain-Driven Design) and TFF (Thin, Fast Functions)
12. **Testing** - Unit tests with mocks for API-critical logic (detailed per script below)

---

## OUTPUT DIRECTORY STRUCTURE

```
/claudefiles/
  /prompts/
    rawprompts.md - Original prompt (append-only)
    LearnToPrompts.md - Critique and improvement guide
  /files/
    changelog.md - Append-only execution log with timestamps
    decision_records.csv - Architecture decisions with rationale
    taskflows.md - Mermaid diagrams of workflows and dependencies
    thinkLikeMe.md - Reasoning process for major decisions
    output_index.md - Master index of all script outputs
  /learnt/
    {pattern_name}.md - One file per pattern, skill, or agent learned
  /cache/
    context.db - SQLite cache for agent context
```

---

## GITHUB AUTHENTICATION STRATEGY

All scripts support multiple auth methods:

| Script | Primary Method | Fallback | Minimum Scope |
|--------|----------------|----------|---------------|
| 1 - Visibility | GitHub App | PAT | org:read, repo:read |
| 2 - Backup | PAT | GitHub CLI | repo:read, gist:read, user:read |
| 3 - Migration | GitHub App | PAT | admin permissions required |
| 4 - Monitoring | GitHub App + Lambda | PAT | repo:read, org:read |
| 5 - Pipeline Check | GitHub App + Lambda | PAT | repo:read, org:read |
| 6 - Best Practices | GitHub App + Lambda | PAT | repo:read, org:read |
| 7 - Version Tracking | Lambda service account | PAT | repo:read (external lookups) |

**Implementation**: Each script includes `--auth-type {pat|app|cli}` flag with validation.

---

## SCRIPT SPECIFICATIONS

### Script 1: GitHub Visibility Checker
**Purpose**: Audit visibility (public/private/internal) across enterprise, orgs, users
**Input**: Enterprise name or org name or user, via CLI or CSV file
**Output**: CSV with format `Enterprise, Organization, Owner, Repository, Visibility, LastChecked`
**Features**:
- Query individual entity or bulk import from CSV
- Export results to CSV with timestamp
- Support import/export operations
- Change visibility (public→private, etc.) via CSV upload
**Authentication**: GitHub App preferred, PAT fallback
**Language**: Python
**Testing**: Unit tests for CSV parsing, API mocking for visibility changes

**Help Text Structure**:
```
github-visibility-checker.py -h
  Usage: github-visibility-checker.py [OPTIONS] COMMAND [ARGS]
  Commands:
    check - Check visibility of repos/orgs/users
    update - Bulk update visibility from CSV
    export - Export current visibility state
  Examples:
    ./github-visibility-checker.py check --enterprise myorg
    ./github-visibility-checker.py update --file changes.csv
```

---

### Script 2: GitHub Enterprise Backup
**Purpose**: Backup all enterprise/org/user data while preserving directory structure
**Input**: Target (enterprise, org, or user) via CLI flags
**Output**: Directory structure + index.md + Ent_Org_User_Gist.csv
**Features**:
- Download repos, gists, wikis, issues maintaining structure
- Create index.md with descriptions
- Generate CSV with relationships
- Target individual enterprise, org, or user
- Metadata: creation date, last modified, visibility
**Authentication**: PAT with repo:read, gist:read
**Language**: Python (git operations + JSON structure)
**Testing**: Test structure preservation, index generation, partial failures

**Output Structure**:
```
./backups/
  {enterprise}/
    index.md
    Ent_Org_User_Gist.csv
    {org}/
      {repo}/
      {gist}/
```

---

### Script 3: Repository Migration
**Purpose**: Move repositories between organizations (within same enterprise)
**Input**: CSV with format `SourceOrg, SourceRepo, TargetOrg` + dry-run verification
**Output**: Success/failure report CSV with per-repo status
**Features**:
- Bulk or individual migration
- Dry-run mode to preview changes
- Feedback CSV showing success/failure with reasons
- Requires admin permissions
- Support change-only workflow
**Language**: Bash (parallelizable git operations)
**Testing**: Test dry-run mode, test failure recovery, test admin validation

---

### Script 4: New Repository Monitor
**Purpose**: Detect newly created repos/orgs in enterprise
**Input**: Top-level enterprise, optional OAuth app config
**Output**: Local: report file | Lambda: S3 bucket location
**Features**:
- Enumerate enterprise → org → account → repo
- Identify new vs existing (requires baseline)
- Lambda deployment with cron trigger
- Local venv deployment
**Language**: Python + Lambda runtime
**Testing**: Mock API responses, test baseline comparison

---

### Script 5: Reusable Pipeline Compliance Checker
**Purpose**: Identify repos NOT using organization's reusable pipeline
**Input**: Organization, pipeline file pattern (via CLI or config)
**Output**: Local: report file | Lambda: S3 location
**Features**:
- Scan all repos in org for pipeline files
- Match against expected patterns
- Generate security posture report
- Support custom file patterns
- Installation instructions in henry_explanation.md
**Language**: Python + Lambda
**Testing**: Test pattern matching, test partial org scans

---

### Script 6: GitHub Best Practices Checker
**Purpose**: Comprehensive audit against GitHub, SANS, OWASP, CIS best practices
**Input**: Enterprise/org level + optional custom rule CSV
**Output**: Report with pass/fail per rule, S3 location if Lambda
**Features**:
- Check enterprise settings, org policies, repo configurations
- Include .gitignore standards, branch protection, etc.
- Support custom rules via imported Excel
- Map to SANS/OWASP/CIS benchmarks
- Support multiple input modes: live API, local file state
**Language**: Python (complex rule engine)
**Testing**: Test each benchmark's rules, test custom rule import

**Best Practices Data Location**: Store as CSV with columns: `Category, Benchmark (SANS|OWASP|CIS), Rule, Severity, CheckLogic`

---

### Script 7: Version/Hash Translator
**Purpose**: Convert between release tags and git hashes for version tracking
**Input**: Module/package name + version or hash
**Output**: Translated value, suitable for dashboard display
**Features**:
- Personal function: query single item
- Business function: bulk lookup via Lambda
- Support release → hash (forward) and hash → release (reverse)
- Support Terraform modules, GitHub Actions
- Integrate with internal artifact repositories
- Output: artifact bucket with lookup results
**Language**: Python + Lambda
**Secrets Format**: Provide documentation on expected format in secrets manager
**Testing**: Test forward/reverse translation, test external lookups

---

## COMMON REQUIREMENTS FOR ALL SCRIPTS

### Input Validation
- Validate GitHub entity names against GitHub API (enterprise/org/user existence)
- Reject invalid characters with clear error message
- Support `--dry-run` to preview without making changes
- Log validation failures to {script}/logs/{date}.log

### Error Handling
- Retry failed API calls 3x with exponential backoff (1s, 2s, 4s)
- Log all errors to {script}/logs/{date}.log with full context
- On partial failure: continue processing, report summary
- Example output: "Processed 50 repos: 48 success, 2 failed (see failed.csv)"

### Rate Limiting
- Respect GitHub API rate limits (5000 req/hr for PAT, 15000 for App)
- Implement 100ms delay between consecutive API calls
- Check rate limit status before batch operations
- Queue requests if approaching limit, with user notification

### Partial Failure Recovery
- Process all targets even if some fail
- Save failed items to {script}/failed_{date}.csv
- Report: "X items succeeded, Y items failed, see failed.csv for retry"
- Rerunning script with --retry flag processes only failed items

### CLI Requirements
All scripts support:
```
--help, -h              Show help text with examples
--interactive, -i       Launch guided setup mode
--dry-run               Preview without making changes
--output-dir PATH       Override default output location
--auth-type TYPE        Choose auth method (pat|app|cli)
--retry                 Retry only previously failed items
--verbose, -v           Show detailed operation logs
--version               Show script version
```

### Logging
- Log to {script}/logs/{date}.log
- Include timestamp, level (DEBUG|INFO|WARN|ERROR), message
- Include full context for errors (what failed, why, recovery suggestion)
- Rotate logs monthly

---

## TESTING STRATEGY

### Unit Tests Required For
- **Script 1**: CSV parsing, API mocking, visibility change logic
- **Script 2**: Structure preservation, index generation, metadata handling
- **Script 3**: Dry-run correctness, admin validation, failure handling
- **Scripts 4-7**: Per-script critical logic (see individual specs)

### Test Setup
- Mock GitHub API responses with realistic data
- Fixtures stored in {script}/tests/fixtures/
- Use pytest for Python scripts
- Test coverage minimum: 80% for API logic, 100% for data transformation

### Test Execution
- Run on every commit (pre-commit hook)
- Run in PR checks (GitHub Actions)
- Run before Lambda deployment

---

## DOCUMENTATION REQUIREMENTS

### README Structure (per toolset)
```
# {Script Name}
[One paragraph explaining what it does and why]

## Installation
[How to install locally or deploy to Lambda]

## Quick Start
[Simplest possible example]

## Usage
[All CLI options with examples]

## Authentication
[Which auth methods supported, how to set up]

## Examples
[3-5 real-world usage examples]

## Troubleshooting
[Common issues and solutions]
```

### Remote Execution Documentation
Every README must show:
1. **Curl execution**: `curl -s https://github.com/h3nryza/gh_scripts/raw/main/{script}/run.sh | bash`
2. **GitHub CLI**: `gh repo clone h3nryza/gh_scripts && cd gh_scripts/{script}`
3. **No cloning required**: Documentation prominently states "You do not need to clone this repository"

---

## EXECUTION PHASES

### Phase 1: Foundation (Scripts 1-2)
- Build visibility checker and backup tool
- Establish output format, auth strategy, testing patterns
- Create example of all golden rules

### Phase 2: Operations (Script 3)
- Build migration tool
- Depends on Phase 1 patterns
- First complex state-changing operation

### Phase 3: Monitoring (Script 4)
- Build new repo detector
- Local + Lambda variants
- Cron scheduling patterns

### Phase 4: Compliance (Scripts 5-6)
- Build pipeline checker and best practices auditor
- Most complex rule engine
- Most comprehensive documentation
- Can run in parallel with Phase 3

### Phase 5: Versioning (Script 7)
- Build version translator
- Depends on understanding all other scripts' outputs
- Integration point for dashboards

---

## PEER REVIEW WORKFLOW

### During Implementation
1. Implementation agent completes task, logs summary
2. Reporter agent reviews code against golden rules
3. Architect agent validates task completion against requirements
4. Approval logged to changelog with timestamp

### Before Release
1. User creates PR with all scripts
2. User verifies: help text, tests pass, documentation complete
3. User approves merge to main
4. Changelog entry: "Released to main by user approval"

### Ongoing Reviews
- Monthly: Reporter audits all scripts against golden rules
- Quarterly: Architect reviews architecture decisions
- Results: logged to changelog, issues filed as needed

---

## LEARNING AND KNOWLEDGE CAPTURE

### Pattern Documentation Format
File: /claudefiles/learnt/{pattern_name}.md
```
# Pattern Name

## Category
Valid Pattern | Anti-Pattern | Skill | Agent | Workflow

## Description
What is this pattern? Why does it matter?

## Context
Where did we learn this? Which script/task revealed it?

## Example
Concrete code or workflow example

## When to Use
Specific conditions where this applies

## When NOT to Use
Common mistakes, anti-patterns to avoid

## Related Patterns
Links to related learnings

## Contributed By
Agent or human who discovered this
```

### Changelog Format
Append-only log at /claudefiles/changelog.md
```
# Changelog

## 2026-05-10 14:15 - Task Complete: Script 1 Visibility Checker
Status: COMPLETED
Agent: Implementation (Sonnet)
Summary: Visibility checker complete with CSV export, import, update features
Tests: 12 unit tests passing
Docs: Help text and README complete
Approval: Reporter approved against golden rules
Issue: None

## 2026-05-10 13:45 - Learning: GitHub API Rate Limiting Strategy
Pattern: github_api_rate_limiting_strategy.md
Context: Script 1 development revealed need for robust rate limiting
Details: 100ms delay, pre-check limits, queue requests
```

---

## SUCCESS CRITERIA

- All 7 scripts complete with help text, tests, documentation
- Remote execution works (curl, gh, or app)
- Peer review workflow documented with examples
- Learning captured in /claudefiles/learnt/ with 5+ patterns
- Changelog complete and append-only
- Architecture decisions recorded in decision_records.csv
- README explains why each script matters and how to use it
- All code follows golden rules
- User can run any script without cloning repo
```

---

## Prompting Tips for Next Time

### 1. **Spell-Check is Non-Negotiable for LLMs**
Spelling errors force LLMs to guess your intent. "hauku" could mean Haiku, or something custom. "labda" breaks the mental model. **Action**: Run spell-check before submitting. Even one typo can cascade into confusion across multi-agent workflows.

### 2. **Define Role Boundaries Before Agent Assignment**
Don't say "agents should communicate." Define: Who makes final decisions? Who merges code? Who approves? Create a responsibility matrix showing inputs/outputs per role. **Action**: Add a table showing each agent's inputs, outputs, and authority level.

### 3. **Separate Concerns Into Distinct Sections**
This prompt mixes authentication strategy, script requirements, agent workflow, testing, documentation, and learning all in one flowing text. **Action**: Use clear section headers: OVERVIEW, EXECUTION FRAMEWORK, SPECIFICATIONS, REQUIREMENTS, TESTING, etc. LLMs organize better with visual structure.

### 4. **Make Ambiguous Rules Explicit**
"Golden Rule 3" was unintelligible. Instead of "Unless other save it to..." say exactly: "Files are saved to {directory}/{script_name}_{timestamp}_{level}.csv unless user specifies --output-dir." **Action**: For every requirement, ask: "Can an LLM execute this without asking clarifying questions?" If no, rewrite it.

### 5. **Specify Edge Cases and Failures Upfront**
"What happens if one org fails during migration?" wasn't addressed. This leaves implementation agents guessing. **Action**: Have a section called "Error Handling" under each script that covers: API failures, partial failures, validation errors, rate limiting, timeout behavior.

### 6. **Create a Dependency Graph When Tasks Are Complex**
"Build 7 scripts" feels parallel, but Script 3 depends on Script 1's CSV format, Script 4 depends on Script 2's backup structure. **Action**: Explicitly state "Phase 1 (Scripts 1-2) must complete before Phase 2 (Script 3)" with rationale.

### 7. **Use Examples for Every Abstract Concept**
"Minimal tokens" and "append-only changelog" are clearer with examples. Show: What does a changelog entry look like? What's in the cache? **Action**: Include JSON/CSV/markdown examples of every output format, every log entry, every data structure agents will work with.

---

## Meta-Note on Critique Quality

This critique itself follows the structure you should use:
1. Scored objectively (3.5/10)
2. Praised strengths (ambitious, clear intent)
3. Listed every issue (15 specific problems)
4. Showed problematic text + corrected version
5. Provided fully rewritten prompt as a template
6. Gave actionable tips tied to specific mistakes

Use this same structure to critique future prompts for consistency.
