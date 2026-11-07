# Informe: propose-4-planner - juez-estudio-codebook-v1

Autor: role-planner, subagente nativo de Claude Code, modelo Claude Sonnet 5.5 (sin tabla "Role executors" en el proyecto). Misma familia que el revisor (Claude); leyó `propose-3-plan-reviewer.md` completo, que es la autoridad de esta vuelta.
Revisión: worktree `agent-a377c2107a7f2b43a`, rama `feat/juez-estudio-codebook-v1`, HEAD `178c343bac96be4f71ac1da4e2bc2b770365d72f`, artefactos sin commitear, 2026-11-06.
Intento: 4 ACOTADO, autorizado por Juani por escrito (tasks.md, "Decisión humana 06/11/2026"). Alcance: solo B1, I1 a I10 y menores de texto. No se rediseñó ni se reabrió nada decidido (opción B, acceso por el estudio, paso a paso, 3 tablas, firewall mínimo).

## EVIDENCIA

- E1 `openspec validate juez-estudio-codebook-v1 --strict --json` (2026-11-06, tras la última edición): `"valid": true`, `issues: []`. Una corrida previa dio 2 WARNING por requisitos de más de 500 caracteres; se acortaron y la segunda corrida quedó limpia. Alcance: formato, no contenido.
- E2 `rg -c "—"` sobre proposal, design, tasks y specs: sin resultados (sin em dashes).
- E3 Lectura de `services/estudio_esquema.py` (líneas 260-510, solo código, sin datos): `evaluar_pedido` levanta 422 con régimen no exento y `regimen_regla is None` (líneas 424-427) y 400 ante claves o `es_frontera` fuera del esquema; `faltantes_cierre` lista `regimen`, `dimension:*`, `cita:*`, `notas`, `confianza` y no lista dimensiones si el régimen está en `dimensiones_opcionales_si_regimen` (líneas 481-509). `regimen_propuesto` es el canal humano de discrepancia (líneas 429-436). Base del orden de D7b.
- E4 `routes/estudio.py:713`: `GET /{clave}/codebook/vigente` devuelve `contenido_md` (VersionOut, línea 456); `services/estudio_codebook.py:37-46` confirma que `contenido_sha256` cubre `{contenido_md, esquema, anclas}`. Base de la verificación de I8.
- No ejecutado: tests, `alembic`, gateway real. No hay código del juez; todo lo dicho sobre su comportamiento es plan, no observación. No se verificaron de nuevo los hechos de código del revisor (E6 a E22 del intento 3) más allá de los citados; los reuso como los reportó.

## Disposición hallazgo por hallazgo

