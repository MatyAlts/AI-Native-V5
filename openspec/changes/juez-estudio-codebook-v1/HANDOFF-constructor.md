# Encargo para construir: juez del estudio

Aprobado por Juani el 06/11/2026 (ver `proposal.md`, `## Aprobación`). Nivel CRITICAL.

## Qué se construye
Un juez LLM que codifica como un codificador más: misma traza ciega, mismo formulario y misma regla que los humanos, guardado aparte. Modelo único: `google/gemini-2.5-flash-lite`. Se prueba técnicamente con las 5 anclas (3 repeticiones, estabilidad 0.8).

Leer en orden: `proposal.md`, `design.md`, `specs/`, `tasks.md`, `informes/propose-4-plan-reviewer.md`.

## Qué no se toca
- El juez de producción (`regimen_llm.py`) ni F15.
- La muestra de 150: este change no la lee ni la corre. Eso es T-002, con su propia aprobación.
- Prompts del tutor.

## Firewall del estudio
Hasta congelar el juez, quien construye no mira contenido, trazas, etiquetas humanas ni veredictos de producción de los 150. Tampoco `analisis_produccion/` ni el Excel `CIbSE2027_produccion_150_CONFIDENCIAL.xlsx`. El prompt no se ajusta por resultados de contenido.

## Corregir primero (hallazgos de la revisión)
- **N3, obligatorio:** al cerrar la corrida, la condición 1 exige `cerrada` antes del `UPDATE`. Leído literal, `cumple_tecnico` da siempre falso y `n_cambios_tras_cumplir` queda en 0, y la regla del paper afirmaría algo falso. Hacer test.
- **N1, obligatorio:** `pasiva` con `d4=transferencia` y cita vacía debe dar `incompleto`, no `inconsistente`.
- **N2 a N12:** ver el informe. Varios mutantes no prueban su falla tal como están escritos: corregirlos antes de contarlos.

## Sin verificar todavía
- Que un modelo real cumpla el contrato de salida: se ve recién con llamadas reales. Flash Lite es más liviano y puede costarle.
- La tabla de precios nativa del gateway no lista este modelo: verificar cómo llega `cost_usd`.
- Que `mensaje k` equivalga a `turno k`, y que `contenido_md` sean las secciones 1 a 9.

## Cierre
Recorrido real con Clerk (excepción documentada: deploy de `main` coordinado, sin los codificadores trabajando, un servicio por vez, y después archivar). La integración de classifier en CI queda como DEUDA de Juani. Antes del archivo: rompedor y auditor APROBADO.
