# ADR-062 — Regla trivaluada (Kleene fuerte) en el juez semántico y bump de `tree_version` a v4.1.0

- **Estado**: Propuesto
- **Fecha**: 2026-09
- **Deciders**: Alberto Cortez, director de tesis (criterio académico). Juani Sarmiento (implementación).
- **Tags**: clasificador, reproducibilidad, llm, datos, tesis
- **Relacionado**: [ADR-057](057-juez-llm-clasificador-oficial-y-eje-autonomo.md) — fija el contrato v4.0.0 (juez LLM como clasificador oficial, eje `autonomo`). Este ADR lo **modifica en dos puntos** y no lo reemplaza: ADR-057 sigue siendo la decisión vigente sobre quién gobierna la etiqueta y qué dejó de ser reproducible bit-a-bit.

## Contexto y problema

Bajo v4.0.0 (ADR-057) el juez emite cuatro dimensiones —Verbalización, Verificación,
Justificación, Autonomía— y una regla determinista en código (`regimen_segun_regla`)
deriva el régimen de ellas. Esa regla era **booleana**: `_Dim.presente: bool`, con
`REFLEXIVA` si `V ∧ (E ∨ J) ∧ ¬oráculo`.

Un booleano tiene dos valores y el instrumento necesita tres. `presente=False`
significaba a la vez **«la dimensión no ocurrió»** —que es una medición— y
**«no pude evaluarla»** —que es la ausencia de medición—. Las dos colapsaban en el
mismo `False`, y ese `False` alcanzaba para emitir `apropiacion_superficial`
automáticamente. El sistema producía etiquetas definitivas sobre episodios que
nunca había podido juzgar.

La **Tabla 3.11 de la tesis** (transcripta en
`openspec/changes/remediaciones-mtac-b2-b5/tabla-3.11-de-la-tesis.md`) especifica
seis casos y un estado terminal para cada uno. El código tenía cuatro estados
(`ok`, `inconsistente`, `baja_confianza`, `error_parseo`) y **ninguno** correspondía
al caso 4, «abstención por traza insuficiente»: la regla escrita en la tesis no
estaba implementada.

El mismo defecto aparecía una capa más arriba, en el árbol determinista:
`_EJE_TO_APPROPRIATION["sin_clasificar"]` apuntaba a `apropiacion_superficial`, así
que un episodio que el árbol declaraba explícitamente no clasificable se persistía
con la etiqueta de una apropiación superficial detectada. Medición contra producción
del 26/09/2026: **131 episodios, el 29% de las 449 superficiales vigentes**. Y la
degradación tenía dirección — caía en la categoría del medio, que es exactamente
donde se concentran las discrepancias entre codificadores humanos: el ruido se
inyectaba en la frontera más disputada del instrumento.

## Drivers de la decisión

- La Tabla 3.11 es **fuente normativa**, no una mejora deseable. El caso 4 estaba escrito y sin implementar.
- Un error de medición que **siempre empuja en la misma dirección** es peor que uno que deriva a revisión: sesga el resultado en vez de declararlo incierto.
- La etiqueta que la tesis cita no puede contener no-mediciones mezcladas con mediciones.
- Si la etiqueta que el árbol produce cambia, el `classifier_config_hash` tiene que cambiar con ella (ADR-020): dos corpus con el mismo hash y etiquetas distintas rompen la auditabilidad que sostiene el piloto.

## Opciones consideradas

### Opción A — Kleene fuerte (elegida)

El valor desconocido se propaga **solo cuando cambia el resultado**. Una dimensión
`ausente` que ya hace falsa la fórmula determina el veredicto aunque las demás sean
`no_evaluable`; el desconocido gana únicamente cuando sin él no hay respuesta.

Es lo que la tesis dice: el caso 3 de la Tabla 3.11 deriva `SUPERFICIAL` con
«V ausente, o A ausente, o E y J ambas ausentes, **cualquiera sea el valor de las
restantes**».

### Opción B — Kleene débil: cualquier dimensión `no_evaluable` deriva

Más simple de explicar y de implementar. Descartada porque **deriva episodios cuyo
veredicto ya estaba determinado** e infla la cola de revisión con casos donde no
había nada que decidir. Una cola que crece sin motivo es una cola que se deja de
mirar, y la cola de revisión es precisamente lo que B5 vino a construir: la habríamos
entregado ya inutilizable.

