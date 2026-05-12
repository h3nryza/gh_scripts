# Think Like Me - Architecture & Reasoning

> Written by Architect Agent (Opus) | 2026-05-10
> This document captures the full thinking, reasoning, and architectural decisions behind the gh_scripts suite.

---

## 1. Overall System Architecture

```mermaid
graph TB
    subgraph "gh_scripts Repository"
        direction TB

        subgraph "Bash Tools (GH CLI Wrappers)"
            S1["gh-visibility-audit<br/>Check/change repo visibility"]
            S2["gh-backup<br/>Download all repos + gists"]
            S3["gh-repo-migrator<br/>Move repos between orgs"]
        end

        subgraph "Python Tools (Lambda + Local)"
            S4["gh-new-resource-detector<br/>Detect new repos/orgs"]
            S5["gh-pipeline-compliance<br/>Reusable pipeline adoption"]
            S6["gh-best-practices-audit<br/>SANS/OWASP/CIS audit"]
            S7["gh-version-resolver<br/>Hash-to-release converter"]
        end

        subgraph "Shared Infrastructure"
            AUTH["auth/<br/>common auth helpers"]
            LIB["lib/<br/>shared utilities"]
            TESTS["tests/<br/>per-tool test suites"]
        end

        subgraph "Project Files"
            CF["claudefiles/<br/>prompts, files, learnt"]
            README["README.md"]
        end
    end

    USER["User / CI / Lambda"] -->|"curl / gh / local"| S1
    USER -->|"curl / gh / local"| S2
    USER -->|"curl / gh / local"| S3
    USER -->|"curl / gh / local"| S4
    USER -->|"curl / gh / local"| S5
    USER -->|"curl / gh / local"| S6
    USER -->|"curl / gh / local"| S7

    S1 --> AUTH
    S2 --> AUTH
    S3 --> AUTH
    S4 --> AUTH
    S5 --> AUTH
    S6 --> AUTH
    S7 --> AUTH

    S4 -->|"Lambda"| AWS["AWS Lambda + S3"]
    S5 -->|"Lambda"| AWS
    S6 -->|"Lambda"| AWS
    S7 -->|"Lambda"| AWS
```

### Reasoning

The architecture follows the user's explicit request: **7 independent tools, not a monolith**. Each tool is self-contained in its own directory. A user can curl a single script and run it without cloning the repo. The shared `auth/` helpers are minimal -- each tool bundles what it needs.

Why not a single CLI with subcommands? Because:
1. User explicitly said "break these up independently"
2. Different languages (bash vs python) make a unified CLI awkward
3. Remote execution via curl requires standalone scripts
4. Lambda deployment needs self-contained packages

---

## 2. How the 7 Tools Relate

```mermaid
graph LR
    subgraph "Discovery & Inventory"
        S1["gh-visibility-audit<br/>(bash)"]
        S4["gh-new-resource-detector<br/>(python)"]
    end

    subgraph "Compliance & Security"
        S5["gh-pipeline-compliance<br/>(python)"]
        S6["gh-best-practices-audit<br/>(python)"]
    end

    subgraph "Operations"
        S2["gh-backup<br/>(bash)"]
        S3["gh-repo-migrator<br/>(bash)"]
    end

    subgraph "Intelligence"
        S7["gh-version-resolver<br/>(python)"]
    end

    S1 -->|"CSV of repos<br/>feeds into"| S6
    S1 -->|"CSV of repos<br/>feeds into"| S5
    S4 -->|"New repos trigger<br/>audit checks"| S6
    S4 -->|"New repos trigger<br/>pipeline check"| S5
    S1 -->|"Visibility data<br/>informs backup scope"| S2
    S2 -->|"Backed-up repos<br/>may need migration"| S3
    S6 -->|"Pinned versions<br/>need resolution"| S7
    S5 -->|"Pipeline refs<br/>need resolution"| S7

    classDef bash fill:#4a9,stroke:#333,color:#fff
    classDef python fill:#36a,stroke:#333,color:#fff
    class S1,S2,S3 bash
    class S4,S5,S6,S7 python
```

### Data Flow Summary

