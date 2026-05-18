/**
 * Guía de capacitación para los 3 docentes participantes del piloto UNSL.
 * Material de onboarding pedagógico para las 2 sesiones pre-piloto.
 */
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, LevelFormat, PageNumber, PageBreak,
  HeadingLevel, BorderStyle, WidthType, ShadingType,
} = require("docx");

const styles = {
  default: { document: { run: { font: "Arial", size: 22 } } },
  paragraphStyles: [
    { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
      run: { size: 32, bold: true, font: "Arial", color: "1F3864" },
      paragraph: { spacing: { before: 360, after: 180 }, outlineLevel: 0 } },
    { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
      run: { size: 26, bold: true, font: "Arial", color: "2E75B6" },
      paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 1 } },
    { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
      run: { size: 22, bold: true, font: "Arial", color: "404040" },
      paragraph: { spacing: { before: 180, after: 80 }, outlineLevel: 2 } },
  ],
};

const P = (text, opts = {}) => new Paragraph({
  children: Array.isArray(text) ? text : [new TextRun(text)],
  spacing: { after: 120, ...opts.spacing },
  alignment: opts.alignment,
});

const H1 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(text)] });
const H2 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(text)] });
const H3 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(text)] });

const Bold = (t) => new TextRun({ text: t, bold: true });
const Italic = (t) => new TextRun({ text: t, italics: true });

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
        shading: rowIdx === 0 ? { fill: "2E75B6", type: ShadingType.CLEAR } : undefined,
        margins: { top: 100, bottom: 100, left: 140, right: 140 },
        children: [new Paragraph({
          children: Array.isArray(cell) ? cell : [new TextRun({
            text: cell, bold: rowIdx === 0,
            color: rowIdx === 0 ? "FFFFFF" : "000000", size: 20,
          })],
          spacing: { after: 0 },
        })],
      })),
    })),
  });
};

// Caja destacada con borde lateral
const CalloutBox = (title, content) => {
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [9360],
    rows: [
      new TableRow({
        children: [new TableCell({
          borders: {
            top: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
            bottom: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
            right: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
            left: { style: BorderStyle.SINGLE, size: 24, color: "2E75B6" },
          },
          shading: { fill: "F0F6FC", type: ShadingType.CLEAR },
          margins: { top: 160, bottom: 160, left: 200, right: 200 },
          width: { size: 9360, type: WidthType.DXA },
          children: [
            new Paragraph({
              children: [new TextRun({ text: title, bold: true, size: 22, color: "1F3864" })],
              spacing: { after: 80 },
            }),
            ...content.map((line) => new Paragraph({
              children: Array.isArray(line) ? line : [new TextRun({ text: line, size: 22 })],
              spacing: { after: 80 },
            })),
          ],
        })],
      }),
    ],
  });
};

// ── Contenido ─────────────────────────────────────────────────────────

const cover = [
  new Paragraph({
    children: [new TextRun({ text: "Plataforma AI-Native N4", size: 44, bold: true, color: "1F3864" })],
    alignment: AlignmentType.CENTER,
    spacing: { before: 2800, after: 240 },
  }),
  new Paragraph({
    children: [new TextRun({ text: "Guía de capacitación docente", size: 32, italics: true, color: "2E75B6" })],
    alignment: AlignmentType.CENTER,
    spacing: { after: 1600 },
  }),
  new Paragraph({
    children: [new TextRun({ text: "Piloto UNSL · Primer cuatrimestre 2026", size: 24 })],
    alignment: AlignmentType.CENTER,
    spacing: { after: 240 },
  }),
  new Paragraph({
    children: [new TextRun({ text: "Programación 1 · Programación 2 · TSU en IA", size: 22, italics: true })],
    alignment: AlignmentType.CENTER,
    spacing: { after: 1800 },
  }),
  new Paragraph({
    children: [new TextRun({ text: "Alberto Alejandro Cortez", size: 22 })],
    alignment: AlignmentType.CENTER,
    spacing: { after: 80 },
  }),
  new Paragraph({
    children: [new TextRun({ text: "Doctorando · UNSL", size: 20, italics: true })],
    alignment: AlignmentType.CENTER,
  }),
  PageBreakP(),
];

