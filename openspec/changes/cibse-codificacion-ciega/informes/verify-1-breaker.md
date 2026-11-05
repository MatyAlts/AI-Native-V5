# verify-1-breaker: rompedor, intento 1

- Rol: breaker (rompedor). Ejecutor: subagente nativo Claude Code (familia Anthropic, la misma que planner, plan-reviewer y constructores A a E). No hay tabla `## Role executors` en el CLAUDE.md del proyecto; no hay independencia de proveedor respecto de los informes previos.
- Fecha: 04/11/2026, 13:54 a 14:03 (-03:00). Nivel CRITICAL.
- Revisión atacada: árbol de trabajo sobre HEAD `b32e621` (rama `feat/cibse-codificacion-ciega`), sin commits. Huella con `scratchpad/hash-arbol.sh` (excluye `openspec/changes/cibse-codificacion-ciega/`):
  - 13:54:16 `diff_HEAD_sha256=7baa7f619f747ee1058b49a13b20c48bb5e8f237630a71c8a695fd423308ac25 untracked_n=59 untracked_list_sha256=133998efb5c58f40eac4899a0cb1f0c9ec865477d670fa6ae76f2135172a5f34 arbol=159b44f425465551`
  - 14:02:50 idéntica. **La huella no cambió.** Los archivos de prueba temporales se copiaron al árbol, se corrieron y se borraron (`git status` sin restos); sus originales quedan en `scratchpad/breaker/`.
- Lecciones L-NNN: no existen en el repo (declarado por el orquestador; no se repitió la búsqueda). Ruta leída: ninguna.
- No edité código de producción ni corrí mutantes sobre la entrega.

## Veredicto

**FALLAS**: 1 MAYOR y 6 MENOR reproducidas. Ninguna BLOQUEANTE por mi juicio; el auditor decide.

| # | Severidad | Lente | Falla |
|---|---|---|---|
| F1 | MAYOR | integridad / régimen | Editar el esquema de un borrador no revalida sus anclas: se congela un codebook cuyo sha cubre respuestas esperadas que la regla congelada no deriva, o con dimensiones que el esquema ya no tiene |
| F2 | MENOR | bordes | `regimen` o `regimen_propuesto` no hashable (lista u objeto) da 500 en vez de 400 |
| F3 | MENOR | bordes | Esquema con lista donde va una clave de régimen da 500 en vez de 400 |
| F4 | MENOR | bordes / cableado | Cerrar sin muestra cargada: 422 `incompleta` con `faltan: 0`; el panel muestra "Faltan 0 ítems para poder cerrar:" con la lista vacía |
| F5 | MENOR | integridad / docs | `TRUNCATE` vacía historial y respuestas de entrenamiento sin que la base lo rechace (y sin RLS: todos los tenants) |
| F6 | MENOR | bordes | El CTR respondiendo 200 con cuerpo no JSON se escapa como `JSONDecodeError`: la traza da 500, no 502 genérico |
| F7 | MENOR | docs | Referencia circular de la "forma exacta del meta-esquema": ADR-063 manda al runbook y el runbook al ADR y a un informe del change |

## EVIDENCIA

Entorno: Postgres de pruebas `cibse-test-pg` (`127.0.0.1:55432`), `CLASSIFIER_TEST_DB_URL=postgresql+asyncpg://classifier_user:***@127.0.0.1:55432/classifier_db`. No toqué el 5432 (`seguridad_jwt_db`), ni el stack del constructor E en `:55433`/`:6379`, ni producción.

Esquema real del codebook v0: el path del brief (`~/Descargas/CIbSE2027_muestra_150/...`) **no existe**; el archivo está en `/home/juanisarmiento/Documentos/MTAC/CIbSE2027_muestra_150/codebook/esquema_v0.json`, sha256 `e011b5c3db70b852c99a18ed1357649c2c17faf69aeb6935e086a76f32b22ffe`, modificado el 04/11 13:26. Usé ese.

### Corridas propias (conteo independiente: 37 tests distintos)

