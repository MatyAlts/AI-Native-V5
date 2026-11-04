# Informe propose-5-planner

- Change: `cibse-codificacion-ciega`
- Rol: planner (propose, intento 5 por decisión del humano sobre la pregunta 12; no es intento fallido de gate)
- Ejecutor declarado: subagente nativo de Claude Code (role planner), familia Anthropic, la misma que el plan-reviewer.
- Base: `origin/main @ b32e621`; artefactos sin commitear.
- Entrada: respuesta de Juani del 04/11/2026 a la P12 (opción B, carga manual del enunciado), con los requisitos transmitidos por el orquestador.
- No se tocó el bloque "Estado de orquestación" de `tasks.md` (ediciones solo después de `## Registro del planner`) ni los informes del reviewer. No se escribió SQL de exportación.
- Revisión entregada (sha256, 12 primeros): proposal `37a59893694b`, design `32c88f7d1742`, tasks `faefbecc656a`, specs: codebook-versionado `ade6518708de` (sin cambios), entrenamiento-calibracion `a2db7a1ab33a`, estudio-codificacion-acceso `d827a1c86fc9` (sin cambios), estudio-codificacion-exportacion `ff8a33476668`, estudio-codificacion `68483d8a2711`, traza-ciega-episodio `e0be95216dc7`. Spec `academic-enunciados-lectura` eliminada.

## Disposición por pedido

| Pedido | Disposición | Dónde quedó |
|---|---|---|
| Sacar todo cambio en academic-service | Eliminados el endpoint interno, la cuenta `estudio_lector`, la política Casbin, el grupo 14, la tarea 12.1b, el paso 0 del Migration Plan, la fila de consumidores de academic, el riesgo de academic caído, la capability `academic-enunciados-lectura` y el KB de academic y del conteo de policies. Alcance: classifier-service y web-teacher | proposal (Capabilities, Impact, Deploy, No se tocan, KB Impact); design Non-Goals, D14, Consumidores, Riesgos, Migration Plan; tasks Registro, 2.1, 2.2, 7.0, 7.1, 7.3, Workflow follow-up |
| Cómo llega el enunciado | El investigador sube por `POST .../{clave}/enunciados` un CSV `tipo,tp_id,ejercicio_id,enunciado`, junto con la muestra o después. Se guarda el sha256 del archivo y de cada texto, autor y fecha. Validación todo o nada por archivo; filas sin uso ignoradas e informadas; cargas parciales permitidas; texto distinto sobre un enunciado ya revisado da 409, sobre uno no revisado lo reemplaza con log de hashes. Muestra y anclas guardan `problema_id` y `ejercicio_id` del CTR, que definen el conjunto requerido y la cobertura | design D1, D2, D14 "Cómo llega"; spec estudio-codificacion "Carga manual de enunciados con cobertura"; tasks 7.0, 7.1, 7.2b, 11.8 |
| Enunciado faltante | Bloqueo de **todo el estudio** para codificar (409 `enunciados_pendientes`) mientras falte o no esté revisado alguno de la muestra. Justificación: los dos codificadores deben codificar los 150 con la misma evidencia, el cierre exige los 150 y la carga es un único archivo. Entrenamiento: bloqueo **por ancla**, porque las anclas son independientes y el entrenamiento no es obligatorio (P10). Traza de un ítem con faltante: 409 `enunciado_pendiente` | design D14 "Enunciado faltante"; specs estudio-codificacion ("Codificar con un enunciado faltante"), traza-ciega-episodio ("Enunciado pendiente"), entrenamiento-calibracion ("Ancla con enunciado faltante o sin revisar"); tasks 7.2b (mutante: bloquear solo el ítem), 7.3 |
| Se mantiene: hash, alertas, revisión | Sin cambios de fondo; el hash ahora cubre también el archivo de origen y se exporta | design D14 "Revisión", "Vista ciega"; spec exportación; tasks 7.0, 7.2b, 10.1 |
| No escribir el SQL | No está en ningún artefacto; Workflow follow-up asigna la consulta al orquestador | tasks Workflow follow-up; design Migration Plan paso 4 |
| P12 respondida | Registrada con fecha y autor (Juani, 04/11/2026), opción B | proposal pregunta 12 (y la 4 actualizada) |

## EVIDENCIA

| Comando / lectura | Momento | Resultado |
|---|---|---|
| `rg` de `academic`, `estudio_lector`, `grupo 14`, `ESTUDIO_LECTOR_ACADEMIC` en proposal, design, tasks y specs tras editar | 04/11 | solo quedan menciones justificativas (alternativas rechazadas, contexto de por qué no hay rol que sirva, "No se tocan") y el historial de intentos de tasks |
| `openspec validate cibse-codificacion-ciega --strict` | 2026-11-04T11:43:48-03:00 | `Change 'cibse-codificacion-ciega' is valid` |
| `rg -c "—"` sobre artefactos | 04/11 | sin em dashes |

## JUICIO

Autor: planner.

- El bloqueo global para codificar es la opción que preserva la comparabilidad entre codificadores; el costo (esperar a completar un archivo) es bajo (confianza alta).
- La carga manual traslada al investigador la garantía de que el texto corresponde a la TP o al ejercicio correctos; el sistema solo puede asegurar cobertura, inmutabilidad y trazabilidad, no fidelidad. Lo dejé como riesgo explícito con declaración en el método del paper (confianza alta).
- Permitir reemplazar un enunciado no revisado evita tener que rehacer el estudio por un error de exportación, sin tocar lo ya revisado (confianza media-alta).

## SUPOSICIÓN

- Que la consulta del orquestador produce exactamente las columnas `tipo,tp_id,ejercicio_id,enunciado`; si cambia el formato, cambia el parser de 7.0.
- Que `episodio_abierto.payload.ejercicio_id` está presente cuando corresponde (heredado del intento 4, no verificado en producción).
- No se ejecutó código ni tests.

## Fuentes leídas

- Artefactos propios del intento 4 y la respuesta del humano transmitida por el orquestador.

## Contaminación por informes ajenos

Ninguna nueva: no se leyó ningún informe de revisión para este intento. No se consultó Engram.
