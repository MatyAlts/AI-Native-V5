# ADR-063 — Estudio de codificación ciega: referencia humana para comparar jueces

- **Estado**: Aceptado (aprobación humana del 04/11/2026, nivel CRITICAL, registrada en `openspec/changes/cibse-codificacion-ciega/proposal.md` § Aprobación)
- **Fecha**: 2026-11
- **Deciders**: Juani Sarmiento (alcance y decisiones de las preguntas abiertas); Alberto Cortez (criterio académico y marco ético, pregunta 1 pendiente)
- **Tags**: investigación, privacidad, seguridad, datos, reproducibilidad, classifier-service, web-teacher
- **Relacionado**: [ADR-046](046-kappa-threshold-070-paper-alignment.md) (umbral κ del protocolo inter-jueces del piloto, que este ADR no modifica), [ADR-055](055-reingreso-episodio-pausado.md) (episodio `paused` por abandono), [ADR-062](062-regla-trivaluada-kleene-y-bump-tree-version.md) (juez semántico que el estudio evalúa). Change OpenSpec `cibse-codificacion-ciega` (design D1 a D14).

## Contexto y problema

El paper CIbSE 2027 compara el juez LLM actual (C0) con uno revisado (C1) contra una **referencia humana**: dos codificadores clasifican a ciegas una muestra fija de 150 episodios del segundo semestre de 2026, siguiendo un codebook que todavía no está congelado.

La herramienta inter-jueces del piloto no servía y además contaminaba la referencia:
- su entrenamiento enseñaba la regla que el paper evalúa ("el sobreuso manda, pasiva");
- su traza mostraba `intento_adverso_detectado`, `prompt_kind`, metadatos del tutor y el payload JSON completo;
- su muestra era dinámica (primeros N por etiqueta de máquina);
- su etiqueta era un solo valor, sin dimensiones ni evidencia citada.

A eso se suma la identidad: en producción el gateway con Clerk le asigna `estudiante,docente` a toda cuenta logueada, así que un control por rol no protege nada. Los codificadores pueden ser externos y sin comisión, y van a leer chats y código de alumnos.

## Drivers de la decisión

- Cegamiento verificable en el servidor: ninguna decisión ni marca de la máquina llega al navegador del codificador.
- Evidencia idéntica y fija para los dos codificadores, aunque el episodio cambie después.
- Acceso por identidad asignada, no por rol genérico; aislamiento entre codificadores.
- El codebook evoluciona: su texto, su formulario y su regla de decisión no pueden vivir en el código.
- Inmutabilidad de la referencia (integridad de auditoría): versiones congeladas, historial y respuestas que la base misma protege.
- Cero impacto sobre las etiquetas oficiales y del piloto; no tocar tutor-service, ctr-service ni academic-service.

## Decisiones (D1 a D14 del design)

### D1. Tablas nuevas, separadas del piloto
Nueve tablas en `classifier_db` con RLS por tenant: `estudio_codificacion`, `estudio_membresia`, `estudio_muestra`, `estudio_enunciado`, `codebook_version`, `estudio_ancla`, `estudio_etiqueta`, `estudio_etiqueta_historial` y `entrenamiento_respuesta`; migración `20261104_0007`. Lo exclusivo de Postgres (unicidad parcial, triggers, FK circular) vive solo en la migración, porque otros paquetes hacen `create_all` del modelo sobre SQLite.
*Alternativa rechazada*: `interrater_ratings` con `protocol="cibse"`. Las etiquetas del estudio quedaban mezcladas en el κ del piloto (`analytics.py::interrater_aggregate`, `pedagogia.py`), que además no tiene control de rol.

### D2. Inmutabilidad por triggers
La base rechaza:
- UPDATE o DELETE de una versión congelada;
- INSERT, UPDATE o DELETE de anclas de una versión congelada;
- UPDATE o DELETE del historial y de las respuestas de entrenamiento;
- UPDATE de la evidencia fija y de los ids de enunciado de muestra y anclas;
- UPDATE o DELETE de un enunciado ya revisado.

*Alternativa rechazada*: disciplina de aplicación cubierta por tests (como `classification_reviews`). Para la referencia de un paper, el esquema tiene que impedirlo aunque un endpoint futuro se equivoque.

