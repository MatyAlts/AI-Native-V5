# ADR-046 — Umbral kappa intercoder a 0,70 + protocolo dual (alineacion paper Cortez & Garis)

- **Estado**: Aceptado
- **Fecha**: 2026-05-10
- **Deciders**: Alberto Cortez (director tesis), Ana Garis (co-directora paper)
- **Tags**: validacion-intercoder, kappa, paper-alignment, pre-defensa, supersede-parcial
- **Supersede PARCIAL**: ADR-027 (Validacion κ con docentes), ADR-032 (Ground truth docente), ADR-044 (Fase B socratic_compliance), ADR-045 (Override lexico anotaciones). En todos estos, el umbral κ ≥ 0,6 queda reemplazado por κ ≥ 0,70 y el protocolo muestral se concreta como dual A+B.

## Contexto y problema

La auditoria comparativa entre el paper "Modelo N4 de trazabilidad cognitiva para la ensenanza universitaria de programacion con asistentes de IA generativa" (Cortez & Garis, UTN-FRM + UNSL) y la implementacion del proyecto identifico dos divergencias operacionalmente relevantes (ver `ppconarev.md` 2026-05-10):

1. **Umbral kappa**: el paper publica `κ ≥ 0,70` consistentemente (Resumen, H3 §6.1, Tabla 5, §7, Tabla 6) citando Landis y Koch (1977) como "acuerdo sustancial". El codigo documentaba `κ ≥ 0,6` en 4 ADRs (027, 032, 044, 045), `event_labeler_lexical.py:19`, `KappaRatingView.tsx:95`, y `docs/limitaciones-declaradas.md:107-108`. Diferencia operativa relevante de cara a la validacion intercoder pendiente (A2 del `plan-accion.md`).

2. **Protocolo muestral**: el paper Sec 7 prescribe 200 eventos estratificados (50 por nivel cognitivo N1-N4) + 20 episodios de calibracion + 50 episodios distintos para remuestreo. Los ADRs 044/045 mencionaban genericamente "50+ anotaciones etiquetadas por 2 docentes" sin estratificacion, lo cual sub-evalua los componentes del clasificador.

**Bug semantico detectado**: 0,60 cae tecnicamente en el rango "moderado" segun Landis-Koch estricto (0,41-0,60); el rango "sustancial" empieza en 0,61. La afirmacion del paper "acuerdo sustancial segun Landis y Koch" es incompatible con κ ≥ 0,60.

## Decision

Adoptamos:

1. **Umbral kappa**: κ ≥ 0,70 (comodamente en rango sustancial Landis-Koch). Reemplaza el umbral 0,6 en todos los ADRs y modulos referenciados arriba.

2. **Protocolo dual**:
   - **Protocolo A — Validacion del etiquetador N1-N4**: 200 eventos estratificados, 50 por nivel cognitivo, etiquetados por 2 docentes independientes. Valida `apps/classifier-service/src/classifier_service/services/event_labeler.py::label_event`.
   - **Protocolo B — Validacion del clasificador de apropiacion**: 50 episodios cerrados distribuidos aproximadamente equilibrados entre las tres categorias esperadas (~16-17 por categoria), clasificados por los mismos 2 docentes. Valida `apps/classifier-service/src/classifier_service/services/tree.py::classify_episode`.
   - Ambos protocolos requieren κ ≥ 0,70 en al menos 2 de 3 pares evaluados (Clasificador vs A1, Clasificador vs A2, A1 vs A2).
   - Sesion previa de calibracion conjunta sobre 20 episodios.

3. **Plan de contingencia (preserva lo del paper Sec 7)**:
   - Si κ cae entre 0,40-0,69: sesion de calibracion + remuestreo de 50 episodios distintos (segunda ronda).
   - Si κ permanece < 0,40 tras dos rondas: reformulacion de los criterios operativos del clasificador.

## Drivers de la decision

