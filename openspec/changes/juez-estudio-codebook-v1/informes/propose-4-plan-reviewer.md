# Informe: propose-4-plan-reviewer - juez-estudio-codebook-v1

Autor: role-plan-reviewer, subagente nativo de Claude Code, modelo Claude Opus 5.5 (sin tabla "Role executors" en el proyecto). Misma familia que el planner y mismo rol y modelo que los informes de los intentos 1 a 3: la independencia es de rol y contexto, no de proveedor.
Revisión: worktree `agent-a377c2107a7f2b43a`, rama `feat/juez-estudio-codebook-v1`, HEAD `178c343bac96be4f71ac1da4e2bc2b770365d72f`, artefactos sin commitear leídos el 2026-11-06 desde las 21:40 -03. sha256 (16 primeros): proposal `8ad952b7ded7ad56`, design `dd3e46dfdb59a788`, tasks `151381500e44da2b`, spec acceso `8c9a82d369923194`, spec codificación `0b2d191ed8fe850e`, spec congelado `d5c9783d3acb8f6c`.
Intento: 4 ACOTADO, autorizado por Juani (tasks.md, "Decisión humana 06/11/2026"). Alcance: hallazgos de `propose-3-plan-reviewer.md` y regresiones directas de sus correcciones. No reabrí decisiones tomadas.

## Veredicto

**APTO PARA APROBACIÓN HUMANA.** 0 BLOQUEANTES, 12 MENORES que pasan como notas para el constructor.

Este veredicto habilita presentar el plan a Juani. No autoriza construir: `## Aprobación` sigue vacía, con diez decisiones pendientes, y ningún visto bueno de agente reemplaza su firma.

Aviso de lectura: N1 y N3 son los dos menores que más cerca estuvieron de bloquear. Explico por qué no bloquean en JUICIO. El orquestador debería mostrárselos a Juani, porque N3 toca el dato que sostiene la regla del paper.

## EVIDENCIA

Todo el 2026-11-06, sobre HEAD `178c343`. Nada de esto prueba el juez: no existe.

Ejecutado:
- E1 `openspec validate juez-estudio-codebook-v1 --strict --json` (al empezar y de nuevo a las 21:47:28, con los seis sha256 sin cambios): `"valid": true`, `issues: []`. `openspec status`: 4 artefactos `done`. Alcance: formato, no contenido.
- E2 Búsqueda de em dashes con `rg -c` sobre proposal, design, tasks y specs (21:40:56): sin resultados.
- E3 Script propio `d7b.py` (21:44:56; `python3 -I`, en el scratchpad, importa solo `services/estudio_esquema.py` por ruta, lee solo `codebook/esquema_v1.json`, sin episodios ni bases). Simula los pasos 2, 4 y 5 de D7b con el `evaluar_pedido` y el `faltantes_cierre` reales; no simula forma ni citas. Es una simulación mía del plan, no el código del juez. Salida:
  - 1 reflexiva completa: `ok`.
  - 2 y 3 reflexiva con `d2` omitida o nula: paso 2, `incompleto`, `dimension:d2_verificacion`.
  - 4 dimensiones completas y `pasiva` afirmada: paso 4, `inconsistente` ("la regla da 'reflexiva'").
  - 5 `evidencia_insuficiente` sin dimensiones, con `notas` y `confianza`: `ok`.
  - 6 sin `notas`: paso 5, `incompleto`, `notas`. 7 sin `confianza`: paso 5, `incompleto`, `confianza`.
  - 8 reflexiva con cita requerida vacía en `d1`: paso 5, `incompleto`, `cita:d1_verbalizacion`.
  - 9 `pasiva`, `d4=transferencia` con cita: `ok`.
  - **10 y 11 `pasiva`, `d4=transferencia` con cita vacía o nula: paso 4, `inconsistente` ("la regla da 'superficial'"), no `incompleto`.**
  - 12 `superficial`, mismas dimensiones, cita vacía: paso 5, `incompleto`, `cita:d4_autonomia`.
  - 13 frontera sin notas: paso 5, `incompleto`, `notas`.
  - **14 `es_frontera: null`: `PedidoInvalidoError` 400 en el paso 2, que D7b no mapea.**
  - **15 `es_frontera: true` con `marca_frontera` falsa (esquema v1 modificado en memoria): ídem, 400 en el paso 2.**
