# Propuesta — fix-pdf-auditoria-qa

## Qué y por qué
El 2026-09-23 se hizo una auditoría QA + seguridad end-to-end del Tutor Socrático
(informe PDF, 21 hallazgos + 3 mejoras). Este change agrupa los hallazgos
**corregibles por código** en la rama `feat/qa-fixes-reapertura-rubrica`, para
cerrarlos con ciclo implementar → testear → auditar por ítem.

## Alcance
DENTRO: bugs de UI/UX del docente y del alumno, la reapertura de episodios con
código previo (Mejora 2), el autocompletado de criterios de rúbrica en la
corrección con IA (Mejora 3 + BUG-19), y el cableado del pie de auditoría.

FUERA (a propósito, no se toca en este change):
- El prompt del tutor (BUG-09 parte-modelo): coautoría Ana Garis, requiere consulta.
- Rotación de la key de OpenRouter / flags Active-IA: secrets + config de prod.
- Deploy.

## Ya hecho antes del ciclo (commit d4ce2a1)
BUG-11 (etiqueta motor), BUG-16 (texto tests públicos), BUG-05 (versión del pie).

## Knowledge Base Impact
none — este change no mueve el modelo de datos ni decisiones de arquitectura
registradas; son correcciones de comportamiento y UX sobre código existente.
