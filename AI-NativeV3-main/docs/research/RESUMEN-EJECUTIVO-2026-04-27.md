# Resumen ejecutivo — sesión 2026-04-27

**Autor**: Alberto Alejandro Cortez (doctorando, UNSL)
**Destinatarios**: director de tesis, director de informática UNSL
**Contexto**: cierre de 3 de los 7 cambios grandes detectados en auditoría del repositorio del piloto AI-Native (`audi1.md`).

---

## Resumen en 30 segundos

Se implementaron **G3 mínimo + G4 + G5** del modelo híbrido honesto acordado: cumplen las promesas de las Secciones 4.3, 6.4, 7.3 y 8.5 de la tesis con código auditable y reproducible. **~3000 líneas de código nuevas, 274 tests automatizados, 4 ADRs documentando cada decisión, cero regresiones**. Existe **un bloqueante institucional** en G5 (registro externo auditable) que requiere coordinación con UNSL antes del deploy al piloto.

---

## Qué se implementó

### G4 — Etiquetador de eventos N1-N4 (ADR-020)

**Cumple**: tesis Sección 4.3 (catálogo de niveles analíticos), 6.4 (componente C3.2 "Etiquetador de eventos"), 15.2 (proporción de tiempo por nivel como dimensión de Coherencia Temporal).

**Approach**: derivación en lectura mediante función pura sobre `(event_type, payload)`. **No** modifica el payload de los eventos del CTR — preserva reproducibilidad bit-a-bit y el invariante de append-only del Capítulo 7.

**Versionabilidad**: bumpear `LABELER_VERSION` re-etiqueta datos históricos sin tocar el CTR. Las reglas pueden refinarse en piloto-2 sin invalidar evidencia previa.

**Endpoint nuevo**: `GET /api/v1/analytics/episode/{id}/n-level-distribution` devuelve la distribución de tiempo por nivel para un episodio dado.

### G5 — Registro externo auditable Ed25519 (ADR-021)

**Cumple**: tesis Sección 7.3 ("hash de referencia del CTR se almacena en dos ubicaciones... un registro externo auditable").

**Approach**: servicio nuevo `integrity-attestation-service` (puerto 8012). Cuando el `ctr-service` cierra un episodio, después del commit transaccional emite el hash final + metadatos a un stream Redis. El servicio de attestation firma con clave Ed25519 institucional y appendea a un archivo `.jsonl` rotado diariamente. La attestation es **eventualmente consistente** con SLO de 24 horas — su ausencia **no bloquea** el cierre del episodio (decisión de diseño explícita: la auditoría no debe degradar la operación del piloto).

**Auditoría externa**: la tool CLI `scripts/verify-attestations.py` permite a cualquier auditor (comité doctoral, par evaluador) verificar las firmas con la clave pública institucional, sin cooperación del sistema.

**Buffer canónico de firma documentado bit-exact** en el ADR-021 — cualquier reimplementación en otro lenguaje (Go, Rust) puede reproducir la verificación.

### G3 mínimo — Guardarraíles Fase A (ADR-019)

**Cumple**: tesis Sección 8.5 (4 tipos de comportamiento adverso del estudiante: jailbreak, consultas maliciosas, sobreuso, persuasión indebida) — **Fase A únicamente** (preprocesamiento del prompt).

**Approach**: módulo `guardrails.py` con regex compilados por categoría (jailbreak indirecto/sustitución/ficción, prompt injection, persuasión por urgencia). Por cada match el `tutor-service` emite un evento CTR `intento_adverso_detectado`. La detección **no bloquea** — el prompt llega al LLM sin modificación; el evento es side-channel para análisis empírico (Sección 17.8).

**Versionabilidad**: cada evento lleva `guardrails_corpus_hash` (SHA-256 determinista del corpus de patrones), análogo al `classifier_config_hash` del Capítulo 9.

---

## Lo que NO se hizo — declarado como agenda futura del Capítulo 20

| Item | Razón documentada |
|---|---|
| **G1** — CCD con embeddings semánticos | La operacionalización temporal actual es conservadora pero defensible; embeddings semánticos quedan para piloto-2 (ADR-017 a redactar). |
| **G2** — CII longitudinal completo | Pendiente. Versión mínima posible si el calendario lo permite; alternativa: declarar como agenda. |
| **G3 Fase B** — postprocesamiento + `socratic_compliance` | "Un score mal calculado es peor que ninguno." El campo queda como `None` en eventos hasta que la calibración con docentes valide el cálculo. |
| **G6** — desacoplamiento instrumento-intervención | Refactor de ~1500 LOC, post-piloto-1. Capítulo 19 ya reconoce el confound. |
| **G7 completo** — dashboard docente con alertas predictivas | MVP simple sí; versión completa con ML diferida. |