- E4 Forma del esquema (mismo archivo): dimensión con `clave, nombre, valores, cita_requerida_si`; `d4_autonomia` con `interlocutor, oraculo, transferencia`, las tres con cita requerida. La regla de `pasiva` tiene un átomo `{"dimension":"d4_autonomia","en":["transferencia"],"con_cita":true}`. `regimen_por_defecto = superficial`.
- E5 `python3 -I` con `traza_ciega.py` cargado por ruta: `filtrar_traza(ev, None)` da `TypeError: '>' not supported between instances of 'int' and 'NoneType'`; `filtrar_traza(ev)` da `TypeError: missing 1 required positional argument`.
- E6 `rg` de residuos: "D2 del motor", "tasks 8.6", "Refrescar", "no solo de variantes" y "decisión 3 de Juani": sin resultados. "testcontainers" solo en negaciones (`design.md:222`, `tasks.md:28`). Quedó `design.md:207`: "superposición imposible por dos escrituras existentes".

Leído:
- E7 `apps/ai-gateway/.../providers/base.py`: Anthropic separa los mensajes `system` y los pasa como `system=` (105-113, 134-141). Gemini los pasa como `system_instruction` (353-363, 373-374, 420-421). OpenAI, Mistral y OpenRouter mandan `messages=request.messages` (206, 292, 526). `routes/complete.py:196-198`: `Message.role` admite `system`. `max_tokens` admite hasta 65536 (215).
- E8 `services/regimen_llm.py:380-391`: producción tolera cercados (`_limpiar_json`), porque "algunos modelos (según el provider...) envuelven la salida en un bloque de código".
- E9 `db/__init__.py:47-60`: `tenant_session` hace `commit` solo si el bloque termina sin excepción, y `rollback` ante cualquiera. `set_config(..., true)` dura la transacción.
- E10 `tests/integration/conftest.py:81-97`: el fixture `app_db` hace que la app use el `tenant_session` real contra la base de test; los tests HTTP del estudio commitean de verdad. `test_submit_review_concurrency_db.py` ya usa un engine aparte para comprobar desde otra sesión.
- E11 `routes/estudio_trabajo.py:155-191`: `traza_ciega` resuelve el enunciado dentro de la sesión y lee el CTR afuera. Un evento con `seq` mayor que el tope no dispara la comprobación de evidencia.
- E12 `routes/estudio.py:713-725`: `GET /{clave}/codebook/vigente` devuelve `version_out(version)` con membresía `ROLES_ESTUDIO`.
- E13 `infrastructure/postgres/init-dbs.sql:44-54`: `apply_tenant_rls` crea una policy solo con `USING`, con ENABLE y FORCE. `estudio_muestra` está en `TABLAS` de la migración 0007 (39, 343-344), con `UNIQUE(estudio_id, episode_id)`.
- E14 `proposal.md:99-101`: `## Aprobación` solo tiene el comentario reservado.

No ejecutado: tests, `alembic`, `make check-rls`, gateway o proveedor real, Postgres. Por encargo no toqué bases, así que todo lo dicho sobre triggers, RLS y transacciones del juez futuro es razonado.

## Estado de los hallazgos del intento 3