| From | To | Data | Purpose |
|------|----|------|---------|
| gh-visibility-audit | gh-best-practices-audit | CSV of repos + visibility | Audit only repos with risky visibility |
| gh-visibility-audit | gh-pipeline-compliance | CSV of repos | Check pipeline adoption across estate |
| gh-new-resource-detector | gh-best-practices-audit | New repo list | Auto-audit newly created repos |
| gh-new-resource-detector | gh-pipeline-compliance | New repo list | Check if new repos use reusable pipelines |
| gh-visibility-audit | gh-backup | Repo inventory | Scope what to back up |
| gh-backup | gh-repo-migrator | Backed-up repos | Migrate after backup |
| gh-best-practices-audit | gh-version-resolver | Pinned action hashes | Resolve hashes to versions |
| gh-pipeline-compliance | gh-version-resolver | Pipeline action refs | Resolve versions |

The tools are **loosely coupled** -- they share CSV as an interchange format but have no hard dependencies on each other. Any tool can run standalone.

---

## 3. Authentication Flow

```mermaid
flowchart TD
    START["Script starts"] --> CHECK{"Auth method<br/>specified?"}

    CHECK -->|"--auth gh-cli"| GHCLI["Use gh auth token<br/>(already logged in)"]
    CHECK -->|"--auth pat"| PAT["Read PAT from<br/>env var or --token"]
    CHECK -->|"--auth app"| APP["GitHub App<br/>OAuth flow"]
    CHECK -->|"None specified"| DETECT{"Auto-detect"}

    DETECT -->|"gh auth status OK"| GHCLI
    DETECT -->|"GITHUB_TOKEN set"| PAT
    DETECT -->|"App credentials<br/>present"| APP
    DETECT -->|"Nothing found"| FAIL["Exit with auth<br/>instructions"]

    GHCLI --> VALIDATE["Validate token<br/>GET /user"]
    PAT --> VALIDATE
    APP --> JWT["Generate JWT<br/>from private key"]
    JWT --> INSTALL["Get installation<br/>token"]
    INSTALL --> VALIDATE

    VALIDATE -->|"200 OK"| SCOPES["Check required<br/>scopes/permissions"]
    VALIDATE -->|"401"| FAIL

    SCOPES -->|"Sufficient"| PROCEED["Proceed with<br/>API calls"]
    SCOPES -->|"Insufficient"| WARN["Warn user:<br/>missing scopes"]
    WARN --> PROCEED

    style GHCLI fill:#4a9,stroke:#333,color:#fff
    style PAT fill:#36a,stroke:#333,color:#fff
    style APP fill:#a63,stroke:#333,color:#fff
    style FAIL fill:#a33,stroke:#333,color:#fff
```

### Auth Method Details

**GH CLI (default for bash tools)**
- Simplest path: user already authenticated via `gh auth login`
- Token obtained via `gh auth token`
- Scopes inherited from `gh auth login` session
- Best for: local interactive use, personal repos

**PAT (Personal Access Token)**
- Environment variable `GITHUB_TOKEN` or `--token` flag
- Classic PAT or fine-grained PAT
- Best for: CI/CD, curl-based remote execution, automation

**GitHub App (OAuth App)**
- Requires: App ID, private key, installation ID
- Script generates JWT, exchanges for installation token
- Installation token scoped to specific orgs/repos
- Best for: enterprise, multi-org, least-privilege
- This is the recommended path for scripts 4-7 (Lambda)

### GitHub App Drill-Down Pattern

```mermaid
sequenceDiagram
    participant Script
    participant GH as GitHub API
    participant App as GitHub App

    Note over Script: Has App ID + Private Key
    Script->>App: Generate JWT (RS256, 10min TTL)
    Script->>GH: GET /app/installations
    GH-->>Script: List of installations (orgs)

    loop For each installation
        Script->>GH: POST /app/installations/{id}/access_tokens
        GH-->>Script: Installation token (1hr TTL)

        Note over Script: Now has org-scoped token
        Script->>GH: GET /orgs/{org}/repos
        GH-->>Script: Repos in that org

        Script->>GH: GET /orgs/{org}/members
        GH-->>Script: Members in that org
    end

    Note over Script: Enterprise-level requires<br/>enterprise admin PAT or<br/>GH App with enterprise scope
```

### Mandatory App Installation Issue

The user noted that mandatory installation of their GitHub App is not happening. Key documentation points:

