# ADR-057 — Juez LLM como clasificador oficial, eje `autonomo` y motor OpenRouter

- **Estado**: Propuesto
- **Fecha**: 2026-06
- **Deciders**: Alberto Cortez, director de tesis
- **Tags**: clasificador, reproducibilidad, datos, llm, prod

## Contexto y problema

Hasta `tree_version` v3.1.0 la etiqueta oficial de apropiación (`Classification.appropriation`)
se derivaba de forma **pura y determinista** del árbol de subgrupos sobre los eventos del
episodio, y el `classifier_config_hash` (`{tree_version, profile}`) garantizaba reproducibilidad
bit-a-bit (ADR-020). El "juez LLM" del eje fino (`services/regimen_llm.py`) corría en **modo
sombra**: leía la conversación para distinguir REFLEXIVA vs SUPERFICIAL en la zona gris, pero
su veredicto se guardaba en `features['regimen_llm']` de forma **informativa** y NO gobernaba
la etiqueta.

Tres cambios de producto motivan esta decisión:

1. **Promover el juez a clasificador principal**: que el veredicto del juez gobierne la etiqueta
   oficial para los episodios *con-tutor no-delegación*, reemplazando el proxy conductual
   `exp >= 0.4` (frágil: distinguía reflexiva/superficial por cantidad de actividad).
2. **Eje `autonomo`**: pre-filtrar los episodios donde el alumno NO habló con el tutor
   (`prompts == 0`) hacia un 4º eje ortogonal, para que los 3 ejes del continuo de apropiación
   contengan únicamente episodios con conversación real.
3. **OpenRouter como motor LLM principal**: ruteo global de los modelos por OpenRouter
   (el juez sigue usando Gemini 2.5 Flash, ahora vía `google/gemini-2.5-flash`).

El problema central: **el juez introduce no-determinismo en la etiqueta oficial**, y el
`classifier_config_hash` NO captura ni el modelo del juez ni su `PROMPT_VERSION`. Esto tensiona
la invariante de reproducibilidad bit-a-bit que sostiene la aceptabilidad doctoral del piloto.

## Drivers de la decisión

- Validez de constructo: el proxy conductual tiene κ ≈ 0 en la zona gris; el juez por contenido
  alcanza κ 0,68. La distinción reflexiva/superficial mejora sustancialmente.
- Limpieza de la taxonomía: mezclar autónomos (sin conversación) en los 3 ejes contamina el
  análisis del continuo de apropiación.
- Reproducibilidad doctoral (ADR-020): no se puede romper en silencio.
- Robustez operacional: el ai-gateway pasa a ser dependencia crítica del cierre — no puede
  bloquear ni romper el cierre del episodio.

## Opciones consideradas

### Opción A — Juez gobierna, se documenta la reproducibilidad condicional (elegida)
El juez gobierna la etiqueta de los con-tutor no-delegación. Se declara explícitamente qué es
reproducible bit-a-bit (el brazo duro determinista) y qué no (la etiqueta gobernada por LLM), y
se compensa con controles auditables. Bump `tree_version` → v4.0.0, reclasificación append-only.

### Opción B — Juez en sombra permanente
Mantener el juez informativo. Conserva reproducibilidad total pero desperdicia su validez de
constructo: la etiqueta oficial sigue saliendo del proxy frágil. Descartada por producto.

### Opción C — Meter `judge_model` + `PROMPT_VERSION` en el `classifier_config_hash`
Hace que el hash refleje la config del juez (cambiar modelo/prompt cambia el hash → invalida
cache y deja traza). NO restituye el determinismo del LLM, pero cierra la divergencia silenciosa
"misma config, distinta etiqueta". **Queda como decisión abierta** (ver Consecuencias) porque
cambia el hash de TODAS las clasificaciones, incluidas las que el juez no toca.

## Decisión

Opción elegida: **A**.

El veredicto del juez gobierna `appropriation` para los subgrupos con-tutor no-delegación
(`colaborador_reflexivo`, `colaborador_funcional`, `desenganchado`). Se introduce el eje
ortogonal `autonomo` para el brazo `prompts == 0`. Se bumpea `tree_version` a **v4.0.0**.