| Hallazgo | Estado | Comprobación |
|---|---|---|
| B1 contrato de salida | **Resuelto** | Ver detalle abajo. Residuales N7, N8, N10 |
| I1 orden de evaluación | **Resuelto, con dos residuales** | E3 casos 1 a 9, 12 y 13 dan lo que dice la spec. Residuales: N1 (casos 10, 11), N2 (14, 15) |
| I2 entre estudios | Resuelto | D5, spec, 4.1, F7. La tabla tiene RLS (E13). Residual de texto: N12 (`design.md:207`) |
| I3 cantidad de anclas | Resuelto | D6, condición 3, 4.2, 4.5, P16; ya no toma `n_items` de la propia corrida como referencia |
| I4 sin ajuste | Resuelto | Límite y regla del paper en proposal; `n_modelos_previos`, `n_cambios_tras_cumplir`; decisión 10. Residual: N3 |
| I5 estabilidad | Resuelto | Decisión 3 trae (a) a (d) y la regla para (e). Residual: N11 |
| I6 transacciones | **Resuelto** | Ver detalle abajo. Residual N9 |
| I7 hash | **Resuelto** | `mensajes_referencia` y `parametros` en el hash, golden del `messages`, condición 2 compara `parametros`. Residual N7 |
| I8 `contenido_md` | Resuelto | D8, Migration Plan 4, 8.0; la ruta devuelve `version_out` (E12). Residual de orden: N12 |
| I9 mutantes | **Mayormente resuelto** | Ver detalle abajo. Residuales N4, N5, N6, N7 |
| I10 `regimen_propuesto` | Resuelto | D7, decisión 9, spec, 3.1, 3.3, mutante E2 |
| M1 a M12 | Resueltos | M1, M2, M12 por E6. M3 en dos escenarios. M4 con residual N4. M5 en el requisito. M6, M7 en D6 y 4.3. M8 en 3.4(e). M9, M10, M11 declarados |

### B1

- Llega en todos los proveedores: la vía elegida es el mensaje de sistema, y los cinco adaptadores reales lo transportan (E7). Esto cierra el punto (a) de B1 por lectura de código, no por observación de un modelo.
- `armar_mensajes` lo recibe como parámetro (`esquema_salida`; D8, D11, 3.4) y `prompt_sha256` lo cubre a través de `mensajes_referencia` (D8).
- `strict` se quitó, coherente en D7, spec "Sin esquema estricto", 3.1, 3.5, B1b.
- 3.4(b) falla si el contrato desaparece: pide las claves en el mensaje de sistema y que el contrato sea el mismo dict que `construir_json_schema`. Esa igualdad también mata una eliminación parcial, y no depende de subcadenas que pudieran estar en `contenido_md`.
- 3.5 falla si el contrato no llega desde el sitio de llamada: exige que el esquema de `response_format` sea el mismo que viaja en los mensajes.
- 3.4(c) necesita ajustes de construcción, no de diseño (N8).

### I6

El aborto se persiste con el comportamiento real: `tenant_session` commitea solo si el bloque sale sin excepción (E9), y D6 obliga a devolver un resultado, cerrar y recién después levantar el 409. El fixture `app_db` usa el `tenant_session` real, así que 4.3 y F8 pueden leer desde otra sesión y el mutante falla por aserción (E10). F9 también es viable. Las fases de D6 resuelven la transacción colgada durante el LLM y el fallo del cierre.

### I9

Puntos (a) a (f) del intento 3 tienen fila o test, salvo los defectos de abajo. Revisé cada mutante nuevo preguntando si alcanza la línea mutada y si el test falla por aserción:
- Prueban una falla real: F7, F8, F9, T3, T4, T5, C8, B1a, B1b, B1c, H1, H2, H3, E1, E2, P12a, P16 a P21.
- No la prueban tal como están escritos: F10 (N4), T1 (N5), P12b (N6), B1d (N7). T2 depende de una guarda (N5).

## Hallazgos

Todos MENORES. El formato es fuente, impacto, criterio y corrección verificable.

### N1. MENOR - Cita vacía con átomo `con_cita`: D7b da `inconsistente` y la spec pide `incompleto`

- Fuente: spec codificación "Cita requerida vacía, notas o confianza exigidas ausentes"; D4 ("Cita requerida VACÍA... da `incompleto`, D7b paso 5"); D7b pasos 4 y 5; E3 casos 10 y 11; E4.
- Observación: con el esquema v1 real, `pasiva` con `d4=transferencia` y cita vacía no llega al paso 5. El átomo `con_cita` no se cumple, la regla deriva `superficial` y el paso 4 da `inconsistente`. Las mismas dimensiones con `superficial` afirmado dan `incompleto` (caso 12).
- Impacto: un caso alcanzable contradice la spec. Las dos salidas fallan la condición 4, así que el criterio no cambia; cambia la etiqueta del estado y la razón que se lee después. La fixture de 3.3 no exige `con_cita`, así que el test podría no verlo.
- Criterio: spec y design deben coincidir; un solo orden.
- Corrección verificable: en el paso 2, tomar de la misma llamada los códigos `dimension:*` y `cita:*`, lo que no agrega una segunda regla. Alternativa: declarar en la spec que ese caso es `inconsistente`, como le pasa al humano con su 422. La fixture de 3.3 lleva un átomo `con_cita` y un test fija la salida elegida.

