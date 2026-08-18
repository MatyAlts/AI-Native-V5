// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
import type { TourFlow } from "@platform/ui"

/**
 * Capa 2 del onboarding del docente: un tutorial por vista.
 *
 * La capa 1 (`docenteTour`) es el panoramico: pasa por arriba de las secciones para
 * que el docente sepa que existe cada una. Estos flows son lo otro: se disparan la
 * primera vez que entra a UNA vista y explican como se trabaja ahi adentro.
 *
 * Mismo motor que el panoramico (`TourFlow` + `maybeStart`), con un `id` propio por
 * vista para que cada uno se recuerde por separado. Ninguno declara `route`: se
 * disparan desde la vista que ya esta montada, navegar seria redundante.
 *
 * Bumpear el `id` re-dispara ese tutorial para todos los docentes. Hacerlo solo
 * cuando el recorrido cambie de verdad, no por retocar una linea de copy.
 *
 * Los textos son provisorios: los pule Alberto. Estan todos aca para que se puedan
 * leer y corregir de una sentada, sin abrir un archivo por vista.
 */

/* ========================================================================== */
/* Unidades                                                                   */
/* ========================================================================== */

export const unidadesTour: TourFlow = {
  id: "docente-unidades-v1",
  steps: [
    {
      id: "unidades-intro",
      title: "La unidad es el tema que agrupa el trabajo",
      body: (
        <>
          <p>
            Una unidad es un tema del programa de la materia: condicionales, repeticion, arreglos.
            Los trabajos practicos de la comision se cuelgan de ella.
          </p>
          <p className="text-muted">
            Es tambien lo que ve el alumno: para llegar a un trabajo elige primero la materia y
            despues la unidad. Con una sola unidad ese paso ni aparece.
          </p>
        </>
      ),
    },
    {
      id: "unidades-nueva",
      anchor: "unidades:nueva",
      placement: "bottom",
      title: "Crear una unidad",
      body: (
        <p>
          Nombre y, si sirve, una descripcion corta. Cada unidad nueva se agrega al final del orden,
          que es el mismo en el que el alumno las va a ver listadas.
        </p>
      ),
    },
    {
      id: "unidades-asignacion",
      anchor: "unidades:lista",
      placement: "top",
      title: "Que TP entra en cada unidad",
      body: (
        <>
          <p>
            Cada unidad se despliega y muestra sus TPs. El desplegable de cada fila lo mueve a otra
            unidad o lo deja sin ninguna.
          </p>
          <p className="text-muted">
            Un TP pertenece a una unidad a la vez. Reasignarlo no toca lo que los alumnos ya
            registraron: cambia donde aparece, no que registro.
          </p>
        </>
      ),
    },
    {
      id: "unidades-sin-unidad",
      anchor: "unidades:sin-unidad",
      placement: "top",
      title: "Los TPs sin unidad no quedan escondidos",
      body: (
        <>
          <p>
            Un TP sin unidad se publica igual y el alumno lo ve, agrupado bajo su propia entrada.
            Organizar por unidades es opcional; nada se bloquea por no hacerlo.
          </p>
          <p className="text-muted">
            Borrar una unidad tampoco borra sus TPs: vuelven aca, a la espera de que los reasignes o
            los dejes asi.
          </p>
        </>
      ),
    },
    {
      id: "unidades-analisis",
      title: "Para que sirve haberlas armado",
      body: (
        <p>
          Con los TPs agrupados por tema, la vista de evolucion por estudiante puede abrir el
          desglose por unidad y mostrar en cual el alumno avanza y en cual se queda. Sin unidades
          esa lectura no existe, pero el resto de la plataforma funciona igual.
        </p>
      ),
    },
  ],
}

/* ========================================================================== */
/* Banco de ejercicios                                                        */
/* ========================================================================== */