| Hallazgo | Corrección | Dónde quedó |
|---|---|---|
| B1 contrato de salida no llega al modelo | El esquema de salida (`construir_json_schema`) es parámetro de `armar_mensajes`, va en el mensaje de sistema en todos los proveedores y entra al hash. `response_format` json_schema SIN `strict` (mismo sobre que producción), dimensiones no requeridas, la garantía es contrato en el prompt más validador local. Ruta de proveedor (OpenRouter o nativo) anotada en la decisión 2. Fenced ```json no se tolera (declarado). | design Context, D7, D8, D11; spec codificación (escenarios "El contrato de salida viaja en el prompt", "Una respuesta de formato esperado se interpreta", "Sin esquema estricto"); tasks 3.1, 3.4 (b, c, d), 3.5; mutantes B1a a B1d; proposal decisión 2 |
| I1 orden de evaluación | Flujo numerado único (D7b) verificado contra `evaluar_pedido` y `faltantes_cierre` (E3): forma, presencia de dimensiones (con `regimen=None`), citas, coherencia, completitud. Sacada la referencia a "D2 del motor". Escenarios de evidencia insuficiente incluyen `confianza`. | design D7b, D4; spec codificación (requisito y escenarios); tasks 3.3; mutante E1 |
| I2 entre estudios | `ancla_en_muestra(session, episode_id)` sin filtro de estudio (RLS acota el tenant); D5 reescrita (imposible solo dentro de un estudio); también al congelar. | design D5, Context; spec acceso; proposal; tasks 4.1, 4.5; mutante F7 |
| I3 cantidad de anclas | `N_ANCLAS_V1 = 5`: 409 en `POST /corridas`, condición 3 con `n_items`, `distinct ancla` y pares exactos. | design D6, D8; spec acceso y congelado; tasks 4.2, 4.5; mutante P16 |
| I4 sin ajuste por resultados | Límite honesto y regla para el paper movidos a proposal ("Decisión humana"). `motivo` también para el modelo (y no solo espacios). Config guarda `n_modelos_previos`, `n_cambios_tras_cumplir` (cambio tras corrida que ya cumplía) y `corridas_previas`. Una sola config por versión (409 `ya_congelada`, sin corridas nuevas tras congelar), alternativa de reemplazo como decisión 10. Eliminados "Refrescar" y "no solo de variantes". | proposal (Decisión humana, Consecuencia, decisión 10); design D8, D9; spec congelado; tasks 4.2, 4.5; mutantes P11, P19, P20 |
| I5 fragilidad de estabilidad | D8 y decisión 3 explican (a) frontera, (b) referencia cambia, (c) 15 de 15 con caídas transitorias, (d) repetir hasta pasar; regla fijada de antemano para ancla de frontera inestable (no se toca prompt ni modelo, se repite y se declara); rastro `corridas_previas`. Umbral: propuesta 1.0, recomendación 0.8, tope de corridas como opción; elige Juani. | proposal (Decisión humana, decisión 3); design D8 ("Fragilidad de la estabilidad") |
| I6 transacciones de `siguiente` | Tres sesiones y un tramo sin sesión; ningún error HTTP dentro de `tenant_session` con algo por persistir; HTTP de cada aborto fijado (409 con código); cierre con `WHERE estado='en_curso'`; peor caso 95 s. | design D6; spec acceso y codificación; tasks 4.3; mutantes F8, F9, F10 |
| I7 `prompt_sha256` | Hash de `{framing, mensajes_referencia (armado completo), parametros}`; golden de `sha256(FRAMING)` y del `messages` completo; condición 2 compara `parametros` y el hash de cada veredicto. | design D8; spec codificación (escenario de armado/parámetros); tasks 3.6, 4.5; mutantes H1, H2, H3 |
| I8 verificación de `contenido_md` | Definida sobre un solo texto: `sha256(contenido_md UTF-8)` del `GET .../codebook/vigente` contra el archivo elegido; se registra cuál de los dos candidatos y qué recorte. Tarea humana 8.0 y paso 4 del Migration Plan. | design D8, Migration Plan 4; tasks 8.0, 7.3 |
| I9 mutantes y CI | Tabla ampliada (F7 a F10, T1 a T5, C8, B1a a B1d, H1 a H3, E1, E2, P12a/P12b, P16 a P21; acceso por ruta x6); P12 reemplazado por dos mutantes con aserción positiva y negativa; declaradas las garantías sin red si la integración queda como DEUDA y qué queda en `tests/unit/`. | tasks 8.1, 2.3, 5.1, 5.2; design Risks; proposal decisión 7 |
| I10 `regimen_propuesto` | Decidido en el plan por defecto: queda fuera del contrato (el juez aplica la regla; discrepar da `inconsistente`); decisión explícita 9 para Juani con recomendación y consecuencia si lo incluye. | design D7, D13; proposal (What Changes, decisión 9); spec codificación (escenario); tasks 3.1, 3.3; mutante E2 |
| M1 referencias | `8.6`->8.3, `D9`->D10, "decisión 3 de Juani" y "Lo que T-002 le pide" corregidos. | design, proposal |
| M2 testcontainers | Quitado. | tasks 0.3, design Migration Plan 1 |
| M3 abortada en `POST /corridas` | Separado en dos escenarios. | spec acceso |
| M4 doble cierre | `UPDATE ... WHERE estado='en_curso'`, 0 filas sin error. | design D6; tasks 4.3; mutante F10 |
| M5 copia y pegado | Agregados al requisito. | spec codificación |
| M6 `prompt_sha256` al reanudar | Aborto `prompt_distinto` y condición por veredicto. | design D6, D8; spec acceso; tasks 4.3; mutante P21 |
| M7 anclas de la versión de la corrida | `corrida.codebook_version_id`. | design D6; tasks 4.3 |
| M8 test del `FRAMING` | Palabra completa, valores de al menos 6 caracteres, guarda de lista no vacía. | design D8; tasks 3.4(e) |
| M9 timeout y costo | Declarados (40 s menor que 60 s de producción, costo del intento cortado fuera de `cost_usd`, `referencia` del último intento). | design D7 |
| M10 falla transitoria | Declarada en Risks; `corridas_previas` guarda las condiciones falladas. | design Risks, D8 |
| M11 proveedor | D13 compara `proveedores_respondieron` y ruta efectiva. | design D13 |
| M12 residuos y 40 filas | Residuos quitados; motivo de solo espacios -> 422; la tabla ahora tiene más filas y no repite el conteo. | design D8; spec congelado; tasks 8.1 |

## JUICIO

- (role-planner, confianza media-alta) B1 queda cerrado en el plan: el contrato llega por el mensaje de sistema, no depende de `response_format` y se prueba en 3.4 (con un `complete` falso que lee el formato solo de los `messages`) antes de la sección 4. Que eso funcione con un modelo real sigue sin observarse.
- (role-planner, confianza media) La exclusión de `regimen_propuesto` es la opción de menor alcance. Si Juani la revierte, cambia contrato, hash y una columna.
- (role-planner, confianza media) Una sola configuración por versión simplifica el significado de "congelada", pero impide corregir un congelado técnicamente malo sin una versión nueva de codebook; por eso quedó como decisión 10 con alternativa.
- (role-planner, confianza baja) Los números de estabilidad (46%, 53%, 67%) son ilustrativos del revisor, con independencia asumida; no los medí.

## SUPOSICIÓN

- Que un `complete` falso que lee el formato de los `messages` sea un sustituto razonable de "el modelo conoce el formato": no equivale a un modelo real.
- Que el proveedor acepte `json_schema` no estricto con dimensiones no requeridas: producción usa el mismo sobre con otro esquema; no probé este esquema contra un proveedor.
- Que `GET .../codebook/vigente` devuelva exactamente el `contenido_md` guardado (lectura de `VersionOut`, no ejecución).
- `es_frontera` de dos anclas y la distribución de regímenes (intento 1, sin reverificar). No leí las anclas ni el codebook.
- Plan-reviewer del intento 4 debe verificar la regla de que `evaluar_pedido(regimen=None)` no levante con dimensiones parciales: la verifiqué por lectura (rama `pedido_regimen is None` y `derivar_regimen`) y por el E2 del revisor, no por ejecución propia.

## Fuentes leídas

`informes/propose-3-plan-reviewer.md` (completo), `design.md`, `proposal.md`, `tasks.md`, los tres `specs/*/spec.md`, `informes/LEEME.md`. Código, solo lectura: `services/estudio_esquema.py` (260-510), `routes/estudio.py` (rg), `services/estudio_codebook.py` (25-50). CLAUDE.md global, de proyecto y de repo. Lecciones L-NNN: no se buscaron de nuevo (el intento 3 informó su ausencia en `docs/`).
**Firewall:** no abrí contenido, trazas, etiquetas humanas ni veredictos de producción de los 150, ni `analisis_produccion/`, ni el texto del codebook, ni las anclas. No toqué bases. No hice commits, push ni deploy. `## Aprobación` queda vacía.

## Contaminación por otros informes

Leí `propose-3-plan-reviewer.md` por encargo y tomé sus hechos de código (E6 a E22) como dados, salvo los que cité arriba. No releí los informes de los intentos 1 y 2 salvo lo que ya estaba incorporado en los artefactos. No consulté Engram. Mismo modelo y familia que el revisor: no hay independencia de proveedor.

## Chequeos no ejecutados

Suites, `alembic`, `make check-rls`, prueba contra ai-gateway o proveedor, lectura de la base: fuera de alcance y de permiso.
