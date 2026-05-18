# ADR-026 — Botón "Insertar código del tutor" en web-student (DIFERIDO a post-defensa)

- **Estado**: Aceptado (decisión: **DIFERIR**, no implementar pre-defensa)
- **Fecha**: 2026-04-29
- **Deciders**: Alberto Cortez, director de tesis
- **Tags**: frontend, web-student, ux, eje-a-b
- **Cierra**: G11 del audi2.md.

## Contexto y problema

F6 (iter 1) agregó el campo `origin: Literal["student_typed", "copied_from_tutor", "pasted_external"]` al payload de `edicion_codigo`. El backend lo recibe y persiste. El [event_labeler](../../apps/classifier-service/src/classifier_service/services/event_labeler.py) lo lee para hacer el override `edicion_codigo → N4` cuando `origin ∈ {copied_from_tutor, pasted_external}` (ADR-020).

**Sin embargo**, [`apps/web-student/src/components/CodeEditor.tsx`](../../apps/web-student/src/components/CodeEditor.tsx) sólo emite `student_typed | pasted_external`. La rama `copied_from_tutor` requiere un botón "Insertar código" en el panel del tutor que aún no existe — verificación: `grep -rn "copied_from_tutor" apps/web-student` → solo aparece en el type literal de TypeScript, **no como string emitido**.

Resultado: el override del labeler captura `pasted_external` (estudiante pegó algo de afuera) pero **no el caso pedagógicamente más informativo**: el estudiante adoptó deliberadamente un bloque de código sugerido por el tutor.

## Decisión

**DIFERIR**. La afordancia UX queda como agenda confirmatoria post-defensa.

### Por qué

- **Confound intervención-medición** (tesis 11.6): el botón cambia la economía de la interacción — ofrece un canal "barato" para tomar código del tutor, lo que puede inducir delegación pasiva como variable confound. No es un cambio neutro de instrumentación; es una **modificación del entorno experimental**.
- **Mid-cohort introduce sesgo de tratamiento**: estudiantes que reciben el botón vs. los que no son cohortes distintas. La condición experimental cambia.
- **audi2.md G11 timing**: *"Agenda confirmatoria, post-defensa. Toca la UX del estudiante y disrumpe condición experimental."*

## Criterio para revisitar

Implementar G11 cuando se cumpla **alguno** de:

1. Inicio de un nuevo cuatrimestre / cohorte limpia.
2. Decisión académica de **estudiar el efecto del botón como variable independiente** (estudio cuasi-experimental con grupo control sin botón) — ahí el cambio NO es ruido, es la variable a medir.
3. Defensa concluida + acuerdo del comité doctoral sobre el alcance del piloto-2.

### Implementación propuesta (referencia)

audi2.md G11 detalla:

1. Detectar bloques de código en respuestas del tutor (regex sobre triple-backtick, parser markdown completo NO necesario en v1).
2. Botón "Insertar en el editor" junto a cada bloque.
3. Click → componente parent del editor recibe el bloque + flag de origen.
4. Editor inserta en posición del cursor o reemplaza la selección.
5. La emisión `edicion_codigo` resultante lleva `origin: "copied_from_tutor"`.

LOC estimado: ~120 (parser + UI button + propagación del flag al hook).

## Consecuencias de DIFERIR

### Positivas

- Condición experimental del piloto-1 queda estable.
- El estudio puede declarar honestamente "el botón está fuera de scope; los estudiantes que copian del tutor lo hacen por paste manual y se etiqueta `pasted_external`".
- Cero LOC nuevo en frontend o tests.

### Negativas

- Pierde evidencia directa de **adopción deliberada** vs **paste manual**. Ambos casos hoy se etiquetan N4 por el override `pasted_external`, pero pedagógicamente son distintos: adopción deliberada vía botón implica intencionalidad declarada por la UX; paste manual puede ser de fuente externa cualquiera.
- El docstring del contract `EdicionCodigoPayload.origin` ya menciona la afordancia faltante — queda como TODO observable hasta que se cierre.

## Referencias

- audi2.md G11.
- ADR-020 — labeler reconoce `copied_from_tutor` (override a N4).
- Tesis 11.6 — confound intervención-medición.
- Tesis 19.5 — `origin` parcialmente operacional (T16 de la tesis).
- Contract: `packages/contracts/src/platform_contracts/ctr/events.py` — `EdicionCodigoPayload.origin`.
