# apply-1-constructor-D: tanda D, parte 1 (grupo 12 y A4-3)

- Rol: constructor. Fase apply, intento 1, tanda D parte 1: 12.1 ADR-063, 12.2 `docs/servicios/classifier-service.md` (endpoints, tablas y runbook), 12.3 `CLAUDE.md` y `docs/SESSION-LOG.md`, y A4-3 del plan-reviewer (secciones Impact y Knowledge Base Impact de `proposal.md`).
- Ejecutor: subagente nativo Claude Code (familia Anthropic; el mismo de las tandas A y B). Fecha: 04/11/2026, 13:26 a 13:33 (-03:00).
- Revisión: árbol de trabajo sobre `origin/main b32e621`, sin commits. Archivos y sha256 (primeros 16 hex) al cierre:

| Archivo | Estado | sha256 |
|---|---|---|
| `docs/adr/063-estudio-codificacion-ciega.md` | nuevo | `f59e021023b3f7eb` |
| `docs/servicios/classifier-service.md` | modificado (§5, §6, §7 y §12 nueva) | `370155d2c62008e2` |
| `CLAUDE.md` | modificado (2 invariantes, keys de `helpContent`, rutas del web-teacher, 63 ADRs) | `90d43255cfffb45a` |
| `docs/SESSION-LOG.md` | modificado (entrada 2026-11-04 al tope) | `0a5721240eca520c` |
| `openspec/changes/cibse-codificacion-ciega/proposal.md` | modificado SOLO en `## Impact` y `## Knowledge Base Impact` | `c389b33adbd6b5fe` |

Además: evidencia bajo 12.1, 12.2 y 12.3 en `tasks.md` (sin tocar "Estado de orquestación") y esta fila en `LEEME.md`. No se tocó código de classifier-service ni `apps/web-teacher`; `docs/adr/README.md` (índice congelado) sin cambios (`git status` vacío).

## EVIDENCIA

Trabajo de documentación: no hay comportamiento ejecutable nuevo, así que no hubo TDD. Lo que se registra es validación de formato y de contrato, más la ejecución real del runbook.

- **Checks de CI (job `check-docs`)**:
  - 13:26:38 línea de base de `python3 scripts/check-claude-md.py` -> `[OK] 3 claims verificados, 2 skip, sin drift`.
  - 13:31:33, después de los cambios -> `[OK] ADRs numerados: 63`, sin drift.
  - 13:31:39 `python3 scripts/check-vite-seed-sync.py` -> `[OK]`, exit 0.
- **Enlaces del ADR**: verificados con `test -f`. Uno apuntaba a un nombre de archivo inventado por mí (ADR-046) y lo corregí.
- **Runbook (12.2)**, ejecutado 2026-11-04T13:30:44:
  - Los 9 bloques `bash` de la §12 se extrajeron del documento con una expresión regular y se corrieron con `source`, en orden, desde un directorio fuera del repo.
  - Contra quién: classifier-service real (uvicorn `:8008`, base `cibse-test-pg`) y un CTR falso HTTP (`:18007`). Insumos sintéticos con UUIDs inventados.
  - Resultados:
    - membresías listadas;
    - esquema validado;
    - ancla creada;
    - muestra aceptada con el `sha256sum` del archivo;
    - cobertura completa, con la fila sin uso en `ignoradas` y la alerta `fecha`;
    - 3 revisiones;
    - versión congelada y vigente fijada;
    - progreso y 3 exportaciones;
    - revocación de C2.

    Sin errores en el log. Servidores bajados al terminar.
  - Antes de ejecutar corregí una contradicción del propio runbook: decía validar "desde el root del repo" con archivos fuera del repo. Ahora usa `uv run --project "$REPO"`.
- **proposal.md**: la sección `## Aprobación` es byte a byte igual a la copia previa. `openspec validate cibse-codificacion-ciega --strict` -> válido.
- **Afirmaciones sobre el front** (SESSION-LOG y CLAUDE.md), verificadas contra el árbol:
  - sin textos del entrenamiento del piloto en `apps/web-teacher/src`;
  - `InterraterTraining.tsx` borrado;
  - `accesoPanel.ts` presente;
  - 22 keys de `helpContent` y 24 archivos de rutas, contados el 04/11.

## JUICIO

Autor: constructor D. Comparación: los documentos contra el design D1 a D14, el código entregado en las tandas A y B y el pedido del orquestador. Confianza: alta en los endpoints, las tablas y el runbook (ejecutado); media en la variante de producción del runbook (no ejecutada).

- Tareas cerradas: 12.1, 12.2, 12.3 y A4-3. Abiertas del grupo 13 (13.1 smoke y 13.2 revisión final): no son de esta parte.
- **Defectos de código encontrados al documentar**: ninguno.
- **Desactualización previa de `docs/servicios/classifier-service.md`** (fuera del encargo, no la corregí): §3 y §11 dicen `LABELER_VERSION = "1.2.0"`, cuando CLAUDE.md dice `1.3.0`. §9 y §11 listan como abierto el bug de idempotencia de `POST /classify_episode`, que CLAUDE.md da como CERRADO el 2026-05-17. §11 habla de "6 archivos unit". Candidato a DEUDA de documentación, para el primer change que vuelva a tocar ese documento.
- El runbook manda revisar los enunciados uno por uno y no trae un lazo que apruebe todos: un lazo invitaría a aprobar sin leer, que es lo que la revisión obligatoria de D14 quiere evitar.

## SUPOSICIÓN

- No verifiqué el runbook contra el stack completo (ctr-service real, api-gateway con `DEV_TRUST_HEADERS`, `platform-postgres`): el 5432 lo ocupa otro proyecto y `platform-postgres` está detenido. Tampoco verifiqué la variante de producción (gateway + token de Clerk; alta de estudio con cuenta en `CLERK_ADMIN_EMAILS`, tomado del design, no ejecutado).
- La frase "el investigador local no necesita ningún rol especial" vale con `require_gateway_signature` apagado (default local). Con la firma encendida, los `curl` directos al classifier necesitan firma o token de servicio.
- No ejecuté `make test-smoke` ni la suite del web-teacher (no corresponden a esta parte).

## Fuentes leídas

`tasks.md` (12.x y 13.x), `proposal.md` (Impact, KB Impact, Aprobación), `design.md` (de las tandas A y B), `informes/propose-4-plan-reviewer.md` (A4-1, A4-2 y A4-3, por pedido del orquestador), `docs/adr/_template.md`, `docs/adr/062-...md` (formato), `docs/adr/046-...md` (encabezado), `docs/servicios/classifier-service.md` completo, cabecera y fechas de `docs/SESSION-LOG.md`, `CLAUDE.md`, `scripts/check-claude-md.py`, `.github/workflows/ci.yml` (job `check-docs`), `apps/web-teacher/src/utils/helpContent.tsx` (keys) y `apps/web-teacher/src/routes/` (solo listado). Lecciones L-NNN: no existen en el repo.

## Contaminación por informes previos

Usé como fuente mis propios informes de las tandas A y B (meta-esquema y contrato HTTP) y el A4-3 del plan-reviewer, por pedido del orquestador. Contrasté contra el código y contra la ejecución del runbook todo lo que documenté sobre endpoints y comportamiento; no copié conclusiones de otros informes como evidencia.