export const ejerciciosTour: TourFlow = {
  id: "docente-ejercicios-v1",
  steps: [
    {
      id: "ejercicios-intro",
      title: "El ejercicio se carga una vez y se usa muchas",
      body: (
        <>
          <p>
            El banco guarda el ejercicio como pieza independiente de cualquier cursada. El mismo
            ejercicio puede aparecer en varios trabajos practicos, en varias comisiones y en varios
            cuatrimestres.
          </p>
          <p className="text-muted">
            Eso es lo que despues permite comparar como resolvieron el mismo problema dos cohortes
            distintas.
          </p>
        </>
      ),
    },
    {
      id: "ejercicios-acciones",
      anchor: "ejercicios:acciones",
      placement: "bottom",
      title: "Tres puertas de entrada, un solo formulario",
      body: (
        <>
          <p>
            <strong className="text-ink">Crear con IA</strong> arma un borrador completo a partir de
            una consigna escrita en lenguaje natural.{" "}
            <strong className="text-ink">Crear manual</strong> abre el formulario vacio.{" "}
            <strong className="text-ink">Importar JSON</strong> toma un ejercicio armado por fuera
            de la plataforma.
          </p>
          <p className="text-muted">
            Las tres terminan en el mismo formulario. El borrador de la IA es un punto de partida,
            no un ejercicio aprobado: se revisa antes de guardarlo.
          </p>
        </>
      ),
    },
    {
      id: "ejercicios-contexto",
      title: "Lo que el ejercicio le presta al tutor",
      body: (
        <>
          <p>
            Ademas del enunciado y los casos de prueba, cada ejercicio guarda su contexto
            pedagogico: el banco de preguntas socraticas, los errores conceptuales que se esperan y
            las pistas graduadas.
          </p>
          <p className="text-muted">
            Ese contexto es con lo que el tutor responde cuando el alumno le pregunta. Un ejercicio
            sin contexto cargado no rompe nada, pero deja al tutor contestando en generico.
          </p>
        </>
      ),
    },
    {
      id: "ejercicios-filtros",
      anchor: "ejercicios:filtros",
      placement: "bottom",
      title: "El banco esta acotado a la materia",
      body: (
        <p>
          Ves los ejercicios de la materia de la comision activa, no los de todo el tenant. Los
          filtros por unidad, dificultad y origen, mas la busqueda por texto, empiezan a hacer falta
          cuando la materia ya junto decenas de ejercicios.
        </p>
      ),
    },
    {
      id: "ejercicios-lista",
      anchor: "ejercicios:lista",
      placement: "top",
      title: "Probarlo antes de ponerlo en un TP",
      body: (
        <>
          <p>
            Desde cada fila podes correr el ejercicio contra sus propios casos de prueba y ver lo
            mismo que va a ver el alumno.
          </p>
          <p className="text-muted">
            Editar un ejercicio que ya esta en uso no crea una copia: los cambios alcanzan a todos
            los TPs que lo referencian y al contexto de las entregas ya trabajadas.
          </p>
        </>
      ),
    },
  ],
}

/* ========================================================================== */
/* Trabajos practicos                                                         */
/* ========================================================================== */

export const tareasPracticasTour: TourFlow = {
  id: "docente-tareas-practicas-v1",
  steps: [
    {
      id: "tp-intro",
      title: "El TP es el ejercicio puesto en fecha y comision",
      body: (
        <>
          <p>
            El banco es reusable; el trabajo practico es la instancia concreta de esta comision, con
            sus fechas, su peso y su rubrica.
          </p>
          <p className="text-muted">
            Los episodios de los alumnos apuntan a la instancia, nunca a la plantilla. Por eso lo
            que ya quedo registrado no cambia de sentido cuando la catedra edita el original.
          </p>
        </>
      ),
    },
    {
      id: "tp-nuevo",
      anchor: "tp:nuevo",
      placement: "bottom",
      title: "Primero se crea, despues se compone",
      body: (
        <p>
          Al crearlo definis codigo, titulo, enunciado, fechas y lenguaje. Nace en borrador: todavia
          no lo ve ningun alumno y se puede editar entero.
        </p>
      ),
    },
    {
      id: "tp-composicion",
      anchor: "tp:composicion",
      placement: "top",
      title: "Composicion: que ejercicios entran",
      body: (
        <>
          <p>
            Desde aca sumas ejercicios del banco y les das el orden en el que el alumno los va a
            resolver.
          </p>
          <p className="text-muted">
            Todos los ejercicios tienen que compartir el lenguaje del TP. La plataforma rechaza la
            mezcla al agregarlos y otra vez al publicar.
          </p>
        </>
      ),
    },
    {
      id: "tp-estados",
      anchor: "tp:filtros",
      placement: "bottom",
      title: "Borrador, publicado, archivado",
      body: (
        <>
          <p>
            Solo un TP publicado acepta episodios. Publicar es el acto que lo habilita para la
            comision.
          </p>
          <p className="text-muted">
            Desde ese momento el contenido queda inmutable: para cambiarlo se crea una version
            nueva, y la anterior queda en el historial junto con todo lo que registro.
          </p>
        </>
      ),
    },
    {
      id: "tp-card",
      anchor: "tp:lista",
      placement: "top",
      title: "Lo que cuenta cada card",
      body: (
        <p>
          Estado, fechas, peso e historial de versiones. Si el TP se instancio desde una plantilla
          de catedra y despues se edito aca, la card lo avisa: esa instancia dejo de seguir al
          original.
        </p>
      ),
    },
  ],
}

