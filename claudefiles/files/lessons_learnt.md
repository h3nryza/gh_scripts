# Lessons Learnt

## Session 2026-05-10

### L1: Parallel Agent Dispatch is Critical for Throughput
- Launching 3-4 independent agents simultaneously cut build time dramatically
- Scripts 1-3 (bash) all built in parallel in ~13 minutes
- Scripts 4-7 (python) launched in parallel next
- Key: agents must be truly independent (different directories, no shared state)

### L2: Haiku is Perfect for Low-Stakes Text Generation
- Prompt critique (LearnToPrompts.md) written by Haiku — fast, cheap, and thorough
- 33KB output with detailed critique and corrected prompt
- Reporter agent role validated: changelogs, status updates, critiques

### L3: Complex Tools Need Opus-Level Agents
- Script 6 (best-practices-audit) assigned to Opus — correct decision
- 79 security rules across CIS/OWASP/SANS benchmarks require domain expertise
- Simpler scripts (1-3) work fine with Sonnet sub-agents

### L4: Gap-Fill Pattern Works Well
- First pass builds core files, second pass fills gaps (tests, docs)
- Avoids overwhelming single agents with too many files
- Pattern: build core → verify → fill gaps → verify again

### L5: Self-Contained Tool Directories Enable True Independence
- Each tool has its own tests, docs, install.sh, requirements
- No cross-tool dependencies means any tool can be run/installed alone
- Enables the curl-based remote execution requirement

### L6: .gitignore Must Be Early in Pipeline
- Python agents create __pycache__ and .pytest_cache during testing
- Need .gitignore before first commit to keep repo clean

### L7: Shellcheck and Pytest Validation During Build
- Agents that run shellcheck/pytest during build catch issues before commit
- Scripts 1-3 all validated clean during build
- Test counts: Script 1 (62 assertions), Script 2 (121 tests), Script 3 (54 tests)

### L8: Auth Abstraction is Reusable
- All 7 tools implement the same 3 auth methods (gh/pat/app)
- Pattern: `auth_method` parameter → auth function → API call wrapper
- Future improvement: extract shared auth module (but violates self-contained principle)
