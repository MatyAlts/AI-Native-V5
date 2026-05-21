# Protocolo de aplicación MAI — Metacognitive Awareness Inventory (CS10)

**Versión**: 1.0.0 — DRAFT pendiente revisión coautoral + comité ético UTN + búsqueda de adaptación validada al castellano.
**Fecha**: 2026-05-16.
**Origen**: `plan1Socra.md` CS10 (P1). Recomendación C1.2 del `informeSocra1.md`.

---

## 0. Resumen

Metacognitive Awareness Inventory (Schraw & Dennison, 1994) — instrumento estandarizado de 52 ítems Likert para medir conciencia metacognitiva (knowledge of cognition + regulation of cognition). Aplicación propuesta al inicio y al final del cuatrimestre del piloto-2 para medir delta-MAI y correlacionar con `cii_evolution_longitudinal` agregado del estudiante.

**Hipótesis convergente operativa**: estudiantes con incremento alto de MAI (delta > 0.5σ entre inicio y fin del cuatrimestre) exhibirán mayor `cii_evolution_longitudinal` (slope positivo más pronunciado). Si la correlación es nula, `cii_evolution_longitudinal` mide ruido léxico y no señal metacognitiva.

---

## 1. Instrumento

### 1.1 Versión a usar

**Opción A — MAI completo (Schraw & Dennison, 1994), 52 ítems Likert 1-5**:
- Knowledge of Cognition: 17 ítems (Declarative + Procedural + Conditional).
- Regulation of Cognition: 35 ítems (Planning + Information Management Strategies + Comprehension Monitoring + Debugging + Evaluation).
- Tiempo estimado: 15-20 minutos.

**Opción B — Jr. MAI (Sperling, Howard, Miller & Murphy, 2002), 18 ítems**:
- Versión adaptada para estudiantes más jóvenes, pero usada en universidad de primer año.
- Tiempo estimado: 8-10 minutos.
- Validez documentada para correlacionar con outcomes académicos.

**Recomendación inicial**: Opción A en pre-test (inicio del cuatrimestre) y Opción B en post-test (fin del cuatrimestre) para reducir fatiga, **con la limitación documentada de que delta(MAI_full vs Jr_MAI) no es estrictamente comparable**. Alternativa: A en ambos momentos.

### 1.2 Adaptación al castellano

Buscar adaptaciones validadas al castellano:
- Huertas, Vesga & Galindo (2014, Colombia) — adaptación del MAI completo, n=350 universitarios.
- Sandoval, Pérez & López (2018, México) — adaptación del Jr. MAI, n=200 secundaria.

Si no hay adaptación rioplatense específica, documentar adaptación propia con pilotaje previo sobre 5-10 estudiantes UTN antes de aplicación masiva. Reportar cualquier ajuste en la sección de método del paper.

---

## 2. Aplicación

### 2.1 Cuándo

- **Pre-test**: primera semana del cuatrimestre, antes de la primera tarea práctica con el sistema. Asincrónico, en línea.
- **Post-test**: última semana del cuatrimestre, después de la entrega del último TP pero antes del examen final. Asincrónico, en línea.

### 2.2 Cómo

- Formulario web hospedado en UTN (no Google Forms — datos académicos).
- Acceso vía link único en el LMS del curso o por email.
- Identificación: `student_pseudonym` del estudiante (UUID), no nombre ni email.
- Persistencia: tabla nueva `metacog_responses` en `academic_main`:
  - `id` UUID PK
  - `student_pseudonym` UUID
  - `phase` text CHECK in ('pre', 'post')
  - `instrument_version` text (ej. 'mai-full-es-huertas2014' o 'jr-mai-es-v1.0.0-utn')
  - `total_score` int (suma cruda de ítems Likert)
  - `subscale_scores` jsonb (knowledge_of_cognition, regulation_of_cognition desagregados)
  - `submitted_at` timestamptz
  - `consent_id` UUID FK a tabla de consentimientos.

### 2.3 Consentimiento

Texto sugerido para consentimiento adicional al del piloto:

> "Al inicio y al final del cuatrimestre vamos a invitarte a responder un cuestionario sobre cómo aprendés (no sobre el contenido del curso). Tarda unos 15 minutos al inicio y 10 al final. Tus respuestas son pseudonimizadas. ¿Estás de acuerdo en participar?"

Aprobación previa del comité ético UTN.

---

## 3. Análisis previsto

### 3.1 Validez convergente con `cii_evolution_longitudinal`

Variable derivada: `delta_mai = (MAI_post − MAI_pre) / std(MAI_pre_cohorte)` (z-score del cambio individual).

Hipótesis principal: `delta_mai` correlaciona positivamente con `cii_evolution_longitudinal` agregado del estudiante (computado vía `cii_longitudinal.py::compute_mean_slope` sobre todas las classifications del cuatrimestre).

Estadístico: Spearman ρ con IC95% mediante bootstrap. n mínimo: 50 estudiantes que completaron ambos cuestionarios.

### 3.2 Validez divergente

Verificar que las subescalas Knowledge vs Regulation **no son intercambiables**:
- Regulation_of_cognition debería correlacionar más fuerte con `cii_evolution_longitudinal` que Knowledge_of_cognition (porque CII captura evolución, no conocimiento estático).
- Si Knowledge correlaciona igual o más, la operacionalización de CII no captura específicamente metacognición regulatoria.

### 3.3 Reporte en el paper

Sección §8.X del paper Cortez & Garis (post-piloto-2). Si la correlación es ρ > 0.4, `cii_evolution_longitudinal` recibe validez convergente con instrumento estandarizado de metacognición.

---

## 4. Decisiones pendientes

1. **Opción A vs B vs híbrida** del instrumento.
2. **Búsqueda de adaptación castellana validada** o decisión de adaptación propia.
3. **Aprobación del comité ético UTN** + consentimiento adicional.
4. **Implementación técnica**: formulario + tabla. Esfuerzo: 12-16 h.
5. **Manejo de no-respondedores**: si <60% del grupo experimental responde el post-test, los análisis convergentes pierden potencia. Estrategias de incentivo a discutir con dirección.

---

## 5. Referencias

- Schraw, G., & Dennison, R. S. (1994). Assessing metacognitive awareness. *Contemporary Educational Psychology*, 19(4), 460-475.
- Sperling, R. A., Howard, B. C., Miller, L. A., & Murphy, C. (2002). Measures of children's knowledge and regulation of cognition. *Contemporary Educational Psychology*, 27(1), 51-79.
- Flavell, J. H. (1979). Metacognition and cognitive monitoring. *American Psychologist*, 34(10), 906-911.
- Veenman, M. V. J., Van Hout-Wolters, B. H. A. M., & Afflerbach, P. (2006). Metacognition and learning. *Metacognition and Learning*, 1(1), 3-14.
- Huertas, A. P., Vesga, G. J., & Galindo, M. (2014). Validación del Inventario de Conciencia Metacognitiva (MAI). *Educación y Educadores*, 17(3), 482-499.
- `informeSocra1.md` §6.3 y §9 (C1.2).
- `plan1Socra.md` CS10.
