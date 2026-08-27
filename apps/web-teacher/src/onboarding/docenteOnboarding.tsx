// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
import type { OnboardingFlow } from "@platform/ui"
import type { EstadoDocente } from "./estadoDocente"

/**
 * Onboarding por estado del docente: carteles sueltos que aparecen segun lo que el
 * docente YA HIZO de verdad. No es un recorrido: no hay orden, no hay contador, y
 * cada cartel se retira solo cuando el estado real dice que el paso esta cumplido.
 *
 * Las dos condiciones de cada paso resuelven cosas distintas y no son intercambiables:
 *
 *   unlockWhen -> "esto ya aplica". Incluye el "ya sabemos lo suficiente para
 *                 hablar": mientras el dato no llego, el paso no se desbloquea y no
 *                 se muestra nada. Un cartel que parpadea porque llego el fetch es
 *                 peor que ninguno.
 *   doneWhen   -> "esto ya se cumplio", derivado del estado real. Si el docente creo
 *                 su TP por afuera de este cartel, el cartel nace cumplido.
 *
 * TODOS los carteles de este flow piden hacer algo que depende del docente, y su
 * `doneWhen` sale de que lo hizo. No hay carteles que solo expliquen una pantalla, y es
 * deliberado: los tres que llegamos a escribir para los paneles vacios de analisis
 * (progresion, cuartiles, adversos) se sacaron el 2026-08-09. Cada una de esas vistas ya
 * explica su propio vacio, y la de cuartiles ademas muestra el umbral y el conteo LEIDOS
 * de la respuesta del backend. Un cartel al lado habria puesto un numero estimado
 * pegado al numero autoritativo, que es peor que no poner nada. Antes de sumar un cartel
 * que explica un vacio: mirar si la vista ya lo explica, y si el dato lo tiene el
 * backend, decirlo desde la vista con el valor del backend.
 *
 * Los pasos son secuenciales en la practica (sin comision no hay TP, sin TP no hay
 * entregas), pero eso lo produce el estado, no un orden declarado aca. Lo que SI es
 * diseno es que el de unidades vaya antes que el del TP: se muestra uno solo a la vez y
 * gana el primero de la lista que califique.
 *
 * Ninguno declara `route`: aplican en cualquier vista. La comparacion del motor es por
 * segmento, asi que `route: "/"` NO seria un comodin — matchearia solo el home.
 *
 * Que ningun cartel se abra encima de un tour NO se resuelve aca: es arbitraje entre
 * los dos mecanismos y vive en `routes/__root.tsx`, que es quien conoce a los dos.
 *
 * Los textos son provisorios: los pule Alberto.
 */
export const docenteOnboarding: OnboardingFlow<EstadoDocente> = {
  id: "docente-v1",
  hints: [
    {
      // Sin comision no hay nada que hacer en ninguna vista, asi que este cartel no
      // se ata a una ruta: corresponde donde sea que este parado el docente.
      id: "sin-comision",
      title: "Todavia no figuras en ninguna comision",
      body: (
        <>
          <p>
            Las comisiones las asigna la administracion academica de la facultad. Hasta que quedes
            cargado como docente, JTP o auxiliar de al menos una, las vistas de trabajo van a estar
            vacias.
          </p>
          <p className="text-muted">
            Si ya deberias tenerla asignada, avisale a quien administra la plataforma en tu
            facultad.
          </p>
        </>
      ),
      unlockWhen: (s) => s.comisionesCargadas,
      doneWhen: (s) => s.tieneComision,
    },
    {
      // ANTES del cartel del TP, y eso es diseno: la unidad es el tema y el TP vive
      // adentro. No va antes que `sin-comision` porque los dos nunca califican a la vez
      // (este exige comision, aquel exige que no haya) y ahi el orden no diria nada.
      id: "sin-unidades",
      anchor: "nav:/unidades",
      placement: "right",
      title: "Podes agrupar los trabajos por tema",
      body: (
        <>
          <p>
            Una unidad es un tema del programa: condicionales, repeticion, arreglos. Es tambien el
            escalon que atraviesa el alumno, que llega al trabajo eligiendo primero la materia y
            despues la unidad.
          </p>
          <p className="text-muted">
            Es opcional y nada se bloquea sin ellas: un TP sin unidad se publica igual y el alumno
            lo ve. Lo que suman es la lectura por tema, para ver en cual la cohorte avanza y en cual
            se traba.
          </p>
        </>
      ),
      unlockWhen: (s) => s.comisionesCargadas && s.tieneComision && s.unidadesCargadas,
      doneWhen: (s) => s.tieneUnidad,
      // OBLIGATORIO en false, y no es una preferencia de copy. `hechos` se deriva de
      // `doneWhen`, nunca del descarte: el docente que cierra este cartel porque
      // legitimamente no usa unidades deja el paso en no-hecho para siempre, y la barra
      // de "primeros pasos N de M" no llegaria nunca a completa. Un paso opcional
      // adentro de un contador obligatorio es un progreso que no cierra.
      countsTowardProgress: false,
    },
    {
      // Anclado al sidebar y sin ruta: el docente que no tiene ningun TP puede estar
      // parado en cualquier vista, y lo que le queremos senalar es adonde ir.
      id: "sin-tp",
      anchor: "nav:/tareas-practicas",
      placement: "right",
      title: "El proximo paso es armar un trabajo practico",
      body: (
        <>
          <p>
            Mientras la comision no tenga un TP publicado, los alumnos no pueden abrir ningun
            episodio: no hay a que trabajo apuntar lo que hagan.
          </p>
          <p className="text-muted">
            El TP se crea en Trabajos Practicos y se compone con ejercicios del banco. Nace en
            borrador; recien al publicarlo queda habilitado para la comision.
          </p>
        </>
      ),
      unlockWhen: (s) => s.comisionesCargadas && s.tieneComision && s.tpsCargados,
      doneWhen: (s) => s.tieneTp,
    },
    {
      id: "primera-entrega-sin-corregir",
      anchor: "nav:/correcciones",
      placement: "right",
      title: "Llego la primera entrega y espera correccion",
      body: (
        <>
          <p>
            En Correcciones vas a ver el codigo que entrego el alumno junto con la linea de tiempo
            de como llego ahi: que pregunto, cuando corrio los tests, que reescribio despues.
          </p>
          <p className="text-muted">
            La nota se carga con la rubrica del TP. Calificar y devolver son dos pasos separados:
            podes cerrar las notas de toda la comision y liberarlas despues.
          </p>
        </>
      ),
      unlockWhen: (s) => s.entregasCargadas && s.hayEntregaPendiente,
      doneWhen: (s) => s.hayEntregaCorregida,
    },
  ],
}
