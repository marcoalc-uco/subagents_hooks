import json

import pytest

from agent_evals_scaffold.cli import main


def test_init_scaffolds_everything(tmp_path, capsys):
    assert main(["init", str(tmp_path), "--target-agent", "my-agent"]) == 0

    hooks = tmp_path / ".github" / "hooks"
    assert (hooks / "hooks.json").exists()
    assert (hooks / "log_event.py").exists()
    assert (hooks / "guard_pretooluse.py").exists()
    assert (tmp_path / "eval_runner.py").exists()
    assert (tmp_path / "sandbox" / "scripts" / "fib.py").exists()
    assert (tmp_path / "tests" / "test_hooks_smoke.py").exists()

    # target agent substituted into the eval hook
    assert '"my-agent"' in (hooks / "eval_subagent.py").read_text(encoding="utf-8")
    # hooks.json valid and fully wired
    config = json.loads((hooks / "hooks.json").read_text(encoding="utf-8"))
    assert set(config["hooks"]) >= {"preToolUse", "postToolUse", "subagentStart", "subagentStop", "stop"}
    # gitignore created
    assert "logs/" in (tmp_path / ".gitignore").read_text(encoding="utf-8")


def test_init_is_idempotent_without_force(tmp_path, capsys):
    main(["init", str(tmp_path)])
    marker = tmp_path / "eval_runner.py"
    marker.write_text("# custom", encoding="utf-8")
    main(["init", str(tmp_path)])
    assert marker.read_text(encoding="utf-8") == "# custom"  # not overwritten

    main(["init", str(tmp_path), "--force"])
    assert marker.read_text(encoding="utf-8") != "# custom"  # overwritten


def test_init_optional_parts(tmp_path):
    main(["init", str(tmp_path), "--no-sandbox", "--no-tests"])
    assert not (tmp_path / "sandbox").exists()
    assert not (tmp_path / "tests").exists()


def test_add_agent_renders_name(tmp_path):
    assert main(["add-agent", "reviewer", str(tmp_path)]) == 0
    content = (tmp_path / ".github" / "agents" / "reviewer.agent.md").read_text(encoding="utf-8")
    assert "name: reviewer" in content
    assert "$agent_name" not in content


def test_add_agent_rogue_variant(tmp_path):
    main(["add-agent", "evil", str(tmp_path), "--rogue"])
    content = (tmp_path / ".github" / "agents" / "evil.agent.md").read_text(encoding="utf-8")
    assert "deliberately faulty" in content


def test_check_passes_on_full_scaffold(tmp_path, capsys):
    main(["init", str(tmp_path)])
    main(["add-agent", "sandbox-runner", str(tmp_path)])
    assert main(["check", str(tmp_path)]) == 0
    assert "OK scaffold complete" in capsys.readouterr().out


def test_check_fails_on_missing_pieces(tmp_path, capsys):
    assert main(["check", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "missing: .github/hooks/hooks.json" in out
    assert "no .github/agents" in out


def test_scaffolded_hooks_actually_run(tmp_path):
    """End-to-end: scaffold + pipe a real payload through the generated guard."""
    import subprocess
    import sys

    main(["init", str(tmp_path)])
    proc = subprocess.run(
        [sys.executable, str(tmp_path / ".github" / "hooks" / "guard_pretooluse.py")],
        input=json.dumps({"tool_name": "run_in_terminal",
                          "tool_input": {"command": "cat ../etc/passwd"}}),
        capture_output=True, text=True,
        env={**__import__("os").environ, "HOOKS_LOG_DIR": str(tmp_path / "logs")},
        cwd=tmp_path,
    )
    assert json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
