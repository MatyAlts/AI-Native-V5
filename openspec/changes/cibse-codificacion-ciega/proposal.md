# Proposal: cibse-codificacion-ciega

## Why

El paper CIbSE 2027 compara el juez LLM actual (C0) con uno revisado (C1) contra una referencia humana: dos codificadores que clasifican a ciegas una muestra fija de 150 episodios del segundo semestre de 2026. La herramienta inter-jueces actual no sirve para eso y además contamina la referencia: su entrenamiento enseña la regla que el paper evalúa ("el sobreuso manda, pasiva"), su traza muestra el evento `intento_adverso_detectado` y otros campos que revelan decisiones de la máquina, su muestra es dinámica (primeros N por etiqueta de máquina) y su etiqueta es un solo valor sin dimensiones ni evidencia. El codebook todavía no está congelado, así que nada de su contenido puede vivir en el código.

## What Changes

- Se rehacen las dos secciones existentes del web-teacher para el estudio, sin pantallas nuevas en el menú:
  - **Entrenamiento-Recalibración**: muestra el codebook versionado (borrador o congelado) y una práctica con anclas persistidas en la base. Se retiran los 7 anclas hardcodeadas del piloto, los ejemplos y los textos de "la trampa" / "sobreuso, pasiva" de `InterraterTraining.tsx`. Sin anclas cargadas, estado vacío explícito.
  - **Codificación (inter-jueces)**: sirve la muestra fija de 150 con vista ciega y un formulario definido por el esquema de la versión congelada del codebook (en el v0: 4 dimensiones con cita, régimen o "evidencia insuficiente", notas), con guardado incremental y cierre. La codificación solo se habilita si la versión vigente está congelada.
- El codebook se persiste versionado en la base (borrador o congelada; una congelada no se edita) y se muestra en Entrenamiento. Cada etiqueta y cada respuesta de entrenamiento registra la versión vigente. El contenido v0 lo prepara el orquestador; el código no trae texto de codebook.
- **BREAKING (UI)**: la codificación del piloto por materia (`/interrater` con protocolo "ejes") y el entrenamiento del piloto dejan de estar disponibles en la interfaz. Motivo: decisión del humano de reutilizar ambas secciones para el estudio. Los 188 episodios ya codificados en `interrater_ratings` no se tocan; los endpoints `/api/v1/interrater/{sample,ratings,my-progress}`, `/api/v1/analytics/interrater/aggregate`, la vista `/interrater-admin`, el cálculo de κ de `pedagogia.py` y `scripts/exportar-episodios-eje-fino.py` siguen funcionando sobre la tabla del piloto.
- Nuevo modelo de datos del estudio en `classifier_db` (tablas aditivas con RLS): estudio, membresías por email (investigador / codificador), muestra fija, codebook versionado, anclas, respuestas de entrenamiento, etiquetas del estudio con historial.
- Nuevos endpoints bajo `/api/v1/interrater/estudios/...` en classifier-service (prefijo ya ruteado por el api-gateway; no se toca el gateway).
- Traza ciega servida por classifier-service: lee el episodio del ctr-service con una cuenta de servicio y aplica una lista blanca versionada (`traza_v1`) por tipo de evento y por campo, con localizadores por tipo (turno, código, ejecución, prueba, nota) y tiempo relativo. No se modifica ctr-service.
- Evidencia fija por ítem: al cargar la muestra o un ancla se fija el tope de la traza (seq y chain hash); eventos posteriores, como una reapertura, no cambian lo que ven los codificadores.
- Régimen según la regla del codebook (v0 §7): el esquema de cada versión declara la regla de decisión entre dimensiones y régimen; el servidor calcula el régimen y rechaza uno distinto. Si el codificador cree que la regla es injusta en un caso, registra `regimen_propuesto` con nota obligatoria; se exportan los dos, junto con `regimen_regla` (lo que da la regla sobre las dimensiones, aun cuando se eligió evidencia insuficiente).
- Identificador opaco por ítem: el codificador nunca recibe el `episode_id`.
- Enunciado en la vista ciega y en las anclas: el de la TP y, si corresponde, el del ejercicio, cargados a mano por el investigador desde un CSV exportado de Postgres, fijados con hash y revisados antes de habilitar la codificación; si falta alguno de la muestra, la codificación de todo el estudio queda bloqueada. Nunca se muestran `rubrica`, `tutor_rules`, `misconceptions`, `respuesta_pista`, `test_cases`, `banco_preguntas` ni otros campos de solución.
- Orden aleatorio distinto y reproducible por codificador (semilla persistida, orden por hash, independiente de la versión de Python).
- Exportación CSV/JSON de etiquetas, respuestas de entrenamiento e historial, restringida al rol investigador del estudio.
- La puerta de entrada del web-teacher admite a miembros de un estudio sin comisiones, con navegación restringida a las dos secciones y sin tour, onboarding ni selectores docentes. Un docente con comisiones entra aunque classifier-service no responda.
- La membresía se asigna por email y queda atada al `user_id` firmado por el gateway en el primer uso.

