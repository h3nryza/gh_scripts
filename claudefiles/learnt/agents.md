# Learnt: Agents, Skills & Slash Commands

## Agents Used

| Agent | Model | Role | Description |
|-------|-------|------|-------------|
| Architect | Opus | Design | Breaks down requirements into phases, tasks, subtasks. Creates architecture diagrams and decision records. |
| Reporter | Haiku | Reporting | Writes changelog entries, prompt critiques, status updates. Low-cost, fast turnaround. |
| Product Owner | Opus | Validation | Validates requirements, acceptance criteria, edge cases. |
| Sub-agent | Sonnet | Implementation | Builds individual tools, writes tests, creates docs. For complex tasks, Architect breaks down further. |
| Orchestrator | Opus (main) | Coordination | Manages agent lifecycle, tracks dependencies, maintains shared context. |

## Skills Discovered

| Skill | What It Does |
|-------|-------------|
| brainstorming | Explores user intent, requirements and design before implementation |
| writing-plans | Creates multi-step implementation plans from specs |
| test-driven-development | TDD workflow - tests before code |
| verification-before-completion | Runs verification before claiming done |
| dispatching-parallel-agents | Parallelizes independent tasks across agents |
| commit-push-pr | Commit, push, and open a PR |

## Slash Commands

| Command | Purpose |
|---------|---------|
| /commit | Create a git commit |
| /commit-push-pr | Commit, push, and open a PR |
| /simplify | Review changed code for quality |

## Patterns Observed

- Haiku is excellent for low-stakes text generation (changelogs, critiques) - saves tokens
- Opus for architecture decisions - worth the cost for correctness
- Sonnet for implementation - good balance of speed and quality
- Parallel agent dispatch for independent tasks cuts wall-clock time significantly
