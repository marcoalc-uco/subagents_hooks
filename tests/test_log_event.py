import json

from conftest import read_jsonl, run_hook


def test_logs_tool_use_payload(log_dir):
    payload = {
        "toolName": "execute",
        "agentName": "sandbox-runner",
        "arguments": {"command": "python sandbox/scripts/fib.py 10"},
    }
    proc = run_hook("log_event.py", payload, log_dir)

    assert proc.returncode == 0
    assert json.loads(proc.stdout) == {}  # fail-open, never blocks

    records = read_jsonl(log_dir / "events.jsonl")
    assert len(records) == 1
    rec = records[0]
    assert rec["event"] == "preToolUse"
    assert rec["toolName"] == "execute"
    assert rec["agentName"] == "sandbox-runner"
    assert rec["payload"]["arguments"]["command"].startswith("python sandbox/")


def test_survives_malformed_payload(log_dir, tmp_path):
    import subprocess
    import sys
    from conftest import HOOKS_DIR, REPO_ROOT
    import os

    env = os.environ.copy()
    env["HOOKS_LOG_DIR"] = str(log_dir)
    proc = subprocess.run(
        [sys.executable, str(HOOKS_DIR / "log_event.py"), "preToolUse"],
        input="not json at all",
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0
    assert json.loads(proc.stdout) == {}
    records = read_jsonl(log_dir / "events.jsonl")
    assert records[0]["payload"]["_raw"] == "unparseable payload"


def test_snake_case_payload_vscode_surface(log_dir):
    # Shape observed live from the VS Code surface (snake_case fields).
    payload = {
        "timestamp": "2026-06-12T22:38:14.707Z",
        "hook_event_name": "PreToolUse",
        "session_id": "4ac50e73",
        "transcript_path": "C:\\Users\\x\\transcripts\\4ac50e73.jsonl",
        "tool_name": "run_in_terminal",
        "tool_input": {"command": "python sandbox/scripts/fib.py 10"},
    }
    proc = run_hook("log_event.py", payload, log_dir)
    assert proc.returncode == 0

    rec = read_jsonl(log_dir / "events.jsonl")[0]
    assert rec["event"] == "PreToolUse"  # hook_event_name wins over argv
    assert rec["toolName"] == "run_in_terminal"
    assert rec["transcriptPath"].endswith("4ac50e73.jsonl")


def test_agent_correlation_via_lifecycle_events(log_dir):
    main_tp = "C:\\transcripts\\main.jsonl"
    sub_tp = "C:\\transcripts\\sub.jsonl"

    # 1. sessionStart registers the main session.
    run_hook("log_event.py", {
        "hook_event_name": "SessionStart",
        "transcript_path": main_tp,
        "session_id": "sess-main",
    }, log_dir)
    # 2. subagentStart registers the subagent's transcript under agent_type.
    run_hook("log_event.py", {
        "hook_event_name": "SubagentStart",
        "agent_type": "sandbox-runner-rogue",
        "transcript_path": sub_tp,
    }, log_dir)
    # 3. Tool events carry no agent field — must resolve via transcript_path.
    run_hook("log_event.py", {
        "hook_event_name": "PreToolUse",
        "tool_name": "run_in_terminal",
        "transcript_path": sub_tp,
    }, log_dir)
    run_hook("log_event.py", {
        "hook_event_name": "PreToolUse",
        "tool_name": "read_file",
        "transcript_path": main_tp,
    }, log_dir)
    # 5. Unknown transcript defaults to main.
    run_hook("log_event.py", {
        "hook_event_name": "PreToolUse",
        "tool_name": "read_file",
        "transcript_path": "C:\\transcripts\\unknown.jsonl",
    }, log_dir)

    agents = [r["agentName"] for r in read_jsonl(log_dir / "events.jsonl")]
    assert agents == ["main", "sandbox-runner-rogue", "sandbox-runner-rogue", "main", "main"]


def test_appends_multiple_events(log_dir):
    for i in range(3):
        run_hook("log_event.py", {"toolName": f"tool-{i}"}, log_dir)
    records = read_jsonl(log_dir / "events.jsonl")
    assert [r["toolName"] for r in records] == ["tool-0", "tool-1", "tool-2"]