// ── Sección 1: Filosofía ──────────────────────────────────────────────

const section1 = [
  H1("1. Qué es esta plataforma y qué no es"),

  P("Antes de los detalles técnicos, una aclaración sobre lo que estás por enseñar a tus estudiantes durante este cuatrimestre: la plataforma NO es un reemplazo de tu docencia ni un chatbot más que les resuelve la tarea. Es un andamio reflexivo que registra auditablemente cómo cada estudiante interactúa con la IA, para que vos (y la investigación) podamos ver si esa interacción los hace pensar o los hace delegar."),

  H2("1.1. El problema pedagógico"),
  P("Los estudiantes ya usan IA generativa — Claude, ChatGPT, Copilot — para resolver sus TPs. No hay forma realista de prohibirlo. Pero hay una diferencia enorme entre:"),

  Bullet([Bold("Delegación pasiva: "), new TextRun('"ChatGPT, dame el código del ejercicio 3" → copia-pega sin entender.')]),
  Bullet([Bold("Apropiación superficial: "), new TextRun('Usa la IA para avanzar, hace cambios cosméticos, pasa la materia pero no construye base conceptual.')]),
  Bullet([Bold("Apropiación reflexiva: "), new TextRun('Usa la IA como tutor. Pregunta por qué su solución es O(n²), compara alternativas, entiende antes de pedir código.')]),

  P("Estos tres modos coexisten hoy en el aula. La plataforma los hace visibles."),

  H2("1.2. Qué ganás vos como docente"),
  Bullet("Una foto objetiva de cómo cada estudiante interactúa con la IA, basada en evidencia (no en intuición)."),
  Bullet("La capacidad de intervenir temprano — si un estudiante viene cayendo hacia delegación pasiva, su trayectoria lo muestra antes de la primera evaluación parcial."),
  Bullet("Datos empíricos para discutir la política de uso de IA de la cátedra, en lugar de discusiones abstractas."),
  Bullet("Una herramienta de investigación reproducible que podés usar en futuras tesinas de estudiantes avanzados."),

  H2("1.3. Qué NO hace la plataforma"),
  Bullet("No corrige TPs ni pone notas. Eso sigue siendo tu trabajo."),
  Bullet("No \"evalúa\" a los estudiantes en el sentido sumativo. El clasificador N4 es descriptivo, no calificatorio."),
  Bullet("No impide a los estudiantes usar IA fuera de la plataforma. La idea es que la plataforma sea lo suficientemente buena para que prefieran usarla."),
  Bullet("No reemplaza clases presenciales, consultas ni revisiones grupales."),

  CalloutBox("Mensaje clave para los estudiantes", [
    "Durante la primera clase, cuando presentes la plataforma a tu comisión, usá esta analogía:",
    [new TextRun({ text: '"Podés usar esta plataforma como una calculadora: ', italics: true }),
     new TextRun({ text: "ingresás el problema y te escupe la respuesta. ", italics: true, bold: true }),
     new TextRun({ text: 'O podés usarla como un tutor: le preguntás, te desafía, y vos pensás. ', italics: true }),
     new TextRun({ text: "Las dos opciones son válidas en lo inmediato", italics: true, bold: true }),
     new TextRun({ text: ", pero solo una te forma. Yo voy a poder ver cómo la estás usando, no para controlarte sino para ayudarte si veo que estás cayendo en la primera.\"", italics: true })],
  ]),
];

// ── Sección 2: Qué ven los estudiantes ────────────────────────────────

