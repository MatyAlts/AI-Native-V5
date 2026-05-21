// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
import type { ReactNode } from "react"

type HelpContentMap = Record<string, ReactNode>

export const helpContent: HelpContentMap = {
  home: (
    <div className="space-y-4 text-sidebar-text-muted">
      <p className="text-lg font-medium text-[var(--text-inverse)]">Tus comisiones</p>
      <p>
        Lista las cohortes asignadas a vos en este periodo. Una card por comision con 4 KPIs densos
        (alumnos, episodios cerrados esta semana, alertas, eventos adversos esta semana). Click en
        "Abrir cohorte" para ver progresion individual.
      </p>
      <ul className="list-disc list-inside space-y-2 ml-4">
        <li>
          <strong>alumnos:</strong> total de inscriptos en la comision (campo n_students del
          endpoint cohort progression).
        </li>
        <li>
          <strong>episodios sem.:</strong> episodios cerrados acumulados de los estudiantes con
          datos. Es un proxy conservador hasta que haya endpoint dedicado por ventana temporal.
        </li>
        <li>
          <strong>alertas:</strong> cantidad de estudiantes con al menos una alerta predictiva
          activa en la cohorte (ADR-022). Combina las 3 alertas pedagogicas: regresion vs cohorte
          (z &lt; -1σ), cuartil inferior (Q1) y slope negativo significativo (&lt; -0.3). Si la
          cohorte tiene menos de 5 estudiantes con slope longitudinal computable, la card muestra
          "—" (privacidad k-anonymity, RN-131). El hover del KPI lista el breakdown por tipo. La
          lista detallada por estudiante esta disponible desde el drill-down.
        </li>
        <li>
          <strong>adversos sem.:</strong> eventos adversos detectados en los ultimos 7 dias (filtro
          por ts del endpoint cohort adversarial-events).
        </li>
        <li>
          <strong>Abrir cohorte:</strong> navega a la vista Progresion preseleccionando esta
          comision. Desde ahi se entra al drill-down individual.
        </li>
        <li>
          <strong>Ver adversos:</strong> drill-down directo a la vista de intentos adversos.
        </li>
      </ul>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-4">
        <p className="text-accent-brand font-medium">Sin comisiones asignadas?</p>
        <p className="text-sm mt-1">
          Pedile al admin que te asigne via bulk-import (ADR-029) o que cree una comision desde
          web-admin con tu rol docente activo.
        </p>
      </div>
    </div>
  ),

  export: (
    <div className="space-y-4 text-sidebar-text-muted">
      <p className="text-lg font-medium text-[var(--text-inverse)]">Exportar Dataset Academico</p>
      <p>
        Genera un dataset anonimizado con los episodios, eventos y clasificaciones N4 de una
        cohorte. Los pseudonimos de estudiantes se hashean con tu salt de investigacion.
      </p>
      <ul className="list-disc list-inside space-y-2 ml-4">
        <li>
          <strong>Comision (UUID):</strong> El identificador de la comision cuya cohorte vas a
          exportar. Obligatorio.
        </li>
        <li>
          <strong>Salt de anonimizacion:</strong> Clave de al menos 16 caracteres para hashear los
          pseudonimos. Con el mismo salt podras correlacionar datasets futuros con este.
        </li>
        <li>
          <strong>Periodo (dias):</strong> Ventana de tiempo hacia atras desde hoy. Por defecto 90
          dias.
        </li>
        <li>
          <strong>Alias de cohorte:</strong> Nombre libre que identifica el dataset en el archivo
          descargado (ej. UTN_2026_P2).
        </li>
        <li>
          <strong>Incluir prompts:</strong> Incluye el texto de los prompts en el dataset. Activar
          solo si es necesario para el analisis: incrementa el riesgo de re-identificacion.
        </li>
        <li>
          <strong>Generar dataset:</strong> Encola el job. El panel de progreso muestra el estado en
          tiempo real; cuando llega a "Completado" aparece el boton de descarga.
        </li>
      </ul>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-4">
        <p className="text-warning font-medium">Importante:</p>
        <p className="text-sm mt-1">
          Guarda el salt en un lugar seguro. Sin el mismo salt no podras correlacionar este dataset
          con exportaciones posteriores de la misma cohorte.
        </p>
      </div>
      <div className="bg-danger/50 p-4 rounded-lg mt-2 border border-danger">
        <p className="text-[var(--danger-text)] font-medium">Advertencia:</p>
        <p className="text-sm mt-1">
          Activar "Incluir prompts" expone texto libre que puede contener informacion
          re-identificable. Usarlo solo con aprobacion del comite de etica del piloto.
        </p>
      </div>
    </div>
  ),

  kappaRating: (
    <div className="space-y-4 text-sidebar-text-muted">
      <p className="text-lg font-medium text-[var(--text-inverse)]">
        Inter-rater Agreement (Kappa)
      </p>
      <p>
        Procedimiento intercoder para calcular el coeficiente Kappa de Cohen entre el juicio humano
        del docente y las predicciones del clasificador automatico N4. Target de la tesis: kappa ≥
        0.6.
      </p>
      <ul className="list-disc list-inside space-y-2 ml-4">
        <li>
          <strong>Episodios cargados:</strong> La lista muestra los episodios asignados al batch con
          la prediccion del modelo visible a la derecha.
        </li>
        <li>
          <strong>Etiquetar:</strong> Para cada episodio, selecciona tu propia clasificacion usando
          uno de los tres botones de categoria. La seleccion queda resaltada con un anillo azul.
        </li>
        <li>
          <strong>Delegacion pasiva:</strong> El estudiante delego la resolucion al tutor sin
          apropiacion real del conocimiento.
        </li>
        <li>
          <strong>Apropiacion superficial:</strong> El estudiante mostro comprension parcial o
          aplicacion mecanica sin profundidad.
        </li>
        <li>
          <strong>Apropiacion reflexiva:</strong> El estudiante demostro comprension profunda,
          pensamiento critico y autonomia.
        </li>
        <li>
          <strong>Calcular Kappa:</strong> Se habilita cuando todos los episodios estan etiquetados.
          Muestra el valor kappa, la interpretacion, la matriz de confusion y el acuerdo por clase.
        </li>
        <li>
          <strong>Reiniciar:</strong> Borra todas las etiquetas para empezar de nuevo.
        </li>
      </ul>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-4">
        <p className="text-warning font-medium">Nota:</p>
        <p className="text-sm mt-1">
          Para el protocolo de tesis, dos docentes deben etiquetar de forma independiente el mismo
          batch de 50 episodios y luego comparar los resultados via kappa. Ver
          docs/pilot/kappa-workflow.md para el procedimiento completo.
        </p>
      </div>
    </div>
  ),

  materiales: (
    <div className="space-y-4 text-sidebar-text-muted">
      <p className="text-lg font-medium text-[var(--text-inverse)]">Materiales del Curso</p>
      <p>
        Gestión del corpus del RAG (Retrieval-Augmented Generation). Los materiales subidos son
        indexados automáticamente y el tutor socratico los usa para responder consultas de
        estudiantes.
      </p>
      <ul className="list-disc list-inside space-y-2 ml-4">
        <li>
          <strong>Subir material:</strong> Selecciona un archivo PDF, Markdown (.md), texto (.txt) o
          ZIP de codigo. Tamano maximo: 50 MB por archivo.
        </li>
        <li>
          <strong>Pipeline de indexacion:</strong> Cada archivo pasa por: Subido → Extrayendo texto
          → Particionando → Embeddings → Indexado. Los estados intermedios pulsan en la tabla.
        </li>
        <li>
          <strong>Indexado:</strong> El material esta disponible para el RAG. El numero de chunks se
          muestra en la columna "Chunks".
        </li>
        <li>
          <strong>Error:</strong> Algo fallo en el pipeline (ej. PDF corrupto, ZIP sin codigo
          valido). El mensaje de error aparece debajo del nombre del archivo.
        </li>
        <li>
          <strong>Eliminar:</strong> Soft delete. El RAG deja de usar ese material en consultas
          futuras; los episodios pasados no se modifican.
        </li>
        <li>
          <strong>Refrescar:</strong> Actualiza la lista manualmente. Los materiales en
          procesamiento se refrescan automáticamente cada 2 segundos.
        </li>
      </ul>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-4">
        <p className="text-warning font-medium">Consejo:</p>
        <p className="text-sm mt-1">
          Subir el material antes de que los estudiantes empiecen a usarlo. El tutor solo puede
          citar material ya indexado (estado "Indexado").
        </p>
      </div>
    </div>
  ),

  progression: (
    <div className="space-y-4 text-sidebar-text-muted">
      <p className="text-lg font-medium text-[var(--text-inverse)]">Progresion Longitudinal</p>
      <p>
        Analisis de la trayectoria de aprendizaje de cada estudiante a lo largo del cuatrimestre,
        basado en las clasificaciones N4 de sus episodios.
      </p>
      <ul className="list-disc list-inside space-y-2 ml-4">
        <li>
          <strong>Mejorando:</strong> El estudiante muestra una tendencia positiva hacia Apropiacion
          Reflexiva en sus ultimos episodios.
        </li>
        <li>
          <strong>Estable:</strong> La clasificacion del estudiante no muestra una tendencia clara
          de mejora ni deterioro.
        </li>
        <li>
          <strong>Empeorando:</strong> Los ultimos episodios muestran regresion hacia categorias de
          menor apropiacion.
        </li>
        <li>
          <strong>Datos insuficientes:</strong> El estudiante tiene menos de 3 episodios
          clasificados, no hay datos suficientes para calcular tendencia.
        </li>
        <li>
          <strong>Net progression ratio:</strong> Indicador global de la cohorte. Rango [-1, +1]:
          positivo significa mas estudiantes mejorando que empeorando.
        </li>
        <li>
          <strong>Trayectorias individuales:</strong> Cada barra de colores representa un episodio
          clasificado en orden cronologico. Rojo = delegacion pasiva, ambar = superficial, verde =
          reflexiva.
        </li>
      </ul>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-4">
        <p className="text-warning font-medium">Nota:</p>
        <p className="text-sm mt-1">
          Solo se muestran estudiantes con al menos 3 episodios clasificados en el campo "con datos
          suficientes". Los demas aparecen en "Insuficiente" en las tarjetas de resumen.
        </p>
      </div>
    </div>
  ),

  tareasPracticas: (
    <div className="space-y-4 text-sidebar-text-muted">
      <p className="text-lg font-medium text-[var(--text-inverse)]">Trabajos Prácticos</p>
      <p>
        Gestión de los TPs de la comision. Solo los TPs en estado "Publicado" son visibles para los
        estudiantes y aceptan episodios del tutor socratico.
      </p>
      <ul className="list-disc list-inside space-y-2 ml-4">
        <li>
          <strong>Nuevo TP:</strong> Crea un TP en estado "Borrador". Completa codigo, titulo,
          enunciado en markdown, fechas opcionales y peso.
        </li>
        <li>
          <strong>Publicar:</strong> Transicion draft → published. Una vez publicado, el TP es
          inmutable: no se puede editar el enunciado.
        </li>
        <li>
          <strong>Nueva version:</strong> Forkea un TP publicado o archivado en un nuevo borrador
          con el mismo contenido, linkeado por parent_tarea_id.
        </li>
        <li>
          <strong>Archivar:</strong> Transicion published → archived. Los estudiantes no pueden
          enviar episodios a un TP archivado.
        </li>
        <li>
          <strong>Eliminar:</strong> Soft delete. Solo disponible en estado draft.
        </li>
        <li>
          <strong>Historial:</strong> Muestra la linea de tiempo de todas las versiones del TP con
          su estado y fecha de creacion.
        </li>
        <li>
          <strong>Ver:</strong> Detalle de lectura del TP publicado o archivado, con el enunciado
          renderizado en markdown.
        </li>
        <li>
          <strong>Badge "Plantilla":</strong> El TP fue auto-generado desde una plantilla de
          cátedra. Si se edita directamente, se marca como "Drift" (perdio sincronizacion con la
          plantilla).
        </li>
        <li>
          <strong>Badge "Drift":</strong> El TP diverge de la plantilla de cátedra. Nuevas versiones
          del template ya no se propagan automáticamente a esta instancia.
        </li>
      </ul>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-4">
        <p className="text-warning font-medium">Nota:</p>
        <p className="text-sm mt-1">
          El orden correcto es: crear borrador → revisar → publicar. Una vez publicado, usar "Nueva
          version" para modificar el contenido sin invalidar los episodios ya registrados.
        </p>
      </div>
      <div className="bg-danger/50 p-4 rounded-lg mt-2 border border-danger">
        <p className="text-[var(--danger-text)] font-medium">Advertencia:</p>
        <p className="text-sm mt-1">
          Publicar un TP es irreversible en cuanto al contenido: el enunciado queda congelado.
          Archivar tambien es irreversible: los episodios en curso quedan suspendidos.
        </p>
      </div>
    </div>
  ),

  templates: (
    <div className="space-y-4 text-sidebar-text-muted">
      <p className="text-lg font-medium text-[var(--text-inverse)]">
        Plantillas de Trabajos Prácticos
      </p>
      <p>
        Las plantillas de TP se definen a nivel de cátedra (materia + periodo) y se instancian
        automáticamente en todas las comisiones de esa materia. Esto asegura que los estudiantes de
        comisiones distintas reciben el mismo material y que la cátedra edita en un solo lugar.
      </p>
      <ul className="list-disc list-inside space-y-2 ml-4">
        <li>
          <strong>Contexto academico:</strong> Selecciona universidad, facultad, carrera, plan,
          materia y periodo. Las plantillas viven a nivel (materia, periodo).
        </li>
        <li>
          <strong>Crear plantilla:</strong> Define codigo, titulo y enunciado markdown. Al guardar,
          el sistema crea automáticamente una TP (instancia) en cada comision de la materia.
        </li>
        <li>
          <strong>Ver instancias:</strong> Lista cada comision donde existe una instancia, con badge
          "Sincronizada" o "Drift" segun si el docente local edito la instancia.
        </li>
        <li>
          <strong>Publicar plantilla:</strong> Marca el template como published (luz verde de la
          cátedra). No publica automáticamente las instancias: cada comision decide.
        </li>
        <li>
          <strong>Nueva version:</strong> Crea v+1 del template en borrador. Con "Re-instanciar
          comisiones sin drift" activado, las instancias que aun siguen al template reciben la nueva
          version automáticamente.
        </li>
        <li>
          <strong>Archivar / Eliminar:</strong> Soft delete. Las instancias existentes en comisiones
          no se tocan (preservan evidencia CTR).
        </li>
      </ul>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-4">
        <p className="text-warning font-medium">Que es "Drift":</p>
        <p className="text-sm mt-1">
          Drift ocurre cuando el docente de una comision edita una instancia de TP que vino del
          template. El link al template se preserva pero la auto-actualizacion se desactiva. Esto
          permite personalizar por comision sin perder trazabilidad. Una vez drifteada, la instancia
          no recibe mas versiones automáticas del template.
        </p>
      </div>
      <div className="bg-danger/50 p-4 rounded-lg mt-2 border border-danger">
        <p className="text-[var(--danger-text)] font-medium">Advertencia:</p>
        <p className="text-sm mt-1">
          Eliminar una plantilla es soft delete: las instancias ya creadas en comisiones NO se
          borran (evidencia del CTR queda intacta). Publicar es reversible solo via archivar.
        </p>
      </div>
    </div>
  ),

  episodeNLevel: (
    <div className="space-y-4 text-sidebar-text-muted">
      <p className="text-lg font-medium text-[var(--text-inverse)]">
        Distribucion N1-N4 por episodio
      </p>
      <p>
        Drill-down del tiempo invertido por el estudiante en cada nivel analitico de un episodio
        especifico. Implementa el componente C3.2 de la tesis (Seccion 6.4) y habilita la metrica de
        "proporcion de tiempo por nivel" (Seccion 15.2). Ver ADR-020 para detalles.
      </p>
      <ul className="list-disc list-inside space-y-2 ml-4">
        <li>
          <strong>UUID del episodio:</strong> pega el episode_id que queres inspeccionar. Lo obtenes
          desde Progresion (cada estudiante tiene listados sus episodios).
        </li>
        <li>
          <strong>Barra apilada:</strong> proporcion del tiempo total del episodio en cada nivel.
          Colores: verde N1 (planificacion), azul N2 (estrategia), amarillo N3 (validacion), naranja
          N4 (interaccion IA), gris meta (apertura/cierre).
        </li>
        <li>
          <strong>Tarjetas por nivel:</strong> tiempo absoluto, porcentaje, y conteo de eventos.
        </li>
      </ul>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-4">
        <p className="text-accent-brand font-medium">Como leer la distribucion:</p>
        <p className="text-sm mt-1">
          Un episodio "saludable" suele tener tiempo en N1 (entendio el problema), N2 (escribio
          codigo), N3 (lo probo), N4 (interactuo con tutor). Un episodio dominado por N4 puede
          indicar dependencia excesiva de la IA. Un episodio sin N3 puede indicar que ejecuto sin
          verificar.
        </p>
      </div>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-2">
        <p className="text-warning font-medium">Limitacion v1.0.0:</p>
        <p className="text-sm mt-1">
          `anotacion_creada` se etiqueta como N2 fijo (override por contenido es agenda futura). Una
          `edicion_codigo` con `origin=copied_from_tutor` se reclasifica a N4 automáticamente. Ver
          ADR-020.
        </p>
      </div>
    </div>
  ),

  studentLongitudinal: (
    <div className="space-y-4 text-sidebar-text-muted">
      <p className="text-lg font-medium text-[var(--text-inverse)]">
        Evolucion longitudinal del estudiante
      </p>
      <p>
        Calcula el slope ordinal de apropiacion del estudiante a traves de problemas analogos (mismo
        TareaPracticaTemplate.id, ADR-016). Cumple la Seccion 15.4 de la tesis (CII como observacion
        longitudinal). Ver ADR-018.
      </p>
      <ul className="list-disc list-inside space-y-2 ml-4">
        <li>
          <strong>Comision:</strong> selecciona la cohorte donde queres analizar al estudiante. La
          query esta limitada por comision para acotar el scope.
        </li>
        <li>
          <strong>UUID del estudiante:</strong> pega el `student_pseudonym`. Lo obtenes desde
          Progresion.
        </li>
        <li>
          <strong>Slope:</strong> regresion lineal sobre `APPROPRIATION_ORDINAL` (delegacion=0,
          superficial=1, reflexiva=2). Slope &gt;0 = mejorando. &lt;0 = empeorando. ~0 = estable.
        </li>
        <li>
          <strong>Sparkline:</strong> trayectoria ordinal del estudiante en cada template ordenada
          por classified_at.
        </li>
      </ul>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-4">
        <p className="text-accent-brand font-medium">Cuando hay "datos insuficientes":</p>
        <p className="text-sm mt-1">
          Templates con menos de 3 episodios cerrados tienen `slope=null` con flag
          `insufficient_data`. La tesis exige longitudinalidad real: con 1-2 episodios el slope es
          trivial o indefinido. Documentado en RN-130.
        </p>
      </div>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-2">
        <p className="text-warning font-medium">Limitaciones declaradas:</p>
        <p className="text-sm mt-1">
          TPs sin `template_id` (huerfanas pre-ADR-016) NO entran al calculo. El slope cardinal
          sobre datos ordinales es operacionalizacion conservadora, defendible pero no afirmamos que
          sea verdad academica. Comparativas estudiante-a-estudiante (ranking) son OK; promediar la
          cohorte tiene sentido limitado.
        </p>
      </div>
    </div>
  ),

  cohortAdversarial: (
    <div className="space-y-4 text-sidebar-text-muted">
      <p className="text-lg font-medium text-[var(--text-inverse)]">Intentos adversos detectados</p>
      <p>
        Visibilidad pedagogica de los matches del corpus de guardrails (ADR-019, RN-129) en los
        prompts de los estudiantes de una cohorte. Cumple Seccion 8.5 de la tesis; habilita Seccion
        17.8 (efectividad de salvaguardas).
      </p>
      <ul className="list-disc list-inside space-y-2 ml-4">
        <li>
          <strong>Categorias:</strong> jailbreak indirecto/sustitucion/ficcion, persuasion por
          urgencia, prompt injection. Cada match emite un evento CTR `intento_adverso_detectado`.
        </li>
        <li>
          <strong>Severidad (1-5):</strong> ordinal, NO cardinal. Es ranking, no peso. Severidad
          &gt;=3 dispara inyeccion de un system message reforzante al LLM (Seccion 8.5.1).
        </li>
        <li>
          <strong>Top estudiantes:</strong> los 10 con mas matches. Util para intervencion
          pedagogica focalizada.
        </li>
        <li>
          <strong>Eventos recientes:</strong> ultimos 50 con texto matcheado truncado a 200 chars.
        </li>
      </ul>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-4">
        <p className="text-accent-brand font-medium">Importante: la deteccion NO bloquea.</p>
        <p className="text-sm mt-1">
          El prompt llega al LLM aunque triggeree un match. El evento es side-channel para analisis
          empirico (Seccion 17.8). Los regex son fragiles: falsos positivos y negativos son
          esperados. Ver RN-129 para limitaciones.
        </p>
      </div>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-2">
        <p className="text-warning font-medium">Limitaciones v1.1.0:</p>
        <p className="text-sm mt-1">
          Evasion intra-palabra (`olvi-da tus instrucciones`) y encadenamientos sofisticados
          (Seccion 8.5.1 tecnica 4) NO estan cubiertos por regex, requieren clasificador ML (Fase B,
          agenda piloto-2). `overuse` (Seccion 8.5.3) requiere ventana cross-prompt y queda
          diferido.
        </p>
      </div>
    </div>
  ),

  ejercicios: (
    <div className="space-y-4 text-sidebar-text-muted">
      <p className="text-lg font-medium text-[var(--text-inverse)]">Banco de Ejercicios</p>
      <p>
        Biblioteca reusable del tenant. Cada ejercicio es una entidad de primera clase con UUID
        propio y schema pedagogico completo PID-UTN. Puede aparecer en N Trabajos Practicos
        distintos sin duplicacion.
      </p>
      <ul className="list-disc list-inside space-y-2 ml-4">
        <li>
          <strong>Crear con IA:</strong> describis el ejercicio en lenguaje natural, eligis unidad
          y dificultad, y el wizard genera un borrador completo con enunciado, tests, rubrica,
          banco socratico N1-N4, misconceptions, anti-patrones y heuristica de cierre. Revisas,
          editas y guardas.
        </li>
        <li>
          <strong>Crear manual:</strong> form completo con secciones colapsables (datos basicos,
          tests, rubrica, pedagogia). Los campos pedagogicos avanzados se editan como JSON
          tipado.
        </li>
        <li>
          <strong>Filtros:</strong> por unidad tematica (secuenciales, condicionales, repetitivas,
          mixtos), dificultad (basica, intermedia, avanzada) y origen (IA o manual).
        </li>
        <li>
          <strong>Editar:</strong> el ejercicio se actualiza globalmente. Cuidado: si el ejercicio
          esta referenciado por TPs publicadas, las ediciones se propagan retroactivamente
          (deuda diferida ADR-047).
        </li>
        <li>
          <strong>Eliminar:</strong> soft delete. Los TPs que lo referencian siguen apuntando a
          esta version (el ejercicio sobrevive en DB con `deleted_at`).
        </li>
      </ul>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-4">
        <p className="text-accent-brand font-medium">Diferencia con TPs:</p>
        <p className="text-sm mt-1">
          El ejercicio es el ESTIMULO pedagogico (enunciado + tests + reglas socraticas). El TP es
          una COMPOSICION de ejercicios para una comision (orden + peso + fechas). Un mismo
          ejercicio puede aparecer en TPs de comisiones distintas — la trazabilidad cognitiva por
          ejercicio (ADR-049) lo aprovecha en el analisis longitudinal.
        </p>
      </div>
    </div>
  ),

  unidades: (
    <div className="space-y-4 text-sidebar-text-muted">
      <p className="text-lg font-medium text-[var(--text-inverse)]">Unidades de Trazabilidad</p>
      <p>
        Agrupacion tematica de TPs dentro de una comision. Las unidades permiten calcular el slope
        de apropiacion por tema (ej. "Condicionales", "Funciones") incluso cuando las TPs no
        comparten un `template_id` (TPs huerfanas de la plantilla de catedra).
      </p>
      <ul className="list-disc list-inside space-y-2 ml-4">
        <li>
          <strong>Nueva unidad:</strong> ingresa nombre (obligatorio) y descripcion opcional. El
          orden se asigna al final de la lista; se puede reordenar luego.
        </li>
        <li>
          <strong>Asignar TP a unidad:</strong> en el dropdown de cada TP dentro del acordeon
          selecciona la unidad destino. "Sin unidad" lo desvincula.
        </li>
        <li>
          <strong>Sin unidad:</strong> seccion especial que agrupa TPs que todavia no tienen unidad
          asignada. Siempre visible para recordar las TPs pendientes de clasificar.
        </li>
        <li>
          <strong>Eliminar unidad:</strong> soft delete. Los TPs asignados quedan en "Sin unidad"
          automaticamente (ON DELETE SET NULL en la DB).
        </li>
        <li>
          <strong>Evolucion por unidad:</strong> una vez que el alumno cierra episodios sobre TPs de
          la misma unidad (N&gt;=3), aparece el slope por unidad en la vista "Evolucion longitudinal
          del estudiante".
        </li>
      </ul>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-4">
        <p className="text-accent-brand font-medium">Diferencia con Templates:</p>
        <p className="text-sm mt-1">
          Los templates agrupan TPs de distintas comisiones que comparten el mismo enunciado
          academico. Las unidades agrupan TPs DENTRO de una comision por tema pedagogico. Ambos ejes
          son independientes y complementarios para el analisis longitudinal.
        </p>
      </div>
    </div>
  ),

  cohortQuartiles: (
    <div className="space-y-4 text-sidebar-text-muted">
      <p className="text-lg font-medium text-[var(--text-inverse)]">Cuartiles CII de cohorte</p>
      <p>
        Distribucion agregada del mean_slope longitudinal de los estudiantes de una comision
        (ADR-022, RN-131). El mean_slope de cada estudiante es la pendiente ordinal sobre
        APPROPRIATION_ORDINAL (delegacion=0, superficial=1, reflexiva=2) calculada por template
        analogo (ADR-018). Los cuartiles agregan esos slopes a nivel cohorte.
      </p>
      <ul className="list-disc list-inside space-y-2 ml-4">
        <li>
          <strong>Q1 (25%):</strong> el primer cuartil. 25% de los estudiantes tiene mean_slope por
          debajo de este valor. Si Q1 es negativo, el cuartil inferior esta regresionando.
        </li>
        <li>
          <strong>Mediana (Q2, 50%):</strong> el alumno tipico de la cohorte. Si la mediana es
          positiva, la mitad o mas de la clase muestra progreso longitudinal.
        </li>
        <li>
          <strong>Q3 (75%):</strong> el tercer cuartil. 75% de los estudiantes esta por debajo de
          este valor. Mide donde esta el "techo razonable" sin tomar el outlier maximo.
        </li>
        <li>
          <strong>Min / Max:</strong> los extremos de la cohorte. Util para detectar outliers
          positivos o estudiantes en riesgo severo.
        </li>
        <li>
          <strong>Mean / Stdev:</strong> media aritmetica y dispersion. La media es sensible a
          outliers; comparala con la mediana para detectar sesgo.
        </li>
      </ul>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-4">
        <p className="text-warning font-medium">Privacidad k-anonymity (N &gt;= 5):</p>
        <p className="text-sm mt-1">
          Si la cohorte tiene menos de 5 estudiantes con mean_slope computable, la vista NO muestra
          cuartiles y devuelve insufficient_data. Es el estandar k-anonymity para cohortes
          educativas: con N &lt;= 4 los cuartiles son trivialmente reconstruibles. Constante en
          packages/platform-ops/src/platform_ops/cii_alerts.py (MIN_STUDENTS_FOR_QUARTILES). Para
          destrabar: esperar mas episodios cerrados o ampliar el periodo evaluado.
        </p>
      </div>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-2">
        <p className="text-accent-brand font-medium">Limitaciones declaradas:</p>
        <p className="text-sm mt-1">
          Slope cardinal sobre datos ordinales es operacionalizacion conservadora (ADR-018, no es
          verdad academica). TPs huerfanas (sin template_id) NO entran al calculo del mean_slope
          por estudiante. Cuartiles por template/unidad agregados es agenda piloto-2.
        </p>
      </div>
    </div>
  ),

  correcciones: (
    <div className="space-y-4 text-sidebar-text-muted">
      <p className="text-lg font-medium text-[var(--text-inverse)]">Correcciones</p>
      <p>
        Lista las entregas de trabajos practicos de los estudiantes de la comision. Cada fila
        muestra el estudiante (pseudonimo), la TP, el estado actual y la fecha de entrega.
      </p>
      <ul className="list-disc list-inside space-y-2 ml-4">
        <li>
          <strong>Enviada:</strong> el estudiante entrego todos los ejercicios y espera correccion.
          Usa el boton "Corregir" para abrir el formulario de calificacion.
        </li>
        <li>
          <strong>Calificada:</strong> ya tiene nota y feedback. Podes usar "Devolver al estudiante"
          si queres que revise la entrega.
        </li>
        <li>
          <strong>Devuelta:</strong> el estudiante puede ver el feedback y la nota.
        </li>
        <li>
          <strong>Drill-down de episodios:</strong> en la vista de correccion, cada ejercicio
          completado muestra el id del episodio con un link al panel N1-N4 para ver la traza
          cognitiva del estudiante.
        </li>
      </ul>
    </div>
  ),
}
