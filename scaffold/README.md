# agent-evals-scaffold

CLI de scaffolding: aplica hooks + evals en runtime (logging, guard, gating)
sobre cualquier repo con custom agents de Copilot (`.agent.md`).

## Install

```powershell
pip install -e scaffold
```

## Uso

```powershell
agent-evals init [path]                      # scaffolds .github/hooks/ + eval_runner + sandbox + smoke tests
agent-evals init --target-agent my-agent     # agente filtrado por el eval de subagentStop
agent-evals init --no-sandbox --no-tests     # solo hooks
agent-evals add-agent reviewer [path]        # crea .github/agents/reviewer.agent.md
agent-evals add-agent evil --rogue           # variante que dispara el gating (demo)
agent-evals check [path]                     # valida scaffold (exit 1 si incompleto)
```

`init` es idempotente: no pisa ficheros existentes salvo `--force`.

## Qué genera

| Fichero | Rol |
|---|---|
| `.github/hooks/hooks.json` | wiring eventos → scripts (bash + powershell) |
| `.github/hooks/log_event.py` | captura toolchain → `logs/events.jsonl`, correlación de agente vía `transcript_path` |
| `.github/hooks/guard_pretooluse.py` | deny inline de comandos peligrosos (`permissionDecision`) |
| `.github/hooks/eval_subagent.py` | eval + gating en `subagentStop`/`stop` → `logs/evals.jsonl` |
| `eval_runner.py` | rúbrica determinista + LLM-judge (Ollama local) — `evaluate(mode=...)` |
| `sandbox/scripts/fib.py` | playground para el agente |
| `tests/test_hooks_smoke.py` | smoke tests del contrato stdin/stdout |

Knobs runtime: `HOOKS_LOG_DIR`, `HOOKS_TARGET_AGENT`, `HOOKS_GATING=1`,
`HOOKS_GATING_THRESHOLD`, `HOOKS_GUARD=0`, `HOOKS_EVAL_MODE`
(`deterministic`|`judge`|`both`), `HOOKS_JUDGE_MODEL` / `HOOKS_JUDGE_BASE_URL`
(Ollama judge; `pip install langchain-openai` para activarlo),
`HOOKS_SECURITY_HARD_FAIL` (default `1`: violación de seguridad → quarantine sin retry).

Detalle de eventos, payloads e intercepción: `../docs/architecture.md`.