### N2. MENOR - El paso 2 de D7b no mapea el 400, y "según esquema" es ambiguo en `validar_forma`

- Fuente: D7b pasos 1, 2 y 4; tasks 3.1; E3 casos 14 y 15.
- Observación: el paso 4 mapea el 400 a `respuesta_malformada`, pero la primera llamada a `evaluar_pedido` ocurre en el paso 2 y ahí no hay mapeo. `es_frontera: null`, si pasa la forma, levanta sin capturar. Además, 3.1 dice "`confianza`/`es_frontera`/`notas` según esquema": si `confianza.obligatoria` se traduce en clave requerida, su ausencia sería `respuesta_malformada` y no `incompleto`.
- Impacto: una excepción no prevista deja el par sin veredicto y sin estado. El test de 3.3 atrapa lo de `confianza`, no lo de `null`.
- Corrección verificable: el 400 se mapea a `respuesta_malformada` en cualquier llamada a `evaluar_pedido`. `validar_forma` requiere solo `regimen`, y define si admite nulos en `es_frontera`, `confianza` y `notas`. Test con `es_frontera: null` y con `es_frontera: true` sin marca.

### N3. MENOR - `cumple_tecnico` al cierre: la condición 1 exige `cerrada` antes del `UPDATE`

- Fuente: D6 sesión 3 ("calcula el `resumen` (incluido `criterio`)... y ejecuta `UPDATE ... SET estado='cerrada'`"); D8 condiciones 1 y 7, "se recalcula al cerrar y al congelar", y "Dato objetivo"; tasks 4.4, 4.5.
- Observación: evaluada literalmente, la condición 1 ve `en_curso` y `cumple_tecnico` da falso en toda corrida. La condición 7 es "al congelar", y 4.5 llama pura a una función que cubre las condiciones 1 a 7, aunque la 7 necesita base. La corrección de I4 hizo que `n_cambios_tras_cumplir` dependa de ese campo.
- Impacto: si se implementa así, `n_cambios_tras_cumplir` queda en 0 siempre, y la regla del paper autorizaría decir "fijado antes de ver resultados" sin que sea cierto. El `resumen` no se puede corregir después, porque el cierre es único. Ningún test lo ve: 4.4 recibe `criterio` por parámetro y 4.5 puede fabricar el `resumen` anterior.
- Criterio: el rastro de I4 debe medir lo que dice medir.
- Corrección verificable: declarar qué condiciones se evalúan al cierre, sin el estado (que se está fijando) y sin firewall, y que la 7 se comprueba aparte en `congelar`. Test de integración en 4.3: una corrida real de 15 `ok` cierra con `resumen.criterio.cumple_tecnico` verdadero. La secuencia de 4.5 usa corridas cerradas por ese camino, no resúmenes armados a mano. Mutante: condición de estado aplicada al cierre.

### N4. MENOR - F10 no alcanza la línea mutada

- Fuente: tasks 4.3 y fila F10; D6 sesión 1 (409 `corrida_no_en_curso`); M4 del intento 3.
- Observación: 4.3 corre con concurrencia 1. El primer `siguiente` tras la caída cierra, y el segundo se corta en la sesión 1 con 409, sin llegar al `UPDATE`. El mutante sobrevive y "0 filas afectadas sin error" queda sin probar.
- Corrección verificable: llamar dos veces a la función de cierre, o cerrar la corrida con otra sesión entre la sesión 1 y la 3 mediante un hook. Con el mutante el trigger rechaza y el test falla por aserción sobre el resultado.

