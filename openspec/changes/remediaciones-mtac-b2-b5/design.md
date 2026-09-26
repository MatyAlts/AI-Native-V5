## Context

Estado verificado del código (leído, no inferido — 2026-09-25):

- `_Dim.presente: bool` (`regimen_llm.py:67`) y el JSON Schema del contrato declara `"presente": {"type": "boolean"}` en las tres dimensiones (`:113,:122,:131`).
- La regla vive en `regimen_segun_regla` (`:168-180`): `a = verbalizacion.presente`; `b = verificacion.presente or justificacion.presente`; `c = not autonomia.oraculo`; REFLEXIVA solo si `a and b and c`.
- Estados terminales: `Estado = Literal["ok","inconsistente","baja_confianza","error_parseo"]` (`:150`). `RegimenLLMResult.regimen` es `None` salvo `ok`.
- `confianza_min: float = 0.70` es **parámetro de `clasificar_regimen_llm`** (`:425`), no constante de módulo.
- El juez solo corre para `SUBGRUPOS_JUZGADOS_POR_JUEZ = {colaborador_reflexivo, colaborador_funcional, desenganchado}` (`:54-56`) — todos con `prompts > 0`. **Un episodio sin diálogo nunca llega al juez.**
- `_EJE_TO_APPROPRIATION` mapea 5 claves a 4 valores (`pipeline.py:78-87`); `sin_clasificar` y `superficial` colisionan en `apropiacion_superficial`. Único uso en `:117`.
- `compute_classifier_config_hash(profile, tree_version="v4.0.0")` (`pipeline.py:41-56`) serializa `{"tree_version","profile"}`. `_TREE_VERSION = "v4.0.0"` también en `routes/health.py:59`, afirmado por `tests/test_health.py:104`.
- `Classification.appropriation` es `String(40)` sin enum de base (`models/__init__.py:78`). Un quinto valor entra **sin migración de columna**.
- `classifier_db` tiene **dos tablas**: `classifications` e `interrater_ratings` (`models/__init__.py:71,:119`). No existe ninguna tabla de revisión humana.
- `needs_review` se escribe en `_marcar_para_revision` (`classify_ep.py:126-136`) y no se lee en ningún lado fuera de tests.
- Rutas existentes del classifier: `POST /classify_episode/{id}`, `GET /classifications/aggregated`, `GET /classifications/{episode_id}`, `/interrater/*`.
- `"/api/v1/classifications": settings.classifier_service_url` ya está en el `ROUTE_MAP` (`api-gateway/routes/proxy.py:61`), y el web-admin consume `/api/v1/classifications/aggregated` a través del gateway — el match es por prefijo.
- El frontend **sí** lee las dimensiones: `EpisodeNLevelView.tsx:418-431` hace `raw.X.presente ? "presente" : "ausente"` para las tres, y `web-teacher/src/lib/api.ts:1324` declara `presente: boolean`.

## Goals / Non-Goals

**Goals**

- Que «no pude evaluar esto» sea un valor persistido y no un `False` indistinguible de «no ocurrió».
- Que la regla determinista sea trivaluada, versionada, y que derive por evidencia insuficiente en vez de inferir.
- Que un episodio no clasificado por el árbol sea legible como tal en la base.
- Que la marca de revisión llegue a un docente y que su anulación quede registrada con historial.
- Que todo lo anterior no rompa el parseo de lo ya persistido.

**Non-Goals**

- Reclasificar históricos. Es operativo, con su propio gate.
- Tocar el hashing de eventos del CTR, los prompts del tutor, o F15.
- Corregir el segundo sumidero (`autonomo`). Se registra, no se toca.
- Cambiar `confianza_min`, los reintentos o el techo de tokens del juez.

## Decisions

### D1 — «no evaluable» deriva; nunca colapsa a ausente

`presente: bool` pasa a `presente: Literal["presente","ausente","no_evaluable"]`, y la regla se evalúa con **Kleene fuerte**: el valor desconocido se propaga **solo cuando cambia el resultado**.

