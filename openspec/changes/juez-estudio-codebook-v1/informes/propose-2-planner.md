# Informe: propose-2-planner - juez-estudio-codebook-v1

Autor: role-planner. Ejecutor: Claude Sonnet 5.5, subagente nativo de Claude Code (sin tabla "Role executors" en el proyecto).
Intento: 2 (corrige `propose-1-plan-reviewer.md`). Revisión: worktree `agent-a377c2107a7f2b43a`, rama `feat/juez-estudio-codebook-v1`, HEAD `178c343`; artefactos del change sin commitear. Fecha: 2026-11-06.
No se implementó código de producción, no hubo commits, push, deploy ni acceso a bases de datos. Firewall del estudio respetado: no se abrió contenido, trazas, etiquetas ni veredictos de los 150; `muestra_150.csv` ni siquiera se abrió en esta vuelta.

## EVIDENCIA

- E1 Lectura completa de `informes/propose-1-plan-reviewer.md`, `informes/propose-1-planner.md`, `proposal.md`, `design.md`, `tasks.md`, `specs/*/spec.md`, `informes/LEEME.md` (2026-11-06).
- E2 `rg -n "^(async )?def |^@router|APIRouter|prefix" routes/estudio_trabajo.py` y `routes/estudio.py`: confirma el router (`prefix="/api/v1/interrater/estudios"`, `dependencies=[Depends(require_gateway_auth)]`), `require_membresia(session, user, clave, roles)`, `INVESTIGADOR`/`CODIFICADOR`/`ROLES_ESTUDIO` (`estudio.py:64-66`), `get_ctr_lector`, `evidencia_fija`, `motivo_rechazo`, `investigador_con_estudio_bloqueado`.
- E3 `rg -n "estudio|classifier" apps/api-gateway/.../routes/proxy.py`: `"/api/v1/interrater": settings.classifier_service_url` (línea 64). El prefijo ya está ruteado: no hace falta tocar el `ROUTE_MAP`.
- E4 Lectura de `routes/estudio_trabajo.py` 85-220, 232-310, 855-1010: `traza_ciega` (validaciones previas a `filtrar_traza`), `cargar_muestra` (la muestra se puede RECARGAR si no hay etiquetas y solo verifica contra anclas), `crear_ancla` (patrón de registro con `episode_id` del pedido bajo lock). Lectura de `routes/estudio.py` 142-250 (`require_membresia`, `_prohibido()` con el mismo cuerpo).
- E5 Lectura de `apps/web-teacher/src/views/estudio/TrazaCiega.tsx` 1-300: la UI muestra `#n` y por tipo `turno k` (mensaje_alumno y respuesta_tutor), `código k`, `ejecución k`, `prueba k`, `nota k`, `lectura k`; `copia`/`pegado`/`fin` sin `k`. El docstring dice que esos textos son los que el codificador escribe en sus citas.
- E6 `rg -n "cache|temperature|..." apps/ai-gateway/.../routes/complete.py`: caché por request (líneas 386-433, 503), sin parámetro para desactivarla. `AIGatewayClient.complete` / `CompleteResult(content, model, provider, ..., cache_hit)` en `services/clients.py:20-83`. `CompleteFn` en `regimen_llm.py:598`.
- E7 `rg` de `alembic/versions/20261104_0007_estudio_codificacion.py`: trigger de SENTENCIA `BEFORE TRUNCATE` (líneas ~430-435). `ls docs/adr | tail`: último ADR `063-...` (el nuevo es 064).
- E8 `openspec validate juez-estudio-codebook-v1 --strict --json` (2026-11-06 20:49:49 -03, tras escribir los artefactos): `"valid": true`, 0 issues; `openspec status --change juez-estudio-codebook-v1 --json`: `isComplete: true`, 4 artefactos `done`. Se repitió tras el último ajuste de formato (ver cierre de este informe).
- E9 `rg -c "—"` sobre los artefactos: un único archivo (`tasks.md`, 3 títulos) tenía em dashes; reemplazados. `git status --short`: solo `?? openspec/changes/juez-estudio-codebook-v1/` (ningún archivo versionado modificado).
- No ejecutado: tests, `alembic`, `make check-rls` (no existe código nuevo; prohibido tocar bases).

## Disposición hallazgo por hallazgo

