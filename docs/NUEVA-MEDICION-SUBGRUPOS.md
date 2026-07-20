# Nueva medición de apropiación — 4 dimensiones / 7 subgrupos (Fase 0)

> **Artefacto Fase 0** de la tarea B1 del [`ROADMAP-EQUIPO-2026-06-10`](../../../Descargas/ROADMAP-EQUIPO-2026-06-10.md).
> Estado: **modo sombra** (dato al lado del oficial, NO pisa, NO bumpea `LABELER_VERSION`).
> Origen: corrige la inversión del constructo documentada en `_monitoring/ANALISIS-CLASIFICACION-APROPIACION.md`.

## El problema que arregla

El clasificador actual (`tree.py` v2.0.0) colapsa al alumno en un eje y tiene una **inversión confirmada en código**: un alumno que programó solo, **sin usar el tutor**, queda marcado como `delegacion_pasiva` (el que más delegó). Mecanismo: sin `prompt_enviado` ni `anotacion_creada`, cada `codigo_ejecutado` es huérfano → `ccd_orphan_ratio=1.0`; y sin prompts el balance de CT colapsa → `ct_summary<0.65`. El árbol (`tree.py:92`) lo manda a `delegacion_pasiva`. Es el opuesto exacto del constructo.

Además: `apropiacion_superficial` es el **default residual** (absorbe falsos negativos de reflexiva) y `apropiacion_reflexiva` **sub-detecta** (exige verbalización escrita rápida y posterior a cada acción).

## La solución: 2 capas

- **Abajo (motor real):** 7 subgrupos sobre **4 dimensiones independientes y observables**.
- **Arriba (presentación):** los 3 ejes de siempre (delegación / superficial / reflexiva) como **roll-up** del subgrupo (opción A) — coherentes, derivados, no la salida cruda del motor viejo.

## Las 4 dimensiones (todas salen de eventos CTR que ya se capturan)

Cada una en `[0,1]`. Umbrales y escalas marcados **🔧 calibrable** — se ajustan con la corrida real (igual que el 50/50 de CT que los autores ya marcaron arbitrario en `ct.py:56`).

| Dim | Qué responde | Fórmula v1 |
|---|---|---|
| **1. Autonomía** | ¿solo o apoyado en IA? | `0.5·(1 − min(1, prompts/PROMPT_SCALE)) + 0.5·(1 − copy_ratio)` · `copy_ratio = edicion_codigo[origin=copied_from_tutor]/total_ediciones`. 1.0 = autónomo puro. |
| **2. Experimentación** | ¿corre, prueba, itera? | `min(1, (codigo_ejecutado + tests_ejecutados)/EXEC_SCALE)` |
| **3. Persistencia** | ¿empuja al trabarse? | tras `tests_ejecutados.failed>0`: `recuperaciones/fallos`; sin fallos → 1.0 (no se trabó) |
| **4. Foco** | ¿concentrado? | `1/(1 + (pestana_perdida + copia_intentada)/FOCUS_SCALE)` |

(+ resultado: `resolvio = tp_entregada OR último tests_ejecutados.failed==0`)

## El árbol de 7 subgrupos + el fix de la inversión

```
0. ¿pocos eventos / episodio muy corto?           → INDETERMINADO 🔒  (sin clasificar)

1. prompts == 0  (trabajó sin IA)  ── FIX INVERSIÓN: sin prompts, delegar es imposible
   ├── resolvio  → AUTÓNOMO COMPETENTE ⭐  → Reflexiva   (no necesitó ayuda: darle más desafío)
   └── ¬resolvio → AUTÓNOMO TRABADO 🆘     → Superficial (ofrecer scaffolding, NO delegó)

2. prompts > 0   (usó el tutor)
   ├── experimentación muy baja + poca actividad   → DESENGANCHADO 💤        → Superficial
   ├── copy_ratio ≥ DEP_COPY  y  experimentación baja → DEPENDIENTE/DELEGADOR ⚠️ → Delegación (la REAL)
   ├── verbaliza  y  experimentación ≥ REFLEX_EXP   → COLABORADOR REFLEXIVO ✅ → Reflexiva
   └── (resto)                                       → COLABORADOR FUNCIONAL    → Superficial
```

`verbaliza = hay anotacion_creada OR prompt_enviado con prompt_kind reflexivo` (mismos kinds que `ccd.py`).

## Umbrales iniciales (🔧 calibrables con la corrida real)

| Constante | v1 | Significado |
|---|---|---|
| `PROMPT_SCALE` | 6 | nº de prompts que satura el componente "apoyo" |
| `EXEC_SCALE` | 8 | nº de ejecuciones que satura experimentación |
| `FOCUS_SCALE` | 3 | distracciones que bajan foco a 0.5 |
| `MIN_EVENTS` | 4 | mínimo de eventos significativos para clasificar (sino INDETERMINADO) |
| `DEP_COPY` | 0.5 | copy_ratio para considerar dependencia |
| `DEP_EXP` | 0.4 | experimentación por debajo de la cual la dependencia se confirma |
| `REFLEX_EXP` | 0.4 | experimentación mínima para colaborador reflexivo |
| `DESENGANCHE_EXP` | 0.2 | experimentación por debajo de la cual + poca actividad = desenganchado |

## Salvedad de reproducibilidad (tesis)