1. **Organization-level installation** can be required by org owners via Settings > Third-party access > Policy
2. **Enterprise-level policy** can mandate app installation across all orgs
3. **The gap**: You cannot force a GitHub App to be installed -- you can only set org policy to require it
4. Recommendation: Use enterprise-level "pre-install" via `PUT /orgs/{org}/installations` with enterprise admin token

---

## 4. Data Flow Per Script

### Script 1: gh-visibility-audit

```mermaid
flowchart LR
    subgraph Inputs
        A1["--enterprise NAME"]
        A2["--org NAME"]
        A3["--user NAME"]
        A4["--import CSV"]
        A5["--visibility public|private|internal"]
    end

    subgraph Processing
        B1["Authenticate"]
        B2["Enumerate repos<br/>at target level"]
        B3["Collect visibility<br/>status for each"]
        B4["If --import:<br/>Apply visibility changes"]
    end

    subgraph Outputs
        C1["YYYYMMDD_HHMMSS_Github_visibility.csv<br/>Ent, Org, User, Repo, Visibility"]
        C2["Console summary"]
        C3["Change log (if import)"]
    end

    A1 --> B1
    A2 --> B1
    A3 --> B1
    A4 --> B4
    A5 --> B4
    B1 --> B2 --> B3 --> C1
    B3 --> C2
    B4 --> C3
```

### Script 2: gh-backup

```mermaid
flowchart LR
    subgraph Inputs
        A1["--enterprise NAME"]
        A2["--org NAME"]
        A3["--user NAME"]
        A4["--include-gists"]
        A5["--output-dir PATH"]
    end

    subgraph Processing
        B1["Authenticate"]
        B2["Enumerate targets"]
        B3["Clone/pull each repo<br/>maintaining structure"]
        B4["Download gists"]
        B5["Generate index.md<br/>with descriptions"]
    end

    subgraph Outputs
        C1["enterprise/<br/>  org/<br/>    user/<br/>      repo/"]
        C2["index.md per level"]
        C3["YYYYMMDD_HHMMSS_Github_backup.csv<br/>Ent, Org, User, Gist"]
    end

    A1 --> B1
    A2 --> B1
    A3 --> B1
    A4 --> B4
    A5 --> C1
    B1 --> B2 --> B3 --> C1
    B3 --> C2
    B4 --> C1
    B2 --> C3
```

### Script 3: gh-repo-migrator

```mermaid
flowchart LR
    subgraph Inputs
        A1["--repo OWNER/REPO"]
        A2["--new-owner ORG"]
        A3["--import CSV<br/>(repo, new_owner)"]
    end

    subgraph Processing
        B1["Authenticate"]
        B2["Validate permissions"]
        B3["Query current owners"]
        B4["Transfer repos<br/>via API"]
        B5["Verify transfers"]
    end

    subgraph Outputs
        C1["YYYYMMDD_HHMMSS_Github_migration.csv<br/>Repo, OldOwner, NewOwner, Status"]
        C2["Console progress"]
    end

    A1 --> B1
    A3 --> B1
    A2 --> B4
    B1 --> B2 --> B3 --> B4 --> B5 --> C1
    B4 --> C2
```

### Script 4: gh-new-resource-detector

```mermaid
flowchart LR
    subgraph Inputs
        A1["--enterprise NAME"]
        A2["--since DATETIME"]
        A3["--type repos|orgs|all"]
        A4["--lambda / --local"]
    end

    subgraph Processing
        B1["Authenticate (App)"]
        B2["Enumerate all orgs"]
        B3["List repos/orgs<br/>with created_at"]
        B4["Filter by --since"]
        B5["Compare against<br/>known baseline"]
    end

    subgraph "Output (local)"
        C1["YYYYMMDD_HHMMSS_new_resources.csv"]
    end

    subgraph "Output (lambda)"
        C2["S3://bucket/new_resources.csv"]
    end

    A1 --> B1
    A2 --> B4
    A3 --> B3
    A4 -->|local| C1
    A4 -->|lambda| C2
    B1 --> B2 --> B3 --> B4 --> B5
    B5 -->|local| C1
    B5 -->|lambda| C2
```

### Script 5: gh-pipeline-compliance

