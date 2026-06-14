import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOKS_DIR = REPO_ROOT / ".github" / "hooks"

# Make eval_runner (repo root) importable from the tests.
sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def log_dir(tmp_path):
    return tmp_path / "logs"


def run_hook(script: str, payload: dict, log_dir: Path, env_extra: dict | None = None):
    """Pipe a JSON payload into a hook script exactly like the agent runtime
    does (payload on stdin, JSON response on stdout)."""
    import os

    env = os.environ.copy()
    env["HOOKS_LOG_DIR"] = str(log_dir)
    env.update(env_extra or {})
    proc = subprocess.run(
        [sys.executable, str(HOOKS_DIR / script)]
        + (["preToolUse"] if script == "log_event.py" else []),
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
    )
    return proc


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
