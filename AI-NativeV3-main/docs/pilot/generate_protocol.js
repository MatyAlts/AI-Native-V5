/**
 * Genera el Protocolo del Piloto UNSL como documento Word.
 * Destinado al capítulo empírico de la tesis de Alberto Cortez.
 */
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, LevelFormat, PageNumber, PageBreak,
  HeadingLevel, BorderStyle, WidthType, ShadingType, TabStopType, TabStopPosition,
} = require("docx");

// ── Styles ────────────────────────────────────────────────────────────

const styles = {
  default: {
    document: { run: { font: "Arial", size: 22 } }, // 11pt
  },
  paragraphStyles: [
    {
      id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
      run: { size: 32, bold: true, font: "Arial", color: "1F3864" },
      paragraph: { spacing: { before: 360, after: 180 }, outlineLevel: 0 },
    },
    {
      id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
      run: { size: 26, bold: true, font: "Arial", color: "2E75B6" },
      paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 1 },
    },
    {
      id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
      run: { size: 22, bold: true, font: "Arial", color: "404040" },
      paragraph: { spacing: { before: 180, after: 80 }, outlineLevel: 2 },
    },
  ],
};

// ── Helpers ────────────────────────────────────────────────────────────

const P = (text, opts = {}) => new Paragraph({
  children: Array.isArray(text) ? text : [new TextRun(text)],
  spacing: { after: 120, ...opts.spacing },
  alignment: opts.alignment,
  ...opts.pOpts,
});

const H1 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_1,
  children: [new TextRun(text)],
  pageBreakBefore: false,
});
const H2 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_2,
  children: [new TextRun(text)],
});
const H3 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_3,
  children: [new TextRun(text)],
});

const Bold = (t) => new TextRun({ text: t, bold: true });
const Italic = (t) => new TextRun({ text: t, italics: true });
const Mono = (t) => new TextRun({ text: t, font: "Consolas", size: 20 });

const Bullet = (text) => new Paragraph({
  numbering: { reference: "bullets", level: 0 },
  children: Array.isArray(text) ? text : [new TextRun(text)],
  spacing: { after: 80 },
});

const Numbered = (text) => new Paragraph({
  numbering: { reference: "numbers", level: 0 },
  children: Array.isArray(text) ? text : [new TextRun(text)],
  spacing: { after: 80 },
});

const PageBreakP = () => new Paragraph({ children: [new PageBreak()] });