| Hora | Comando | Resultado |
|---|---|---|
| 13:58:18 | `pnpm exec vitest run tests/zzBreakerBasepath.test.tsx` (web-teacher, temporal) | `2 passed`: con `basepath: "/teacher"` el `beforeLoad` del root ve `/entrenamiento-recalibracion` (sin basepath) y `/teacher/progression` redirige a `/interrater`. Sin falla. |
| 14:00:08 | `uv run pytest apps/classifier-service/tests/unit/test_zz_breaker_unit.py -q` (temporal) | `5 failed, 23 passed`. Los 23 verdes: regla v0 (8 combinaciones), exento, frontera, propuesto sin nota, CSV con BOM/CRLF/comillas/comas, muestra vacía, UUID en otra forma, prefijo CSV, payload nulo. Los 5 rojos: `TypeError: unhashable type: 'list'` en `estudio_esquema.py:365`, `:367`, `:217`, `:245`, `:187` (F2, F3). Fallan por excepción no controlada, no por aserción: por eso los reproduje también por HTTP. |
| 14:00:39 | `CLASSIFIER_TEST_DB_URL=... uv run pytest apps/classifier-service/tests/integration/test_zz_breaker_db.py -q -s` (temporal) | `6 failed`, todos por **aserción** (F1 x2, F2, F3, F4, F5). |
| 14:02:45 | `uv run pytest apps/classifier-service/tests/unit/test_zz_breaker_ctr.py -q` (temporal) | `1 failed` por aserción (F6). |
| 14:02:35 | script `CTRLector` con `httpx.MockTransport` 200 `text/html` | `EXCEPCION NO CONTROLADA: JSONDecodeError` (F6). |

Archivos de prueba: `scratchpad/breaker/{zzBreakerBasepath.test.tsx,test_zz_breaker_unit.py,test_zz_breaker_db.py,test_zz_breaker_ctr.py}` (scratchpad de la sesión `dbd486d5-...`). Los tests de integración commitean bajo tenants aleatorios, como los del constructor: dejaron filas en `cibse-test-pg`, incluidas versiones congeladas que la base no deja borrar. El `TRUNCATE` de F5 corrió dentro de una transacción con `ROLLBACK`: no borró nada.

### F1 (MAYOR): anclas incoherentes con el esquema congelado

Pasos (`test_zz_breaker_db.py::test_BREAKER_ancla_queda_incoherente_con_el_esquema_congelado` y `::test_BREAKER_ancla_con_dimension_renombrada`):
1. Borrador `v0` con `ESQUEMA_PRUEBA`; ancla de práctica con la etiqueta reflexiva (201, `respuesta_esperada.regimen = "reflexiva"`, derivado por la regla de ese momento).
2. `PUT /codebook/v0` con un esquema B donde reflexiva exige `d4 = oraculo` (o con `d1` renombrada a `d1_nueva`).
3. `POST /codebook/v0/congelar`.

Salida:
```
BREAKER PUT esquema B con anclas -> 200
BREAKER congelar -> 200 c666674b0d7ad7c79523ce153c64cd10479c892cbc63f0b2ba204ebbd8435106
BREAKER esperada.regimen= reflexiva  regla congelada deriva= superficial
E       AssertionError: ancla congelada con un regimen que la regla congelada no da
E       assert 'reflexiva' == 'superficial'
BREAKER congelar con ancla de dimension inexistente -> 200
BREAKER respuesta esperada congelada invalida: ["respuestas: dimensión desconocida 'd1'"]
E       AssertionError: la version congelada contiene un ancla cuya respuesta esperada no valida contra su esquema
```
Código: `routes/estudio.py::editar_version` cambia `esquema_formulario` sin mirar las anclas; `congelar_version` valida solo el esquema (`validar_esquema`) y calcula el sha sobre anclas sin revalidarlas (`_anclas_para_sha`). `respuesta_guardable` fija el régimen esperado en el alta del ancla (`estudio_trabajo.py:861`). Consecuencia: `responder_practica` devuelve `coincide` contra un esperado que la regla vigente no produce, y el sha congelado certifica ese estado.

Contraste: spec `entrenamiento-calibracion` ("respuesta esperada validada contra el esquema de esa versión"); design D9 ("el régimen persistido es siempre el que da la regla"); runbook 12.3 del servicio ("se valida contra el esquema de la versión"). El design lista como mitigación una tarea humana de follow-up ("validar el esquema del v0 contra las anclas antes de congelar"), no un control del sistema.

### F2 (MENOR): régimen no hashable da 500