const section2 = [
  PageBreakP(),
  H1("2. La experiencia del estudiante"),
  P("Para entender qué vas a analizar, primero veamos qué hace un estudiante durante un episodio de trabajo."),

  H2("2.1. El flujo de un episodio"),
  Numbered([Bold("Entra al sitio "), new TextRun("student.plataforma.unsl.edu.ar y se loguea con su cuenta institucional (LDAP UNSL).")]),
  Numbered([Bold("Selecciona un problema "), new TextRun("del listado que vos cargaste en tu comisión.")]),
  Numbered([Bold("Abre un episodio "), new TextRun("— desde ese momento todo queda registrado: prompts al tutor, respuestas, código ejecutado.")]),
  Numbered([Bold("Trabaja con el tutor "), new TextRun("en un panel de chat. El tutor es un LLM con un prompt de estilo socrático — no da la respuesta directa, guía con preguntas.")]),
  Numbered([Bold("Escribe y ejecuta código "), new TextRun("en el editor integrado. Python corre 100% en el navegador (Pyodide), no consume ningún recurso del servidor.")]),
  Numbered([Bold("Puede anotar "), new TextRun('en cualquier momento un pensamiento propio. Esto se marca como "anotación reflexiva" y pesa positivamente en la clasificación.')]),
  Numbered([Bold("Cierra el episodio "), new TextRun("cuando termina.")]),

  H2("2.2. Qué se registra (y qué no)"),
  P("La plataforma NO registra:"),
  Bullet("Actividad del estudiante fuera de la plataforma."),
  Bullet("Pestañas abiertas en paralelo, ventana activa, etc."),
  Bullet("Mensajes entre estudiantes o con vos."),

  P("La plataforma SÍ registra, dentro del CTR criptográfico:"),
  Bullet("Cada prompt que envía el estudiante al tutor (texto literal)."),
  Bullet("Cada respuesta que recibe."),
  Bullet("Cada ejecución de código (el código mismo + stdout + stderr)."),
  Bullet("Cada anotación personal que escribe."),
  Bullet("Duración del episodio y tiempos entre eventos."),

  H2("2.3. Cómo usan los estudiantes el editor"),
  P("El editor es Monaco (mismo que VS Code) con sintaxis Python. Para ejecutar, presionan el botón ▶. La ejecución corre en una VM WebAssembly que se descarga la primera vez (~6 MB, cacheada después). Limitaciones: sin network, sin librerías externas (solo stdlib por default)."),

  P("Es importante entender esto: una ejecución de código es barata y segura (no toca tu infra). Un estudiante que ejecuta mucho código no molesta al sistema, pero SÍ genera datos ricos para el análisis."),
];

// ── Sección 3: Las tres vistas del docente ─────────────────────────────