```mermaid
flowchart LR
    subgraph Inputs
        A1["--org NAME"]
        A2["--pipeline-pattern REGEX"]
        A3["--reusable-workflow OWNER/REPO"]
        A4["--lambda / --local"]
    end

    subgraph Processing
        B1["Authenticate"]
        B2["Enumerate repos"]
        B3["Scan .github/workflows/"]
        B4["Check for reusable<br/>workflow references"]
        B5["Score compliance"]
    end

    subgraph "Output (local)"
        C1["YYYYMMDD_HHMMSS_pipeline_compliance.csv"]
    end

    subgraph "Output (lambda)"
        C2["S3://bucket/pipeline_compliance.csv"]
    end

    A1 --> B1
    A2 --> B3
    A3 --> B4
    B1 --> B2 --> B3 --> B4 --> B5
    B5 -->|local| C1
    B5 -->|lambda| C2
```

### Script 6: gh-best-practices-audit

```mermaid
flowchart LR
    subgraph Inputs
        A1["--enterprise NAME"]
        A2["--org NAME"]
        A3["--custom-checks FILE.xlsx"]
        A4["--frameworks SANS,OWASP,CIS"]
        A5["--lambda / --local"]
        A6["--local-files PATH"]
    end

    subgraph Processing
        B1["Authenticate"]
        B2["Load benchmark rules<br/>(SANS/OWASP/CIS)"]
        B3["Load custom checks<br/>from spreadsheet"]
        B4["Enumerate targets"]
        B5["Run checks:<br/>- Branch protection<br/>- Signed commits<br/>- .gitignore quality<br/>- Secret scanning<br/>- Dependabot<br/>- Code scanning<br/>- Webhook config<br/>- Org settings<br/>- Enterprise policies"]
        B6["Score and grade"]
    end

    subgraph "Output (local)"
        C1["YYYYMMDD_HHMMSS_best_practices_audit.csv"]
        C2["YYYYMMDD_HHMMSS_best_practices_report.html"]
    end

    subgraph "Output (lambda)"
        C3["S3://bucket/audit_report/"]
    end

    A1 --> B1
    A2 --> B1
    A3 --> B3
    A4 --> B2
    A6 --> B5
    B1 --> B4 --> B5 --> B6
    B2 --> B5
    B3 --> B5
    B6 -->|local| C1
    B6 -->|local| C2
    B6 -->|lambda| C3
```

### Script 7: gh-version-resolver

```mermaid
flowchart LR
    subgraph Inputs
        A1["--hash COMMIT_SHA"]
        A2["--release v1.2.3"]
        A3["--action owner/action"]
        A4["--module terraform/module"]
        A5["--import CSV"]
        A6["--lambda / --local"]
    end

    subgraph Processing
        B1["Authenticate"]
        B2{"Direction?"}
        B3["Forward: release -> hash<br/>GET /repos/{}/git/ref/tags/{}"]
        B4["Reverse: hash -> release<br/>GET /repos/{}/tags then match"]
        B5["Version currency check:<br/>current / M-1 / N-1 / older"]
    end

    subgraph "Output (local)"
        C1["YYYYMMDD_HHMMSS_version_resolution.csv"]
    end

    subgraph "Output (lambda)"
        C2["S3://bucket/version_resolution.csv"]
    end

    A1 --> B2
    A2 --> B2
    A3 --> B1
    A4 --> B1
    A5 --> B1
    B1 --> B2
    B2 -->|"release given"| B3
    B2 -->|"hash given"| B4
    B3 --> B5
    B4 --> B5
    B5 -->|local| C1
    B5 -->|lambda| C2
```

---

## 5. Agent Workflow

```mermaid
sequenceDiagram
    participant User
    participant Arch as Architect (Opus)
    participant PO as Product Owner (Opus)
    participant Sub as Sub-Agent (Sonnet 6)
    participant Rep as Reporter (Haiku)

    User->>Arch: Raw requirements
    Arch->>Arch: Analyze, decompose into<br/>phases, tasks, subtasks
    Arch->>PO: Architecture docs +<br/>task breakdown

    PO->>PO: Prioritize tasks,<br/>define acceptance criteria
    PO->>Sub: Assign task with<br/>full context

    loop For each task
        Sub->>Sub: Implement task
        Sub->>Sub: Write tests (TDD)
        Sub->>Arch: Request review if<br/>complex/uncertain

        alt Simple task
            Sub->>PO: Deliver completed task
        else Complex task
            Sub->>Arch: Request breakdown
            Arch->>Sub: Subtask definitions
            Sub->>PO: Deliver completed task
        end

        PO->>Rep: Log completion to changelog
        Rep->>Rep: Append to changelog.md
    end

    Note over Sub: Peer Review Flow
    Sub->>Sub: Peer 1 reviews code
    Sub->>Sub: Peer 2 reviews code
    Sub->>Sub: Peer 3 runs tests

    PO->>User: PR ready for review
```