| Situación | Resultado |
|---|---|
| `verbalizacion = ausente` | SUPERFICIAL — determinado, aunque las otras sean `no_evaluable` |
| `verificacion = no_evaluable` pero `justificacion = presente` | el término `b` ya es verdadero → veredicto determinado |
| `verbalizacion = no_evaluable` | **indeterminado** → deriva |
| `verbalizacion = presente`, `verificacion = no_evaluable`, `justificacion = ausente` | **indeterminado** → deriva |

La derivación es un estado terminal nuevo, ~~`evidencia_insuficiente`~~, que se suma a los cuatro de `Estado` y entra por el mismo camino de fallback que ya existe: se conserva la etiqueta del proxy conductual y se marca `needs_review`. **No inventa camino nuevo**: reusa `_marcar_para_revision`.

> **Corrección (auditoría, 2026-09-25): el nombre de arriba está MAL y no se
> implementó así.** `evidencia_insuficiente` es el nombre que la Tabla 3.11
> reserva para el CASO 2 («verdadero, no auditable» — depende de la
> verificación literal de citas, pendiente B4, NO construida). El caso que
> describe ESTE D1 (Kleene indeterminado) es el **caso 4** de la tabla,
> «abstención por traza insuficiente», y el código lo implementó como
> `abstencion_traza_insuficiente` — deliberadamente distinto, para que el
> nombre no mande al próximo lector justo al estado que significa «no
> construido» (`CASO_2_ESTADO_FUTURO_NO_IMPLEMENTADO =
> "derivado_evidencia_insuficiente"` en `regimen_llm.py`). D1 quedó sin
> corregir cuando D2 y D4 sí se corrigieron — esta nota cierra esa brecha. Ver
> el comentario junto a `Estado` en `regimen_llm.py` para la correspondencia
> completa de los seis casos.

**Alternativa rechazada (a): `no_evaluable ≡ ausente`.** Es el status quo con otro nombre. El pendiente pide exactamente lo contrario.

**Alternativa rechazada (b): `no_evaluable ≡ presente` (beneficio de la duda).** Sesga hacia arriba: infla `apropiacion_reflexiva`, que es la categoría más alta. Un error de medición que siempre empuja en la misma dirección es peor que uno que deriva.

**Alternativa rechazada (c): Kleene débil — cualquier dimensión `no_evaluable` deriva.** Más simple de explicar, pero deriva episodios cuyo veredicto ya estaba determinado, e infla la cola de revisión con casos donde no había nada que decidir. Una cola que crece sin motivo es una cola que se deja de mirar, y eso es justo lo que B3+B5 vino a arreglar.

**Costo de revertir**: bajo. La regla se versiona junto al prompt del juez (`PROMPT_VERSION`, hoy `eje_fino_v1.1.0`), y esa versión **ya se persiste** en `features['regimen_llm']['prompt_version']`. Revertir es apuntar a la versión anterior; los veredictos emitidos bajo cada regla siguen siendo recomputables porque dicen bajo cuál se emitieron. **No mueve `classifier_config_hash`**, que cubre solo `{tree_version, profile}` — la regla del juez no está adentro.

### D2 — Se conserva el nombre de campo `presente`, y el parseo acepta booleanos

El campo sigue llamándose `presente` aunque ahora pueda valer `"ausente"`. Un `field_validator(mode="before")` coacciona `True → "presente"` y `False → "ausente"` al deserializar.

La retrocompatibilidad **no es del modelo nuevo hacia atrás nada más**: `features['regimen_llm']['raw']` persistido en JSONB se re-parsea al leer una clasificación vieja, y el frontend lee esas mismas claves.

