# Informe de avance de comisión (imprimible, para el docente)

## Qué y por qué
El docente necesita un **informe legible del estado de avance de su comisión** que
pueda leer y compartir en coordinación — no un volcado de datos. Hoy el botón
"Exportar" sólo produce un dataset académico anonimizado en JSON. Esta mejora
agrega, sobre el mismo flujo de Exportar, la generación de un **informe imprimible
(HTML → PDF vía `window.print()`)** con el avance de una comisión.

Decisión de producto (Juani, 2026-09-24): el informe lleva **nombres reales** de
los alumnos, porque es lo que le sirve al docente para actuar. Es viable sin
romper privacidad: los nombres ya son accesibles legítimamente por el docente
para SU comisión vía `GET /comisiones/{id}/students/profiles`
(`useStudentProfiles` / `studentShortLabel`), un patrón ya en uso en Progresión,
Cohorte y Longitudinal. El join nombre↔pseudónimo ocurre client-side; el CTR
sigue anónimo.

## Alcance
- **Frontend-only** (web-teacher). NO se toca backend, ni el CTR/hashing, ni el
  contrato de export académico existente.
- Se **compone** desde endpoints ya existentes y gateados (progresión, cuartiles
  CII, resumen de alertas, perfiles de alumno). Sin endpoint nuevo.
- Formato: **HTML imprimible** con `@media print`, disparado con `window.print()`.
  Sin librería de PDF (no hay en el repo; el usuario "Guardar como PDF").

## Gobierno de privacidad (línea dura)
- El informe es **UI interna del docente para SU propia comisión** → patrón ya
  autorizado (invariante `student_pseudonym` de CLAUDE.md permite nombre/pseudónimo
  en UI interna; gate por comisión ya existe en el endpoint de perfiles).
- **Portada/resumen**: agregados de la comisión, respetan `insufficient_data`
  (k-anonymity N≥5 en cuartiles/alertas). No expone individuos.
- **Detalle por alumno**: con nombres, rotulado explícito "uso interno de la
  cátedra — contiene datos personales, no publicar/compartir".
- NO es el export académico anonimizado (ese sigue con `student_alias` + salt, sin
  tocar). Son dos artefactos con dos gobiernos distintos.

## No incluye (por ahora)
- Backend aggregator (se compone en el cliente).
- Export del informe al dataset de tesis / público (ahí regiría student_alias).
- Distribución N1-N4 por cohorte (el endpoint existente es por episodio).

## Knowledge Base Impact
none — feature de presentación en frontend; no cambia modelo de datos, reglas de
negocio ni arquitectura documentada en la KB.