## Capabilities

### New Capabilities
- `estudio-codificacion-acceso`: alta de estudios, membresías por email con rol investigador o codificador, puerta de entrada y aislamiento entre roles.
- `estudio-codificacion`: muestra fija, orden por codificador, formulario de etiquetado, guardado incremental, cierre y separación respecto de las etiquetas del piloto y oficiales.
- `traza-ciega-episodio`: presentación del episodio sin información que revele decisiones de la máquina ni identidad del alumno.
- `codebook-versionado`: versiones de codebook en borrador o congeladas, inmutabilidad de las congeladas y versión vigente del estudio.
- `entrenamiento-calibracion`: anclas persistidas (ejemplos y práctica), exclusión respecto de la muestra y registro de respuestas de entrenamiento.
- `estudio-codificacion-exportacion`: exportación para análisis restringida al investigador.

### Modified Capabilities
- Ninguna. No hay specs previas de inter-jueces en `openspec/specs/` (verificado con `openspec list --specs`).

## Impact

- **classifier-service**: módulo de modelos nuevo y migración Alembic `20261104_0007` aditiva, con nueve tablas, entre ellas `estudio_enunciado` para los enunciados cargados a mano (design D14). Dos routers: `routes/estudio.py` y `routes/estudio_trabajo.py`. Endpoints de carga, cobertura y revisión de enunciados (`POST/GET .../enunciados`, `POST .../enunciados/{id}/revision`) y lecturas para el panel del investigador (`GET .../membresias` y `GET .../codebook/versiones[/{etiqueta}]`, tareas 5.2 y 5.3). Además: cliente de lectura del CTR con cuenta de servicio propia, filtro de traza y exportación. Sin cambios en `classifications`, `interrater_ratings`, `classifier_config_hash`, `LABELER_VERSION` ni `tree_version`.
- **web-teacher**: `main.tsx` (puerta de entrada), `utils/accesoPanel.ts` (nuevo), `routes/__root.tsx` (navegación restringida, sin tour ni onboarding en ese modo), `routes/entrenamiento-recalibracion.tsx`, `routes/interrater.tsx`, `views/InterraterTraining.tsx`, `views/InterraterCodingView.tsx`, `views/interraterShared.tsx`, `lib/api.ts`, `utils/helpContent.tsx`, tests nuevos.
- **No se tocan**: tutor-service, ctr-service, academic-service, api-gateway, analytics-service, web-student, web-admin.
- **Consumidores del piloto preservados**: ver design.md, "Consumidores".
- **Deploy**: dos servicios, de a uno: classifier-service (con migración) primero, web-teacher después. Ninguno es tutor ni ctr.
- **Datos**: los codificadores ven contenido de episodios de alumnos (chat, código, salidas). Pueden ser externos al equipo.

## Clasificación

**Propuesta del planner: CRITICAL** (el orquestador propuso HIGH).

Justificación: el change no solo expone datos de alumnos; crea un camino de autorización nuevo que concede lectura de episodios completos a personas que hoy no tienen acceso (externos sin comisión), salteando el gate A0.6 de ctr-service mediante una cuenta de servicio. Eso cruza el límite de seguridad y de datos sensibles, que el workflow clasifica CRITICAL aunque el diff sea chico. Además, en producción el gateway con Clerk le asigna los roles base `estudiante,docente` a todo usuario logueado (`apps/api-gateway/src/api_gateway/config.py:112`), así que un control por rol no protege nada: el diseño entero depende de la asignación por identidad, y un error ahí expone episodios a cualquier cuenta. La integridad de la referencia del paper (cegamiento, aislamiento, inmutabilidad del codebook congelado) es integridad de auditoría.