- **D1**: Defendibilidad academica ante tribunal doctoral UNSL. El paper es el ancla publica del proyecto; modificarlo post-publicacion es mas costoso que modificar el codigo.
- **D2**: Alineamiento con literatura del campo. Evidence-centered design (Mislevy/Steinberg/Almond 2003, citado en el paper), AERA/APA/NCME (2014) y la convencion de educational measurement rigurosa usan 0,70 como umbral minimo para clasificacion de constructos cognitivos.
- **D3**: Margen de seguridad ante varianza muestral. Con N=50-200 muestras el kappa estimado tiene varianza del orden de ±0,06; un umbral mas alto deja margen ante oscilaciones.
- **D4**: Eliminacion del bug semantico "0,6 = sustancial".

## Opciones consideradas

### Opcion A — Umbral 0,70 + protocolo dual A+B (elegida)

Ya descrita en la seccion Decision.

**Ventajas**:
- Coherencia paper ↔ codigo ↔ ADRs (los tres artefactos publican el mismo numero).
- Defendibilidad ante reviewers academicos del campo (educational measurement).
- Cubre los dos componentes del clasificador por separado (etiquetador N1-N4 y arbol de apropiacion) — kappa global no enmascara fallas locales.
- El plan de contingencia del paper queda calibrado para el umbral correcto.

**Desventajas**:
- Costo operacional alto: 2 docentes × (200 + 50) = 500 actos de etiquetado totales (vs 100 con protocolo unificado de 50 anotaciones), ~25-30 horas/docente con calibracion previa de 20 episodios.
- Mayor probabilidad de no cumplir el gate en primera ronda → segunda ronda de calibracion + remuestreo planificada.
- Features dependientes del gate (`socratic_compliance_enabled`, `lexical_anotacion_override_enabled`) tardaran mas en activarse.

### Opcion B — Mantener κ ≥ 0,60 + actualizar el paper

Editar el paper para que publique 0,60, dejando codigo y ADRs como estan.

**Desventajas que la descartan**:
- El paper esta en flujo de revision/publicacion academica — modificar post-submission es operacionalmente mas costoso que modificar codigo interno.
- 0,60 queda en rango "moderado" Landis-Koch, contradiciendo la calificacion textual del paper ("acuerdo sustancial"). Mantenerlo perpetua el bug semantico.
- Pierde alineamiento con la literatura del campo (AERA/APA/NCME 2014 usa 0,70 como minimo para constructos cognitivos).

### Opcion C — Umbral 0,70 con protocolo unico (solo Protocolo A o solo B)

Subir el umbral pero unificar a un solo protocolo de validacion (etiquetador o arbol, no ambos).

**Desventajas que la descartan**:
- Un kappa unico sobre etiquetas finales del clasificador no permite atribuir fallas a etiquetado (N1-N4 sobre eventos) vs clasificacion (apropiacion sobre episodios) — son dos operacionalizaciones distintas con corpora distintos.
- El paper Sec 7 prescribe explicitamente ambos componentes; reducirlo a uno solo se aleja del diseno publicado.

## Criterios de exito

1. Todos los ADRs historicos que mencionan `κ ≥ 0,6` (027, 032, 044, 045) quedan marcados con `Supersede PARCIAL: ADR-046` en este nuevo ADR; los ADRs viejos no se modifican retrospectivamente.
2. Los modulos de codigo afectados (`event_labeler_lexical.py:19`, `KappaRatingView.tsx:95`) actualizan sus comentarios/strings al nuevo umbral 0,70 con referencia explicita a ADR-046.
3. `docs/limitaciones-declaradas.md` agrega entrada de versionado 2026-05-10 documentando el cambio.
4. Verificable por grep: `grep -r "kappa.*0[,.]6" docs/ apps/` no debe devolver resultados nuevos post-ADR (las menciones en ADRs historicos 027/032/044/045 quedan congeladas como historico).
5. Cuando se ejecute la validacion intercoder real (A2 del `plan-accion.md`), el report debe documentar Protocolo A y Protocolo B por separado, con kappa por cada uno y por cada par evaluador.

## Criterio de revisita

