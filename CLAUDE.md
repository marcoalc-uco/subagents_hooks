# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Demo for evaluating GitHub Copilot custom agents (`.agent.md`) by capturing the runtime toolchain (tools invoked, commands run, subagent lifecycle) via Copilot hooks. Design rationale and the official hook payload reference live in `docs/contexto.md` — read it before changing hook behavior. The full event/interception flow (diagram, payload shapes, gating semantics) is documented in `docs/architecture.md` — keep it in sync when changing hooks.

## Commands

```powershell
# Bootstrap .venv (if missing) + full test suite
.\run_tests.ps1

# Direct (venv already exists)
.venv\Scripts\python -m pytest tests -v

# Single test
.venv\Scripts\python -m pytest tests/test_eval_subagent.py::test_gating_blocks_low_score -v

# Score a transcript manually
.venv\Scripts\python eval_runner.py --transcript <path> --json
```

No lint/build step. Python 3.14, pytest is the only dependency.

```powershell
# Scaffold package (CLI: agent-evals init/add-agent/check)
.venv\Scripts\python -m pip install -e scaffold
.venv\Scripts\python -m pytest tests scaffold/tests -q   # full suite (both)
```

The `scaffold/` package (`agent-evals-scaffold`) ships the hook scripts as templates (`scaffold/src/agent_evals_scaffold/templates/*.tmpl`). **When you change a hook script in `.github/hooks/`, mirror the change into its `.tmpl` counterpart** (templates are verbatim copies except `eval_subagent.py.tmpl`, which has the `$target_agent` placeholder).

## Architecture

Event flow at runtime (Copilot CLI loads hooks from `.github/hooks/hooks.json`, agents from `.github/agents/`):