Consecuencias si se acepta CRITICAL: mutante sobre cada aserción de seguridad y de datos; recorrido humano real con Clerk antes de archivar (cuenta asignada entra, cuenta no asignada no, codificador no ve al otro); rutas no visitadas quedan como DEUDA. Si el humano decide HIGH, que quede escrito con fecha en la sección Aprobación.

## Preguntas abiertas para el humano

Decisiones no técnicas que el planner no toma. Las que tienen un default técnico lo dicen; cambiarlas puede cambiar specs.

1. **Consentimiento y marco ético**: ¿el consentimiento informado del piloto y el convenio con UTN cubren que personas externas al equipo lean chats y código de alumnos (pseudonimizados)? ¿Hace falta acuerdo de confidencialidad firmado por los codificadores externos? Ojo: el change les da a personas externas una cuenta de Clerk con motivo para entrar, y con Clerk toda cuenta recibe hoy el rol `docente` (ver DEUDA en design, Riesgos). La construcción puede avanzar, pero bloquea dar de alta a los codificadores (texto literal de la aprobación de Juani, 04/11/2026: aplica a todos los codificadores, no solo a externos). **Respondida por Juani el 04/11/2026: el consentimiento ya está.** Antes figuraba sin responder: no bloquea la construcción; bloquea dar de alta a los codificadores (texto literal de la aprobación de Juani, 04/11/2026: aplica a todos los codificadores, no solo a externos).
2. **Quiénes codifican** y quién es investigador. **Respondida por Juani el 04/11/2026: codifican dos profesores que no conocen los episodios de la muestra.** Queda pendiente nombrar al investigador (rol que carga muestra, codebook y anclas, y exporta). Recomendación técnica original, que la respuesta cumple: que los codificadores no sean docentes de las comisiones de la muestra, porque un docente de la comisión puede ver la etiqueta de la máquina en otras pantallas (Progresión, Niveles N1-N4) aunque esta sección la oculte. El identificador opaco mitiga, no elimina.
3. **Exposición previa al entrenamiento del piloto**: ¿alguno de los candidatos ya hizo el entrenamiento actual? Si sí, ¿queda excluido? El sistema no puede deshacer esa exposición.
4. **Enunciado del ejercicio**. **Respondida por Juani el 04/11/2026: SÍ se muestra el enunciado en la vista ciega, para codificar y también en las anclas de entrenamiento.** Se muestran el de la TP y, si el episodio trabajó un ejercicio del banco, también el del ejercicio. Cómo llegan: ver pregunta 12 y design D14.
5. **Evidencia de la traza ciega y episodios terminados** (decisión del investigador, default fijado por el orquestador el 04/11): se incluyen `lectura_enunciado`, `copia_intentada` y `pega_intentada` (sin el texto pegado), y se distingue "fin: cerrado" de "fin: abandonado"; se excluyen `reflexion_completada` (posterior al cierre), `pestana_*` y la procedencia automática del código. El codificador ve más que el juez (salidas, estados intermedios, copias, lecturas); la diferencia queda en design D4 para el método del paper. Cambiarla después de cargar la muestra exige un estudio nuevo. Se consideran terminados los episodios `closed` y los `paused` abandonados (ADR-055); se rechazan los `open` y, por default, los marcados `integrity_compromised`: ¿confirmar este último? **Respondida por Juani el 04/11/2026: confirma el default completo**, incluido el rechazo de los episodios marcados `integrity_compromised`.
6. **Régimen según la regla** (decisión del orquestador del 04/11, corrige la del intento 2 que contradecía el v0 §7): el régimen persistido es siempre el que da la regla sobre las dimensiones (o evidencia insuficiente, elegida explícitamente); el desacuerdo se registra en `regimen_propuesto` con nota obligatoria y no cambia el régimen. Alternativa descartada: permitir cerrar con un régimen distinto de la regla, que exigiría cambiar el texto de la §7 antes de congelar. El investigador confirma. **Respondida por Juani el 04/11/2026: confirma.**
7. **Valores de las dimensiones y confianza**: el sistema no los fija; los define el esquema de cada versión del codebook (D1-D3 presente/ausente y D4 interlocutor/oráculo/transferencia en el v0). El juez C1 usa además `no_evaluable` por dimensión: si la comparación lo necesita, se resuelve en el codebook, no en código.
8. **Completitud al cerrar**: la regla la toma el esquema de la versión congelada (dimensiones exceptuadas por régimen, cita requerida por valor, notas obligatorias por régimen o por marca de frontera, confianza obligatoria o no). El investigador debe confirmar que el esquema del codebook congelado refleja lo que quiere exigir.
9. **Reapertura**: default, una codificación cerrada no se reabre desde el sistema. ¿Hace falta que el investigador pueda reabrir con motivo registrado?
10. **Entrenamiento como requisito**. **Respondida por Juani el 04/11/2026: el entrenamiento NO es obligatorio para codificar.** Coincide con el default: el sistema no exige aprobarlo.
11. **Clasificación**: CRITICAL propuesto por el planner y confirmado por el plan-reviewer (J-1), contra HIGH del orquestador.
12. **Alcance en academic-service**. **Respondida por Juani el 04/11/2026: opción B, el enunciado se carga A MANO.** No se toca academic-service: el investigador sube un CSV exportado desde la consola de Postgres (una fila por TP y por ejercicio con `tipo`, `tp_id` o `ejercicio_id` y el texto), por endpoint del investigador, junto con la muestra o después; se valida que cubra todos los `problema_id` y `ejercicio_id` de la muestra y de las anclas. La consulta SQL la prepara el orquestador fuera del plan. Si falta un enunciado de la muestra, se bloquea la codificación de todo el estudio (design D14).