`test_BREAKER_http_regimen_lista_da_400`: `PUT /items/{item}/mi-etiqueta` con `{"respuestas": ..., "regimen": ["reflexiva"]}`:
```
BREAKER PUT mi-etiqueta regimen=list -> 500 Internal Server Error
E       assert 500 == 400
```
Causa: `_errores_de_campos` hace `pedido_regimen not in regimenes` con `regimenes` un `set` (`estudio_esquema.py:365`, `:367`). Mismo camino en `POST .../entrenamiento/{item}/respuesta` y en el alta/edición de anclas (todos pasan por `evaluar_pedido`). Contraste: spec `estudio-codificacion`, "Valor fuera del esquema -> 400". El 500 no filtra datos (cuerpo genérico).

### F3 (MENOR): esquema con lista donde va clave da 500

`test_BREAKER_http_esquema_con_lista_da_400`: `PUT /codebook/v0` con `regimen_evidencia_insuficiente: ["evidencia_insuficiente"]`:
```
BREAKER PUT codebook esquema ei=list -> 500 Internal Server Error
E       assert 500 == 400
```
También con `regimen_por_defecto` lista (`:245`) y `regimenes_exentos: [[...]]` (`:187`), por la unitaria. Contraste: spec `codebook-versionado`, "El sistema SHALL rechazar con 400 un esquema que no cumpla el meta-esquema cerrado". Solo el investigador llega a este endpoint.

### F4 (MENOR): cerrar sin muestra dice "faltan 0"

`test_BREAKER_cerrar_sin_muestra`: codebook congelado y vigente, sin muestra, `POST /mi-codificacion/cerrar` de un codificador:
```
BREAKER cerrar sin muestra -> 422 {"detail":{"codigo":"incompleta","faltan":0,"faltantes":[]}}
E       AssertionError: rechaza por 'incompleta' diciendo que faltan 0
```
Panel (por lectura, no ejecutado): `CodificacionEstudioView.tsx` muestra "0 de 0 completos" y el botón de cerrar; al cerrar, `faltantesDe` devuelve `[]` (truthy) y se renderiza "Faltan 0 ítems para poder cerrar:" con la lista vacía (`:223-225`). Coincide con lo que reportó el front. No hay estado vacío "la muestra todavía no se cargó" para el codificador. El parser rechaza una muestra de 0 filas ("muestra vacía"), así que el caso real es "muestra no cargada", no "muestra de 0".

### F5 (MENOR): TRUNCATE salta el append-only

`test_BREAKER_truncate_historial_y_entrenamiento`, con `classifier_user` (dueño, no superuser) y `ROLLBACK` al final:
```
BREAKER historial antes= 1 despues TRUNCATE= 0 error= None
```
(la aserción `error is not None` falla). Los triggers de la migración son `FOR EACH ROW` sobre `UPDATE OR DELETE`; `TRUNCATE` no los dispara y RLS no aplica a `TRUNCATE`, así que vacía las filas de todos los tenants. Las specs solo nombran UPDATE y DELETE, pero CLAUDE.md ("La base protege la referencia con triggers: ... historial, respuestas de entrenamiento...") y ADR-063 ("La referencia del paper queda protegida por la base") afirman más de lo que la base hace. Aplica igual a `estudio_enunciado` y, con `CASCADE`, a `codebook_version`/`estudio_ancla` (no ejecutado).

### F6 (MENOR): CTR con 200 no JSON da 500

`test_zz_breaker_ctr.py`:
```
E       AssertionError: se escapa JSONDecodeError: la traza responde 500, no 502
```
`ctr_lectura.py::CTRLector.episodio` hace `r.json()` fuera del `try`. Contraste: spec `traza-ciega-episodio`, "Fallas del registro de episodios -> 502 genérico"; docstring del módulo ("cualquier otro error HTTP o de red -> CTRNoDisponibleError"). En la carga de muestra pasa lo mismo (un 500 en vez de 502, sin cargar nada: la transacción se revierte).

### F7 (MENOR): referencia circular del meta-esquema

- `docs/adr/063-estudio-codificacion-ciega.md:115`: "Forma exacta del meta-esquema: `docs/servicios/classifier-service.md`, runbook del estudio."
- `docs/servicios/classifier-service.md:411`: "forma completa en el informe `apply-1-constructor-B.md` del change y en ADR-063 D9".
- `rg "notas_obligatorias_si_frontera|con_cita|regimenes_exentos"` en ADR, doc del servicio y CLAUDE.md: sin resultados. La forma exacta solo vive en el docstring de `services/estudio_esquema.py` y en `informes/apply-1-constructor-B.md`, que cambia de ruta al archivar el change.

## Cobertura por lente