### Agent Responsibilities

| Agent | Model | Role | Produces |
|-------|-------|------|----------|
| Architect | Opus | System design, task decomposition, complex decisions | Architecture docs, task breakdowns, decision records |
| Product Owner | Opus | Prioritization, acceptance criteria, coordination | Task assignments, PRs, sprint plans |
| Sub-Agent | Sonnet 6 | Implementation, testing, code review | Code, tests, documentation |
| Reporter | Haiku | Logging, changelog, status updates | changelog.md entries, status summaries |

### Context Sharing Strategy

```mermaid
flowchart TD
    subgraph "Context Store (SQLite)"
        DB["gh_scripts_state.db"]
        T1["phases<br/>id, name, status, order"]
        T2["tasks<br/>id, phase_id, name, status,<br/>agent, context, deps"]
        T3["subtasks<br/>id, task_id, name, status,<br/>agent, output"]
        T4["issues<br/>id, task_id, description,<br/>resolution, timestamp"]
        T5["patterns<br/>id, name, type,<br/>description, timestamp"]
    end

    ARCH["Architect"] -->|"CREATE phases/tasks"| DB
    PO["Product Owner"] -->|"UPDATE status, ASSIGN agent"| DB
    SUB["Sub-Agent"] -->|"QUERY context, UPDATE progress"| DB
    REP["Reporter"] -->|"QUERY completed, APPEND changelog"| DB

    DB --> T1
    DB --> T2
    DB --> T3
    DB --> T4
    DB --> T5
```

Each agent queries the SQLite store for context before starting work. This minimizes tokens -- an agent only pulls the rows it needs rather than reading the entire project state.

---

## 6. Directory Structure