> **Corrección (QA, 2026-09-25): esta línea era FALSA contra el código, y de ahí
> nació un bug real.** Los validadores de coacción (`_Dim`/`_Autonomia`) solo
> corren cuando el dict pasa por `RegimenLLMRaw.model_validate` — y el único
> lugar de código no-test que hacía eso era `clasificar_regimen_llm`, sobre la
> salida FRESCA del LLM. El endpoint de lectura (`get_current_classification`,
> `classify_ep.py`) devolvía `feats.get("regimen_llm")` — el dict crudo del
> JSONB, **sin pasar por el modelo**. Para V/E/J no se notaba (mismo nombre de
> campo); para autonomía sí, porque el campo legado se llama `oraculo`, no
> `presente` — un registro juzgado bajo `eje_fino_v1.1.0` perdía la dimensión
> en el frontend, en blanco y sin log. **Medido contra la base del piloto
> (2026-09-25): 663 de 689 episodios juzgados (96,2%) tienen la forma legada;
> 26 tienen `raw=None` (juez sin veredicto usable); 0 tienen la forma nueva
> (código todavía no desplegado).**
>
> El fix normaliza en el ÚNICO borde de lectura
> (`normalizar_regimen_llm_persistido` en `regimen_llm.py`, invocado desde
> `classify_ep.py::get_current_classification`): reusa la validación completa
> de `RegimenLLMResult` para que la frase de arriba sea VERDADERA, en vez de
> hacer que el frontend entienda dos formas del mismo dato (`oraculo` y
> `presente`), que es exactamente lo que este D2 quería evitar. Si el dict
> persistido no valida (corrupción), se degrada devolviendo el dict original
> sin romper la lectura — nunca se asume que `raw` es siempre un dict
> navegable, porque el `raw=None` de los 26 casos de `error_parseo` es real.

**Alternativa rechazada: renombrar a `valor` o `estado`.** Obliga a un alias de validación para leer lo viejo, y deja el frontend teniendo que conocer dos formas del mismo dato. El nombre queda un poco torcido (`presente: "ausente"`); el costo de la alternativa es un campo más que puede desincronizarse.

**Alternativa rechazada: agregar un campo nuevo al lado del booleano.** Dos campos que pueden contradecirse, y ninguna regla que diga cuál gana.

### D3 — El tercer valor tiene que llegar a la pantalla

`EpisodeNLevelView.tsx:418-431` construye `estado: raw.X.presente ? "presente" : "ausente"`. Si esto no se toca, «no evaluable» se dibuja como «ausente» y **el colapso que la change elimina en la base se reintroduce en la UI**, que es donde el docente realmente lee el episodio.

Es parte del alcance, no una mejora opcional.

### D4 — CORREGIDA: `autonomia` también es trivaluada (las CUATRO dimensiones)

> **Corrección post-Tabla 3.11 (2026-09-25).** La versión original de esta
> decisión (texto conservado más abajo) suponía que `autonomia.oraculo` podía
> quedar booleana. La **Tabla B.2** de la tesis (`tabla-3.11-de-la-tesis.md`,
> transcripta literal y adjunta a este change) define explícitamente un valor
> `no evaluable` para Autonomía: «no hay propuestas del asistente sobre las
> que observar la conducta, o el registro está incompleto». El argumento
> estructural de la versión original — «el juez solo corre sobre subgrupos con
> `prompts > 0`» — prueba que hay transcripción del ALUMNO, pero no prueba que
> haya **propuestas del ASISTENTE** que el alumno pueda cuestionar o aceptar.
> Esas son dos cosas distintas, y la tabla trivalúa la segunda. D4 queda
> revertida: las CUATRO dimensiones (V, E, J, A) son trivaluadas, con la misma
> forma (`presente: Literal["presente","ausente","no_evaluable"]`). El campo
> `oraculo: bool` se retiene solo como formato LEGADO para retrocompatibilidad
> de lectura (D2), con la traducción de sentido invertida: `oraculo=True`
> (comportamiento oráculo) → `presente="ausente"`; `oraculo=False`
> (interlocutor) → `presente="presente"`.

---

**Texto original de D4 (superado, se conserva por trazabilidad — NO vigente):**

~~El pendiente habla de «presente/ausente/no evaluable», que son valores de una afirmación de presencia. `oraculo` no lo es: afirma un modo de interacción, no la presencia de un marcador.~~

~~El argumento que cierra la decisión es estructural: el juez **solo corre sobre subgrupos con `prompts > 0`**. Siempre hay transcripción para juzgar si el tutor operó como oráculo. El caso «no hay con qué evaluarlo» no es alcanzable por construcción.~~