1. **Ciego**: LIMPIO. Revisé `filtrar_traza` (copia por clave permitida, tipos no listados omitidos, `n` y `t_seg` después de filtrar), el endpoint de traza (resuelve `item_id` de muestra o anclas del estudio; `episode_id` nunca sale), lista e ítems (solo `item_id`, `posicion`, `estado`), `mi-etiqueta` (solo la propia), entrenamiento (prácticas sin esperada; la esperada solo de esa ancla al responder), `GET .../versiones/{etiqueta}` (codificador: `item_id`, `uso`, `orden`), errores 4xx/5xx (códigos sin datos; 500 genéricos), logs (`rg logger` en ambos routers: alias, ids, hashes, nunca emails ni valores), exportación (solo investigador). Payload anidado: los valores permitidos se copian tal cual; con el contrato vigente son `str`/`int`/`list[str]`, así que no hay vía. Estrato, origen y tp no se persisten. Que `intento_adverso_detectado` no aparezca lo cubre `test_traza_ciega.py` (unitaria), no el smoke (lo dice el constructor E).
2. **Acceso**: LIMPIO. `require_membresia` por `lower(email)` + `revocada_at IS NULL` + rol + atadura condicional del `user_id`; revocado, otra capitalización, otro `user_id`, `docente` y `superadmin` sin membresía, codificador exportando o gestionando, IDOR por `item_id` de otro estudio o `episode_id` real: todo cubierto por los tests del constructor y consistente con el código. Ambos routers declaran `require_gateway_auth` y `test_con_firma_exigida...` toca rutas de los dos.
3. **Integridad**: F1 y F5. Lo demás (congelada por API y SQL, historial UPDATE/DELETE, evidencia fija, tope y chain hash, muestra con hash distinto o con etiquetas, enunciado revisado, exclusión anclas/muestra bajo el lock del estudio, clonado) está cubierto y lo verifiqué por lectura.
4. **Régimen**: con el v0 real, 8 combinaciones derivan lo que dice la regla; exento, frontera, propuesto sin nota (`None`, `""`, `"   "`), régimen distinto (422) e incompleto (422) se comportan según D9. Falla F1 (anclas) y F2 (borde).
5. **Bordes**: F2, F3, F4, F6. CSV con BOM, CRLF, comillas y comas en la muestra: OK; vacía y duplicada (incluido el mismo UUID con llaves): OK.
6. **Exportación**: LIMPIO en lo especificado (prefijo `'` para `=`, `+`, `-`, `@`, tab y CR; sin emails ni contenido). Ver S3.
7. **Cableado**: LIMPIO. El front llama rutas que existen con las formas reales (`estudioApi.ts` contra los routers); el Bearer lo pone el interceptor global (`installApiFetchInterceptor`), así que `misMembresias()` sin `getToken` no es un defecto; `consultarAcceso` usa `allSettled` (docente entra con classifier caído); modo restringido sin tour, onboarding ni selectores, y con basepath real (mi vitest). Consumidores del piloto: `routes/interrater.py`, analytics y `/interrater-admin` sin cambios; ninguna tabla del estudio se lee fuera de los dos routers (`rg` sobre `apps`, `packages`, `scripts`); los 7 UUID del entrenamiento viejo solo aparecen en `tests/sinEntrenamientoPiloto.test.ts`.
8. **Docs**: F5 (afirmación de CLAUDE.md/ADR) y F7. Endpoints del runbook coinciden con los routers; claves de `helpContent` (22) y rutas del web-teacher coinciden con CLAUDE.md; `scripts/check-claude-md.py`: `[OK] 3 claims verificados, 2 skip, sin drift`; el procedimiento D7 del ADR coincide con `estudio_orden.py`.

## JUICIO

Autor: breaker verify-1. Comparación: código entregado contra proposal, design D1 a D14, las seis specs, ADR-063, runbook y CLAUDE.md. Confianza alta en F1 a F7 (reproducidas con salida propia); media en la severidad de F1.