### Opción C — `no_evaluable ≡ ausente`

El status quo con otro nombre. Descartada: es exactamente el defecto que motiva
este ADR.

### Opción D — `no_evaluable ≡ presente` (beneficio de la duda)

Descartada porque sesga hacia arriba: infla `apropiacion_reflexiva`, la categoría
más alta del continuo. Entre dos errores sistemáticos, el que deriva a revisión es
auditable y el que asciende no.

### Sobre el número de versión: v4.1.0 y no v5.0.0

El precedente del repo (`LABELER_VERSION`) reserva el major para un cambio semántico
de criterio. Acá el árbol **no cambió de criterio**: dejó de mentir sobre lo que ya
decidía. Minor.

## Decisión

Opción elegida: **A**, más el bump correspondiente.

1. **Las cuatro dimensiones son trivaluadas**: `Literal["presente","ausente","no_evaluable"]`, incluida Autonomía. Autonomía se había supuesto booleana porque el juez solo corre sobre subgrupos con `prompts > 0`, pero la Tabla B.2 admite `no evaluable` para A —«no hay propuestas del asistente sobre las que observar la conducta»—, y que el estudiante haya escrito prompts no garantiza que el asistente haya propuesto algo que cuestionar.
2. **La regla es Kleene fuerte** (`_kleene_desde_dim`/`_kleene_and`/`_kleene_or` en `regimen_llm.py`) y devuelve `REFLEXIVA | SUPERFICIAL | INDETERMINADO`.
3. **Estado terminal nuevo `abstencion_traza_insuficiente`** (caso 4). Rutea por el fallback que ya existía (`_marcar_para_revision`): se conserva la etiqueta del proxy conductual y se marca `needs_review`. No inventa camino nuevo.
4. **La regla se versiona con el prompt**: `PROMPT_VERSION` pasa de `eje_fino_v1.1.0` a `eje_fino_v1.2.0`, y esa versión **ya se persiste por veredicto** en `features['regimen_llm']['prompt_version']`. Cada veredicto dice bajo qué regla se emitió, así que revertir la regla no invalida lo ya clasificado. `PROMPT_VERSION` **no entra** al `classifier_config_hash`, que cubre solo `{tree_version, profile}`.
5. **`sin_clasificar` pasa a ser su propio valor de `appropriation`** (quinto), excluido del mapa ordinal de progresión por no ser un punto del continuo sino la ausencia de medición.
6. **`tree_version` sube `v4.0.0 → v4.1.0`**, porque el punto 5 cambia la etiqueta que el árbol produce.

## Qué queda fuera de alcance, y por qué

**Los casos 2 y 5 de la Tabla 3.11 no se implementan.** Los dos dependen de la
**verificación literal de citas** (pendiente B4), que no está construida en este
repo: el caso 2 exige distinguir una dimensión portadora *con* cita verificada de
una *sin* ella, y el caso 5 exige detectar una cita no localizable o atribuida a un
turno del tutor. Sin ese verificador no hay camino de código que pueda producir
ninguno de los dos estados.

Sus nombres **sí** existen en el código, como constantes con nombre explícito
(`CASO_2_ESTADO_FUTURO_NO_IMPLEMENTADO = "derivado_evidencia_insuficiente"`,
`CASO_5_ESTADO_FUTURO_NO_IMPLEMENTADO = "salida_invalida"`), para que el día que B4
se construya el estado ya tenga el nombre que fija la tesis y no se improvise otro.
Pero **no están en `Estado`** ni en ningún `Literal` vivo: un valor declarado como
válido sin un camino de código que lo produzca sería documentación disfrazada de
contrato, y el próximo lector lo leería como una capacidad existente.

Esa brecha está medida, no estimada. La auditoría de citas del 25/09/2026 encontró
**2 citas del tutor atribuidas al estudiante** (episodio `339ee925`) y **9 no
localizables** sobre 224 emitidas, ninguna de las cuales produce hoy salida
inválida; y el esquema exige 380 citas sobre 95 episodios con 224 emitidas (59%),
que es la población que el caso 2 mandaría a revisión.

