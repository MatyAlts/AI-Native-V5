# Tasks — informe-avance-comisiones

Frontend-only (web-teacher). Cada helper puro con TDD (test que falla sin el
cambio y pasa con él). La presentación imprimible se verifica con test de render
(RTL) donde aplique + verificación manual del print.

## Lote 1 — modelo de datos del informe (helpers puros, TDD)
- [ ] IAC-01 · `buildResumenComision(progression, quartiles, alertsSummary)` —
      función pura que arma el view-model de la PORTADA desde los responses ya
      existentes. Debe manejar `insufficient_data` (N<5) devolviendo un estado
      "datos insuficientes por privacidad", NO ceros. Test: caso normal, caso N<5,
      caso sin datos.
- [ ] IAC-02 · `buildDetallePorAlumno(progression.trajectories, profilesMap, alerts?)`
      — función pura que arma la TABLA por alumno cruzando las trayectorias con el
      Map de nombres (patrón `studentShortLabel`: nombre real, fallback "Est.
      xxxxxx"). Test: alumno con nombre, alumno sin profile (fallback), orden
      estable.

## Lote 2 — presentación imprimible
- [ ] IAC-03 · Componente `InformeAvanceComision` (web-teacher) que renderiza
      portada (resumen) + detalle por alumno. Print CSS (`@media print`) — nueva en
      el repo, scoped al informe. El bloque de detalle lleva rótulo visible "uso
      interno de la cátedra — datos personales, no publicar". Test RTL: renderiza
      nombres del map; muestra el rótulo de privacidad; muestra "datos
      insuficientes" cuando corresponde.
- [ ] IAC-04 · Wiring en `ExportView`: acción "Informe de avance (imprimible)"
      junto al export JSON existente. Arma el informe para la comisión seleccionada
      (reusa `getCohortProgression`, `getCohortCIIQuartiles`,
      `getCohortAlertsSummary`, `useStudentProfiles`/`listStudentProfiles`) y
      dispara `window.print()` (o abre la vista dedicada e imprime). No romper el
      flujo de export JSON existente. Verificación manual del print + test del
      wiring donde sea testeable.

## Gates duros (todas las tareas)
- Solo web-teacher. NO backend, NO CTR/hashing, NO prompt del tutor, NO
  secrets/OpenRouter, NO tocar el export académico anonimizado existente.
- Nombres SOLO vía el endpoint de perfiles ya gateado por comisión. El detalle
  por alumno siempre rotulado como uso interno.
- `tsc --noEmit` verde + suite web-teacher sin regresión.