- F1 es la única que toca la referencia. No contamina las etiquetas de los codificadores (el régimen de cada etiqueta se deriva al guardar contra la vigente congelada), pero sí el entrenamiento: un codificador que aplica bien la regla congelada recibe "no coincide" y la explicación de un ancla pensada para otra regla, y el `contenido_sha256` que se cita en el método certifica ese estado. El orden del runbook (anclas antes de congelar, esquema editable en el borrador) hace probable el camino. Lo marco MAYOR y no BLOQUEANTE porque el entrenamiento no es obligatorio (P10) y hay una tarea humana de follow-up que lo detectaría si se ejecuta; si el auditor considera que el sha congelado es integridad de auditoría (CRITICAL), corresponde subirla.
- F2, F3 y F6 son manejo de errores: 500 en vez del código especificado, sin fuga de datos.
- F4 es contrato y UX: el backend rechaza con `incompleta` y dice que faltan 0.
- F5 es la distancia entre lo que la documentación afirma ("la base lo impide") y lo que hace. El riesgo real requiere acceso SQL con el usuario de la app.

## SUPOSICIÓN (sin reproducir)

- **S1, posible deadlock en el primer uso**: `bloquear_para_codificar` llama a `require_membresia`, que en el primer uso hace `UPDATE estudio_membresia` (lock de la fila) ANTES del `FOR SHARE` del estudio; una revocación concurrente toma el estudio `FOR UPDATE` y después actualiza esa membresía. Es el orden inverso de D10b y Postgres abortaría una de las dos con 500. Poco probable (el primer uso suele ser `mis-membresias` al entrar al panel). Falta: test concurrente con dos sesiones y un `pg_sleep`.
- **S2, gather sin cancelar**: en `leer_episodios`, si un episodio da `CTRNoDisponibleError`, `asyncio.gather` propaga y los demás pedidos siguen corriendo en segundo plano. Sin efecto sobre datos; falta medir.
- **S3, celdas CSV que empiezan con LF o con espacios antes de `=`**: no se prefijan. La spec no las exige; no verifiqué cómo las interpreta LibreOffice o Excel.
- **S4, regla v0 y dimensiones no referenciadas por la condición decisiva**: con D1 presente, D2 presente, D4 interlocutor y D3 sin valor, el régimen queda nulo aunque la regla ya esté determinada. Es lo que dice D9 ("todas las dimensiones que la regla referencia"); lo dejo para el investigador, no como defecto.
- **S5, pasiva parcial**: con D4 `transferencia` sin cita, un guardado parcial deriva `superficial`; al cerrar se exige la cita y el régimen pasa a `pasiva`. Coherente con D9; puede sorprender al codificador.
- No ejecutado: CI, firma real del gateway contra ctr-service, Clerk, el smoke (reusé su resultado: `make test-smoke` 100 passed, 13:47:06), la suite completa (reusé 617 passed + 4 ambientales, 13:47:58), mutantes sobre la entrega.

## Fuentes leídas

`proposal.md`, `design.md`, las seis `specs/*/spec.md` (completos); `tasks.md` (solo las líneas del entorno de pruebas); `CLAUDE.md` del repo; código: `routes/estudio.py`, `routes/estudio_trabajo.py`, `services/{traza_ciega,ctr_lectura,estudio_esquema,estudio_muestra,estudio_export,estudio_orden,estudio_codebook,estudio_enunciados}.py`, `models/estudio.py`, la migración `20261104_0007`, `auth/__init__.py`, `main.py` (diff), `tests/integration/conftest.py` (diff), nombres de todos los tests del estudio, `test_estudio_acceso_db.py` (procedencia); ctr-service `routes/events.py::get_episode` y `schemas`; `packages/contracts/.../ctr/events.py` (payloads); api-gateway `middleware/jwt_auth.py` (inyección de headers); web-teacher: `main.tsx`, `routes/__root.tsx` (diff), `lib/estudioApi.ts`, `utils/accesoPanel.ts`, `views/estudio/{CodificacionEstudioView.tsx (110-240),mensajesError.ts}`, `helpContent.tsx` (diff), `tests/rootModoRestringido.test.tsx` (1-70), `vite.config.ts`; `docs/adr/063-estudio-codificacion-ciega.md`, `docs/servicios/classifier-service.md` (diff); `esquema_v0.json`.

## Contaminación

- Leí `informes/apply-1-constructor-E.md` completo (para reusar los checks, como pidió el orquestador) y `informes/LEEME.md`. De ahí tomé: los resultados de la suite y del smoke que no repetí, la URL de la base de pruebas y la observación de que el mutante de `intento_adverso_detectado` sobrevive al smoke. No leí los informes A, B, C, D ni los de propose.
- Mismo proveedor y familia que todos los roles previos: mis hallazgos no son independientes por proveedor; lo son por ejecución (tests y salidas propias).