### N5. MENOR - T1 muere por `TypeError`, y T2 puede pasar vacío

- Fuente: tasks fila T1 y T2, 4.3, regla de la sección 8 ("falle por aserción"); E5.
- Observación: en T1, "no pasar `seq_tope`" o "pasar `None`" dan `TypeError`: no prueba la aserción. En T2, razonado porque `hay_contenido` no existe: con eventos crudos, que traen `event_type` y no `tipo`, `hay_contenido` podría dar falso, el modelo no se llamaría, y "`messages` no contiene el campo" pasaría sobre una captura vacía.
- Corrección verificable: T1 pasa un tope mayor que todo `seq` (por ejemplo `10**9`). El test de 4.3 afirma primero que `complete` se llamó exactamente una vez, y que un evento anterior al tope sí figura en `messages`.
- Nota de P8: la fixture debe diferir en la tercera repetición, o el mutante "comparar solo dos" sobrevive.

### N6. MENOR - P12b falla por setup, lo mismo que I9(b) pedía evitar

- Fuente: tasks 2.3 y fila P12b; E13; `propose-3-plan-reviewer.md` I9(b).
- Observación: sin policy y con FORCE, el `INSERT` del dueño también se rechaza (SUPOSICIÓN por documentación de Postgres, no lo probé), así que el test muere al insertar y no en la aserción positiva. P12a está bien. La aserción positiva agregada a 2.3 también está bien; lo que falla es el mutante.
- Corrección verificable: insertar y commitear la fila antes de aplicar el mutante, o mutar con `USING (false) WITH CHECK (true)`.

### N7. MENOR - B1d nombra un test que no lo mata, y el contrato falta en la lista de 3.6

- Fuente: fila B1d; tasks 3.6; spec "Cambio del armado de mensajes o de los parámetros".
- Observación: el golden del `messages` se calcula sobre `armar_mensajes`, no sobre `prompt_sha256`: quitar `mensajes_referencia` del hash lo deja verde. Lo mata otro test de 3.6, el que comprueba que el hash cambia con `armar_mensajes` modificado. La spec nombra el contrato entre lo que mueve el hash, y 3.6 no lo enumera.
- Corrección verificable: B1d apunta al test de cambio de hash, y 3.6 agrega "el hash cambia si cambia el `esquema_salida`".

### N8. MENOR - 3.4(c): el falso no puede llegar a `ok` leyendo solo el contrato, salvo con una fixture pensada

- Fuente: D11, tasks 3.4(c), spec "Una respuesta de formato esperado se interpreta"; E4.
- Observación: el contrato no trae la regla ni `cita_requerida_si`. Un falso que solo lee el contrato no puede saber qué régimen es coherente ni qué localizador citar. Si responde con el régimen exento, llega a `ok` sin usar las claves de dimensión, y la prueba mide poco. Además, 3.4 usa un `complete` antes de que exista el llamador de 3.5.
- Corrección verificable: fixture propia donde el primer valor de cada dimensión no exija cita y derive el primer régimen; el falso llena las dimensiones leídas. Sin contrato devuelve texto vacío, no levanta, para que el fallo sea por aserción. El test llama al falso directamente con la salida de `armar_mensajes`; el sitio de llamada lo cubre 3.5.

### N9. MENOR - Huecos de fases en `siguiente`

- Fuente: D6, D8; 4.3; E11.
- Observación: (a) los `UPDATE` de aborto no dicen `WHERE estado='en_curso'`: con dos pasos concurrentes, el trigger rechazaría el segundo y daría 500. (b) D6 no ubica la carga del enunciado, `contenido_md` y esquema, ni `hay_contenido`. El enunciado necesita sesión; `enunciado_pendiente` se detecta en la sesión 1, que "escribe solo abortos", y el veredicto va a la sesión 2. (c) La comparación de `prompt_sha256` debe usar `contenido_md` y esquema de `corrida.codebook_version_id`, no de la vigente, o aborta en falso si la vigente cambió.
- Corrección verificable: agregar esas tres líneas a D6. Test en 4.3 para (c) con la vigente cambiada.

