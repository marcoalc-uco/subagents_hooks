"""agent-evals CLI: scaffold runtime hooks + evals onto a repo with Copilot
custom agents.

Commands:
    agent-evals init [path]        scaffold .github/hooks/ + eval_runner + sandbox
    agent-evals add-agent NAME     scaffold a .github/agents/NAME.agent.md
    agent-evals check [path]       validate an existing scaffold

Templates are the battle-tested scripts from the subagents_hooks demo:
cross-surface payload dialects (CLI camelCase / VS Code snake_case /
agent_type), agent correlation via transcript_path, preToolUse guard with
permissionDecision deny, and Stop/subagentStop gating with stop_hook_active
loop protection.
"""
import argparse
import json
import sys
from importlib.resources import files
from pathlib import Path
from string import Template

TEMPLATES = files("agent_evals_scaffold") / "templates"

# (template name, destination relative to target, needs substitution)
INIT_FILES = [
    ("hooks.json.tmpl", ".github/hooks/hooks.json", False),
    ("log_event.py.tmpl", ".github/hooks/log_event.py", False),
    ("guard_pretooluse.py.tmpl", ".github/hooks/guard_pretooluse.py", False),
    ("eval_subagent.py.tmpl", ".github/hooks/eval_subagent.py", True),
    ("eval_runner.py.tmpl", "eval_runner.py", False),
]
SANDBOX_FILES = [
    ("fib.py.tmpl", "sandbox/scripts/fib.py", False),
]
TEST_FILES = [
    ("test_hooks_smoke.py.tmpl", "tests/test_hooks_smoke.py", False),
]
GITIGNORE_LINES = ["logs/", "sandbox/out/", "__pycache__/", ".pytest_cache/"]


def render(template_name: str, subs: dict | None = None) -> str:
    text = (TEMPLATES / template_name).read_text(encoding="utf-8")
    if subs:
        text = Template(text).safe_substitute(subs)
    return text


def write_file(dest: Path, content: str, force: bool) -> str:
    if dest.exists() and not force:
        return "skip (exists)"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8", newline="\n")
    return "written"


def ensure_gitignore(target: Path) -> str:
    gi = target / ".gitignore"
    existing = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
    missing = [line for line in GITIGNORE_LINES if line not in existing]
    if not missing:
        return "skip (up to date)"
    gi.write_text("\n".join(existing + missing) + "\n", encoding="utf-8")
    return f"updated (+{len(missing)} entries)"


def cmd_init(args) -> int:
    target = Path(args.path).resolve()
    target.mkdir(parents=True, exist_ok=True)
    subs = {"target_agent": args.target_agent}

    plan = list(INIT_FILES)
    if not args.no_sandbox:
        plan += SANDBOX_FILES
    if not args.no_tests:
        plan += TEST_FILES

    for template_name, rel_dest, needs_subs in plan:
        status = write_file(
            target / rel_dest,
            render(template_name, subs if needs_subs else None),
            args.force,
        )
        print(f"  {rel_dest}: {status}")
    print(f"  .gitignore: {ensure_gitignore(target)}")

    print(f"\nScaffold ready at {target}")
    print(f"  target agent for subagentStop eval: {args.target_agent}")
    print("  next: agent-evals add-agent <name>  |  agent-evals check")
    return 0


def cmd_add_agent(args) -> int:
    target = Path(args.path).resolve()
    template = "rogue.agent.md.tmpl" if args.rogue else "agent.agent.md.tmpl"
    description = args.description or (
        f"Custom agent '{args.name}' confined to sandbox/ so hooks can capture "
        "and evaluate its runtime toolchain."
    )
    dest = target / ".github" / "agents" / f"{args.name}.agent.md"
    status = write_file(
        dest,
        render(template, {"agent_name": args.name, "agent_description": description}),
        args.force,
    )
    print(f"  {dest.relative_to(target)}: {status}")
    return 0


def cmd_check(args) -> int:
    target = Path(args.path).resolve()
    problems = []

    hooks_json = target / ".github" / "hooks" / "hooks.json"
    for _, rel_dest, _ in INIT_FILES:
        if not (target / rel_dest).exists():
            problems.append(f"missing: {rel_dest}")

    if hooks_json.exists():
        try:
            config = json.loads(hooks_json.read_text(encoding="utf-8"))
            for event in ("preToolUse", "subagentStart", "subagentStop", "stop"):
                if event not in config.get("hooks", {}):
                    problems.append(f"hooks.json: event '{event}' not wired")
        except json.JSONDecodeError as exc:
            problems.append(f"hooks.json: invalid JSON ({exc})")

    agents_dir = target / ".github" / "agents"
    agents = sorted(agents_dir.glob("*.agent.md")) if agents_dir.exists() else []
    if not agents:
        problems.append("no .github/agents/*.agent.md found (run: agent-evals add-agent <name>)")

    print(f"check: {target}")
    for agent in agents:
        print(f"  agent: {agent.stem.removesuffix('.agent')}")
    if problems:
        for problem in problems:
            print(f"  FAIL {problem}")
        return 1
    print("  OK scaffold complete")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="agent-evals", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="scaffold hooks + evals into a repo")
    p_init.add_argument("path", nargs="?", default=".")
    p_init.add_argument("--target-agent", default="sandbox-runner",
                        help="agent name filtered by the subagentStop eval (default: sandbox-runner)")
    p_init.add_argument("--no-sandbox", action="store_true", help="skip sandbox/ playground")
    p_init.add_argument("--no-tests", action="store_true", help="skip smoke tests")
    p_init.add_argument("--force", action="store_true", help="overwrite existing files")
    p_init.set_defaults(func=cmd_init)

    p_add = sub.add_parser("add-agent", help="scaffold a custom agent definition")
    p_add.add_argument("name")
    p_add.add_argument("path", nargs="?", default=".")
    p_add.add_argument("--description", default=None)
    p_add.add_argument("--rogue", action="store_true",
                       help="deliberately misbehaving agent to demo eval gating")
    p_add.add_argument("--force", action="store_true")
    p_add.set_defaults(func=cmd_add_agent)

    p_check = sub.add_parser("check", help="validate an existing scaffold")
    p_check.add_argument("path", nargs="?", default=".")
    p_check.set_defaults(func=cmd_check)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