1. `preToolUse` / `postToolUse` / `sessionStart` / `subagentStart` → `log_event.py` → appends one JSON line per event to `logs/events.jsonl` (flattens `toolName`, `agentName`, `transcriptPath` for easy grep; full payload nested under `payload`).
2. `subagentStop` and `stop` (main agent) → `eval_subagent.py` → reads the transcript at `transcriptPath`, scores it via `eval_runner.evaluate(text, mode=HOOKS_EVAL_MODE)`, appends to `logs/evals.jsonl`. Optionally emits `{"decision":"block","reason":...}` to force a corrective turn (reflexion gating). Each record carries a `verdict`: `pass` | `observed_fail` | `reflexion_block` | `security_quarantine`. **Security and quality are gated differently**: a failed `no_security_violations` check → `security_quarantine` (recorded, never reflexion-blocked — you don't invite a possibly-rogue agent to retry; the breach was already denied inline at `preToolUse`). Only quality failures get the corrective `reflexion_block`. `Stop` events skip the agent-name filter (logged as `agent:"main"`) and never re-block when `stop_hook_active` is true.
3. `preToolUse` also runs `guard_pretooluse.py` (before the logger): deterministic denylist (`DENY_RULES`) that can deny tool execution via `permissionDecision:"deny"` — works for main agent and subagents. Decisions go to `logs/guard.jsonl`; disable with `HOOKS_GUARD=0`.

`eval_runner.py` has two scoring backends, both returning `{"score", "checks"}` over the same 3 gated dimensions (weights in `WEIGHTS`: `stayed_in_scope` 0.34, `did_the_work` 0.33, `no_security_violations` 0.33):
- **Deterministic** (`score_transcript`, default, offline, no deps) — regex rubric.
- **LLM judge** (`judge_transcript`) — local Ollama via `langchain_openai.ChatOpenAI` against the OpenAI-compatible endpoint (`HOOKS_JUDGE_BASE_URL`, default `http://localhost:11434/v1`; model `HOOKS_JUDGE_MODEL`, default `llama3.1`). Few-shot prompted, returns the same shape plus a `rationale`. **Fail-open**: returns `None` if langchain isn't installed or Ollama is down.

`evaluate(text, mode)` selects the backend: `deterministic` | `judge` | `both` (`both` averages the two scores and ANDs the per-check booleans; `judge`/`both` fall back to deterministic if the judge is unavailable). The hook picks the mode via `HOOKS_EVAL_MODE` (default `deterministic`). Import-shared with the hook (`sys.path.insert(0, os.getcwd())` — hooks run from repo root) and also a CLI (`--mode`, `--model`).

`sandbox/` is the playground the `sandbox-runner` agent is confined to; `sandbox/out/` and `logs/` are runtime artifacts (gitignored).

## Hook protocol invariants (from docs/contexto.md — do not break)

- **Fail-open**: hook scripts always exit 0 and print `{}` on stdout, even on malformed payloads. Gating goes through the JSON `decision` field, never exit codes (non-zero is logged and ignored by the runtime, it does not block).
- **`subagentStop` has no `matcher` support** — agent filtering happens inside `eval_subagent.py` via the `HOOKS_TARGET_AGENT` env var (default `sandbox-runner`). Only `subagentStart` supports `matcher` (on `agentName`).
- Hook entries in `hooks.json` carry both `bash` and `powershell` command variants — keep both in sync when editing.
- Env knobs: `HOOKS_LOG_DIR` (log destination, used by tests to redirect to tmp dirs), `HOOKS_GATING=1` + `HOOKS_GATING_THRESHOLD` (default 0.7), `HOOKS_EVAL_MODE` (`deterministic`|`judge`|`both`), `HOOKS_JUDGE_MODEL` / `HOOKS_JUDGE_BASE_URL` (Ollama judge), `HOOKS_SECURITY_HARD_FAIL` (default `1`: security violation → quarantine, no retry).

## Testing pattern

Tests do not import hook scripts — they exercise them exactly like the Copilot runtime does: spawn the script as a subprocess, pipe a JSON payload to stdin, parse the JSON response from stdout (`run_hook()` in `tests/conftest.py`). Keep new hook tests in that style so the stdin/stdout contract stays covered.

<!-- rtk-instructions v2 -->
# RTK (Rust Token Killer) - Token-Optimized Commands

## Golden Rule

**Always prefix commands with `rtk`**. If RTK has a dedicated filter, it uses it. If not, it passes through unchanged. This means RTK is always safe to use.

**Important**: Even in command chains with `&&`, use `rtk`:
```bash
# ❌ Wrong
git add . && git commit -m "msg" && git push

# ✅ Correct
rtk git add . && rtk git commit -m "msg" && rtk git push
```

## RTK Commands by Workflow

### Build & Compile (80-90% savings)
```bash
rtk cargo build         # Cargo build output
rtk cargo check         # Cargo check output
rtk cargo clippy        # Clippy warnings grouped by file (80%)
rtk tsc                 # TypeScript errors grouped by file/code (83%)
rtk lint                # ESLint/Biome violations grouped (84%)
rtk prettier --check    # Files needing format only (70%)
rtk next build          # Next.js build with route metrics (87%)
```

### Test (60-99% savings)
```bash
rtk cargo test          # Cargo test failures only (90%)
rtk go test             # Go test failures only (90%)
rtk jest                # Jest failures only (99.5%)
rtk vitest              # Vitest failures only (99.5%)
rtk playwright test     # Playwright failures only (94%)
rtk pytest              # Python test failures only (90%)
rtk rake test           # Ruby test failures only (90%)
rtk rspec               # RSpec test failures only (60%)
rtk test <cmd>          # Generic test wrapper - failures only
```

### Git (59-80% savings)
```bash
rtk git status          # Compact status
rtk git log             # Compact log (works with all git flags)
rtk git diff            # Compact diff (80%)
rtk git show            # Compact show (80%)
rtk git add             # Ultra-compact confirmations (59%)
rtk git commit          # Ultra-compact confirmations (59%)
rtk git push            # Ultra-compact confirmations
rtk git pull            # Ultra-compact confirmations
rtk git branch          # Compact branch list
rtk git fetch           # Compact fetch
rtk git stash           # Compact stash
rtk git worktree        # Compact worktree
```

Note: Git passthrough works for ALL subcommands, even those not explicitly listed.

### GitHub (26-87% savings)
```bash
rtk gh pr view <num>    # Compact PR view (87%)
rtk gh pr checks        # Compact PR checks (79%)
rtk gh run list         # Compact workflow runs (82%)
rtk gh issue list       # Compact issue list (80%)
rtk gh api              # Compact API responses (26%)
```

### JavaScript/TypeScript Tooling (70-90% savings)
```bash
rtk pnpm list           # Compact dependency tree (70%)
rtk pnpm outdated       # Compact outdated packages (80%)
rtk pnpm install        # Compact install output (90%)
rtk npm run <script>    # Compact npm script output
rtk npx <cmd>           # Compact npx command output
rtk prisma              # Prisma without ASCII art (88%)
```

### Files & Search (60-75% savings)
```bash
rtk ls <path>           # Tree format, compact (65%)
rtk read <file>         # Code reading with filtering (60%)
rtk grep <pattern>      # Search grouped by file (75%)
rtk find <pattern>      # Find grouped by directory (70%)
```

### Analysis & Debug (70-90% savings)
```bash
rtk err <cmd>           # Filter errors only from any command
rtk log <file>          # Deduplicated logs with counts
rtk json <file>         # JSON structure without values
rtk deps                # Dependency overview
rtk env                 # Environment variables compact
rtk summary <cmd>       # Smart summary of command output
rtk diff                # Ultra-compact diffs
```

### Infrastructure (85% savings)
```bash
rtk docker ps           # Compact container list
rtk docker images       # Compact image list
rtk docker logs <c>     # Deduplicated logs
rtk kubectl get         # Compact resource list
rtk kubectl logs        # Deduplicated pod logs
```

### Network (65-70% savings)
```bash
rtk curl <url>          # Compact HTTP responses (70%)
rtk wget <url>          # Compact download output (65%)
```

### Meta Commands
```bash
rtk gain                # View token savings statistics
rtk gain --history      # View command history with savings
rtk discover            # Analyze Claude Code sessions for missed RTK usage
rtk proxy <cmd>         # Run command without filtering (for debugging)
rtk init                # Add RTK instructions to CLAUDE.md
rtk init --global       # Add RTK to ~/.claude/CLAUDE.md
```

## Token Savings Overview

| Category | Commands | Typical Savings |
|----------|----------|-----------------|
| Tests | vitest, playwright, cargo test | 90-99% |
| Build | next, tsc, lint, prettier | 70-87% |
| Git | status, log, diff, add, commit | 59-80% |
| GitHub | gh pr, gh run, gh issue | 26-87% |
| Package Managers | pnpm, npm, npx | 70-90% |
| Files | ls, read, grep, find | 60-75% |
| Infrastructure | docker, kubectl | 85% |
| Network | curl, wget | 65-70% |

Overall average: **60-90% token reduction** on common development operations.
<!-- /rtk-instructions -->