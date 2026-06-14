import json

from conftest import read_jsonl, run_hook


def make_payload(command):
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "run_in_terminal",
        "tool_input": {"command": command},
    }


def get_guard_log(log_dir):
    return read_jsonl(log_dir / "guard.jsonl")


def test_allows_benign_sandbox_command(log_dir):
    proc = run_hook("guard_pretooluse.py", make_payload("python sandbox/scripts/fib.py 10"), log_dir)
    assert json.loads(proc.stdout) == {}
    assert get_guard_log(log_dir)[0]["decision"] == "allow"


def test_denies_path_traversal(log_dir):
    proc = run_hook("guard_pretooluse.py", make_payload("cat ../secrets.txt"), log_dir)
    out = json.loads(proc.stdout)
    hso = out["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"
    assert "path-traversal" in hso["permissionDecisionReason"]
    assert get_guard_log(log_dir)[0]["rule"] == "path-traversal"


def test_denies_system_path(log_dir):
    proc = run_hook("guard_pretooluse.py", make_payload("type C:\\Windows\\System32\\config"), log_dir)
    out = json.loads(proc.stdout)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_denies_recursive_delete_outside_sandbox(log_dir):
    proc = run_hook("guard_pretooluse.py", make_payload("Remove-Item -Recurse -Force src"), log_dir)
    assert json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_allows_recursive_delete_inside_sandbox(log_dir):
    proc = run_hook("guard_pretooluse.py", make_payload("Remove-Item -Recurse -Force sandbox\\out"), log_dir)
    assert json.loads(proc.stdout) == {}


def test_inspects_file_edit_tools(log_dir):
    payload = {
        "tool_name": "create_file",
        "tool_input": {"filePath": "..\\..\\outside\\evil.txt"},
    }
    proc = run_hook("guard_pretooluse.py", payload, log_dir)
    assert json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_guard_disabled_via_env(log_dir):
    proc = run_hook(
        "guard_pretooluse.py", make_payload("cat ../secrets.txt"), log_dir,
        env_extra={"HOOKS_GUARD": "0"},
    )
    assert json.loads(proc.stdout) == {}
    assert get_guard_log(log_dir) == []