### D3. Acceso por membresía atada al `user_id` firmado
Un investigador o un administrador asigna un email como `investigador` o `codificador`. En el primer uso, la membresía se ata al `X-User-Id`, que es el campo que cubre la firma del gateway (el email no). Otra cuenta con el mismo email recibe 403 y queda en el log (`estudio_membresia_user_id_distinto`). Los roles `docente`, `superadmin` o `docente_admin` no alcanzan para leer datos del estudio. Revocar no borra nada; una re-asignación crea una membresía nueva.
*Alternativas rechazadas*:
- rol nuevo en Clerk o Casbin: el gateway no transporta roles por usuario;
- usar `docente`: lo tiene cualquier cuenta;
- asignar los codificadores a una comisión: les daría el CTR completo;
- llave solo por email: no está firmado.

*Supuesto declarado*: el email de Clerk es verificado. Se confirma en el recorrido humano.

### D4. Traza ciega con lista blanca versionada (`traza_v1`)
classifier-service lee el episodio con una cuenta de servicio propia (`ESTUDIO_LECTOR_SERVICE_USER_ID`, rol `classifier_worker`, firma HMAC si hay secreto) y arma la respuesta desde cero.

Lista blanca por tipo y por campo:
- inicio; lectura de la consigna (latidos agrupados);
- mensajes del alumno y del tutor (solo el texto);
- estados del código; ejecuciones con salidas y conteos; corridas de pruebas (conteos);
- notas del alumno; intentos de copiar y de pegar (sin el texto pegado);
- fin cerrado o abandonado (sin motivo).

Todo lo demás se omite, incluidos los tipos futuros. Un test enumera los `event_type` del contrato y exige una decisión explícita para cada uno. Los localizadores (`n` global; turno, código, ejecución, prueba, nota y lectura por tipo) se asignan después de filtrar, y el tiempo se da relativo al inicio.

*Alternativas rechazadas*:
- filtrar en el front: el payload completo viajaría al navegador;
- endpoint filtrado en ctr-service: está fuera de alcance;
- usar la sesión del codificador contra `/api/v1/audit`: los externos fallan el gate A0.6 y los docentes recibirían el payload completo.

**Diferencia de evidencia humano/juez (para la sección de método del paper)**: con `traza_v1` el codificador ve, además de lo que ve el juez, stdout y stderr, todos los estados intermedios del código, los intentos de copiar y pegar (sin contenido), las lecturas de la consigna y si el episodio terminó cerrado o abandonado. El juez (`services/regimen_llm.py`) ve solo el transcript, las anotaciones, el último snapshot y conteos. La diferencia es deliberada (la evidencia humana sigue el codebook §2 y §4), tiene que declararse en el paper y cambiarla exige una `traza_version` nueva.

### D4b. Evidencia fija por ítem
Al cargar un ítem se guardan `seq_tope`, `chain_hash_tope`, `events_count_carga`, `last_chain_hash_carga` y `estado_carga`. La traza sirve solo hasta el tope.
- Si el evento del tope ya no coincide: 409 `evidencia_alterada` y log.
- Si la versión de lista blanca del código difiere de la del estudio, fijada en el alta: 409 `traza_version_distinta`.

### D5. Identificador opaco
El codificador ve solo `item_id`, nunca `episode_id`. La exportación del investigador sí lo incluye.

### D6. Muestra cargada por endpoint, nunca en el repo
El investigador sube el CSV crudo, con `sha256_esperado` opcional. Se calcula el sha256 de los bytes, se guarda solo `episode_id` y el resto se descarta. La carga es todo o nada.

Episodios aceptados: `closed`, o `paused` cuyo último evento de cierre es `episodio_abandonado`. Se rechazan `open`, `paused` sin abandono y los marcados `integrity_compromised` (pregunta 5, confirmada por el humano).
*Alternativas rechazadas*:
- commitear los IDs: quedarían en GitHub junto con estrato y origen;
- script contra la base de producción: saltea la auditoría;
- hash declarado por el navegador: no es verificable.

### D7. Orden por codificador reproducible
Cada codificador tiene una `semilla = secrets.randbits(63)`, distinta dentro del estudio.