### N10. MENOR - "El plan vale por cualquiera de las dos rutas" promete de más

- Fuente: proposal decisión 2; D7; E7; E8.
- Observación: el contrato llega por las dos rutas, pero el juez rechaza cercados y producción los tolera porque ocurren (E8). Anthropic no aplica `response_format`. Un modelo que cerque daría 15 `respuesta_malformada`. D7 lo declara como riesgo; la decisión 2, que es donde Juani elige, no.
- Corrección verificable: agregar a la decisión 2 esa frase. No pido cambiar la decisión de no tolerar cercados.

### N11. MENOR - `Decisión humana (Juani, 06/11/2026)` contiene cosas que Juani todavía no decidió

- Fuente: proposal líneas 13, 14 y 78-80, y 88; `informes/propose-3-plan-reviewer.md` I5.
- Observación: bajo ese título están la regla ante un ancla de frontera y la configuración única, que las decisiones 3 y 10 presentan como pendientes con recomendación. Además, el dato "2 de las 5 anclas son de frontera" aparece como hecho en la decisión 3, y design lo marca sin reverificar. "La corrida queda como no cumplida" solo vale con `ESTABILIDAD_MIN_V1 = 1.0`.
- Impacto: atribuye al humano una elección que no hizo. No afecta la construcción, pero sí lo que firma.
- Corrección verificable: rotular esos dos puntos como propuesta sujeta a las decisiones 3 y 10, y marcar el dato de frontera como no reverificado. Si Juani las acepta al firmar, el texto queda cierto.

### N12. MENOR - Texto residual

- `design.md:207`: "superposición imposible por dos escrituras existentes" contradice D5 reescrita. Debe decir "dentro de un estudio".
- `tasks.md:160`: "Precede 8.0" se lee al revés de `tasks.md:83` ("Precede a 8.5"). Debe decir "La precede 8.0".
- 7.3 pide en el ADR el resultado de 8.0, pero 8.0 necesita el servicio desplegado, después de la sección 7. Declarar que el ADR se completa después del deploy.
- Lista "Lo que sí corre en CI" de 8.1: incluye P11, cuyo test (4.2) necesita base para ver la corrida anterior. P21 (4.3) tampoco aparece en la lista de garantías sin red. Corregir las dos listas, para que Juani firme la decisión 7 con la cobertura real.

## Decisiones de proposal: ¿alcanza la información?

| Decisión | Información | Observación |
|---|---|---|
| 1 Vía y nivel | Suficiente | |
| 2 Proveedor | Suficiente, con N10 | Falta el riesgo de cercados |
| 3 Valores y estabilidad | Suficiente, con N11 | (a) a (d), regla, tope y recomendación presentes |
| 4 Alcance ampliado | Suficiente | |
| 5 T-002 | Suficiente | |
| 6 Ambiente Clerk | Suficiente | Tres opciones con su dependencia de la decisión 2 |
| 7 CI | Suficiente, con N12 | La consecuencia está; la lista exacta tiene errores |
| 8 Operación sin UI | Suficiente | |
| 9 `regimen_propuesto` | Suficiente | Consecuencia y costo de revertir |
| 10 Configuración que rige | Suficiente | Alternativa y efecto en el paper |

Que estén pendientes no es defecto. Ninguna de las diez impide decidir.

## JUICIO

- (role-plan-reviewer, comparación de plan contra código, confianza alta) B1 está resuelto. La vía elegida no depende del proveedor, y las pruebas fallan si el contrato falta. Que un modelo real cumpla el contrato sigue sin observarse.
- (role-plan-reviewer, confianza alta) I6 está resuelto: el mecanismo coincide con `tenant_session` y el fixture real permite probarlo.
- (role-plan-reviewer, confianza media-alta) N1 es una contradicción literal entre spec y design, y por eso lo pensé como bloqueante. Queda MENOR: es un caso acotado, el criterio de congelado no cambia, no hay riesgo de datos y la corrección es de una línea, sin segunda regla.
- (role-plan-reviewer, confianza media) N3 es el menor de más consecuencia. Queda MENOR porque "se recalcula al cerrar" admite la lectura correcta, y la corrección es una aclaración más un test. Si el constructor no la recibe, el daño sería silencioso en un dato del paper: tiene que ir en su brief.
- (role-plan-reviewer, confianza media-alta) N4 a N7 son defectos de la tabla de mutantes, no del diseño. Por la regla de la sección 8, el constructor los descubriría al aplicarlos, porque el mutante sobreviviría o fallaría por setup.
- (role-plan-reviewer, confianza alta) Las correcciones del intento 4 no agregaron alcance fuera de lo autorizado. La decisión 10 y la exclusión de `regimen_propuesto` son respuestas a preguntas que el intento 3 abrió.