```
gh_scripts/
|-- README.md                           # Project overview, per-tool summary, how-to-run
|-- claudefiles/
|   |-- prompts/
|   |   |-- rawprompts.md               # Raw user prompts (append-only)
|   |-- files/
|   |   |-- thinkLikeMe.md             # This file
|   |   |-- taskflows.md               # Task flow diagrams
|   |   |-- changelog.md               # Append-only changelog
|   |   |-- decision_records.csv       # Architecture decisions
|   |-- learnt/
|       |-- skills.md                   # New skills discovered
|       |-- agents.md                   # Agent configurations
|       |-- patterns.md                 # Valid patterns
|       |-- anti-patterns.md           # Anti-patterns found
|
|-- tools/
|   |-- gh-visibility-audit/
|   |   |-- gh-visibility-audit.sh      # Main script
|   |   |-- lib/
|   |   |   |-- auth.sh                # Auth helpers
|   |   |   |-- csv.sh                 # CSV helpers
|   |   |   |-- help.sh                # Help/usage text
|   |   |   |-- interactive.sh         # Interactive mode
|   |   |-- tests/
|   |   |   |-- test_visibility.sh     # Unit tests
|   |   |   |-- mocks/                 # Mock API responses
|   |   |-- README.md
|   |
|   |-- gh-backup/
|   |   |-- gh-backup.sh
|   |   |-- lib/
|   |   |   |-- auth.sh
|   |   |   |-- clone.sh              # Clone/pull logic
|   |   |   |-- index.sh              # index.md generator
|   |   |   |-- help.sh
|   |   |   |-- interactive.sh
|   |   |-- tests/
|   |   |   |-- test_backup.sh
|   |   |   |-- mocks/
|   |   |-- README.md
|   |
|   |-- gh-repo-migrator/
|   |   |-- gh-repo-migrator.sh
|   |   |-- lib/
|   |   |   |-- auth.sh
|   |   |   |-- transfer.sh           # Transfer logic
|   |   |   |-- help.sh
|   |   |   |-- interactive.sh
|   |   |-- tests/
|   |   |   |-- test_migrator.sh
|   |   |   |-- mocks/
|   |   |-- README.md
|   |
|   |-- gh-new-resource-detector/
|   |   |-- main.py                    # CLI entrypoint
|   |   |-- lambda_handler.py          # Lambda entrypoint
|   |   |-- lib/
|   |   |   |-- auth.py               # Auth helpers
|   |   |   |-- detector.py           # Core detection logic
|   |   |   |-- output.py             # CSV/S3 output
|   |   |   |-- help.py               # Help text
|   |   |   |-- interactive.py        # Interactive mode
|   |   |-- tests/
|   |   |   |-- test_detector.py
|   |   |   |-- conftest.py
|   |   |   |-- mocks/
|   |   |-- requirements.txt
|   |   |-- setup_venv.sh             # Create and activate venv
|   |   |-- teardown_venv.sh          # Deactivate and remove venv
|   |   |-- template.yaml             # SAM/CloudFormation
|   |   |-- README.md
|   |
|   |-- gh-pipeline-compliance/
|   |   |-- main.py
|   |   |-- lambda_handler.py
|   |   |-- lib/
|   |   |   |-- auth.py
|   |   |   |-- scanner.py            # Workflow file scanner
|   |   |   |-- compliance.py         # Compliance scoring
|   |   |   |-- output.py
|   |   |   |-- help.py
|   |   |   |-- interactive.py
|   |   |-- tests/
|   |   |   |-- test_compliance.py
|   |   |   |-- conftest.py
|   |   |   |-- mocks/
|   |   |-- requirements.txt
|   |   |-- setup_venv.sh
|   |   |-- teardown_venv.sh
|   |   |-- template.yaml
|   |   |-- henrysexplanation.md       # How to auto-install
|   |   |-- README.md
|   |
|   |-- gh-best-practices-audit/
|   |   |-- main.py
|   |   |-- lambda_handler.py
|   |   |-- lib/
|   |   |   |-- auth.py
|   |   |   |-- benchmarks/
|   |   |   |   |-- sans.py           # SANS benchmark checks
|   |   |   |   |-- owasp.py          # OWASP benchmark checks
|   |   |   |   |-- cis.py            # CIS benchmark checks
|   |   |   |   |-- custom.py         # Custom checks from spreadsheet
|   |   |   |-- auditor.py            # Core audit engine
|   |   |   |-- scorer.py             # Scoring and grading
|   |   |   |-- output.py
|   |   |   |-- help.py
|   |   |   |-- interactive.py
|   |   |-- tests/
|   |   |   |-- test_auditor.py
|   |   |   |-- test_benchmarks.py
|   |   |   |-- conftest.py
|   |   |   |-- mocks/
|   |   |-- data/
|   |   |   |-- best_practices.yaml   # Default rule definitions
|   |   |   |-- sample_custom.xlsx    # Example custom checks
|   |   |-- requirements.txt
|   |   |-- setup_venv.sh
|   |   |-- teardown_venv.sh
|   |   |-- template.yaml
|   |   |-- README.md
|   |
|   |-- gh-version-resolver/
|       |-- main.py
|       |-- lambda_handler.py
|       |-- lib/
|       |   |-- auth.py
|       |   |-- resolver.py           # Hash <-> version resolution
|       |   |-- currency.py           # Version currency checker
|       |   |-- output.py
|       |   |-- help.py
|       |   |-- interactive.py
|       |-- tests/
|       |   |-- test_resolver.py
|       |   |-- conftest.py
|       |   |-- mocks/
|       |-- requirements.txt
|       |-- setup_venv.sh
|       |-- teardown_venv.sh
|       |-- template.yaml
|       |-- README.md
|
|-- index.md                           # Master index of all tools
```

### Why This Structure

