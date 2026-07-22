## ADDED Requirements

### Requirement: Modal de reflexión opcional al cerrar episodio

El sistema SHALL ofrecer al alumno un modal de reflexión metacognitiva inmediatamente después del cierre exitoso de un episodio. El modal SHALL ser opcional — el alumno PUEDE cerrarlo sin responder. El cierre del episodio (`EpisodioCerrado`) SHALL NO esperar la respuesta del modal — son flujos independientes.

#### Scenario: Alumno cierra modal sin responder

- **WHEN** el episodio cierra exitosamente y el alumno presiona "X" en el modal de reflexión
- **THEN** el sistema SHALL cerrar el modal sin emitir evento `reflexion_completada`
- **AND** el episodio SHALL quedar cerrado con su evento `EpisodioCerrado` ya appendeado al CTR

#### Scenario: Alumno responde reflexión

- **WHEN** el alumno completa los campos del modal y presiona "Enviar"
- **THEN** el sistema SHALL pegar `POST /api/v1/episodes/{id}/reflection` con el payload
- **AND** el endpoint SHALL emitir un evento `reflexion_completada` al CTR

### Requirement: Evento `reflexion_completada` como side-channel

El sistema SHALL emitir el evento `reflexion_completada` con payload: `que_aprendiste` (string ≤500 chars), `dificultad_encontrada` (string ≤500 chars), `que_haria_distinto` (string ≤500 chars), `prompt_version` (string, ej: "reflection/v1.0.0"), `tiempo_completado_ms` (integer). El evento SHALL appendarse al CTR del episodio aunque el episodio ya esté cerrado (CTR es append-only — un episodio cerrado no rechaza eventos posteriores).

#### Scenario: Reflexión emitida después de episodio cerrado

- **WHEN** un episodio tiene `estado=cerrado` y el alumno envía reflexión 5 minutos después del cierre
- **THEN** el evento `reflexion_completada` SHALL appendarse al CTR con `seq` posterior al `EpisodioCerrado`
- **AND** la cadena criptográfica SHALL preservarse (chain_hash continúa)

### Requirement: Reflexión NO entra al classifier ni a features

El classifier-service SHALL excluir explícitamente todos los eventos `reflexion_completada` del feature extraction. La presencia o ausencia de reflexión SHALL NO afectar el `classifier_config_hash` ni el resultado de la clasificación N4 del episodio.

#### Scenario: Reproducibilidad bit-a-bit con/sin reflexión

- **WHEN** dos episodios idénticos en eventos pedagógicos pero uno tiene `reflexion_completada` y el otro no
- **THEN** el classifier SHALL producir el mismo resultado (mismas features, mismas coherencias, mismo `classifier_config_hash`) para ambos

### Requirement: Privacy de reflexión — campos en español, no anonimizados en CTR

El sistema SHALL persistir el contenido de la reflexión tal cual lo escribió el alumno (string libre) en el payload del evento. El export académico anonimizado (`packages/platform-ops/academic_export.py`) SHALL excluir los campos textuales de reflexión por default — `include_reflections=false` default.

#### Scenario: Export académico omite reflexiones por default

- **WHEN** un investigador corre `make export-academic` sin flag adicional
- **THEN** el JSON exportado SHALL incluir el evento `reflexion_completada` con `prompt_version` y `tiempo_completado_ms` pero los 3 campos textuales SHALL aparecer como `[redacted]`

#### Scenario: Investigador con consentimiento exporta reflexiones

- **WHEN** se invoca el export con flag `--include-reflections`
- **THEN** los 3 campos textuales SHALL aparecer íntegros y el export SHALL registrar audit log structlog `reflections_exported_with_consent`