const section3 = [
  PageBreakP(),
  H1("3. Las tres vistas de tu panel docente"),
  P("Entrás a teacher.plataforma.unsl.edu.ar con tu cuenta UNSL (misma credencial). Tu panel tiene 3 tabs:"),

  H2("3.1. Vista Progresión"),
  P("La tab más importante durante el cuatrimestre. Muestra cómo va cada estudiante."),

  H3("3.1.1. Lo que vas a ver"),
  Bullet([Bold("Summary cards arriba: "), new TextRun('cuántos estudiantes están "mejorando", "estables", "empeorando" o con datos "insuficientes".')]),
  Bullet([Bold("Barra de net progression ratio: "), new TextRun('un número entre -1 y +1 que resume la salud de la cohorte. Si está en verde (≥ 0.3), la cohorte como conjunto está progresando bien.')]),
  Bullet([Bold("Timeline por estudiante: "), new TextRun('cada estudiante es una fila. Los cuadraditos coloreados de izquierda a derecha son sus episodios en orden cronológico. Rojo = delegación pasiva, amarillo = superficial, verde = reflexiva.')]),

  H3("3.1.2. Cómo interpretar"),
  P("El objetivo NO es que todos los estudiantes estén en verde todo el tiempo. El objetivo es que la TRAYECTORIA mejore. Un estudiante que empieza con rojos y termina con verdes es un éxito pedagógico aunque su promedio sea amarillo."),

  CalloutBox("Patrón de alerta temprana", [
    "Si en la semana 6 ves un estudiante que ha tenido 5+ episodios y todos en rojo — hablá con él directamente. La plataforma no te da su nombre (solo el pseudónimo), pero el docente admin puede resolver el pseudónimo a identidad cuando hay razón justificada.",
    [Bold("Regla pedagógica: "), new TextRun("intervení temprano. El piloto no es para castigar delegadores pasivos; es para ayudarlos a salir de ahí.")],
  ]),

  H3("3.1.3. Qué hacer con los datos"),
  Bullet("Revisar la vista 1 vez por semana, no todos los días — el ruido de un episodio individual no dice nada."),
  Bullet("Enfocarse en trayectorias, no en episodios aislados."),
  Bullet("Si ves una trayectoria empeorando, es señal para intervención docente individual (no de castigo)."),

  H2("3.2. Vista Inter-rater"),
  P("Esta tab te permite validar el clasificador automático contra tu propio juicio. Es opcional desde el punto de vista operativo del cuatrimestre, pero es CRÍTICA para la validez empírica de la tesis."),

  H3("3.2.1. Cómo funciona"),
  Numbered("Te muestra una lista de episodios recientes, cada uno con un resumen de los prompts del estudiante + la clasificación que hizo el modelo automático."),
  Numbered("Vos elegís uno de los 3 botones por cada episodio: qué hubieras clasificado vos."),
  Numbered('Cuando terminas todos, hacés clic en "Calcular Kappa".'),
  Numbered("La plataforma te devuelve el coeficiente κ de Cohen + interpretación + matriz de confusión + acuerdo por clase."),

  H3("3.2.2. Cuándo usarla"),
  P("Cuatro momentos durante el piloto:"),
  Bullet("Semana 4: primer calibration check con 15-20 episodios."),
  Bullet("Semana 8: segunda evaluación con ~30 episodios."),
  Bullet("Semana 12: tercera evaluación con ~30 episodios."),
  Bullet("Semana 16: evaluación final con 40+ episodios (la que cuenta para la tesis)."),

  H3("3.2.3. Cómo leer los resultados"),
  makeTable([
    ["Valor de κ", "Interpretación", "Qué hacer"],
    ["≥ 0.81", "Casi perfecto", "Modelo excelente — no tocar"],
    ["0.61 – 0.80", "Sustancial", "Modelo aceptable — publicar resultados"],
    ["0.41 – 0.60", "Moderado", "Revisar clases problemáticas"],
    ["0.21 – 0.40", "Justo", "Intervención requerida — hablar con Alberto"],
    ["< 0.21", "Pobre", "Rollback o refinamiento del árbol N4"],
  ], [1800, 2800, 4760]),

  P("La matriz de confusión te muestra en qué clase el modelo y vos no coinciden. Si hay mucho tráfico entre \"superficial\" y \"reflexiva\", el árbol N4 tiene un umbral mal calibrado en esa frontera."),

  H2("3.3. Vista Exportar"),
  P("Esta tab genera un dataset anonymizado para análisis externo (tesinas, papers, etc.)."),

  H3("3.3.1. Cuándo generarlo"),
  Bullet("Semana 17 (post-cierre del cuatrimestre) — dataset final que va al paper."),
  Bullet("En cualquier momento durante el cuatrimestre si lo necesitás para una ponencia preliminar o reunión de comité."),

  H3("3.3.2. El salt de investigación"),
  P("Al exportar te va a pedir un \"salt\" de al menos 16 caracteres. Este salt es CRÍTICO:"),
  Bullet("Con el mismo salt, dos exports distintos generan los mismos pseudónimos — podés correlacionar análisis."),
  Bullet("Con salt distinto, nadie puede cross-referenciar tu dataset con otro."),

  CalloutBox("Regla de oro sobre el salt", [
    "Generá UN salt por grupo de investigación y guardalo en el password manager del grupo. Si compartís ese salt con alguien, le estás dando la capacidad de cross-referenciar futuros exports.",
    "NUNCA lo pongas en el paper. En el paper publicás el salt_hash (un hash de un hash) — eso permite a revisores verificar reproducibilidad sin permitirles re-identificar.",
  ]),

  H3("3.3.3. Include prompts — sí o no"),
  P("El checkbox \"Incluir texto de prompts\" tiene implicaciones éticas:"),
  Bullet([Bold("Si lo dejás sin marcar (default): "), new TextRun("el export NO incluye el texto de los prompts. Suficiente para análisis cuantitativo. Mínimo riesgo de re-identificación.")]),
  Bullet([Bold("Si lo marcás: "), new TextRun("el export incluye los prompts literales. Los prompts pueden contener pistas que identifiquen al estudiante (nombres propios, ejemplos de su propia experiencia). Marcalo SOLO si el comité de ética lo aprobó específicamente y si tenés un acuerdo firmado con los co-investigadores que recibirán el dataset.")]),
];

