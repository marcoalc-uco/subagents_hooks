Los detalles del payload de los eventos de subagente en la referencia oficial, que es lo que determina si puedes capturar datos útiles para evals.**Sí, y Copilot expone justo la superficie que necesitas para evals — pero con un matiz de framing importante:** no interceptas el fichero de definición del agente (eso es config estática); interceptas el **ciclo de vida del subagente en runtime** mediante dos eventos de hook. El filtrado es por `agentName` (el nombre que el agente registra), no por la ruta del `.agent.md`.

## Los dos puntos de intercepción

Copilot soporta hooks en dos surfaces (Copilot CLI y cloud agent), con eventos `subagentStart` y `subagentStop`:

| Evento          | Cuándo                          | Control de output                                                                           | Payload clave para evals                                                              |
| --------------- | ------------------------------- | ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| `subagentStart` | antes de que el subagente corra | no puede bloquear la creación, pero `additionalContext` se antepone al prompt del subagente | `agentName`, `agentDescription`, `transcriptPath` — soporta `matcher` por `agentName` |
| `subagentStop`  | al completar el subagente       | `decision:"block"` fuerza otra vuelta usando `reason` como prompt; `"allow"` acepta         | `agentName`, `transcriptPath`, `stopReason` — sin matcher (filtras en el script)      |

**La clave para evals es `transcriptPath`.** El payload no trae el output inline, pero sí un **puntero al transcript completo del subagente** en disco: tu hook lo lee y lo scorea. (Alternativa: `postToolUse` filtrado a `toolName == "task"` —la tool con la que se ejecutan los subagentes— te da el resultado final vía `toolResult.textResultForLlm`; menos rico que el transcript, solo la respuesta).

## Tres patrones según el objetivo

1. **Eval observacional** (capturar + scorear offline): `subagentStop` → lee `transcriptPath` → append a `evals.jsonl`. No interfiere con la ejecución.
2. **Eval-in-the-loop / gating**: `subagentStop` → si el score falla, devuelve `{"decision":"block","reason":"..."}` para forzar corrección (patrón _reflexion_). Ojo: _fuerza continuación_, no rechaza limpio.
3. **Inyección de rúbrica / canary**: `subagentStart` con `matcher:"<agentName>"` → `additionalContext` para inyectar criterios o un canary en el prompt del subagente objetivo.

## Esqueleto

```json
// .github/hooks/evals.json
{
  "version": 1,
  "hooks": {
    "subagentStop": [
      {
        "type": "command",
        "bash": "./.github/hooks/eval-subagent.sh",
        "timeoutSec": 60
      }
    ]
  }
}
```

```bash
#!/usr/bin/env bash
payload=$(cat)                                        # payload por stdin
agent=$(jq -r '.agentName'      <<<"$payload")
transcript=$(jq -r '.transcriptPath' <<<"$payload")

# subagentStop NO soporta matcher → filtras el agente objetivo aquí
[[ "$agent" != "security-reviewer" ]] && { echo '{}'; exit 0; }

# scorea: regla determinista o judge model vía API/MCP
score=$(python eval_runner.py --transcript "$transcript" --agent "$agent")
echo "{\"agent\":\"$agent\",\"score\":$score}" >> evals.jsonl

# gating opcional
awk "BEGIN{exit !($score < 0.7)}" \
  && echo '{"decision":"block","reason":"Eval failed: corrige X y reintenta"}' \
  || echo '{}'
```

## Caveats / best practices

- **`subagentStop` no tiene `matcher`** (solo `subagentStart` lo soporta sobre `agentName`) → filtras dentro del script.
- **El hook es determinista** (`command`), pero el script _puede_ llamar a un judge model por API/MCP → tienes **LLM-as-judge** sin romper el modelo de hooks.
- **Cloud agent**: el filesystem es efímero; logs, CSVs y transcripts escritos por hooks se descartan al terminar el job — para retenerlos hay que enviarlos vía un hook `http`, y la red de salida está restringida por firewall: solo hosts de GitHub/Copilot por defecto, cualquier otro requiere regla de admin. En **CLI local** escribes a disco sin restricción.
- **Exit codes**: `0` parsea stdout como JSON de salida; otros no-cero son fail-open (se loguean y se omiten, no bloquean). Para gating real usa el JSON `decision`, nunca el exit code.
- **Surfaces** (relevante porque trabajas en VS Code): CLI = todos los eventos · cloud agent = los subagent events disparan pero en sandbox non-interactive · VS Code = preview de 8 eventos.

**Para evals sistemáticos a escala**, complementa con **OpenTelemetry** (el Copilot SDK expone observabilidad OTel con spans de subagente): hooks = captura inline + gating en el loop; OTel = trazas estructuradas para agregación y análisis offline.

¿Te armo el `eval_runner.py` (rúbrica determinista + judge opcional) o el setup de cloud agent con exfiltración `http`?
