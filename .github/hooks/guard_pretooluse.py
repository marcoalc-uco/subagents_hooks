#!/usr/bin/env python3
"""preToolUse guard: inspects the tool call BEFORE it runs and denies it when
it matches a dangerous pattern. This is the inline-blocking point for the
MAIN agent (works for subagents too — preToolUse fires for both).

Deny response (VS Code schema):
    {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                            "permissionDecision": "deny",
                            "permissionDecisionReason": "..."}}

'deny' blocks the tool execution outright; the agent sees the reason and can
try a different approach. Disable the guard with HOOKS_GUARD=0.

Every decision (allow/deny) is appended to logs/guard.jsonl.
"""
import json
import os
import re
import sys
from datetime import datetime, timezone

# Patterns that should never run in this demo workspace.
DENY_RULES = [
    ("path-traversal", re.compile(r"\.\./|\.\.\\")),
    ("system-path", re.compile(r"[Cc]:\\Windows|/etc/|/usr/|HKLM:|HKEY_", re.IGNORECASE)),
    ("recursive-delete-outside-sandbox", re.compile(
        r"(rm\s+-rf|Remove-Item\s+(?=[^|;]*-Recurse)(?=[^|;]*-Force))(?![^|;]*sandbox)",
        re.IGNORECASE)),
    ("disk-format", re.compile(r"\bformat\s+[a-z]:|mkfs", re.IGNORECASE)),
]

# Tools whose input we inspect, and the fields holding command/path strings.
INSPECTED_FIELDS = ("command", "filePath", "file_path", "path", "replacements")


def log_dir() -> str:
    return os.environ.get("HOOKS_LOG_DIR", os.path.join(os.getcwd(), "logs"))


def extract_text(tool_input) -> str:
    """Flatten the inspected fields of tool_input into one searchable string."""
    if not isinstance(tool_input, dict):
        return str(tool_input or "")
    parts = []
    for key in INSPECTED_FIELDS:
        value = tool_input.get(key)
        if value is not None:
            parts.append(json.dumps(value) if isinstance(value, (dict, list)) else str(value))
    return " ".join(parts)


def check(tool_name: str, tool_input) -> tuple[str, str] | None:
    """Return (rule, matched_text) for the first deny rule hit, else None."""
    text = extract_text(tool_input)
    if not text:
        return None
    for rule, pattern in DENY_RULES:
        match = pattern.search(text)
        if match:
            return rule, match.group(0)
    return None


def main() -> int:
    if os.environ.get("HOOKS_GUARD", "1") == "0":
        print("{}")
        return 0

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        print("{}")
        return 0

    tool_name = payload.get("tool_name") or payload.get("toolName") or ""
    tool_input = payload.get("tool_input") or payload.get("toolInput")
    hit = check(tool_name, tool_input)

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "toolName": tool_name,
        "decision": "deny" if hit else "allow",
        "rule": hit[0] if hit else None,
        "matched": hit[1] if hit else None,
    }
    os.makedirs(log_dir(), exist_ok=True)
    with open(os.path.join(log_dir(), "guard.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    if hit:
        rule, matched = hit
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"Blocked by guard rule '{rule}' (matched: {matched!r}). "
                    "Stay inside sandbox/ and avoid destructive operations."
                ),
            }
        }))
    else:
        print("{}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
