#!/usr/bin/env python3
"""subagentStop hook: scores the finished subagent's transcript and appends
the result to logs/evals.jsonl.

subagentStop has no matcher support, so the target agent is filtered here.

Gating: if HOOKS_GATING=1 and the score is below HOOKS_GATING_THRESHOLD
(default 0.7), the hook emits {"decision": "block", "reason": ...} which
forces the subagent to take another corrective turn (reflexion pattern).
Otherwise it emits '{}' (observational mode, never interferes).
"""
import json
import os
import sys
from datetime import datetime, timezone

# Make eval_runner importable when the hook runs from the repo root.
sys.path.insert(0, os.getcwd())

TARGET_AGENT = os.environ.get("HOOKS_TARGET_AGENT", "sandbox-runner")


def log_dir() -> str:
    return os.environ.get("HOOKS_LOG_DIR", os.path.join(os.getcwd(), "logs"))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        print("{}")
        return 0

    # Accept all surface dialects: camelCase (CLI docs), snake_case, and
    # VS Code's agent_type (SubagentStart/Stop carry agent_id + agent_type).
    agent = (
        payload.get("agentName")
        or payload.get("agent_name")
        or payload.get("agent_type")
    )
    transcript_path = payload.get("transcriptPath") or payload.get("transcript_path")
    event = payload.get("hook_event_name") or payload.get("hookEventName") or "SubagentStop"

    # Stop = MAIN agent finishing. No agent name in the payload — evaluate
    # always (the main loop is what we're gating). SubagentStop keeps the
    # per-agent filter since every subagent fires it.
    is_main_stop = event.lower() == "stop"
    if is_main_stop:
        agent = agent or "main"
    elif agent != TARGET_AGENT:
        print("{}")
        return 0

    from eval_runner import evaluate

    transcript_text = ""
    if transcript_path and os.path.isfile(transcript_path):
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as fh:
            transcript_text = fh.read()

    # HOOKS_EVAL_MODE: deterministic (default, offline) | judge | both.
    # judge/both call the local Ollama judge and fall back to deterministic
    # if it is unavailable (fail-open).
    mode = os.environ.get("HOOKS_EVAL_MODE", "deterministic")
    result = evaluate(transcript_text, mode=mode)

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "agent": agent,
        "transcriptPath": transcript_path,
        "stopReason": payload.get("stopReason"),
        "score": result["score"],
        "checks": result["checks"],
        "mode": result.get("mode", mode),
    }
    if "rationale" in result:
        record["rationale"] = result["rationale"]

    gating = os.environ.get("HOOKS_GATING") == "1"
    threshold = float(os.environ.get("HOOKS_GATING_THRESHOLD", "0.7"))
    # Security violations are NOT a quality problem you reflexion-retry — that
    # would invite a possibly-rogue agent to try again. The real enforcement
    # already happened inline at preToolUse (deny). Here we quarantine: flag it
    # hard and let the run stop, never issue a corrective block. On by default.
    security_hard_fail = os.environ.get("HOOKS_SECURITY_HARD_FAIL", "1") == "1"
    security_ok = bool(result["checks"].get("no_security_violations", True))
    # stop_hook_active means this run is ALREADY a continuation forced by a
    # previous block — never block twice, or the agent loops forever.
    already_blocked = bool(payload.get("stop_hook_active"))

    failed = [name for name, ok in result["checks"].items() if not ok]
    # Quality-only failure = everything below threshold EXCEPT the security check.
    quality_fail = result["score"] < threshold

    output = {}
    if security_hard_fail and not security_ok:
        # Policy breach: quarantine, no retry. Record loudly, do not block.
        record["verdict"] = "security_quarantine"
    elif gating and not already_blocked and quality_fail:
        record["verdict"] = "reflexion_block"
        reason = (
            f"Eval failed (score {result['score']:.2f} < {threshold}). "
            f"Failed checks: {', '.join(failed)}. "
            "Fix the issues and finish again."
        )
        # Emit both output dialects: top-level decision (Copilot CLI
        # subagentStop) and hookSpecificOutput (VS Code Stop/SubagentStop).
        output = {
            "decision": "block",
            "reason": reason,
            "hookSpecificOutput": {
                "hookEventName": event,
                "decision": "block",
                "reason": reason,
            },
        }
    else:
        record["verdict"] = "pass" if not failed else "observed_fail"

    os.makedirs(log_dir(), exist_ok=True)
    with open(os.path.join(log_dir(), "evals.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(json.dumps(output) if output else "{}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