/* ========================================================================== */
/* Correcciones                                                               */
/* ========================================================================== */

export const correccionesTour: TourFlow = {
  id: "docente-correcciones-v1",
  steps: [
    {
      id: "correcciones-intro",
      title: "Corregis mirando el proceso, no el archivo final",
      body: (
        <>
          <p>
            Cada entrega trae el codigo que escribio el alumno y la linea de tiempo de como llego
            ahi: que le pregunto al tutor, cuando corrio los tests, que reescribio despues de cada
            respuesta.
          </p>
          <p className="text-muted">
            Dos entregas identicas pueden tener recorridos muy distintos. Eso es lo que la nota
            puede tomar en cuenta y antes no se veia.
          </p>
        </>
      ),
    },
    {
      id: "correcciones-estados",
      anchor: "correcciones:filtros",
      placement: "bottom",
      title: "Los cuatro estados de una entrega",
      body: (
        <>
          <p>
            <strong className="text-ink">Borrador</strong> es trabajo que el alumno todavia no
            envio. <strong className="text-ink">Enviada</strong> es lo que espera correccion.{" "}
            <strong className="text-ink">Calificada</strong> ya tiene nota cargada.{" "}
            <strong className="text-ink">Devuelta</strong> es la que el alumno ya puede leer con su
            devolucion.
          </p>
          <p className="text-muted">
            Calificar y devolver son dos pasos separados a proposito: podes cerrar las notas de toda
            la comision y recien despues liberarlas.
          </p>
        </>
      ),
    },
    {
      id: "correcciones-lista",
      anchor: "correcciones:lista",
      placement: "top",
      title: "Abrir una entrega",
      body: (
        <p>
          Se abre el detalle con los ejercicios del TP, el codigo de cada uno y la rubrica cargada.
          La nota sugerida sale de los puntajes por criterio, y podes pisarla con la que
          corresponda.
        </p>
      ),
    },
    {
      id: "correcciones-lote",
      anchor: "correcciones:lote",
      placement: "bottom",
      title: "Corregir en lote",
      body: (
        <p>
          Toma las entregas pendientes que quedaron en pantalla, respetando el filtro y la busqueda
          que tengas puestos, y las encadena de la mas vieja a la mas nueva sin volver a la lista.
        </p>
      ),
    },
  ],
}

/* ========================================================================== */
/* Niveles N1-N4                                                              */
/* ========================================================================== */

export const nivelesTour: TourFlow = {
  id: "docente-niveles-v1",
  steps: [
    {
      id: "niveles-intro",
      title: "Como se arma esta lectura",
      body: (
        <>
          <p>
            Cada evento del alumno se etiqueta con un nivel segun el tipo de trabajo cognitivo que
            implica: leer el enunciado, escribir por su cuenta, probar y corregir, o dialogar con el
            tutor.
          </p>
          <p className="text-muted">
            La etiqueta se calcula al leer, no se guarda dentro del evento. Por eso mejorar la regla
            de etiquetado vuelve a leer lo historico sin alterar ni un byte de lo que quedo
            registrado.
          </p>
        </>
      ),
    },
    {
      id: "niveles-distribucion",
      anchor: "niveles:distribucion",
      placement: "top",
      title: "Esto no es una nota",
      body: (
        <>
          <p>
            La distribucion dice en que paso el tiempo el alumno, no cuanto vale lo que hizo. Una
            sesion cargada de prueba y correccion es un alumno trabajando bien.
          </p>
          <p className="text-muted">
            Lo que si vale mirar es la forma del reparto: una sesion casi entera de dialogo con el
            tutor, sin escritura propia ni pruebas en el medio, es otra cosa.
          </p>
        </>
      ),
    },
    {
      id: "niveles-lectura",
      anchor: "niveles:lectura",
      placement: "bottom",
      title: "La lectura de apropiacion",
      body: (
        <>
          <p>
            Sobre la misma sesion, el sistema arriesga una lectura: si el alumno se apropio del
            problema, si paso por arriba, o si delego. Viene con la evidencia textual que la
            sostiene.
          </p>
          <p className="text-muted">
            Cuando el modelo no queda seguro lo dice y manda el episodio a revision humana, en vez
            de inventar una categoria.
          </p>
        </>
      ),
    },
    {
      id: "niveles-episodio",
      anchor: "niveles:episodio",
      placement: "bottom",
      title: "De la lectura a la evidencia",
      body: (
        <p>
          El identificador de la sesion abre el timeline evento por evento, con su cadena de
          verificacion. Es el nivel de detalle que necesitas si alguna vez tenes que justificar una
          nota.
        </p>
      ),
    },
  ],
}