// ── Sección 4: Primera semana ─────────────────────────────────────────

const section4 = [
  PageBreakP(),
  H1("4. Qué hacer la primera semana"),

  H2("4.1. Día 1 — Presentación a la comisión"),
  P("20 minutos al final de la primera clase:"),
  Numbered("Explicá qué es la plataforma y por qué vamos a usarla (ver la analogía calculadora/tutor de la sección 1)."),
  Numbered("Aclará explícitamente: \"Esto no afecta tu calificación.\" Si no se creen eso, van a performar — no van a trabajar naturalmente."),
  Numbered("Mostrá una demo en vivo si es posible: abrí un episodio de palíndromos, escribí un prompt pésimo (\"dame el código\"), mostrá lo que el tutor responde, después escribí un prompt reflexivo (\"¿cuándo conviene usar recursión vs iteración?\") y contrastá."),
  Numbered("Hablá del consentimiento informado — pasar formularios, que los traigan firmados la próxima clase."),
  Numbered("Subrayá los derechos: retiro sin penalización, acceso a sus datos, derecho al olvido."),

  H2("4.2. Día 2 — Primer episodio"),
  P("Abrir 60 minutos de la clase para que cada estudiante ejecute el \"episodio de línea base\" — el problema de palíndromos. Es crítico que todos hagan este episodio porque es el punto de comparación al final del cuatrimestre."),

  P("Monitoreá en tu Grafana: ¿llegaron todos al paso de \"episodio cerrado\"? ¿Alguno no logueó? ¿Alguien tiene bugs?"),

  H2("4.3. Semana 1 — Seguimiento"),
  Bullet("Revisar la vista Progresión al menos 3 veces esa primera semana. Detectar problemas técnicos temprano."),
  Bullet("Reportar cualquier bug en el canal Slack/Teams del piloto — la infraestructura de respuesta está preparada."),
  Bullet("Anotar observaciones cualitativas tuyas (\"los estudiantes no entienden qué es una anotación\", \"el editor se les colgó a 3 personas\"). Esto va al capítulo de discusión."),
];

// ── Sección 5: Casos difíciles ────────────────────────────────────────

