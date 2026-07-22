# Protocolo de aplicación de escala de autoeficacia en programación (CS12)

**Versión**: 1.0.0 — DRAFT pendiente revisión coautoral + comité ético + búsqueda/adaptación de instrumento.
**Fecha**: 2026-05-16.
**Origen**: `plan1Socra.md` CS12 (P1). Recomendación C1.4 del `informeSocra1.md`.

---

## 0. Resumen

Aplicación de una escala de autoeficacia adaptada de Bandura (1997) calibrada para programación universitaria. Sirve como **covariable de control** en los análisis de H1 y H2 del paper: las diferencias entre tipos de apropiación deben mantenerse significativas **después de controlar por autoeficacia inicial**, descartando que el efecto sea explicado por disposición afectiva previa.

---

## 1. Instrumento

### 1.1 Opciones

**Opción A — Computer Programming Self-Efficacy Scale (Ramalingam & Wiedenbeck, 1998)**:
- 32 ítems Likert 1-7 sobre autoeficacia específica en programación.
- Validada con n=300+ estudiantes de CS1/CS2 en universidades anglófonas.
- Tiempo: 15-20 min.

**Opción B — General Self-Efficacy Scale + ítems específicos** (Schwarzer & Jerusalem, 1995):
- 10 ítems generales + 5 ítems específicos diseñados para programación universitaria.
- Tiempo: 8-10 min.
- Validez convergente con outcomes académicos documentada en Lishinski et al. (2016).

**Opción C — CS Self-Efficacy Scale de Lishinski et al. (2016)**:
- 28 ítems específicos para ciencias de la computación universitaria.
- Validada con n=190 estudiantes en EE.UU.
- Tiempo: 12-15 min.

**Recomendación inicial**: Opción C (Lishinski et al., 2016) por ser más específica al dominio CS universitario y tener tiempo razonable. Validar disponibilidad de adaptación al castellano.

### 1.2 Adaptación

Si no hay adaptación rioplatense validada:
- Traducción inversa por dos traductores independientes.
- Pilotaje cognitivo con 3-5 estudiantes UTN (think-aloud sobre cómo interpretan cada ítem).
- Análisis preliminar de consistencia interna (Cronbach α ≥ 0,8 esperado sobre n=30).

---

## 2. Aplicación

### 2.1 Cuándo

- **Pre-test único** al inicio del cuatrimestre, antes de cualquier interacción con el sistema.
- Razón: la autoeficacia es la **disposición previa** que se controla; medirla post-intervención introduciría el efecto que se quiere controlar.
- Asincrónico, en línea, 10-15 min.

### 2.2 Cómo

- Formulario web (mismo sistema que MAI, CS10).
- Identificación: `student_pseudonym`.
- Persistencia: tabla `self_efficacy_responses` en `academic_main`:
  - `id` UUID PK
  - `student_pseudonym` UUID
  - `instrument_version` text (ej. `'lishinski-2016-es-utn-v1.0.0'`)
  - `total_score` int
  - `subscale_scores` jsonb
  - `submitted_at` timestamptz

### 2.3 Consentimiento

Texto sugerido:

> "Antes de empezar a usar el sistema te vamos a hacer unas preguntas sobre tu confianza en tu capacidad de aprender programación. No hay respuestas correctas o incorrectas. Sirve para entender mejor cómo distintos estudiantes usan el sistema. ¿Estás de acuerdo en responderlas?"

---

## 3. Análisis previsto

### 3.1 Como covariable de control en H1

Modelo lineal generalizado:
```
appropriation ~ coherence_profile + self_efficacy_pretest + error
```
Donde `appropriation` es la categoría dominante (variable categórica nominal) y `coherence_profile` son las 5 coherencias agregadas. Si las 5 coherencias siguen siendo predictoras significativas después de controlar por self_efficacy_pretest, H1 se sostiene independientemente de la disposición afectiva previa.

### 3.2 Como covariable de control en H2

```
transfer_score ~ coherence_profile + self_efficacy_pretest + error
```
Mismo razonamiento. Si la coherencia predice transfer después de controlar autoeficacia, H2 se sostiene.

### 3.3 Hipótesis exploratoria adicional

¿Estudiantes con baja autoeficacia inicial muestran mayor cambio en `cii_evolution_longitudinal` después de usar el sistema? Esto sería evidencia indirecta de que el sistema reduce la brecha de autoeficacia. Análisis: correlación parcial entre autoeficacia_pretest y delta `cii_evolution_longitudinal`.

### 3.4 Validez convergente con MAI

Correlación esperada moderada entre autoeficacia y MAI total (ambos miden construcciones afectivo-cognitivas relacionadas, pero distinguibles). Si la correlación es > 0.85, los dos instrumentos miden lo mismo y uno es redundante. Si es < 0.4, son ortogonales y vale aplicar ambos.

---

## 4. Decisiones pendientes

1. **Selección del instrumento** (A vs B vs C) por dirección + Ana Garis.
2. **Búsqueda de adaptación castellana** o decisión de adaptación propia.
3. **Aprobación ética** + consentimiento.
4. **Implementación técnica**: formulario + tabla. Esfuerzo: 8-12 h.
5. **Riesgo de carga**: aplicar MAI + autoeficacia en la primera semana suma 25-35 min de cuestionarios. Considerar **espaciar**: autoeficacia día 1, MAI día 3-4. Decisión coordinada con dirección.

---

## 5. Referencias

- Bandura, A. (1997). *Self-efficacy: The exercise of control*. W. H. Freeman.
- Ramalingam, V., & Wiedenbeck, S. (1998). Development and validation of scores on a computer programming self-efficacy scale. *Journal of Educational Computing Research*, 19(4), 367-381.
- Schwarzer, R., & Jerusalem, M. (1995). Generalized Self-Efficacy scale. En J. Weinman, S. Wright & M. Johnston (Eds.), *Measures in health psychology* (pp. 35-37). NFER-NELSON.
- Lishinski, A., Yadav, A., Good, J., & Enbody, R. (2016). Learning to program: Gender differences and interactive effects of students' motivation, goals, and self-efficacy on performance. *ICER '16 Proceedings*, 211-220.
- `informeSocra1.md` §6.6 y §9 (C1.4).
- `plan1Socra.md` CS12.