~~**Alternativa rechazada: trivaluar las cuatro por simetría.** Agranda el radio de impacto (JSON Schema, prompt, frontend, tests) para cubrir un caso que el gate de subgrupos ya excluye. Queda como pregunta abierta si en el futuro el juez se extiende al brazo sin tutor.~~

### D5 — `sin_clasificar` se persiste como su propio valor, y los consumidores lo tratan explícitamente

`_EJE_TO_APPROPRIATION["sin_clasificar"]` pasa a `"sin_clasificar"`. La columna es `String(40)` sin enum: **no hay migración de esquema**. Lo que sí hay es un quinto valor circulando por κ, el mapa ordinal de CII longitudinal, el export académico y tres frontends.

El mapa ordinal (`APPROPRIATION_ORDINAL`: delegacion=0, superficial=1, reflexiva=2) **no tiene posición para este valor y no debe tenerla**: no es un punto del continuo, es la ausencia de medición. Los cálculos que ordenan excluyen explícitamente el valor nuevo, del mismo modo que el CII longitudinal ya excluye TPs huérfanas. Un `KeyError` sería preferible a un cero silencioso, pero lo correcto es la exclusión declarada.

**Alternativa rechazada: dejar `apropiacion_superficial` y marcar `needs_review`.** Radio de impacto casi nulo, y por eso es tentadora. Pero la etiqueta en la base sigue siendo falsa, y es la que la tesis cita. El pendiente no pide señalizar el problema: pide que el episodio no clasificado no se cuente como una categoría del continuo.

**Costo de revertir**: alto y asimétrico. Revertir el mapeo es una línea, pero las clasificaciones escritas bajo el `tree_version` nuevo ya llevan el hash nuevo, y volver atrás las deja con un hash que no corresponde a ninguna configuración vigente.

### D6 — El bump de `tree_version` es deliberado y se hace en un solo lugar

`v4.0.0 → v4.1.0`. El valor vive en **dos** sitios que hay que mover juntos: el default de `compute_classifier_config_hash` (`pipeline.py:41`) y `_TREE_VERSION` (`routes/health.py:59`), más el test que afirma el valor (`tests/test_health.py:104`).

Esto **sí** mueve `classifier_config_hash` — a propósito, porque la etiqueta que produce el árbol cambió. B2a no lo mueve; B2b sí. Que sean la misma change es lo que obliga a que los tests de reproducibilidad bit-a-bit (`test_pipeline_reproducibility.py`, 13 tests) se corran separando ambos efectos: el hash debe ser idéntico antes y después de B2a, y distinto y estable después de B2b.

**Alternativa rechazada: `v5.0.0`.** El precedente del repo (`LABELER_VERSION`) reserva el major para cambios semánticos de criterio. Acá el árbol no cambió de criterio: dejó de mentir sobre lo que ya decidía.

### D7 — La revisión humana es una tabla append-only nueva, no una columna

Tabla `classification_reviews` en `classifier_db`, con `tenant_id` y policy RLS activa (ADR-001, no negociable), append-only como el resto del plano pedagógico (ADR-010). Cada fila: episodio, clasificación revisada, revisor, veredicto humano, motivo, timestamp. **El historial es la tabla**: corregir una revisión es una fila nueva, nunca un UPDATE.

**Alternativa rechazada: reusar `interrater_ratings`.** Esa tabla existe para calibración intercoder (κ) sobre una muestra dirigida, con su propio vocabulario y su propio protocolo. Mezclar anulaciones operativas con ratings de calibración contamina el cálculo de κ, que es un resultado de la tesis.

**Alternativa rechazada: columnas nuevas en `classifications`.** Rompe append-only: revisar exigiría un UPDATE sobre una fila que la cadena trata como inmutable.

### D8 — Los endpoints nuevos van bajo `/api/v1/classifications`, y por eso el gateway no se toca