const section5 = [
  PageBreakP(),
  H1("5. Casos difíciles y cómo manejarlos"),

  H2("5.1. Un estudiante pide anonimizar sus datos"),
  P("La plataforma soporta right-to-be-forgotten (Ley 25.326 y GDPR). El procedimiento:"),
  Numbered("El estudiante te escribe formalmente (mail o persona) pidiéndolo."),
  Numbered("Vos escribís a Alberto."),
  Numbered("Alberto corre `platform_ops.anonymize_student(pseudonym, data_source)`."),
  Numbered("Efecto: el pseudónimo del estudiante en la tabla operativa se rota. Los eventos CTR no se borran (por integridad criptográfica) pero ya no son vinculables a ese estudiante."),
  Numbered("Confirmación por escrito al estudiante."),

  P("Esto preserva la validez del estudio (la cadena CTR queda intacta) y respeta el derecho del estudiante."),

  H2("5.2. El clasificador N4 está equivocado sobre un episodio"),
  P("Puede pasar. El árbol es explicable pero no perfecto. Si estás seguro de que el modelo se equivocó:"),
  Bullet("Marcalo en la vista Inter-rater en la próxima evaluación."),
  Bullet("Tu rating agregado baja el Kappa global → eso es una señal válida y deseada."),
  Bullet("Si ves un patrón (\"siempre falla con código muy corto\"), decile a Alberto — es candidato para A/B testing de refinamiento del árbol."),

  H2("5.3. Un estudiante trae \"código de ChatGPT\" y lo pega en el editor"),
  P("Esto está permitido. No es tu rol vigilarlo. Lo que el sistema va a registrar es el código ejecutado + las preguntas que el estudiante le haga al tutor DESPUÉS de pegar el código. El clasificador va a detectar:"),
  Bullet("Si el estudiante no pregunta nada → probablemente delegación pasiva."),
  Bullet("Si el estudiante pregunta \"¿por qué esto usa set comprehension?\" → empieza a mostrar apropiación superficial o reflexiva."),

  P("Es decir: la PLATAFORMA tiene una forma implícita de diferenciar copiar/pegar consciente de copiar/pegar reflexivo, y no requiere que vos vigiles."),

  H2("5.4. Dos estudiantes parecen tener trayectorias idénticas"),
  P("Posible señal de colaboración o de delegación entre pares. No es necesariamente \"trampa\" — la colaboración puede ser saludable. Pero si ves 2+ estudiantes con trayectorias idénticas en timing y contenido, mencionalo a Alberto para análisis detallado caso por caso."),

  H2("5.5. Tenés dudas sobre qué etiqueta poner en la vista Inter-rater"),
  P("La guía rápida:"),
  makeTable([
    ["Situación", "Etiqueta"],
    ["El estudiante pidió código directo sin contextualizar, lo copió y ejecutó", "delegacion_pasiva"],
    ["Pidió conceptos sueltos, los usó para avanzar sin integrarlos", "apropiacion_superficial"],
    ["Hizo preguntas conectando el problema actual con algo aprendido antes", "apropiacion_reflexiva"],
    ["Probó alternativas antes de aceptar la solución", "apropiacion_reflexiva"],
    ["Ejecutó código sin discusión ni anotación", "delegacion_pasiva o superficial"],
    ["Generó código, anotó algo propio, iteró", "apropiacion_reflexiva"],
  ], [4680, 4680]),

  P("Si estás genuinamente confundido entre 2 categorías, clasificá como la MENOS favorable — es más honesto, no te asumas lo mejor sin evidencia clara. Ese es el criterio que usamos para definir el gold standard."),
];

// ── Sección 6: Preguntas frecuentes ───────────────────────────────────