1. **Self-contained directories** (Golden Rule #9): Each tool has everything it needs -- code, tests, mocks, docs, venv scripts. No reaching outside your directory.

2. **No need to clone**: Bash tools can be curled directly. Python tools can be fetched and run with `setup_venv.sh`. The README explains this for each tool.

3. **Consistent patterns**: Every bash tool has `lib/{auth,help,interactive}.sh`. Every python tool has `lib/{auth,help,interactive,output}.py`. Predictable, boring, good.

4. **Tests live next to code**: `tests/` inside each tool directory. Not a top-level test folder. This makes each tool truly independent.

5. **Lambda alongside local**: Python tools have both `main.py` (local CLI) and `lambda_handler.py` (Lambda entrypoint). Same core logic, different wrappers.

---

## 7. Language Choice Rationale

```mermaid
graph TD
    subgraph "Decision: Bash or Python?"
        Q1{"Does it wrap<br/>GH CLI directly?"} -->|Yes| BASH["Bash"]
        Q1 -->|No| Q2{"Does it need<br/>Lambda deployment?"}
        Q2 -->|Yes| PYTHON["Python"]
        Q2 -->|No| Q3{"Complex data<br/>processing?"}
        Q3 -->|Yes| PYTHON
        Q3 -->|No| Q4{"Multiple API<br/>integrations?"}
        Q4 -->|Yes| PYTHON
        Q4 -->|No| BASH
    end

    BASH --> S1["gh-visibility-audit"]
    BASH --> S2["gh-backup"]
    BASH --> S3["gh-repo-migrator"]

    PYTHON --> S4["gh-new-resource-detector"]
    PYTHON --> S5["gh-pipeline-compliance"]
    PYTHON --> S6["gh-best-practices-audit"]
    PYTHON --> S7["gh-version-resolver"]

    style BASH fill:#4a9,stroke:#333,color:#fff
    style PYTHON fill:#36a,stroke:#333,color:#fff
```

| Tool | Language | Rationale |
|------|----------|-----------|
| gh-visibility-audit | Bash | Simple GH CLI wrapper. List repos, read/write visibility. `gh api` does the heavy lifting. |
| gh-backup | Bash | Primarily `git clone` and `gh api` calls. File system operations are natural in bash. |
| gh-repo-migrator | Bash | Simple API calls to transfer repos. CSV parsing is manageable in bash. |
| gh-new-resource-detector | Python | Lambda deployment needed. Date/time comparison logic. Pagination handling. |
| gh-pipeline-compliance | Python | Lambda deployment. YAML parsing of workflow files. Pattern matching. Scoring logic. |
| gh-best-practices-audit | Python | Most complex tool. Multiple benchmark frameworks. Excel parsing. Scoring engine. Lambda. |
| gh-version-resolver | Python | Lambda deployment. Complex version comparison. Semantic versioning. Multiple registries. |

---

## 8. Remote Execution Pattern

The user emphasized: "always allow the user to run this script remotely via curl or GH and not have to clone this."

### Bash Tools (curl-based)

```bash
# Direct execution
curl -sL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/tools/gh-visibility-audit/gh-visibility-audit.sh | bash -s -- --org my-org

# Or via gh
gh repo view h3nryza/gh_scripts --json url -q '.url' | xargs -I {} curl -sL {}/raw/main/tools/gh-visibility-audit/gh-visibility-audit.sh | bash -s -- --org my-org
```

### Python Tools (fetch and run)

```bash
# Fetch, setup venv, run, teardown
curl -sL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/tools/gh-new-resource-detector/setup_venv.sh | bash
curl -sL https://raw.githubusercontent.com/h3nryza/gh_scripts/main/tools/gh-new-resource-detector/main.py -o /tmp/gh-nrd/main.py
# ... fetch lib/ files ...
/tmp/gh-nrd/venv/bin/python /tmp/gh-nrd/main.py --enterprise my-ent
```

For Python tools, we will provide a `run_remote.sh` wrapper that handles the fetch-setup-run-teardown cycle in one command.

---

## 9. Lambda vs Local Decision Matrix

```mermaid
graph TD
    subgraph "Runtime Decision"
        INPUT["User runs tool"] --> MODE{"--lambda flag?"}

        MODE -->|"--lambda"| LAMBDA_PATH["Lambda Path"]
        MODE -->|"--local or default"| LOCAL_PATH["Local Path"]

        LAMBDA_PATH --> L1["Package as ZIP"]
        L1 --> L2["Deploy via SAM/CF"]
        L2 --> L3["Invoke Lambda"]
        L3 --> L4["Output to S3"]
        L4 --> L5["Return S3 URI"]

        LOCAL_PATH --> R1["Run in venv"]
        R1 --> R2["Process locally"]
        R2 --> R3["Output to local CSV"]
        R3 --> R4["Print file path"]
    end
```

| Aspect | Local | Lambda |
|--------|-------|--------|
| Auth | Any (GH CLI, PAT, App) | App or PAT only (no GH CLI) |
| Output | Local CSV file | S3 bucket |
| Scheduling | cron / manual | EventBridge rule |
| Timeout | None | 15 min max |
| Cost | Free | Pay per invocation |
| Best for | Ad-hoc, development | Scheduled monitoring |

---

## 10. CSV Output Standard

All tools produce CSV with a standard header pattern:

```
timestamp,enterprise,org,user,repo,<tool-specific-columns>
```

- **Timestamp**: ISO 8601 format (`2026-05-10T14:30:00Z`)
- **File naming**: `YYYYMMDD_HHMMSS_<tool_name>.csv`
- **Location**: Current working directory (unless `--output-dir` specified)
- **Encoding**: UTF-8
- **Delimiter**: Comma (no tabs, no pipes)

This ensures any tool's output can be used as another tool's input.

---

## 11. CLI Interface Standard

Every tool supports this minimum interface:

```
tool-name [options]

Options:
  -h, --help              Show this help message with examples
  -i, --interactive       Interactive mode (guided questions)
  -v, --verbose           Verbose output
  -q, --quiet             Suppress non-essential output
  --version               Show version
  --auth TYPE             Auth method: gh-cli|pat|app (default: auto-detect)
  --token TOKEN           PAT token (or set GITHUB_TOKEN env var)
  --app-id ID             GitHub App ID
  --app-key FILE          GitHub App private key file
  --output-dir DIR        Output directory (default: current directory)
  --output-format FORMAT  Output format: csv|json (default: csv)
  --enterprise NAME       Target enterprise
  --org NAME              Target organization
  --user NAME             Target user
  --import FILE           Import CSV for batch operations
  --export FILE           Export results to specific file
```

### Interactive Mode Flow

```mermaid
flowchart TD
    START["User runs: tool -i"] --> Q1["What would you like to do?<br/>1. Audit  2. Change  3. Export"]
    Q1 --> Q2["Select scope:<br/>1. Enterprise  2. Org  3. User"]
    Q2 --> Q3["Enter name:"]
    Q3 --> Q4["Auth method:<br/>1. GH CLI  2. PAT  3. App"]
    Q4 --> CONFIRM["Confirm settings<br/>and execute"]
    CONFIRM --> RUN["Execute with<br/>collected parameters"]
```

---

## 12. Testing Strategy

```mermaid
graph TD
    subgraph "Test Pyramid"
        UNIT["Unit Tests<br/>(many, fast, mocked)"]
        INTEG["Integration Tests<br/>(fewer, slower, real API)"]
        E2E["E2E Tests<br/>(minimal, full flow)"]
    end

    UNIT --> MOCK["Mock Layer"]
    MOCK --> M1["Mock GH API responses"]
    MOCK --> M2["Mock file system"]
    MOCK --> M3["Mock S3 (moto)"]

    subgraph "Bash Testing"
        BATS["bats-core framework"]
        BATS --> B1["test_*.sh files"]
        BATS --> B2["Mock gh cli calls"]
    end

    subgraph "Python Testing"
        PYTEST["pytest framework"]
        PYTEST --> P1["test_*.py files"]
        PYTEST --> P2["conftest.py fixtures"]
        PYTEST --> P3["responses/moto mocks"]
    end

    E2E --> INTEG --> UNIT
```

- **Bash tests**: Use [bats-core](https://github.com/bats-core/bats-core). Mock `gh` and `curl` commands with function overrides.
- **Python tests**: Use pytest with `responses` library for HTTP mocking and `moto` for AWS mocking.
- **TDD**: Write tests first. Golden Rule #11.
- **Coverage target**: 80%+ for core logic. Auth and help modules get basic smoke tests.

---

## 13. Key Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| GitHub API rate limiting | 5000 req/hr for PAT, 15000 for App | Implement exponential backoff; use conditional requests; cache responses |
| Enterprise API requires special permissions | Scripts 1,4,6 may fail | Document required scopes; fail gracefully with clear error messages |
| Large orgs with 1000+ repos | Timeouts, memory issues | Pagination with streaming; process in batches; progress indicators |
| Lambda cold starts | Slow first invocation | Use provisioned concurrency for critical tools; keep packages small |
| CSV injection | Security vulnerability | Sanitize cell values; prefix with single quote for formulas |
| Token leakage in logs | Security breach | Never log tokens; mask in verbose output; use env vars |

---

*This document is maintained by the Architect Agent. Updates are logged in changelog.md.*
*Written by h3nryza*
