#!/usr/bin/env python3
"""Generic hook logger: reads the hook payload from stdin and appends it as
one JSON line to logs/events.jsonl.

Usage (wired from .github/hooks/hooks.json):
    python log_event.py <eventName>

Captures the runtime toolchain: for preToolUse/postToolUse the payload carries
toolName + arguments (the commands the subagent actually ran), for
subagentStart it carries agentName/agentDescription/transcriptPath.

Always exits 0 and prints '{}' so the hook never blocks execution (fail-open).
"""
import json
import os
import sys
from datetime import datetime, timezone


def log_dir() -> str:
    return os.environ.get("HOOKS_LOG_DIR", os.path.join(os.getcwd(), "logs"))


def load_context(ldir: str) -> dict:
    path = os.path.join(ldir, "agent_context.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def save_context(ldir: str, ctx: dict) -> None:
    with open(os.path.join(ldir, "agent_context.json"), "w", encoding="utf-8") as fh:
        json.dump(ctx, fh)


def resolve_agent(payload: dict, event: str, field, ldir: str) -> str:
    """Tool events (VS Code) carry no agent field — correlate them with the
    lifecycle events via transcript_path / session_id.

    sessionStart registers the main session; subagentStart registers the
    subagent's transcript/session under its agent_type. Tool events then look
    themselves up by those keys; unmatched events default to 'main'.
    """
    direct = field("agentName", "agent_name", "agent_type")
    keys = [k for k in (field("transcriptPath", "transcript_path"),
                        field("session_id", "sessionId")) if k]
    ev = (event or "").lower()

    if ev in ("sessionstart", "subagentstart"):
        name = direct or ("main" if ev == "sessionstart" else None)
        if name and keys:
            ctx = load_context(ldir)
            for key in keys:
                ctx[key] = name
            save_context(ldir, ctx)
        return name or "main"

    if direct:
        return direct

    ctx = load_context(ldir)
    for key in keys:
        if key in ctx:
            return ctx[key]
    return "main"


def main() -> int:
    event = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {"_raw": "unparseable payload"}

    # Field names differ per surface: CLI docs use camelCase (toolName),
    # the VS Code surface emits snake_case (tool_name) — accept both.
    def field(*names):
        for name in names:
            if payload.get(name) is not None:
                return payload[name]
        return None

    ldir = log_dir()
    os.makedirs(ldir, exist_ok=True)
    event_name = field("hook_event_name") or event

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event_name,
        # Flatten the fields most useful for evals so jq/grep stay trivial.
        "agentName": resolve_agent(payload, event_name, field, ldir),
        "toolName": field("toolName", "tool_name"),
        "transcriptPath": field("transcriptPath", "transcript_path"),
        "payload": payload,
    }

    with open(os.path.join(log_dir(), "events.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    print("{}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