const section6 = [
  PageBreakP(),
  H1("6. Preguntas frecuentes"),

  H3("¿Puedo ver los nombres reales de los estudiantes?"),
  P("Sí, pero no desde el web-teacher directamente. El web-teacher muestra pseudónimos. Si necesitás vincular pseudónimo a nombre (por ejemplo, para hablar con un estudiante con trayectoria preocupante), pedile al docente_admin de tu comisión que haga el resolve. Esto queda auditado."),

  H3("¿Qué pasa si un estudiante NO firma el consentimiento?"),
  P("No puede usar la plataforma. Seguí dándole clase normalmente sin asignarle la plataforma como tarea. No se registra información suya. No penalices esta decisión en la calificación — el consentimiento es voluntario."),

  H3("¿Puedo asignar trabajos obligatorios en la plataforma?"),
  P("Podés SUGERIR que usen la plataforma para resolver tal o cual TP, pero no podés hacerlo OBLIGATORIO sin ofrecer una alternativa equivalente. El piloto no es excluyente — un estudiante debe poder aprobar la materia sin tocar la plataforma si así lo decide."),

  H3("¿Los estudiantes ven su clasificación N4?"),
  P("Sí. El feature flag `show_n4_to_students` está activado para UNSL por decisión pedagógica (transparencia). Los estudiantes ven en su propio dashboard cuál es su clasificación actual. No es sanción, es autoconocimiento."),

  H3("¿Cuánto LLM budget gasta cada estudiante?"),
  P("Aproximadamente 500 tokens por prompt (envío + respuesta). Un episodio típico tiene 10-15 prompts → 7500 tokens. Con 180 estudiantes haciendo 8 episodios cada uno a lo largo del cuatrimestre = ~11 millones de tokens. En Claude Sonnet esto cuesta alrededor de $30-50 USD total para todo el piloto."),

  H3("¿Qué pasa si Claude está caído?"),
  P("El tutor no responde. El estudiante puede seguir usando el editor de código (Pyodide corre localmente). Cuando Claude vuelve, el tutor funciona de nuevo. El ai-gateway tiene fallback entre Sonnet y Opus."),

  H3("¿Puedo añadir más materiales (PDFs, apuntes) a la plataforma?"),
  P("Sí, a través de la interfaz admin o pidiéndole a TI. Los materiales se chunkean automáticamente y el RAG los incluye en las respuestas del tutor. Cargalos etiquetados por comisión para que no se mezclen."),

  H3("¿Qué hago si un estudiante encuentra un bug crítico?"),
  P("Reportalo al canal de soporte del piloto con: (a) pseudónimo del estudiante, (b) timestamp aproximado, (c) descripción del bug. El equipo técnico replica y parchea. La integridad del CTR se preserva incluso si hay un bug en el frontend."),

  H3("¿Puedo usar la plataforma yo mismo como estudiante de prueba?"),
  P("Sí, y te lo RECOMIENDO. Antes de la semana 1 de clases, hacete 3-4 episodios de prueba resolviendo problemas tuyos. Te ayuda a entender qué experimentan tus estudiantes."),

  H3("¿Los datos del piloto se usan para entrenar IA?"),
  P("NO. Los datos se usan exclusivamente para la investigación de la tesis y publicaciones científicas derivadas. Los prompts que los estudiantes envían NO se usan para entrenar ningún modelo, ni de Anthropic ni de otra empresa. La plataforma usa la API de Claude con el flag de no-training."),
];

// ── Ejercicio práctico ────────────────────────────────────────────────