**Procedimiento exacto (copiar al método del paper)**: la posición de cada ítem es su rango, en orden ascendente del hex, de `sha256((str(semilla) + ":" + item_id).encode("utf-8"))`, donde `semilla` es el entero en decimal sin relleno e `item_id` es el UUID en minúsculas con guiones (forma canónica de 36 caracteres). No depende de `random` ni de la versión del lenguaje: se recomputa con `printf '%s' "<semilla>:<item_id>" | sha256sum`. La exportación incluye semilla y posición.
*Alternativa rechazada*: `random.shuffle` con semilla, que depende de la implementación de Python.

### D8. Codebook versionado en la base
Una versión nace en borrador (vacía o clonando texto, esquema y anclas). Al congelarla se calcula `contenido_sha256` sobre `{contenido_md, esquema, anclas}`:
- cada ancla entra con exactamente `uso, orden, episode_id, respuesta_esperada, explicacion_md, consensuado_por, seq_tope, chain_hash_tope`;
- las anclas se ordenan por `(uso, orden, episode_id)`;
- la serialización es `json.dumps(sort_keys=True, ensure_ascii=False, separators=(",", ":"))` en UTF-8.

Con etiquetas existentes, la versión vigente ya no cambia. La codificación exige la vigente congelada; el entrenamiento usa la vigente aunque sea borrador.
*Alternativa rechazada*: el codebook como archivo del repo. Cada edición del borrador exigiría PR y redeploy, y el estado congelado dependería de convenciones de git.

### D9. Formulario y regla de decisión definidos por el esquema de la versión
Un meta-esquema cerrado declara:
- dimensiones con valores y valores que exigen cita;
- regímenes, el de evidencia insuficiente y los regímenes exentos;
- dimensiones opcionales y notas obligatorias por régimen, y marca de frontera con notas obligatorias;
- confianza;
- `reglas_regimen`: lista ordenada de condiciones, cada una una conjunción de disyunciones de átomos.

El régimen persistido es siempre el que da la regla, salvo un exento elegido explícitamente. `regimen_regla` se guarda siempre que sea calculable. El desacuerdo va en `regimen_propuesto`, con nota obligatoria; `disiente_de_regla` se deriva y no se persiste. Forma exacta del meta-esquema: `docs/servicios/classifier-service.md`, sección 12.2, «Forma exacta del meta-esquema» (único lugar canónico; este ADR no la repite). Congelar una versión revalida sus anclas contra ese esquema y rechaza con 422 si alguna no vale o no está completa con la misma regla que el cierre de una codificación.
*Alternativas rechazadas*:
- formulario fijo en código según el v0 §7: el §9 deja abiertos cambios;
- permitir cerrar con un régimen distinto de la regla: contradice el v0 §7 (pregunta 6, confirmada por el humano).

### D10 y D10b. Etiquetado, historial, cierre y concurrencia
- Guardado incremental validado contra el esquema, con historial append-only en la misma transacción.
- Cierre con completitud del esquema; después del cierre, todo guardado da 409.
- Orden de locks fijo: fila del estudio (`FOR SHARE` al guardar y cerrar; `FOR UPDATE` al cambiar la vigente, cargar la muestra, congelar o tocar anclas) y después la membresía (`FOR UPDATE`).
- Ningún endpoint de codificador acepta otro `membresia_id`; el investigador ve solo cantidades.

### D11. Entrenamiento con anclas persistidas
Las anclas `ejemplo` se muestran con traza, respuesta esperada y explicación. Las de `practica` se muestran a ciegas, y la respuesta esperada y la explicación llegan recién tras responder (append-only). Una muestra y sus anclas se excluyen mutuamente, bajo el lock del estudio. No hay umbral de aprobación: el entrenamiento no es obligatorio (pregunta 10).
*Alternativa rechazada*: anclas hardcodeadas en el front, como en el piloto (retiradas).

### D12. Exportación solo para el investigador
CSV y JSON con las mismas filas, en tres contenidos: etiquetas, entrenamiento e historial. Cada fila incluye la semilla, la posición, la versión y el sha del codebook, la `traza_version`, las columnas `dim_<clave>_valor`/`_cita`, `regimen`, `regimen_regla`, `regimen_propuesto` y el desacuerdo derivado, y los sha256 de los enunciados. No lleva emails ni contenido de episodios. En el CSV, una celda que empieza con `=`, `+`, `-`, `@`, tabulador o CR se prefija con `'`. Cada exportación queda en el log.