Mientras el subgrupo sea **dato extra al lado** del clasificador oficial (modo sombra), NO toca `classifier_config_hash`, NO bumpea `LABELER_VERSION`, NO rompe la reproducibilidad del piloto-1. La decisión de oficializar (reemplazar) se toma DESPUÉS, con el delta de la corrida real en la mano, y ahí sí va `LABELER_VERSION 2.0.0` + re-clasificar.

---

## Ajustes por datos reales de prod (2026-06-10)

Al correr contra `ctr_store` de prod (305 episodios cerrados), el modelo de eventos asumido (sacado del código + seed) **no coincidía con la realidad**. Ajustes aplicados al script y a esta spec:

| Asumíamos | Real en prod | Ajuste |
|---|---|---|
| `edicion_codigo.origin == copied_from_tutor` | origin = `student_typed` / `pasted_external` (no existe copied_from_tutor) | autonomía usa `pasted_external`; delegación se mide por `solicitud_directa` |
| `anotacion_creada` = fuente de verbalización | **0 anotaciones en toda la historia** | reflexión se infiere del comportamiento de código, no de verbalización escrita |
| `tests_ejecutados` / `tp_entregada` marcan resultado | no existen como evento CTR | `resolvió` = última `codigo_ejecutado` limpia (stdout sin stderr) |
| una anti-trampa (`copia_intentada`) | existen DOS: `copia_intentada` + `pega_intentada` | foco suma ambas |

**`resolvió` refinado:** la ÚLTIMA ejecución terminó limpia (no "alguna vez le anduvo").

**8º subgrupo (agregado por calibración):** **Escribió sin validar 📝** — ≥10 ediciones pero
casi sin ejecutar (escribió código y no lo probó). Roll-up → superficial. Acción: fomentar el
hábito de ejecutar/probar. (Confirmado con datos: ejecutar funcionaba; fue elección del alumno.)

**Reglas de actividad calibradas:**
- **Desenganchado 💤** = trabajó poco EN GENERAL (<10 ediciones Y <2 ejecuciones). Editar mucho ya es trabajo.
- **Autónomo trabado 🆘** = ejecutó ≥2 veces sin lograrlo (peleó) → scaffolding (panel docente; tutor proactivo = tarea futura en `tutor-service`).
- En la rama con-tutor, la delegación se evalúa ANTES que "poco trabajo" (el delegador labura poco *porque* copia).

## Distribución final sobre datos reales de prod (307 episodios cerrados, 2026-06-10)

| Subgrupo | eps | eje |
|---|---|---|
| Autónomo competente ⭐ | 72 | reflexiva |
| Colaborador reflexivo ✅ | 49 | reflexiva |
| Escribió sin validar 📝 | 62 | superficial |
| Autónomo trabado 🆘 | 24 | superficial |
| Desenganchado 💤 | 37 | superficial |
| Colaborador funcional | 22 | superficial |
| Dependiente/delegador ⚠️ | **1** | delegación |
| Indeterminado 🔒 | 40 | — |

**El hallazgo central, cuantificado:** el motor viejo marcaba ~224 episodios como
`delegacion_pasiva`. La medición nueva encuentra **1 (un) delegador real en 307 episodios**.
La medición vieja no estaba sesgada — estaba **invertida**. Eje agregado: 121 reflexiva /
145 superficial / 1 delegación / 40 indeterminado. Umbrales (`EDIT_MIN=10`, `TRABADO_MIN_EJEC=2`,
`DEP_SOLICITA=2`) calibrados sobre estos datos; revisables con más pilotos.

---

## Contrato del endpoint (para el frontend — Neyen)

El endpoint de clasificación devuelve, además del eje de siempre, el subgrupo y las 4 dimensiones.
**El `eje` ya viene derivado del subgrupo (roll-up, opción A)** — el front NO calcula nada, solo muestra.

```json
{
  "episode_id": "...",
  "eje": "reflexiva",          // reflexiva | superficial | delegacion_pasiva | sin_clasificar
  "subgrupo": { "key": "autonomo_competente", "label": "Autónomo competente", "accion_docente": "Darle más desafío" },
  "dimensiones": { "autonomia": 0.8, "experimentacion": 0.6, "persistencia": 0.7, "foco": 0.9 },
  "resultado": { "resolvio": true }
}
```

Los 8 `key` posibles + su roll-up al eje:

| key | label | acción docente | eje |
|---|---|---|---|
| `autonomo_competente` | Autónomo competente ⭐ | Darle más desafío | reflexiva |
| `colaborador_reflexivo` | Colaborador reflexivo ✅ | Va bien | reflexiva |
| `escribe_sin_validar` | Escribió sin validar 📝 | Fomentar ejecutar/probar | superficial |
| `autonomo_trabado` | Autónomo trabado 🆘 | Ofrecer scaffolding | superficial |
| `desenganchado` | Desenganchado 💤 | Re-enganchar | superficial |
| `colaborador_funcional` | Colaborador funcional | Empujar a profundizar | superficial |
| `dependiente_delegador` | Dependiente/delegador ⚠️ | Intervenir | delegacion_pasiva |
| `indeterminado` | Indeterminado 🔒 | No concluir (episodio corto) | sin_clasificar |

> **Modo sombra:** mientras el subgrupo sea dato al lado del oficial, el endpoint puede exponerlo
> como campo adicional sin tocar la clasificación vigente. El front muestra eje + subgrupo + 4 barras.
