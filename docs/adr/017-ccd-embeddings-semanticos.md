# ADR-017 — CCD con embeddings semánticos (DIFERIDO a Eje B post-defensa)

- **Estado**: Aceptado (decisión: **DIFERIR**, no implementar pre-defensa)
- **Fecha**: 2026-04-29
- **Deciders**: Alberto Cortez, director de tesis
- **Tags**: classifier, ccd, eje-b, agenda-confirmatoria
- **Cierra slot reservado**: G1 del audi1.md original; G14 del audi2.md.

## Contexto y problema

[`apps/classifier-service/src/classifier_service/services/ccd.py`](../../apps/classifier-service/src/classifier_service/services/ccd.py) opera por **proximidad temporal** de 2 minutos entre acciones (código) y verbalizaciones (anotaciones / prompts / respuestas). La tesis Sección 15.3 caracteriza CCD como "similitud semántica entre explicaciones en chat y contenido del código (mediante técnicas de embeddings)". La 15.6 ya declara la implementación temporal como gap explícito: *"La operacionalización temporal es computacionalmente liviana, determinista, reproducible bit-a-bit y libre de dependencias externas; captura una señal importante del proceso pero no su contenido."*

Un estudiante que escribe "hola" en una nota cada vez que ejecuta código sacaría CCD altísimo con la implementación actual — el contenido es semánticamente irrelevante.

## Decisión

**DIFERIR** la migración a embeddings semánticos. La operacionalización temporal v1.0.0 es la versión del piloto.

### Por qué

- **Dependencias nuevas pesadas**: requiere endpoint `/embeddings` en `ai-gateway`, integración con budget tracking, decisión de modelo (proveedor cloud vs `fastembed` local con ~500MB de pesos en CPU).
- **Reproducibilidad bit-a-bit comprometida si el modelo cambia**: necesita pin exacto de modelo + versión + agregarlo a `classifier_config_hash`. Append-only del CTR (ADR-010) cubre la reclasificación, pero la coordinación con el piloto activo es delicada.
- **El gap está honestamente declarado en la tesis**: 15.6 reconoce que la operacionalización temporal "captura una señal importante del proceso pero no su contenido". Defender con la operacionalización temporal v1.0.0 + 15.6 explícita es coherente con el modelo híbrido honesto.
- **Costo del piloto bajo, costo de coordinación alto**: ~$0.80 USD para 500 estudiantes × 20 episodios × 10 pares × 2 embeddings × 200 tokens × $0.00002/1k tokens. El costo monetario es despreciable, pero el costo de validar reproducibilidad + cambiar el `classifier_config_hash` mid-cohort no.

## Criterio para revisitar (Eje B post-defensa)

Implementar G14 cuando se cumpla **alguno** de:

1. El reporte empírico del piloto-1 muestra que el sesgo del CCD temporal explica una varianza significativa del clasificador (ej. estudiantes con CCD-temporal alto pero contenido irrelevante).
2. Se acepta una pausa entre cuatrimestres lo suficientemente larga (≥1 mes) para validar el embedding pipeline + bumpear `classifier_config_hash` sin afectar la cohorte activa.
3. El comité doctoral acepta la migración como agenda Eje B y prioriza el upgrade.

### Pipeline propuesto (referencia)

Detallado en audi2.md G14: pipeline de 4 pasos (extracción de pares acción↔discurso → embedding código + discurso → score coseno → agregación con `ccd_mean` + `ccd_orphan_ratio` + nuevo `ccd_contradiction_ratio`).

## Consecuencias de DIFERIR

### Positivas

- Defensa pre-piloto-1 puede usar `ccd_mean` / `ccd_orphan_ratio` con la operacionalización temporal sin sorpresas.
- Cero coordinación con `ai-gateway` ahora (no hay endpoint `/embeddings` que mantener).
- `classifier_config_hash` permanece estable durante el piloto.

### Negativas

- El sesgo "CCD alto con contenido irrelevante" es real y declarable como limitación del piloto-1.
- Cuando se implemente, la migración tiene impacto en al menos: `ccd.py`, `pipeline.py` (config hash), `ai-gateway` (endpoint nuevo), corpus de golden fixtures, ADR de bump.

## Referencias

- audi1.md G1 (slot 017 reservado).
- audi2.md G14 — pipeline propuesto detallado.
- ADR-010 — append-only del CTR (cubre reclasificación).
- Tesis Sección 15.3, 15.6, 20.5.1 (Eje B).
