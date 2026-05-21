# Protocolo de aplicación NASA-TLX (CS09)

**Versión**: 1.0.0 — DRAFT pendiente revisión coautoral + comité ético UTN.
**Fecha**: 2026-05-16.
**Origen**: `plan1Socra.md` CS09 (P1, antes de submisión final). Recomendación C1.1 del `informeSocra1.md`.
**Estado**: propuesta para piloto-2. NO aplicar antes de revisión.

---

## 0. Resumen

NASA Task Load Index (Hart & Staveland, 1988) — instrumento estandarizado para medir carga cognitiva subjetiva post-tarea. Aplicación propuesta al cierre de un subconjunto aleatorio de episodios del piloto-2 (~20%) para validez convergente con la coherencia temporal CT del Modelo N4.

**Hipótesis convergente operativa**: si CT captura "patrón de trabajo sostenido y equilibrado", una CT alta correlaciona negativamente con la dimensión Frustration de NASA-TLX y positivamente (moderada) con Effort. Una correlación nula entre CT y NASA-TLX indicaría que CT mide ruido temporal y no señal cognitiva.

---

## 1. Instrumento

### 1.1 Versión a usar

**Cognitive Load Scale de Paas (1992)** — versión simplificada de 9 puntos sobre mental effort. Razones:
- 1 ítem único, 30 segundos de aplicación. Mínima fricción sobre el estudiante.
- Validez convergente documentada con NASA-TLX (Paas & van Merrienboer, 1994).
- Apta para administración post-cada-episodio sin saturar.

Alternativa para subconjunto reducido (10% del subconjunto): **NASA-TLX completo** (6 dimensiones: mental demand, physical demand, temporal demand, performance, effort, frustration). 2-3 minutos de aplicación.

### 1.2 Ítem único de Paas

> "Indique el esfuerzo mental que invirtió para completar este ejercicio."
>
> Escala de 9 puntos:
> 1 = Esfuerzo mental muy, muy bajo
> 5 = Esfuerzo mental medio
> 9 = Esfuerzo mental muy, muy alto

Adaptación al castellano rioplatense neutro pendiente; validar con dirección antes de aplicar.

---

## 2. Aplicación

### 2.1 Cuándo

- **Inmediatamente después** del modal de reflexión (`ReflectionModal`) al cierre del episodio.
- **Antes** de cualquier devolución metacognitiva (R5, si está activada).
- Solo en una **fracción aleatoria del 20%** de los episodios cerrados — para no contaminar sistemáticamente el comportamiento del estudiante con consciencia de medición de carga.

### 2.2 Cómo

- Modal nuevo en `web-student`: `CognitiveLoadModal.tsx`. Aparece solo si el episodio fue elegido aleatoriamente para esta medición.
- Selección aleatoria: hash determinista de `(episode_id, "nasa-tlx-2026")` % 5 == 0 → seleccionado.
- Persistencia: tabla nueva `cognitive_load_responses` en `academic_main` con columnas:
  - `id` UUID PK
  - `episode_id` UUID FK a `episodes.id` (en `ctr_store`, sin FK cross-base)
  - `student_pseudonym` UUID
  - `mental_effort_score` int CHECK 1..9
  - `submitted_at` timestamptz
  - `instrument_version` text DEFAULT `'paas-1992-es-v1.0.0'`

### 2.3 Consentimiento adicional

Aplicar este instrumento requiere consentimiento informado adicional al del piloto (no era contemplado en el consentimiento original). Texto sugerido:

> "Al cerrar algunos episodios el sistema te va a preguntar cuánto esfuerzo mental sentís que invertiste. Es una pregunta sobre tu experiencia personal, no se usa para evaluarte. Sirve para mejorar el sistema. ¿Estás de acuerdo en responderla cuando aparezca?"

Si el estudiante no consiente, no se le muestra el modal — pero el sistema captura `consent_status` en su perfil para mantener trazabilidad.

---

## 3. Análisis previsto

### 3.1 Validez convergente con CT

Hipótesis: `CT_summary` correlaciona con `mental_effort_score` de manera estructurada:
- Correlación moderada negativa esperada con `frustration` (en NASA-TLX completo).
- Correlación moderada positiva esperada con `effort`.
- Correlación nula esperada con `performance` (CT no mide auto-percepción de éxito).

Estadístico: Spearman ρ con IC95% mediante bootstrap. n mínimo recomendado: 50 episodios con respuesta de NASA-TLX (≈ 250 episodios totales del piloto con muestreo del 20%).

### 3.2 Validez divergente

Verificar que `ccd_orphan_ratio` y `cii_stability` NO correlacionan fuertemente con NASA-TLX (correlación < 0.3). Si correlacionan fuertemente con la misma dimensión, las cinco coherencias colapsan parcialmente sobre el mismo constructo (carga cognitiva), lo cual contradiría el rechazo del score único.

### 3.3 Reporte en el paper

Sección §8.X del paper Cortez & Garis (post-piloto-2): tabla con correlaciones + interpretación. Si las correlaciones son consistentes con las hipótesis, CT recibe validez convergente. Si no, refinar la operacionalización de CT.

---

## 4. Decisiones pendientes (requieren participación humana)

1. **Versión exacta del instrumento**: Paas 1992 (1 ítem) vs NASA-TLX completo (6 dimensiones) vs híbrido (Paas en 80% + NASA-TLX completo en 20% adicional). Dirección + Ana Garis.
2. **Aprobación del consentimiento adicional** por comité ético UTN.
3. **Adaptación al castellano rioplatense** del ítem único. Calibrar con 3-5 estudiantes piloto antes de aplicación masiva.
4. **Implementación técnica del `CognitiveLoadModal`** y la tabla `cognitive_load_responses`. Esfuerzo estimado: 8-12 h coordinadas con frontend + back-end.

---

## 5. Referencias

- Hart, S. G., & Staveland, L. E. (1988). Development of NASA-TLX (Task Load Index). En P. A. Hancock & N. Meshkati (Eds.), *Human Mental Workload* (pp. 139-183). North Holland.
- Paas, F. G. W. C. (1992). Training strategies for attaining transfer of problem-solving skill in statistics. *Journal of Educational Psychology*, 84(4), 429-434.
- Paas, F. G. W. C., & van Merrienboer, J. J. G. (1994). Instructional control of cognitive load. *Educational Psychology Review*, 6(4), 351-371.
- Sweller, J., van Merrienboer, J. J. G., & Paas, F. (2019). Cognitive architecture and instructional design: 20 years later. *Educational Psychology Review*, 31(2), 261-292.
- `informeSocra1.md` §6.2 y §9 (C1.1).
- `plan1Socra.md` CS09.