El nombre del estado nuevo se eligió con esto en mente: el caso 4 se llama
`abstencion_traza_insuficiente` y **no** `evidencia_insuficiente`, que es el nombre
que la tabla reserva para el caso 2. Un nombre que mande al próximo lector al estado
que significa «no construido» es peor que uno largo.

## Consecuencias

### Positivas

- «No pude evaluar esto» es un valor persistido y auditable, no un `False` indistinguible de «no ocurrió».
- El caso 4 de la Tabla 3.11 deja de ser una regla escrita y sin implementar.
- Los episodios no clasificados salen de `apropiacion_superficial`: la categoría del medio deja de recibir 131 episodios que nunca se juzgaron.
- Cada veredicto es recomputable contra la regla bajo la que se emitió, porque la versión viaja con él.

### Negativas / trade-offs

- **El bump deja todo el corpus con hash legacy.** El hash de referencia pasó de `28e111aec4c5ec470bc8836cd716f563f41639d043d79bc95dca7da99e62b774` a `56f3905858c19def2f20741a03378e9d5e3dfe1a4f0e4dd75d7440367fdc1180`. Eso se suma a un backlog que **ya estaba abierto**: 106 clasificaciones con hash legacy `9dd96894...` (pre-`LABELER_VERSION` 1.2.0), bloqueadas por la acción A1 del plan. Este ADR **agranda ese backlog y lo declara** en vez de esconderlo; no lo crea.
- El juez va a derivar más episodios a revisión que antes. Kleene fuerte acota cuántos, pero el volumen real de la primera corrida sobre el piloto hay que medirlo: si deriva mucho más de lo esperado, el problema está en el prompt del juez —que tiene que definir `no_evaluable` por lo que falta y no por la confianza del modelo— y no en la regla.
- El quinto valor de `appropriation` circula por κ, el export académico, analytics y los tres frontends. El riesgo no es un crash sino un conteo silenciosamente mal.

### Neutras

- `Classification.appropriation` es `String(40)` sin enum: el quinto valor entra **sin migración**.
- `PROMPT_VERSION` y el veredicto completo ya se persistían en `features` (JSONB): sin migración.

## Lo que NO se hizo, con su motivo

**No se reclasificaron los 131 episodios ya persistidos como superficiales.** Corre
contra la base real del piloto y tiene **gate operativo aparte**, por decisión
explícita del autor el 26/09/2026: cambiar etiquetas que la tesis cita no puede
pasar como efecto secundario de un merge. Queda abierto junto con el backlog de
hash legacy.

**No se tocó el segundo sumidero.** El eje `autonomo` se lleva **21 de 105**
episodios del conjunto de referencia donde los **dos codificadores humanos sí
coincidieron** en superficial-o-reflexiva, y el acuerdo entre ellos sobre esa rama
es **0,160 con intervalo que cruza el cero**. Es el mismo patrón que este ADR
corrige para `sin_clasificar` —episodios desviados a una categoría que no los
describe— pero con una diferencia que lo saca de alcance: la corrección exige
decidir qué es `autonomo` como constructo, y eso es una decisión académica sobre el
instrumento, no un mapeo mal escrito. Registrado con sus mediciones, no arreglado.

## Referencias

- [ADR-057](057-juez-llm-clasificador-oficial-y-eje-autonomo.md) — contrato v4.0.0: el juez gobierna la etiqueta, eje `autonomo`, y qué dejó de ser reproducible bit-a-bit.
- [ADR-020](020-event-labeler-n-level.md) — `classifier_config_hash` determinista y disciplina de versionado.
- [ADR-010](010-append-only-clasificaciones.md) — append-only / reclasificación por `is_current`.
- [ADR-018](018-cii-evolution-longitudinal.md) — CII longitudinal ordinal; el criterio de exclusión que `sin_clasificar` reusa.
- `openspec/changes/remediaciones-mtac-b2-b5/tabla-3.11-de-la-tesis.md` — transcripción literal de la Tabla 3.11 y de la Tabla B.2 (definiciones operativas de cada valor de cada dimensión).
- `openspec/changes/remediaciones-mtac-b2-b5/design.md` — D1 (regla trivaluada), D4 corregida (autonomía), D5 (`sin_clasificar`), D6 (bump).