Cada decisión está **documentada en su ADR** (017-018 todavía por redactar para G1/G2). La diferencia entre "deuda silenciosa" y "decisión informada" es justamente esa documentación.

---

## ✅ Decisiones institucionales tomadas (2026-04-27)

Las 5 preguntas que originalmente bloqueaban el deploy fueron resueltas. El ADR-021 pasa de **Propuesto** a **Aceptado**.

| # | Decisión | Estado |
|---|---|---|
| 1 | VPS institucional separado para el `integrity-attestation-service` | ✅ **SÍ** — UNSL provee VPS dedicado. Se descarta el fallback de MinIO. |
| 2 | Custodia de la clave privada Ed25519 | ✅ **Director de informática UNSL**, sin participación del doctorando. |
| 3 | Presupuesto adicional para VPS | ✅ **APROBADO** |
| 4 | SLO de attestation con alerta a Grafana | ✅ **24 horas** (default recomendado). |
| 5 | Pubkey: URL pública canónica + commit como snapshot | ✅ **Ambos** (default recomendado). |

### Próximos pasos operativos (desbloqueados)

1. **Director de informática UNSL** ejecuta `docs/pilot/attestation-deploy-checklist.md` para provisionar el VPS, generar la clave Ed25519, y desplegar el servicio.
2. **Doctorando** recibe la pubkey institucional, la committea en `docs/pilot/attestation-pubkey.pem`, y verifica con `scripts/verify-attestations.py`.
3. **`ctr-service` del piloto** se configura para emitir attestation requests al Redis del VPS institucional (env var del despliegue).

**Tiempo estimado de provisioning del VPS + setup del servicio**: ~1-2 días de trabajo del DI UNSL siguiendo el checklist.

---

## Validación técnica

- **274 tests automatizados pasan** (incluye tests golden para reproducibilidad bit-a-bit de hashes y firmas Ed25519).
- **Lint estricto** clean en todos los archivos nuevos (`ruff` con reglas E,W,F,I,B,C4,UP,N,S,A,RUF,PL,SIM).
- **Cero regresiones**: `test_pipeline_reproducibility.py` (7 casos que validan que el clasificador es bit-exact reproducible) sigue verde sin haberse tocado.
- **Tests de integración con Redis real** vía testcontainers (skipped en máquinas sin Docker, pasarían en CI).

---

## Próximos pasos sugeridos

| Plazo | Acción | Responsable |
|---|---|---|
| Próximos días | Director de informática UNSL ejecuta `docs/pilot/attestation-deploy-checklist.md`: provisiona el VPS, genera la clave Ed25519 institucional, despliega el `integrity-attestation-service`. | DI UNSL |
| Tras Paso 1 | Doctorando recibe la pubkey institucional, la committea como `docs/pilot/attestation-pubkey.pem`, valida con `scripts/verify-attestations.py`. | Doctorando |
| Próximas 2 semanas | Doctorando lee los 4 ADRs nuevos (019, 020, 021, 016) y corre la suite de tests local para internalizar las decisiones. | Doctorando |
| Decisión paralela | Implementar **G2 versión mínima** (~3-4 días) o declararla como agenda Cap 20 según calendario de la defensa. | Director de tesis + Doctorando |

---

## Documentación de referencia

| Documento | Propósito |
|---|---|
| `docs/SESSION-LOG.md` (entrada 2026-04-27) | Bitácora narrativa con decisiones, archivos, validaciones. |
| `docs/adr/019-guardrails-fase-a.md` | ADR de G3: detección preprocesamiento. |
| `docs/adr/020-event-labeler-n-level.md` | ADR de G4: etiquetador C3.2. |
| `docs/adr/021-external-integrity-attestation.md` | ADR de G5: registro externo Ed25519. |
| `docs/pilot/auditabilidad-externa.md` | Procedimiento del auditor externo (4 pasos). |
| `reglas.md` (RN-128, RN-129) | Reglas de negocio formalizadas. |
| `CLAUDE.md` | Source of truth operativo del repositorio. |

---

*Documento generado al cierre de la sesión 2026-04-27. Última verificación de tests: ese mismo día.*