## Knowledge Base Impact

- `docs/adr/063-estudio-codificacion-ciega.md`: NUEVO (APPEND al conjunto de ADRs). Decisiones de cegamiento server-side, identidad por email, codebook en base, tablas separadas del piloto y carga manual de enunciados con revisión obligatoria (D14), con su riesgo de fidelidad: el texto subido no se puede verificar contra academic-service y `Ejercicio.enunciado_md` se edita en el lugar. No se toca el índice congelado de `docs/adr/README.md` (deuda conocida, CLAUDE.md).
- `CLAUDE.md` del repo: APPEND en "Propiedades críticas" de dos invariantes: la lista blanca de la traza ciega falla cerrada ante tipos de evento nuevos; las tablas del estudio no las lee ningún endpoint fuera del estudio. REWRITE de la línea del catálogo de keys de `helpContent` (sección "Sistema de ayuda in-app", suma `estudioEntrenamiento`) y de la lista de rutas del web-teacher ("Frontends React", rutas `entrenamiento-recalibracion` e `interrater` con su nuevo uso). No se tocan Casbin ni roles.
- `docs/servicios/classifier-service.md`: REWRITE de la sección de endpoints y tablas: agregar `/api/v1/interrater/estudios/*`, incluidos los de enunciados y las lecturas 5.2/5.3, y las tablas nuevas, incluida `estudio_enunciado`.
- `docs/SESSION-LOG.md`: APPEND con la entrada del change.
- `../obsidian.md` (nota viva, symlink al Cerebro Digital): REWRITE de `Estado actual`, `Últimos avances`, `Próximos pasos` y frontmatter al cerrar; APPEND en `Decisiones clave` y `Gotchas`. No se edita en esta fase.
- Runbook de carga (membresías, codebook y esquema, anclas, muestra, carga manual de enunciados y su revisión, congelado, exportación): sección nueva en `docs/servicios/classifier-service.md`, sin IDs de episodios. Incluye el riesgo de fidelidad de los enunciados cargados a mano y la nota de que la mayoría de las corridas de pruebas (`tests_ejecutados`) traen solo conteos, sin salida, aunque el codebook §2 hable de "lo que imprimió y el error".

## Aprobación

<!-- Sección reservada para el humano. El planner no la completa. -->

Texto escrito por el humano (Juani Sarmiento) en el chat el 04/11/2026, transcripto textual por el orquestador:

> Apruebo el 04/11/2026. Nivel CRITICAL. Alcance: Codificación (inter-jueces) y Entrenamiento-Recalibración, sólo classifier-service y web-teacher, enunciado por carga manual. Confirmo las preguntas 5 y 6. La 1 (consentimiento) queda pendiente con Alberto y bloquea dar de alta a los codificadores.