- Si tras dos rondas de calibracion el umbral 0,70 demuestra ser inalcanzable con el corpus disponible y el equipo decide bajar, sera necesario un ADR-047 explicito que documente la decision con argumentacion metodologica (ver `ppconarev.md` sobre "contra-recomendacion"). NO bajar el umbral por la via de hecho.
- Si en el futuro la validacion intercoder pos-defensa muestra que el corpus permite umbrales mas altos sin perder activacion, podra emitirse un ADR-047 que considere `κ ≥ 0,75` u 0,80.

## Consecuencias

### Positivas

- Coherencia paper ↔ codigo ↔ ADRs sobre el umbral kappa.
- Defendibilidad ante reviewers academicos y tribunal doctoral.
- Plan de contingencia del paper Sec 7 queda calibrado para el umbral correcto.
- Eliminacion del bug semantico "0,6 = sustancial" segun Landis-Koch.
- Validacion por componente (etiquetador vs arbol de apropiacion) permite diagnosticar fallas con granularidad.

### Negativas

- 2 docentes × (200 + 50) = 500 actos de etiquetado totales (vs 100 con protocolo unificado de 50 anotaciones).
- ~25-30 horas/docente con calibracion previa de 20 episodios.
- Mas alta probabilidad de no cumplir el gate en primera ronda → segunda ronda de calibracion + remuestreo.
- Features dependientes del gate (`socratic_compliance_enabled`, `lexical_anotacion_override_enabled`) tardaran mas en activarse.

### Neutras

- Los ADRs 027, 032, 044, 045 NO se modifican retrospectivamente. Su numeracion + contenido original quedan como historico de la decision previa. Este ADR-046 es la nueva fuente de verdad sobre el umbral kappa.
- El contrato del CTR no cambia. El `classifier_config_hash` no cambia. Las classifications historicas del piloto-1 no se recomputan por este ADR.
- El LABELER_VERSION no se bumpea por este ADR (el cambio es sobre umbrales de validacion humana, no sobre la logica de etiquetado).

## Archivos modificados con este ADR (2026-05-10)

- `apps/classifier-service/src/classifier_service/services/event_labeler_lexical.py:19` — comment actualizado de `κ ≥ 0.6` a `κ ≥ 0.70` con referencia a paper + ADR-046 + descripcion de protocolo dual.
- `apps/web-teacher/src/views/KappaRatingView.tsx:95` — descripcion UI actualizada a `kappa >= 0.70` con referencia a Landis-Koch y paper.
- `docs/limitaciones-declaradas.md` — agregada entrada de versionado 2026-05-10 documentando el cambio.
- `paper-draft.md` (cwd padre) — markers `[DECISION PENDIENTE]` de kappa y protocolo muestral resueltos en linea con esta ADR.

## Referencias

- ADR-027 — DIFERIR la Fase B (umbral kappa actualizado por este ADR; resto de la decision intacto).
- ADR-032 — Ground truth docente (umbral kappa actualizado por este ADR).
- ADR-044 — Esqueleto Fase B `socratic_compliance` (umbral kappa de su criterio de revisita actualizado por este ADR).
- ADR-045 — Esqueleto override lexico `anotacion_creada` G8b (umbral kappa de su criterio de revisita actualizado por este ADR).
- Landis, J. R., & Koch, G. G. (1977). The measurement of observer agreement for categorical data. Biometrics, 33(1), 159-174.
- Mislevy, R. J., Steinberg, L. S., & Almond, R. G. (2003). Focus article: On the structure of educational assessments. Measurement: Interdisciplinary Research and Perspectives, 1(1), 3-62.
- AERA, APA, & NCME (2014). Standards for educational and psychological testing. American Educational Research Association.
- Paper Cortez & Garis — "Modelo N4 de trazabilidad cognitiva para la ensenanza universitaria de programacion con asistentes de IA generativa" (UTN-FRM + UNSL).
- `ppconarev.md` (2026-05-10) — auditoria comparativa paper ↔ codigo que motiva este ADR.
- `plan-accion.md` A2 — validacion intercoder pendiente, ahora calibrada al protocolo dual.
- `docs/limitaciones-declaradas.md` — entrada 2026-05-10 sobre el cambio de umbral.