`GET /api/v1/classifications/review-queue` y `POST /api/v1/classifications/{episode_id}/review`. El prefijo ya está en el `ROUTE_MAP` (`proxy.py:61`) y el proxy resuelve por prefijo — evidencia: el web-admin consume `/api/v1/classifications/aggregated` a través del gateway hoy.

**Alternativa rechazada: un prefijo propio `/api/v1/review`.** Más legible, y obliga a una entrada nueva en el `ROUTE_MAP`. Sin esa entrada el endpoint queda inalcanzable desde frontend y el fallo es silencioso — es un gotcha documentado del repo. No vale la legibilidad.

## Risks / Trade-offs

**El juez emite más derivaciones de las esperadas y la cola crece** → D1 elige Kleene fuerte justamente para que solo derive cuando el desconocido decide. Aun así, la primera corrida sobre el piloto hay que medirla antes de asumir el volumen: si deriva mucho más que los 40 actuales, el problema es el prompt del juez, no la regla.

**El quinto valor de `appropriation` rompe un consumidor que nadie recordaba** → hay ~20 sitios de código real (más docs y tests) que mencionan los valores. El riesgo no es un crash: es un `.get(valor, 0)` que lo cuenta como otra cosa. Mitigación: la tarea de rastreo de consumidores es explícita y precede al cambio del mapeo.

**El hash nuevo deja todo el corpus con hash legacy** → ya hay 106 clasificaciones en esa situación, bloqueadas por el mismo trabajo operativo. Esta change agranda ese backlog en vez de crearlo, y lo dice en vez de esconderlo.

**La anulación humana cambia la etiqueta que la tesis cita** → por eso está declarada como decisión que requiere aprobación humana, y no se resuelve acá.

**«No evaluable» se convierte en el cajón de sastre del juez** → si el prompt no dice con precisión cuándo corresponde, el modelo lo va a usar para todo lo dudoso. El prompt tiene que definirlo por lo que falta (no hay transcripción que citar sobre esa dimensión), no por la confianza del modelo — para eso ya está `confianza_min`.

## Migration Plan

1. **B2a sin efecto observable**: modelo trivaluado + retrocompatibilidad de parseo, con la regla todavía produciendo los mismos veredictos. El hash no se mueve y los 13 tests de reproducibilidad lo prueban.
2. **B2a con efecto**: regla trivaluada, estado terminal nuevo, prompt y JSON Schema del juez, versión de la regla.
3. **B2a en la UI**: tercer estado en el frontend.
4. **B3+B5**: tabla, migración, endpoints, pantalla. Es aditivo puro — no cambia el comportamiento existente.
5. **B2b, último y solo**: mapeo, bump de `tree_version`, guardas en los consumidores. Es el único paso que mueve el hash, y va aislado para que el diff que lo mueve sea legible.

**Rollback**: los pasos 1–4 revierten con un redeploy sin tocar datos. El paso 5 no: ver D5.

## Open Questions

**¿Cuáles son los seis casos de la Tabla 3.11?** El pendiente pide pruebas unitarias sobre ellos y la tabla no está en el repo. Es entrada bloqueante de la fase de specs. Si no se aporta, los casos se derivan de la matriz de D1 y eso queda declarado como supuesto — no como cumplimiento del pendiente.

**¿La anulación humana reemplaza la etiqueta oficial o queda al lado?** Reemplazar respeta el espíritu de B5 («registro de anulación humana para todas las rutas») y respeta append-only creando una `Classification` nueva con marca de procedencia humana. Quedar al lado no toca el corpus pero deja al docente revisando algo que no cambia nada, y eso vacía la funcionalidad. **Recomendación: reemplazar, con marca explícita de procedencia y reversible por otra fila.** No es decisión del implementador.

**¿Qué rol puede anular?** El repo tiene Casbin con 4 roles. Docente, docente_admin y superadmin son candidatos; el estudiante no. Requiere policies nuevas en el seed y un bump del conteo.

**¿El episodio `sin_clasificar` entra o no al muestreo intercoder?** Hoy `/interrater/sample` filtra por los 5 subgrupos con prompts. Con el valor nuevo hay que decidir si un episodio no clasificado es material de calibración o ruido.