### D13. Web-teacher
Las dos secciones existentes, Entrenamiento-Recalibración y Codificación (inter-jueces), se rehacen para el estudio. Un miembro sin comisiones entra en modo restringido: solo esas dos secciones, sin tour, onboarding ni selectores. Un docente con comisiones entra aunque classifier-service no responda.
*Alternativa rechazada*: pantallas nuevas en el menú.

### D14. Enunciado en la vista ciega, cargado a mano
Se muestra la consigna de la TP y, si el episodio trabajó un ejercicio, también la del ejercicio. Nunca se muestran rúbrica, tests, material del tutor, título, código ni fechas.

- **Carga**: el investigador sube un CSV exportado de Postgres (`tipo,tp_id,ejercicio_id,enunciado`). El texto se fija con su sha256 y el del archivo. Las filas sin uso se ignoran y se informan, y se devuelve la cobertura respecto de los `problema_id`/`ejercicio_id` fijados en la muestra y las anclas.
- **Revisión obligatoria**: alertas automáticas de fechas, emails, docentes, comisiones y horarios, y de rúbrica, tests, pistas y soluciones (A4-2). El investigador aprueba el original o guarda una versión editada; el original nunca se borra.
- **Bloqueo**: si falta o no está revisado algún enunciado de la muestra, se bloquea la codificación de TODO el estudio. El entrenamiento se bloquea ancla por ancla.

*Alternativas rechazadas* (pregunta 12, opción B):
- endpoint interno en academic-service: amplía el alcance a otro servicio;
- usar endpoints existentes con roles de servicio: traen soluciones;
- leer `academic_main` desde classifier: lo prohíbe ADR-003.

**Riesgo propio**: el sistema no puede verificar que el texto subido sea el de academic-service. `Ejercicio.enunciado_md` se edita en el lugar, sin versión (A4-1 del plan-reviewer). La mitigación es procedimental: la consulta de exportación la arma el orquestador, `archivo_sha256` queda registrado, la revisión es obligatoria y el método lo declara.

## Consecuencias

### Positivas
- El cegamiento y la evidencia fija se verifican en el servidor, con tests y mutantes (lista blanca que falla cerrada, cobertura de tipos, tope y chain hash).
- La referencia del paper queda protegida por la base (triggers) además de la API.
- El codebook puede cambiar sin tocar código; la reproducibilidad se ancla en el sha al congelar.
- Las etiquetas oficiales y del piloto quedan intactas (test de separación).

### Negativas / trade-offs
- La cuenta de servicio lee cualquier episodio del tenant. La mitigación es que solo resuelve `item_id` del estudio del caller.
- Los codificadores ven más evidencia que el juez, y esa diferencia tiene que declararse.
- La fidelidad de los enunciados depende de una carga manual.
- Con Clerk, el email no está firmado: la atadura al `user_id` limita el daño, pero no lo elimina hasta el primer uso.

### Neutras
- Endpoints bajo `/api/v1/interrater/estudios/*`, ya ruteado por el gateway; el gateway no se toca.
- Los endpoints del piloto (`/sample`, `/ratings`, `/my-progress`, el agregado κ y `/interrater-admin`) siguen funcionando sobre `interrater_ratings`.
- Deuda preexistente fuera de alcance: `POST /api/v1/interrater/ratings` y `/api/v1/analytics/interrater/aggregate` aceptan cualquier cuenta de Clerk (observado por lectura, no reproducido).

## Referencias

- `openspec/changes/cibse-codificacion-ciega/` (proposal, design, specs, tasks e informes).
- `docs/servicios/classifier-service.md`: endpoints, tablas y runbook del estudio.
- Código: `apps/classifier-service/src/classifier_service/{models/estudio.py, routes/estudio.py, routes/estudio_trabajo.py, services/traza_ciega.py, services/estudio_*.py, services/ctr_lectura.py}` y la migración `alembic/versions/20261104_0007_estudio_codificacion.py`.