## SUPOSICIÓN

- Que el `INSERT` falle sin policy y con FORCE (N6) sale de la documentación de Postgres; no lo probé.
- T2 vacuo (N5) y F10 sobreviviente (N4) son análisis del plan: esos mutantes no se pueden ejecutar todavía.
- `d7b.py` reproduce mi lectura de D7b. El constructor podría escribirlo distinto, pero el resultado de N1 sale de `evaluar_pedido` real.
- Que Anthropic u otro modelo cerque la salida no lo medí: me baso en el comentario de producción (E8).
- No sé si el texto del codebook explica cuándo es obligatoria una cita ni cómo mapear `d1_verbalizacion` a su sección. El contrato trae claves, no `nombre` ni `cita_requerida_si`. Si no lo explica, habrá más `incompleto`. No lo verifiqué, por no abrir ese texto; aparecería en la primera corrida.
- `es_frontera` de dos anclas: dato del intento 1, sin reverificar.
- No sé qué keys hay en producción ni cuántas anclas hay cargadas.

## Fuentes leídas

Completos: `proposal.md`, `design.md`, `tasks.md`, los tres `specs/*/spec.md`, `informes/propose-3-plan-reviewer.md`, `informes/propose-4-planner.md`, `informes/LEEME.md`.
Código en la revisión indicada: `services/estudio_esquema.py` (240-510), `db/__init__.py`, `services/traza_ciega.py` (74-119 e imports), `services/regimen_llm.py` (rg, 378-395), `services/clients.py` (rg), `routes/estudio_trabajo.py` (118-200, rg), `routes/estudio.py` (708-735, rg), `models/estudio.py` (rg), `tests/integration/conftest.py` (1-130), `tests/integration` (rg), `alembic/versions/20261104_0007` (rg), `apps/ai-gateway/.../providers/base.py` (rg), `routes/complete.py` (196-233), `infrastructure/postgres/init-dbs.sql` (35-54, 63-84). CLAUDE.md global, de proyecto y de repo.
Datos: solo `codebook/esquema_v1.json`, autorizado por el brief. Imprimí claves, valores, `cita_requerida_si` y `reglas_regimen`.
**Firewall:** no abrí contenido, trazas, etiquetas humanas ni veredictos de producción de los 150. No abrí `analisis_produccion/`, `muestra_150.csv`, el texto del codebook ni las anclas. No toqué bases. Sin commits, push ni deploy. No edité el plan.
Lecciones L-NNN: no las busqué de nuevo (el intento 3 informó su ausencia en `docs/`).

## Contaminación por otros informes

Leí por encargo `propose-3-plan-reviewer.md` y `propose-4-planner.md`, y usé la tabla del planner como lista de afirmaciones a comprobar. Reverifiqué contra código B1, D7b, I6 y parte de I9. Reuso sin reverificar del intento 3: E3 (claves de dimensión ausentes del codebook), E6, E8, E12 a E16 salvo lo citado acá. Soy el mismo rol y modelo que escribió los hallazgos que estoy cerrando: no es una segunda opinión independiente, y puedo compartir sus puntos ciegos. No consulté Engram ni informes de otros changes.

## Chequeos no ejecutados

- Suites, baseline, `alembic`, `make check-rls`, `make test-rls`: requieren entorno o base, fuera del encargo.
- Prueba contra ai-gateway o proveedor real: fuera de alcance.
- Lectura de `anclas_v1.json` y del texto del codebook: no necesarias, y evitadas por el firewall.