**Qué SIGUE siendo reproducible bit-a-bit** (función pura sobre eventos + `config_hash`):
- El ruteo de subgrupos (qué brazo del árbol, qué subgrupo).
- El eje `autonomo` y la etiqueta de delegación pasiva (etapa dura).
- Las 5 métricas de coherencia (CT/CCD/CII) — siguen calculándose para auditoría.

**Qué NO es reproducible bit-a-bit** (gobernado por LLM):
- La etiqueta `apropiacion_reflexiva` vs `apropiacion_superficial` de los con-tutor no-delegación.

**Controles compensatorios** (auditabilidad sin determinismo):
- `temperature = 0` + modelo pinneado (`google/gemini-2.5-flash`) + `PROMPT_VERSION` pinneado.
- El veredicto completo (régimen, confianza, evidencia textual por dimensión, modelo, prompt
  version) se persiste en `features['regimen_llm']` → traza auditable de cada decisión.
- Regla de decisión en código (`regimen_segun_regla`), no en el LLM: si el veredicto no respeta
  la regla aplicada a sus propias dimensiones, o la confianza es < 0,70, o el JSON no parsea →
  `needs_review=True` y se conserva la etiqueta del proxy conductual.
- Idempotencia por `config_hash`: el re-POST devuelve la fila persistida (no se re-juzga), así
  que el veredicto queda congelado en estado estable.

## Consecuencias

### Positivas
- Mejor validez de constructo en la distinción reflexiva/superficial (κ 0,68 vs ≈0).
- Los 3 ejes del continuo quedan limpios (solo conversación real); `autonomo` aislado.
- Trazabilidad completa del veredicto del juez (no es una caja negra: cita evidencia).
- El cierre del episodio nunca depende del LLM (fallback al proxy + `needs_review`).

### Negativas / trade-offs
- **La reproducibilidad bit-a-bit deja de ser total**: para con-tutor no-delegación, recomputar
  desde cero puede arrojar otra etiqueta. La auditabilidad pasa de "determinismo" a "traza
  auditable + revisión humana". Esto debe reflejarse en la tesis (Sección de reproducibilidad)
  y en ambos `CLAUDE.md` (hoy afirman reproducibilidad bit-a-bit como verdad absoluta).
- **El paper define 3 categorías de apropiación; el código emite un 4º valor (`autonomo`)**.
  Requiere actualizar el paper/tesis o declarar `autonomo` como dimensión ortogonal de pre-filtro.
- El backfill (v4.0.0) invoca 1 llamada LLM por episodio con-tutor → costo, latencia y dependencia
  del gateway durante la corrida.

### Neutras
- `appropriation` es `String(40)`: el 4º valor `autonomo` entra sin migración. `needs_review`
  vive en `features` (JSONB): sin migración.
- Reclasificación append-only (ADR-010): las clasificaciones v3.1.0 quedan `is_current=false`;
  las nuevas se insertan con hash v4.0.0. El histórico del piloto-1 se preserva.

## Decisiones abiertas (requieren resolución académica)

1. **¿Meter `judge_model` + `PROMPT_VERSION` en el `classifier_config_hash`?** (Opción C). Cierra
   la divergencia "misma config, distinta etiqueta" pero cambia el hash de todas las clasificaciones.
2. **Validación intercoder κ del juez fuera de la zona gris**: hoy el κ 0,68 se midió solo en la
   zona gris. Promoverlo a todos los con-tutor extiende su alcance sin re-validar. Definir si se
   corre el k-fold antes de confiar la etiqueta oficial al juez en producción.
3. **El eje `autonomo` no tiene corpus de κ**: es un pre-filtro mecánico (`prompts == 0`),
   ortogonal al continuo, y el corpus inter-jueces es con-tutor. Se excluye del protocolo κ por
   diseño — confirmar que es aceptable.

## Referencias

- ADR-020 — `classifier_config_hash` determinista (reproducibilidad bit-a-bit).
- ADR-010 — CTR append-only / reclasificación.
- ADR-046 — umbral κ ≥ 0,70 y protocolo dual.
- ADR-018 — CII longitudinal ordinal (`autonomo` queda fuera del slope, es ortogonal).
- `apps/classifier-service/docs/JUEZ-LLM-EJE-FINO.md` — diseño del juez y hoja de ruta de promoción.
