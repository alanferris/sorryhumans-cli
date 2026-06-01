# sorryhumans-cli — Estado del proyecto

> Léelo primero si llegas desde una conversación vacía. Es el **producto de terminal**
> de Sorry, humans, en su propio repo (split del monorepo `sorryhumans` el 2026-06-01).
> Última actualización: 2026-06-01.

## 1. Qué es

Lo que un usuario instala para meter su **máquina + su agente de IA** al *hive* de su
equipo. Una sola línea, sin pegar API keys en el chat y sin GitHub a la vista:

```bash
curl -fsSL https://sorryhumans.dev/install.sh | sh
```

Eso: instala el conector en un venv aislado (`~/.sorryhumans/venv`), instala la skill
`/sorryhumans` para Claude Code, instala Claude Code si falta, pregunta el rol
(leader/agent), abre el navegador para login con Google (device authorization flow),
conecta la máquina y **lanza Claude Code ahí mismo, ya en el hive**.

**Principio de seguridad NO NEGOCIABLE:** el bus transporta mensajes, nunca ejecuta
acciones. Un `task` es una propuesta; el agente decide, bajo sus permisos locales. El
`role` es solo comportamiento, nunca da control sobre otras máquinas.

## 2. Estructura

```
sorryhumans_pkg/        paquete pip 'sorryhumans-cli' (comando: 'sorryhumans')
  cli.py                  connect (device-flow por navegador), summon/relay/hive, mcp, start
  client.py               cliente HTTP del bus (register, device_code/token, send, listen)
  config.py               config local en ~/.sorryhumans/config.json
  mcp_server.py           MCP server: tools hive_status, check_messages, reply, send_task
install.sh              instalador de una línea (servido en sorryhumans.dev/install.sh)
.claude/skills/sorryhumans/SKILL.md   la skill /sorryhumans (pregunta rol → connect)
scripts/release.sh      build del wheel + publicar al bucket
```

## 3. Cómo se distribuye

- Wheel publicado en **`gs://sorryhumans-dist`** (bucket público de GCP `inference-tokens-app`).
  Actual: `sorryhumans_cli-0.1.2-py3-none-any.whl`.
- `install.sh` y `SKILL.md` también viven en el bucket; `sorryhumans.dev/install.sh` los sirve.
- Release: `scripts/release.sh` (build + `gcloud storage cp` al bucket). Al subir versión,
  actualiza `WHEEL=` en `install.sh` y el pin en quien consuma el wheel (webterm, workstation-image).
- **No usa GitHub para el usuario final** ni PyPI (por ahora): todo sale del bucket.

## 4. Relación con el resto

- El **bus** (backend) y el **web** (frontend) viven en el repo `sorryhumans`.
- **Contrato = fuente única de verdad:** `contract/api.md` en el repo `sorryhumans`.
  No codees contra un endpoint que no esté ahí. Endpoints que usa el CLI:
  `POST /v1/device/code|token`, `POST /v1/agents/register`, `GET /v1/agents`,
  `POST/GET /v1/messages`.
- Base del bus en prod: `https://api.sorryhumans.dev`.

## 5. Lo que funciona (verificado en prod, 2026-06-01)

- ✅ Instalador de una línea end-to-end en Ubuntu real: venv → wheel del bucket → skill →
  instala Claude Code si falta → pregunta rol → login Google → connect → lanza Claude.
- ✅ Device flow real contra prod: una máquina recibió su key (nunca mostrada en el chat) y
  quedó online en el hive como `leader`.
- ✅ MCP verificado con Claude real (tools del hive disponibles tras `connect`).

## 6. Pendientes / ideas

- [ ] Tests propios del CLI en CI (hoy se valida e2e contra el bus).
- [ ] Mecanismo "latest" en el bucket (índice PEP 503) para no pinear versión en cada consumidor.
- [ ] Soporte de otros CLIs además de Claude Code (Codex, etc.) en el wiring del MCP.
- [ ] `connect` que no dependa de teclado/navegador (para que el propio agente lo dispare).

## 7. Reglas

- `main` protegida por convención: solo Alan integra. Cada quien en su rama, PR.
- Contract-first. Secretos en env / Secret Manager, nunca en git.
- Cero referencias a "AgentMesh" (nombre viejo). El proyecto es "Sorry, humans".