const section7 = [
  PageBreakP(),
  H1("7. Ejercicio práctico para la segunda sesión de capacitación"),

  P("Durante la segunda sesión (90 min, la semana previa al inicio del piloto), vamos a hacer un ejercicio completo en vivo para que llegues confiado al día 1."),

  H2("Parte A (20 min) — Vos como estudiante"),
  Numbered("Logueate al web-student con tu cuenta docente."),
  Numbered("Abrí el problema de palíndromos."),
  Numbered("Resolvelo con estilo \"delegación pasiva\": pedí código directo, copialo, ejecutalo."),
  Numbered("Cerrá el episodio."),
  Numbered("Abrí OTRO episodio del mismo problema."),
  Numbered("Ahora resolvelo con estilo \"apropiación reflexiva\": preguntá conceptos, probá alternativas, anotá observaciones."),
  Numbered("Cerrá el episodio."),

  H2("Parte B (20 min) — Análisis cuantitativo"),
  Numbered("Cambiate al web-teacher."),
  Numbered("Andá a la vista Progresión."),
  Numbered("Buscá tu propio pseudónimo — deberías ver tus dos episodios con distinta clasificación."),
  Numbered("Confirmá que las clasificaciones tienen sentido con lo que hiciste."),

  H2("Parte C (20 min) — Calibración Inter-rater"),
  Numbered("Andá a la vista Inter-rater."),
  Numbered("Vamos a pedirte que clasifiques 10 episodios sintéticos (preparados por Alberto)."),
  Numbered("Hacé clic en Calcular Kappa."),
  Numbered("Discutimos en grupo los casos donde el modelo y vos no coincidieron."),

  H2("Parte D (30 min) — Discusión pedagógica"),
  P("Preguntas para el grupo:"),
  Bullet("\"¿Cómo comunicarías esto a tu comisión el primer día?\""),
  Bullet("\"¿Qué hacés si ves a un estudiante con trayectoria empeorando?\""),
  Bullet("\"¿Cambia esto cómo enseñás? ¿Qué ajustás en el syllabus?\""),
  Bullet("\"¿Qué dudas te quedan sobre la ética o el consentimiento?\""),

  CalloutBox("Meta de la sesión 2", [
    "Al terminar, deberías sentirte cómodo enseñando con la plataforma. Si algo sigue confuso, Alberto está disponible en su mail y celular durante toda la semana antes del piloto.",
  ]),
];

// ── Contacto ──────────────────────────────────────────────────────────

const contactSection = [
  PageBreakP(),
  H1("8. Contacto durante el piloto"),
  P("Durante las 16 semanas del piloto + las 4 de análisis posterior:"),

  makeTable([
    ["Canal", "Para qué", "Tiempo de respuesta"],
    ["Slack / Teams #piloto-unsl-2026", "Dudas operativas, bugs menores, preguntas del día a día", "Mismo día"],
    ["Mail a Alberto", "Cuestiones pedagógicas o de investigación", "24-48h"],
    ["Reunión mensual (30 min)", "Revisión de progreso y ajustes", "Programada"],
    ["Emergencia técnica (Bug crítico)", "Celular de Alberto o TI UNSL", "2-4h"],
  ], [2800, 4000, 2560]),

  P(""),
  P([Italic("Esta guía es un documento vivo. Si encontrás algo confuso, incorrecto o desactualizado, escribilo — la próxima versión lo corrige.")]),
  P(""),
  P([new TextRun({ text: "Versión 1.0 — Abril 2026", size: 20, italics: true })]),
];

// ── Header y footer ──────────────────────────────────────────────────

const headerP = new Header({
  children: [new Paragraph({
    children: [new TextRun({ text: "Guía de capacitación docente — Piloto UNSL", size: 18, italics: true, color: "808080" })],
    alignment: AlignmentType.RIGHT,
  })],
});

const footerP = new Footer({
  children: [new Paragraph({
    children: [
      new TextRun({ text: "Alberto A. Cortez — Tesis Doctoral UNSL     Página ", size: 18, color: "808080" }),
      new TextRun({ children: [PageNumber.CURRENT], size: 18, color: "808080" }),
      new TextRun({ text: " de ", size: 18, color: "808080" }),
      new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 18, color: "808080" }),
    ],
    alignment: AlignmentType.CENTER,
  })],
});

// ── Armado ────────────────────────────────────────────────────────────

const allChildren = [
  ...cover,
  ...section1,
  ...section2,
  ...section3,
  ...section4,
  ...section5,
  ...section6,
  ...section7,
  ...contactSection,
];

const doc = new Document({
  creator: "Alberto Alejandro Cortez",
  title: "Guía de capacitación docente — Piloto UNSL",
  styles,
  numbering: {
    config: [
      { reference: "bullets",
        levels: [{ level: 0, format: LevelFormat.BULLET, text: "•",
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "numbers",
        levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.",
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
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
  const outPath = "guia-capacitacion-docente.docx";
  fs.writeFileSync(outPath, buffer);
  console.log(`Generado: ${outPath} (${buffer.length} bytes)`);
});