| Hallazgo | Disposición | Dónde quedó resuelto |
|---|---|---|
| B1 gramática de citas | Resuelto en el plan. Gramática con plurales, listas, rangos, `mensaje`=`turno`, `#n`; multi-token exige que todos existan; forma canónica `{tipo,k,n}` + texto original; preflight de gramática contra las citas humanas antes de llamar al modelo; test parametrizado con las 5 citas literales. La equivalencia `mensaje`=`turno` es SUPOSICIÓN, verificada en 3.2 y en el preflight | design D4; spec codificación (citas); tasks 3.2, 4.4 |
| B2 modelo efectivo | Resuelto. Se persiste `CompleteResult.model`/`provider`/`cache_hit`; mock, otro modelo o caché -> estados `modelo_no_pinneado`/`respuesta_de_cache`, no ok; sin tocar ai-gateway; referencia por llamada contra caché (suposición sobre la clave de caché declarada; la defensa real es el chequeo de `cache_hit`) | design D10; spec codificación (modelo); tasks 3.5 |
| B3 vía de acceso | Resuelto como decisión de trabajo (SUPOSICIÓN hasta firma de Juani): endpoint del estudio con membresía de investigador, ítems resueltos por el servidor, sin script directo a la base. **Clasificación reevaluada: CRITICAL**, con implicancias nombradas. Registro en `ROUTE_MAP`: no corresponde (prefijo existente), con test de premisa. Enmienda de dos invariantes de `CLAUDE.md` en KB Impact | proposal (Clasificación, KB); design D2; spec acceso; tasks 5.x, 7.2, 8.x |
| B4 una historia de persistencia | Resuelto. 4 tablas: ítems de calibración, corrida (inserta antes de llamar, cierre único), veredicto (todo estado, por ítem y repetición), config (cita la corrida de prueba y cuenta variantes) | design D8, D9; spec calibración (rastro); tasks 2.x, 4.4 |
| I1 criterio engañoso | Resuelto en el plan, con pregunta para Juani. Ajuste/prueba separados; anclas nunca en el prompt (test); repeticiones sin caché y estabilidad; cobertura de regímenes (incluye evidencia insuficiente); reporte por dimensión y por frontera obligatorio; tope de 3 variantes sobre `prueba`; recomendación 16+3 episodios consensuados fuera de la muestra, elegidos por sorteo con semilla sobre IDs que no estén en `estudio_muestra` (sin abrir la muestra). Umbrales = propuesta | design D6, D8, D11; spec calibración; proposal decisión 3 |
| I2 firewall | Resuelto. Fuente = `estudio_muestra` en la base (columna `episode_id` solamente), no el CSV; fail-closed (sin muestra, vacía, mal tipada, sin candidatos); corre antes del CTR y se repite por lectura; recarga de muestra cubierta; 5 mutantes. El CSV queda para verificación humana por sha y conteo | design D7; spec calibración; tasks 4.1, 8.2 |
| I3 completitud | Resuelto. `evaluar_item` llama `faltantes_cierre` tras `evaluar_pedido`; estado `incompleto`; `regimen` obligatorio en el contrato; `notas`/`confianza`/`es_frontera` en el contrato | design D5; spec codificación; tasks 3.3 |
| I4 misma fuente | Resuelto con ampliación de alcance a aprobar: extracción a `services/estudio_traza.py` y `traza_ciega` llamándola, tests existentes verdes sin editar; casos `evidencia_alterada`, `enunciado_pendiente`, `episodio_inexistente`, CTR caído, `traza_version_distinta`. Alternativa y su costo documentados | design D3; spec acceso; tasks 1.x, 5.4; proposal decisión 4 |
| I5 hash de prompt | Resuelto. `prompt_sha256` (framing + JSON Schema) en corrida, veredicto y config; golden literal del framing; T-002 compara y se niega si difiere | design D9; spec codificación (reproducibilidad); tasks 3.6 |
| I6 migración | Resuelto. `tenant_id` explícito, trigger TRUNCATE, `make check-rls` y `test-rls` en tareas, verificación post-deploy y verificación en runtime (`verificar_esquema_juez`, 503) porque el entrypoint arranca aunque falle `alembic` | design D9, Migration Plan; spec acceso; tasks 2.2-2.4, 8.6 |
| I7 escenarios sin tarea | Resuelto. Test de ceguera del prompt, vigente sin congelar, recalibración con fila nueva | spec codificación; spec calibración; tasks 3.4, 4.5, 5.x |
| I8 baseline | Resuelto. Paso 0 con `uv sync` y baseline unitario e integración registrados antes de tocar código | tasks 0.x, 6.1 |
| M1 `sin_contenido` | Resuelto. Disparador = ningún mensaje del alumno, código, ejecución, prueba o nota; solo copias/pegados va al modelo | design D5; spec codificación; tasks 3.3 |
| M2 test de separación | Resuelto. Test estático sobre `src/` con lista permitida | tasks 5.5 |
| M3 candidatos | Resuelto. Los episodios de calibración extra se registran con etiqueta consensuada; sin etiqueta no entran | design D6 |
| M4 lógica en script | Resuelto. No hay script; la lógica está en servicios importables | design D2, D8 |
| M5 contrato LLM | Resuelto. `feature="estudio_juez"`, `max_tokens=6000`, 2 reintentos solo por infraestructura, 0 ante JSON inválido/truncado | design D10 |
| M6 referencias | Resuelto. `CompleteFn` corregido a `regimen_llm.py`; Protocol propio; L-NNN ausentes (confirmado por el revisor, E18) | design D10; proposal |