// Tabla helper
const border = { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF" };
const cellBorders = { top: border, bottom: border, left: border, right: border };

const makeTable = (rows, columnWidths) => {
  const totalWidth = columnWidths.reduce((a, b) => a + b, 0);
  return new Table({
    width: { size: totalWidth, type: WidthType.DXA },
    columnWidths,
    rows: rows.map((row, rowIdx) => new TableRow({
      children: row.map((cell, colIdx) => new TableCell({
        borders: cellBorders,
        width: { size: columnWidths[colIdx], type: WidthType.DXA },
        shading: rowIdx === 0
          ? { fill: "2E75B6", type: ShadingType.CLEAR }
          : undefined,
        margins: { top: 100, bottom: 100, left: 140, right: 140 },
        children: [new Paragraph({
          children: Array.isArray(cell)
            ? cell
            : [new TextRun({
                text: cell,
                bold: rowIdx === 0,
                color: rowIdx === 0 ? "FFFFFF" : "000000",
                size: rowIdx === 0 ? 20 : 20,
              })],
          spacing: { after: 0 },
        })],
      })),
    })),
  });
};

// ── Contenido ─────────────────────────────────────────────────────────

const cover = [
  new Paragraph({
    children: [
      new TextRun({ text: "Universidad Nacional de San Luis", size: 24, bold: true }),
    ],
    alignment: AlignmentType.CENTER,
    spacing: { before: 2400, after: 120 },
  }),
  new Paragraph({
    children: [new TextRun({ text: "Doctorado en Ciencias de la Computación", size: 22 })],
    alignment: AlignmentType.CENTER,
    spacing: { after: 1600 },
  }),

  new Paragraph({
    children: [
      new TextRun({
        text: "Protocolo del Estudio Piloto",
        size: 48,
        bold: true,
        color: "1F3864",
      }),
    ],
    alignment: AlignmentType.CENTER,
    spacing: { after: 240 },
  }),
  new Paragraph({
    children: [
      new TextRun({
        text: "Modelo AI-Native con Trazabilidad Cognitiva N4",
        size: 32,
        italics: true,
        color: "2E75B6",
      }),
    ],
    alignment: AlignmentType.CENTER,
    spacing: { after: 120 },
  }),
  new Paragraph({
    children: [
      new TextRun({
        text: "para la Formación en Programación Universitaria",
        size: 28,
        italics: true,
        color: "2E75B6",
      }),
    ],
    alignment: AlignmentType.CENTER,
    spacing: { after: 2400 },
  }),

  new Paragraph({
    children: [
      new TextRun({ text: "Doctorando: ", bold: true, size: 22 }),
      new TextRun({ text: "Alberto Alejandro Cortez", size: 22 }),
    ],
    alignment: AlignmentType.CENTER,
    spacing: { after: 120 },
  }),
  new Paragraph({
    children: [
      new TextRun({ text: "Director: ", bold: true, size: 22 }),
      new TextRun({ text: "[A definir]", size: 22 }),
    ],
    alignment: AlignmentType.CENTER,
    spacing: { after: 120 },
  }),
  new Paragraph({
    children: [
      new TextRun({ text: "Facultad de Ciencias Físico-Matemáticas y Naturales", size: 22 }),
    ],
    alignment: AlignmentType.CENTER,
    spacing: { after: 1800 },
  }),

  new Paragraph({
    children: [new TextRun({ text: "Versión 1.0 — Abril 2026", size: 20, italics: true })],
    alignment: AlignmentType.CENTER,
  }),

  PageBreakP(),
];

// ── Sección 1: Resumen ejecutivo ─────────────────────────────────────

const section1 = [
  H1("1. Resumen ejecutivo"),
  P("Este documento describe el protocolo del estudio piloto cuasi-experimental que validará empíricamente el Modelo AI-Native con Trazabilidad Cognitiva N4 propuesto en la tesis doctoral. El piloto se ejecutará durante el primer cuatrimestre de 2026 en tres cátedras de la Facultad de Ciencias Físico-Matemáticas y Naturales de la Universidad Nacional de San Luis."),
  P([
    Bold("Objetivo principal: "),
    new TextRun("verificar la hipótesis central H1 — los estudiantes que utilizan la plataforma AI-Native durante un cuatrimestre muestran una progresión observable desde apropiación pasiva o superficial hacia apropiación reflexiva del conocimiento, medida mediante la clasificación automática N4."),
  ]),
  P([
    Bold("Población de estudio: "),
    new TextRun("estudiantes de Programación 1 (aprox. 80 matriculados), Programación 2 (aprox. 60) y Tecnicatura Superior Universitaria en Programación con IA (TSU-IA, aprox. 40). Total estimado: 180 estudiantes."),
  ]),
  P([
    Bold("Duración: "),
    new TextRun("16 semanas (un cuatrimestre académico completo), de marzo a julio de 2026."),
  ]),
  P([
    Bold("Instrumento principal: "),
    new TextRun("plataforma AI-Native desplegada específicamente para UNSL, con registro auditable de cada interacción estudiante-IA mediante el Cuaderno de Trabajo Reflexivo criptográfico."),
  ]),
];

// ── Sección 2: Objetivos e hipótesis ─────────────────────────────────

const section2 = [
  PageBreakP(),
  H1("2. Objetivos e hipótesis operativas"),
  H2("2.1. Objetivo general"),
  P("Evaluar la factibilidad, usabilidad y validez del Modelo AI-Native con Trazabilidad Cognitiva N4 como dispositivo pedagógico en contextos reales de enseñanza universitaria de programación."),

  H2("2.2. Objetivos específicos"),
  Numbered([new TextRun({ text: "OE1: ", bold: true }), new TextRun("Validar que el clasificador automático N4 reproduce el juicio experto con acuerdo sustancial (κ ≥ 0,6 en Kappa de Cohen) sobre un subconjunto etiquetado por docentes.")]),
  Numbered([new TextRun({ text: "OE2: ", bold: true }), new TextRun("Medir la progresión longitudinal de la apropiación cognitiva a lo largo del cuatrimestre, verificando si la razón neta de progresión (net progression ratio) supera el umbral de 0,3 en cohortes que completan el piloto.")]),
  Numbered([new TextRun({ text: "OE3: ", bold: true }), new TextRun("Caracterizar los patrones de interacción con la IA según las cinco coherencias (CT, CCD_mean, CCD_orphan, CII_stability, CII_evolution) y determinar cuáles predicen mejor el desempeño en las evaluaciones formales de la cátedra.")]),
  Numbered([new TextRun({ text: "OE4: ", bold: true }), new TextRun("Identificar obstáculos de adopción institucional (integración con SSO, LDAP, requisitos de infraestructura) mediante la observación del proceso de onboarding de UNSL como primer tenant del piloto.")]),
  Numbered([new TextRun({ text: "OE5: ", bold: true }), new TextRun("Recoger retroalimentación cualitativa de estudiantes y docentes sobre la experiencia de uso, mediante entrevistas semiestructuradas al final del cuatrimestre.")]),

  H2("2.3. Hipótesis de trabajo"),
  P([Bold("H1 (principal): "), new TextRun("La utilización sostenida de la plataforma AI-Native durante un cuatrimestre induce una progresión significativa desde apropiación superficial o pasiva hacia apropiación reflexiva, medible mediante el clasificador N4.")]),
  P([Bold("H2: "), new TextRun("El clasificador automático basado en árbol de decisión explícito y las cinco coherencias computadas sobre el CTR alcanza un acuerdo sustancial con el juicio experto humano (κ ≥ 0,6).")]),
  P([Bold("H3: "), new TextRun("Los estudiantes con mayor estabilidad (CII_stability) y evolución (CII_evolution) a lo largo de sus episodios muestran mejores resultados académicos en las evaluaciones regulares de la cátedra.")]),
];

// ── Sección 3: Diseño metodológico ───────────────────────────────────

const section3 = [
  PageBreakP(),
  H1("3. Diseño metodológico"),
  P("El estudio adopta un diseño cuasi-experimental longitudinal de un solo grupo con medidas repetidas, enmarcado en la metodología Design-Based Research (Wang & Hannafin, 2005). La ausencia de grupo control se justifica por razones éticas (privar a parte de la cohorte del acceso a una herramienta potencialmente beneficiosa) y por el carácter exploratorio de esta primera validación."),

  H2("3.1. Variables"),
  H3("3.1.1. Variables dependientes (resultados)"),
  Bullet([Bold("Clasificación N4 "), new TextRun("categórica con tres niveles: delegación pasiva, apropiación superficial, apropiación reflexiva.")]),
  Bullet([Bold("Razón neta de progresión "), new TextRun("(net progression ratio): (mejorando − empeorando) / estudiantes_con_datos_suficientes. Rango [−1, +1].")]),
  Bullet([Bold("Coeficiente Kappa de Cohen "), new TextRun("entre el clasificador automático y el etiquetado de docentes sobre un subconjunto validatorio.")]),
  Bullet([Bold("Rendimiento académico "), new TextRun("(nota final de la cátedra, tasa de aprobación).")]),

  H3("3.1.2. Variables independientes"),
  Bullet([Bold("Cátedra "), new TextRun("(P1, P2, TSU-IA) como factor contextual que permitirá análisis comparativos secundarios.")]),
  Bullet([Bold("Fase del cuatrimestre "), new TextRun("(primer tercio / medio / último tercio) para la medición de progresión.")]),

  H3("3.1.3. Variables de control"),
  Bullet("Edad y año de carrera."),
  Bullet("Experiencia previa autorreportada con herramientas de IA generativa."),
  Bullet("Horas totales de uso de la plataforma (registradas automáticamente)."),

  H2("3.2. Instrumentos"),
  H3("3.2.1. Instrumento principal — Plataforma AI-Native"),
  P("La plataforma registra cada interacción del estudiante con el tutor de IA en un Cuaderno de Trabajo Reflexivo (CTR) criptográfico append-only. Sobre esta traza, un clasificador determinista con árbol de decisión explícito asigna una de las tres categorías N4 a cada episodio, computando cinco coherencias intermedias que explican la decisión."),
  P([
    Bold("Propiedades críticas verificadas: "),
    new TextRun("reproducibilidad bit a bit del clasificador (mismo input + misma config → misma salida), trazabilidad completa mediante hash de cadena (cualquier manipulación del CTR rompe la cadena), y preservación de las coherencias individuales (no se colapsan en un único score)."),
  ]),

  H3("3.2.2. Etiquetado humano para Kappa"),
  P("Subconjunto de 60 episodios (20 por cátedra) etiquetados independientemente por dos docentes experimentados de la cátedra correspondiente. Las discrepancias se resuelven en reunión de consenso con el investigador principal. Este conjunto constituye el gold standard contra el que se calcula κ."),

  H3("3.2.3. Entrevistas semiestructuradas al cierre"),
  P("15 estudiantes (5 por cátedra, seleccionados por muestreo estratificado según su etiqueta N4 final) y los 3 docentes responsables. Duración estimada: 45 min por entrevista. Grabadas con consentimiento, transcritas y codificadas temáticamente."),

  H2("3.3. Procedimiento"),
  P("La intervención se estructura en cuatro fases:"),

  H3("Fase 0 — Preparación (febrero 2026, 4 semanas)"),
  Bullet("Onboarding de UNSL como tenant de la plataforma (script unsl_onboarding.py)."),
  Bullet("Federación del LDAP institucional contra Keycloak."),
  Bullet("Configuración del feature flag enable_code_execution=true para UNSL."),
  Bullet("Capacitación de los 3 docentes (2 sesiones de 90 min)."),
  Bullet("Reclutamiento y firma del consentimiento informado con los estudiantes."),

  H3("Fase 1 — Línea base (semana 1)"),
  Bullet("Cada estudiante ejecuta un episodio inicial con el tutor sobre un problema de diagnóstico común a las tres cátedras (palíndromos, diseñado como problema-caso ilustrativo en la tesis)."),
  Bullet("La clasificación N4 de este episodio funciona como medida pretest."),

  H3("Fase 2 — Intervención (semanas 2 a 15)"),
  Bullet("Uso habitual de la plataforma como complemento de las clases regulares."),
  Bullet("Mínimo solicitado: 8 episodios por estudiante a lo largo del cuatrimestre (aprox. uno cada dos semanas)."),
  Bullet("Las clases y las evaluaciones regulares de la cátedra continúan con normalidad — la plataforma es un andamiaje adicional, no reemplaza la instrucción docente."),

  H3("Fase 3 — Cierre y análisis (semana 16 y posterior)"),
  Bullet("Episodio post-test equivalente al de la línea base (problema del mismo nivel de dificultad pero temática distinta para evitar efecto de familiaridad)."),
  Bullet("Exportación del dataset académico anonymizado mediante el endpoint POST /cohort/export."),
  Bullet("Análisis longitudinal con endpoint GET /cohort/{id}/progression."),
  Bullet("Etiquetado humano del subconjunto validatorio y cálculo de κ con POST /analytics/kappa."),
  Bullet("Entrevistas semiestructuradas."),
];

// ── Sección 4: Métricas y análisis ───────────────────────────────────

const section4 = [
  PageBreakP(),
  H1("4. Métricas primarias y secundarias"),
  P("Las métricas se agrupan según su rol en la verificación de hipótesis:"),

  H2("4.1. Métricas primarias"),
  makeTable([
    ["Métrica", "Hipótesis", "Umbral de éxito", "Obtenida mediante"],
    ["Cohen's κ (modelo vs humano)", "H2", "κ ≥ 0,6 (sustancial)", "POST /analytics/kappa sobre 60 episodios validatorios"],
    ["Net progression ratio", "H1", "≥ 0,3 en al menos 2 de 3 cátedras", "GET /cohort/{id}/progression"],
    ["% de estudiantes que alcanzan apropiacion_reflexiva en algún episodio", "H1", "≥ 40 %", "Agregación de max_appropriation_reached"],
  ], [2800, 1500, 2500, 2560]),

  H2("4.2. Métricas secundarias"),
  makeTable([
    ["Métrica", "Propósito", "Fuente"],
    ["Cantidad de episodios por estudiante", "Descartar sesgo de baja exposición", "Conteo en CTR"],
    ["Promedio de código ejecutado por episodio", "Caracterizar estilo de interacción", "Eventos codigo_ejecutado"],
    ["Correlación (CII_stability, nota final)", "H3", "Exportación académica + datos de la cátedra"],
    ["Tiempo de adopción (días hasta el primer episodio)", "OE4", "Logs de api-gateway"],
    ["Integridad del CTR (violaciones de cadena)", "Control interno", "Métrica ctr_episodes_integrity_compromised_total"],
  ], [2700, 2700, 3960]),

  H2("4.3. Criterios de ajuste (stopping rules)"),
  P("Para resguardar la integridad del estudio y a los participantes, el piloto contempla tres criterios de detención o ajuste:"),
  Bullet([
    Bold("Interrupción técnica crítica: "),
    new TextRun("si se registra una violación de integridad del CTR (chain_hash roto) en más del 1% de los eventos durante una semana, se suspenderá temporalmente el piloto hasta identificar y remediar la causa."),
  ]),
  Bullet([
    Bold("Degradación pedagógica: "),
    new TextRun("si la razón neta de progresión de una cátedra resulta negativa (< −0,2) en el tercer mes, se convocará a una reunión extraordinaria con el docente responsable para evaluar la continuidad en esa cátedra específica."),
  ]),
  Bullet([
    Bold("Bajo acuerdo inter-rater intermedio: "),
    new TextRun("si el primer cómputo de κ (al mes 2) resulta inferior a 0,4 (acuerdo pobre), se revisará el árbol de decisión del clasificador y se documentará el ajuste mediante A/B testing de reference_profiles antes de continuar."),
  ]),
];

// ── Sección 5: Análisis estadístico ──────────────────────────────────

const section5 = [
  PageBreakP(),
  H1("5. Estrategia de análisis"),
  H2("5.1. Análisis cuantitativo"),
  P("El análisis cuantitativo se estructura en tres niveles:"),

  H3("5.1.1. Nivel episodio"),
  Bullet("Estadística descriptiva de las cinco coherencias (media, desvío, distribución)."),
  Bullet("Matriz de correlación entre coherencias."),
  Bullet("Boxplots comparativos por cátedra y por fase del cuatrimestre."),

  H3("5.1.2. Nivel estudiante"),
  Bullet("Trayectoria longitudinal del N4 de cada estudiante."),
  Bullet("Clasificación de trayectorias (mejorando / estable / empeorando / insuficiente) según el método de tercios."),
  Bullet("Análisis de componentes principales (PCA) sobre las cinco coherencias para identificar dimensiones latentes."),

  H3("5.1.3. Nivel cohorte"),
  Bullet("Razón neta de progresión por cátedra."),
  Bullet("Análisis de varianza (ANOVA) de la coherencia CII_evolution entre cátedras."),
  Bullet("Test de McNemar para comparar la distribución N4 entre línea base y cierre."),

  H2("5.2. Análisis cualitativo"),
  P("Las 18 entrevistas (15 estudiantes + 3 docentes) se transcribirán y codificarán temáticamente con el siguiente procedimiento:"),
  Numbered("Lectura completa sin codificar para familiarización."),
  Numbered("Codificación inductiva abierta identificando unidades de significado."),
  Numbered("Agrupamiento en categorías emergentes."),
  Numbered("Triangulación con los datos cuantitativos — contrastar la percepción con la trayectoria N4 observada."),
  Numbered("Redacción de casos ilustrativos para el capítulo de discusión."),

  H2("5.3. Herramientas"),
  Bullet([Bold("Endpoint del analytics-service: "), new TextRun("para cómputos reproducibles de κ y net_progression.")]),
  Bullet([Bold("Dataset exportado: "), new TextRun("análisis con Python (pandas, scipy, scikit-learn) en notebooks versionados en Git.")]),
  Bullet([Bold("Grafana UNSL Pilot Dashboard: "), new TextRun("monitoreo en vivo de las métricas a lo largo del cuatrimestre.")]),
  Bullet([Bold("Atlas.ti: "), new TextRun("para codificación cualitativa de las entrevistas.")]),
];

// ── Sección 6: Ética ──────────────────────────────────────────────────

const section6 = [
  PageBreakP(),
  H1("6. Consideraciones éticas"),
  P("El estudio se ajusta a las disposiciones de la Ley Argentina 25.326 de Protección de Datos Personales, al Reglamento General de Protección de Datos (GDPR, aplicable por comparación), y a los principios éticos para la investigación en seres humanos establecidos en la Declaración de Helsinki (2013). La investigación se someterá al Comité de Ética de la Investigación de la UNSL antes de su inicio."),

  H2("6.1. Consentimiento informado"),
  P("Todos los participantes firmarán un consentimiento informado que incluye:"),
  Bullet("Descripción clara del estudio, su duración y métodos."),
  Bullet("Explicación de qué datos se recogen, cómo se almacenan y cuánto tiempo."),
  Bullet("Derecho a retirarse en cualquier momento sin consecuencias académicas."),
  Bullet("Derecho a acceder a sus propios datos (export individual mediante platform_ops.privacy.export_student_data)."),
  Bullet("Derecho al olvido (anonimización mediante platform_ops.privacy.anonymize_student, que preserva la cadena criptográfica rotando el pseudónimo)."),
  Bullet("Contactos del investigador principal y del comité de ética para consultas o quejas."),

  H2("6.2. Minimización y protección de datos"),
  P("La plataforma implementa varias salvaguardas técnicas:"),
  Bullet([Bold("Pseudonimización de origen: "), new TextRun("los estudiantes se identifican internamente por un UUID (student_pseudonym) que no se liga a su identidad real en las tablas operativas del CTR. Solo el academic-service vincula pseudónimo ↔ identidad.")]),
  Bullet([Bold("Exportación anonymizada: "), new TextRun("el dataset para análisis externo reemplaza student_pseudonym por un hash determinista con salt. Investigadores distintos con salts distintos no pueden cross-referenciar.")]),
  Bullet([Bold("Exclusión del texto de prompts por defecto: "), new TextRun("el export académico NO incluye el texto literal de los prompts enviados por el estudiante salvo que se active include_prompts=true (decisión explícita registrada en el log).")]),
  Bullet([Bold("RLS multi-tenant: "), new TextRun("ningún tenant puede ver datos de otro tenant, ni siquiera accidentalmente.")]),
  Bullet([Bold("Auditoría de accesos: "), new TextRun("AuditEngine detecta y reporta intentos de acceso cross-tenant (severidad CRITICAL), logins fallidos repetidos y tokens anómalos.")]),

  H2("6.3. Uso secundario y difusión"),
  Bullet("Los datos recogidos se utilizarán exclusivamente para los fines del estudio y de la tesis doctoral."),
  Bullet("Las publicaciones derivadas (artículos, presentaciones) reportarán resultados agregados o casos ilustrativos completamente anonimizados."),
  Bullet("El dataset anonymizado podrá compartirse con otros investigadores bajo acuerdo formal y publicación del salt_hash para reproducibilidad — nunca el salt en claro."),

  H2("6.4. Gestión del riesgo"),
  P("Se identifican los siguientes riesgos y sus mitigaciones:"),
  makeTable([
    ["Riesgo", "Probabilidad", "Mitigación"],
    ["Fuga de datos personales", "Baja", "RLS + cifrado en tránsito y reposo + auditoría automática"],
    ["Dependencia tecnológica del estudiante", "Media", "Las clases tradicionales no se reemplazan; la plataforma complementa"],
    ["Sesgo del clasificador", "Media", "Validación κ inter-rater + A/B de profiles permite ajustes"],
    ["Abandono del piloto por sobrecarga", "Baja", "Mínimo solicitado: 8 episodios (no semanal obligatorio)"],
    ["Afectación del rendimiento académico", "Baja", "No se modifican los criterios de evaluación de la cátedra"],
  ], [2700, 1500, 5160]),
];

// ── Sección 7: Cronograma ────────────────────────────────────────────

const section7 = [
  PageBreakP(),
  H1("7. Cronograma"),
  P("El piloto se extiende a lo largo de 20 semanas desde la preparación hasta el reporte final:"),
  makeTable([
    ["Semana", "Fase", "Actividad principal", "Producto"],
    ["−4 a −1", "Preparación", "Onboarding UNSL + LDAP + capacitación docente", "Tenant configurado; 3 docentes capacitados"],
    ["1", "Línea base", "Episodio de diagnóstico (palíndromos)", "Clasificación N4 inicial"],
    ["2–15", "Intervención", "Uso habitual; mínimo 8 episodios/estudiante", "~1.440 episodios esperados"],
    ["8", "Check intermedio", "Primer cómputo de κ sobre 30 episodios", "Informe de validez intermedio"],
    ["16", "Cierre", "Episodio post-test + exportación + κ final", "Dataset anonymizado + reporte"],
    ["17–20", "Entrevistas y análisis", "Entrevistas semiestructuradas + análisis", "Capítulo empírico en borrador"],
  ], [1100, 1500, 3960, 2800]),
];

// ── Sección 8: Productos esperados ───────────────────────────────────

const section8 = [
  PageBreakP(),
  H1("8. Productos esperados"),
  H2("8.1. Productos académicos primarios"),
  Numbered("Capítulo empírico de la tesis doctoral (aproximadamente 60 páginas, incluyendo figuras y tablas)."),
  Numbered("Dataset académico anonymizado depositado en repositorio institucional con su salt_hash para reproducibilidad."),
  Numbered("Paper para congreso internacional (target: ICALT 2026 o SITE 2026) reportando la validación del clasificador N4."),
  Numbered("Ponencia en WICC 2026 reportando resultados preliminares del piloto."),

  H2("8.2. Productos para UNSL"),
  Numbered("Informe interno con recomendaciones para la adopción institucional de la plataforma."),
  Numbered("Documentación de instalación y operación (ya incluida en el repositorio como docs/onboarding.md)."),
  Numbered("Capacitación de docentes (2 sesiones grabadas disponibles para futuras cohortes)."),

  H2("8.3. Productos secundarios"),
  Numbered("Refinamiento del árbol de decisión N4 basado en el A/B testing de reference_profiles."),
  Numbered("Guía de buenas prácticas para el docente en el uso del tutor socrático con estudiantes."),
  Numbered("Catálogo de casos ilustrativos (un episodio representativo de cada categoría N4, con análisis)."),
];

// ── Anexos ───────────────────────────────────────────────────────────

const annexes = [
  PageBreakP(),
  H1("Anexo A — Modelo de consentimiento informado"),
  P([Italic("El siguiente texto se entregará a cada participante antes del inicio del piloto. La firma es requisito para el uso de la plataforma en el contexto del estudio.")]),
  P(""),
  P([Bold("TÍTULO DEL ESTUDIO: "), new TextRun("Modelo AI-Native con Trazabilidad Cognitiva N4 para la Formación en Programación Universitaria — Estudio Piloto UNSL 2026.")]),
  P([Bold("INVESTIGADOR PRINCIPAL: "), new TextRun("Alberto Alejandro Cortez · Doctorando en Ciencias de la Computación · UNSL.")]),
  P([Bold("COMITÉ DE ÉTICA: "), new TextRun("Comité de Ética de la Investigación de UNSL. Contacto: cei@unsl.edu.ar.")]),
  P(""),
  H3("¿En qué consiste el estudio?"),
  P("Se te invita a utilizar, durante el cuatrimestre, una plataforma de tutoría por inteligencia artificial específicamente diseñada para acompañar tu aprendizaje de programación. La plataforma registra tus interacciones con la IA (preguntas, código ejecutado, respuestas recibidas) y las organiza en un cuaderno digital que tu docente puede revisar. Un sistema automático clasifica cómo estás interactuando con la IA en tres niveles: delegación pasiva (pedir soluciones sin reflexionar), apropiación superficial (usar la IA para avanzar sin construir comprensión profunda) y apropiación reflexiva (usar la IA como andamio para construir tu propio conocimiento)."),

  H3("¿Qué datos se recogen?"),
  Bullet("Tu nombre, correo electrónico y legajo (para autenticación) — guardados por separado de las interacciones."),
  Bullet("El texto de los prompts que envíes al tutor y las respuestas que recibas."),
  Bullet("El código que ejecutes dentro de la plataforma y sus resultados."),
  Bullet("La clasificación N4 que el sistema asigne a cada episodio."),
  Bullet("Las anotaciones que escribas sobre tus propios episodios."),

  H3("¿Qué NO se recoge?"),
  Bullet("Datos de navegación fuera de la plataforma."),
  Bullet("Información de tus redes sociales o comunicaciones personales."),
  Bullet("Datos biométricos o de geolocalización precisa."),

  H3("¿Cómo se protegen mis datos?"),
  Bullet("La plataforma almacena tus datos en servidores de UNSL con cifrado en tránsito y reposo."),
  Bullet("Tu identidad se separa técnicamente de las interacciones: en las bases de análisis solo figura un identificador opaco (pseudónimo)."),
  Bullet("Las publicaciones académicas derivadas del estudio reportan agregados o casos ilustrativos completamente anonimizados."),
  Bullet("Si el investigador comparte el dataset con otros investigadores, se entrega con un hash adicional que impide identificarte incluso conociéndote."),

  H3("¿Cuáles son mis derechos?"),
  Bullet([Bold("Retirarte del estudio en cualquier momento "), new TextRun("sin necesidad de justificar motivos y sin consecuencias académicas. Tu calificación final no se verá afectada por tu decisión.")]),
  Bullet([Bold("Acceder a tus datos "), new TextRun("en cualquier momento. Podés solicitar al investigador una descarga completa de todos tus registros.")]),
  Bullet([Bold("Solicitar la anonimización "), new TextRun("(\"derecho al olvido\"). Tu identidad se desvincula de tus datos; los datos agregados quedan en el estudio porque su eliminación rompería la trazabilidad del CTR exigida por la arquitectura. Quedás imposibilitado de re-ligarte a esos datos.")]),
  Bullet([Bold("Presentar una queja "), new TextRun("ante el Comité de Ética de UNSL (cei@unsl.edu.ar) o ante la Agencia de Acceso a la Información Pública.")]),

  H3("¿Qué pasa si no quiero participar?"),
  P("Si decidís no firmar este consentimiento, seguís cursando la materia con normalidad utilizando los materiales y clases regulares. No se registrará información tuya en la plataforma. Esta decisión no afecta tu calificación ni tu relación con la cátedra."),

  H3("Firma"),
  P(""),
  P([new TextRun("He leído y comprendido este documento. Tuve la oportunidad de hacer preguntas y recibí respuestas satisfactorias. Otorgo mi consentimiento libre, voluntario e informado para participar en el estudio en las condiciones descritas.")]),
  P(""),
  P([new TextRun({ text: "Nombre y apellido: __________________________________________", size: 22 })]),
  P([new TextRun({ text: "DNI: _______________________    Legajo UNSL: ________________", size: 22 })]),
  P([new TextRun({ text: "Correo electrónico: __________________________________________", size: 22 })]),
  P([new TextRun({ text: "Fecha: _____/_____/2026           Firma: __________________________", size: 22 })]),
];

// ── Anexo B: Glosario ────────────────────────────────────────────────

const annexB = [
  PageBreakP(),
  H1("Anexo B — Glosario técnico"),
  P("Términos relevantes para la lectura crítica del protocolo:"),

  makeTable([
    ["Término", "Definición"],
    ["N4", "Modelo de cuatro niveles de granularidad del pensamiento computacional, utilizado como marco teórico del clasificador. Ver capítulo de marco teórico de la tesis."],
    ["CTR", "Cuaderno de Trabajo Reflexivo. Registro append-only de la interacción estudiante-IA con cadena criptográfica (cada evento contiene un chain_hash que encadena al anterior)."],
    ["Episodio", "Sesión completa de trabajo con el tutor sobre un problema específico, desde episodio_abierto hasta episodio_cerrado."],
    ["Coherencia temporal (CT)", "Métrica de continuidad del trabajo. Mide la fracción de ventanas de actividad contiguas respecto del total."],
    ["Coherencia código-discurso (CCD)", "Alineación entre el código que el estudiante ejecuta y las consultas textuales que formula al tutor."],
    ["CCD orphan ratio", "Fracción de código ejecutado sin discusión previa o de prompts sin código asociado. Proxies de delegación pasiva."],
    ["Coherencia inter-iteración (CII)", "Dos componentes: CII_stability (persistencia del enfoque entre interacciones sucesivas) y CII_evolution (calidad relativa de cada iteración respecto de la anterior)."],
    ["Cohen's κ", "Coeficiente de acuerdo inter-observador que corrige por el acuerdo esperado por azar. Rango [−1, +1]. Interpretación de Landis & Koch: ≥ 0,6 sustancial, ≥ 0,8 casi perfecto."],
    ["Net progression ratio", "(nº estudiantes mejorando − nº estudiantes empeorando) / nº con datos suficientes. Indicador agregado de progresión de una cohorte."],
    ["reference_profile", "Conjunto de umbrales del árbol de decisión N4. Versionado en Git con hash determinista; permite A/B testing."],
    ["Tenant", "Organización cliente de la plataforma (en este piloto, UNSL). Aislada mediante Row-Level Security de Postgres."],
    ["RLS", "Row-Level Security. Mecanismo de Postgres que filtra filas automáticamente por un valor de sesión (app.current_tenant)."],
    ["Salt de investigación", "Cadena secreta de ≥16 caracteres utilizada para pseudonimizar determinísticamente los student_pseudonym en el dataset exportado."],
  ], [2000, 7360]),
];

// ── Header y footer ──────────────────────────────────────────────────

const headerP = new Header({
  children: [new Paragraph({
    children: [
      new TextRun({
        text: "Protocolo del Piloto UNSL — Modelo AI-Native N4",
        size: 18, italics: true, color: "808080",
      }),
    ],
    alignment: AlignmentType.RIGHT,
  })],
});

const footerP = new Footer({
  children: [new Paragraph({
    children: [
      new TextRun({ text: "Alberto A. Cortez — Tesis Doctoral UNSL       Página ", size: 18, color: "808080" }),
      new TextRun({ children: [PageNumber.CURRENT], size: 18, color: "808080" }),
      new TextRun({ text: " de ", size: 18, color: "808080" }),
      new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 18, color: "808080" }),
    ],
    alignment: AlignmentType.CENTER,
  })],
});

// ── Armado del documento ──────────────────────────────────────────────

const allChildren = [
  ...cover,
  ...section1,
  ...section2,
  ...section3,
  ...section4,
  ...section5,
  ...section6,
  ...section7,
  ...section8,
  ...annexes,
  ...annexB,
];

const doc = new Document({
  creator: "Alberto Alejandro Cortez",
  title: "Protocolo del Piloto UNSL — Modelo AI-Native N4",
  description: "Protocolo del estudio piloto para la tesis doctoral",
  styles,
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [
          {
            level: 0, format: LevelFormat.BULLET, text: "•",
            alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } },
          },
        ],
      },
      {
        reference: "numbers",
        levels: [
          {
            level: 0, format: LevelFormat.DECIMAL, text: "%1.",
            alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } },
          },
        ],
      },
    ],
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
      },
    },
    headers: { default: headerP },
    footers: { default: footerP },
    children: allChildren,
  }],
});

Packer.toBuffer(doc).then((buffer) => {
  const outPath = "protocolo-piloto-unsl.docx";
  fs.writeFileSync(outPath, buffer);
  console.log(`Generado: ${outPath} (${buffer.length} bytes)`);
});