Decisiones abiertas explícitas para Juani (proposal "Decisiones pendientes"): (1) vía de acceso y CRITICAL; (2) modelo/proveedor y si el convenio cubre enviar trazas al proveedor; (3) conjunto de calibración, cantidad, quién lo etiqueta y umbrales; (4) autorizar tocar `traza_ciega` en `estudio_trabajo.py`; (5) T-002 como change aparte; (6) operación sin UI.

## JUICIO

- (role-planner, confianza media-alta) Subir a CRITICAL es lo que corresponde por la regla del proyecto: hay endpoints nuevos que usan la cuenta lectora del CTR sobre datos de alumnos y los mandan a un proveedor externo. Lo que lo hace tolerable es que los IDs los decide el servidor, no el pedido.
- (role-planner, confianza media) El diseño creció (4 tablas, un proceso de fondo, una extracción). Cada pieza responde a un hallazgo concreto: rastro de intentos (B4), ítems de calibración (I1/I2 y pedido de Juani), proceso de fondo (una corrida de 48 a 120 llamadas no entra en un request), extracción (I4). Si el revisor ve una pieza evitable, la candidata es el proceso de fondo (alternativa: corridas chicas sincrónicas), a costa de usabilidad.
- (role-planner, confianza media) Los umbrales (85%, 90%, 16+3 ítems, tope de 3 variantes, 3 repeticiones) son propuestas razonables, no derivadas de datos; con 16 ítems los intervalos son anchos. No se vendió el criterio como validación fuerte.
- (role-planner, confianza media) La gramática de citas cubre las 5 citas conocidas y las formas del codebook, pero no vi las trazas de las anclas; el preflight de la primera corrida es la verificación real.

## SUPOSICIÓN

- La vía de acceso (D2) es la recomendada por el orquestador; Juani no firmó.
- `mensaje k` equivale a `turno k` en cómo citaron los humanos (no verificado contra trazas).
- La clave de caché del ai-gateway incluye los mensajes (leído como "por request", no probado contra un gateway real).
- El `esquema_formulario` y las anclas cargadas en la base reflejan el codebook v1 y `anclas_v1.json` (sin acceso a la base).
- `contenido_md` del codebook no incluye ejemplos copiados de las anclas (la tarea 3.4 avisa si una `explicacion_md` aparece contenida).
- `evidencia_fija(episodio)` devuelve las columnas que el ítem de calibración replica (usada con el mismo patrón que `crear_ancla`; no leí su cuerpo).
- Los nombres exactos de los helpers de `estudio_trabajo.py` que se mueven coinciden con los de las líneas leídas; el constructor ajusta si difieren.
- No ejecuté tests ni migraciones; todo comportamiento del juez futuro es diseño, no observación.

## Fuentes leídas

Artefactos del change (todos), informes previos, `routes/estudio_trabajo.py` (85-220, 232-310, 855-1010), `routes/estudio.py` (142-250 y mapa de funciones), `apps/web-teacher/src/views/estudio/TrazaCiega.tsx` (1-300), `apps/ai-gateway/.../routes/complete.py` (rg), `services/clients.py` (rg), `services/regimen_llm.py` (rg), `alembic/.../20261104_0007_...py` (rg), `apps/api-gateway/.../routes/proxy.py` (rg), `main.py` y `config.py` del classifier (rg), `docs/adr` (listado). `CLAUDE.md` global, del proyecto y del repo (contexto). No leí `muestra_150.csv`, `anclas_v1.json` ni el codebook en esta vuelta; usé lo que el revisor citó (E13, E14).

## Contaminación por otros informes

Leí `propose-1-plan-reviewer.md` completo, por encargo: es la autoridad de esta vuelta, y sus hechos de código (E2-E16) los reutilicé; los que cambian el diseño (cobertura del ROUTE_MAP, `cargar_muestra` recargable, UI de localizadores) los reverifiqué con comandos propios (E2-E7). También leí `propose-1-planner.md` (mi intento previo). No consulté informes de otros changes ni Engram. Misma familia de modelo que el revisor (Claude): la independencia es de rol y contexto, no de proveedor.
