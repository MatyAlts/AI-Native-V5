// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
import type { TourFlow } from "@platform/ui"

/**
 * Tour de primer ingreso del docente.
 *
 * El orden sigue el trabajo real, no el sidebar: se abre el tema, se arma el ejercicio,
 * se lo pone en un TP, se corrige lo que entra, y recien ahi se mira que dice el modelo.
 * El ultimo paso es el unico lugar de toda la app donde N1-N4 se explica en vez de
 * mostrarse.
 *
 * La unidad va antes que el ejercicio y que el TP porque es lo que los contiene: es el
 * tema del programa, y es el escalon que el alumno atraviesa (materia -> unidad -> TP).
 * Que sea opcional no la corre de lugar en el relato: la corre del contador de primeros
 * pasos, que es otra cosa y vive en el onboarding por estado.
 *
 * Bumpear el `id` re-dispara el tour para todos los docentes. Hacerlo solo cuando el
 * recorrido cambie de verdad, no por retocar una linea de copy.
 *
 * Sumar el paso de Unidades cambio el recorrido y AUN ASI el `id` sigue en `docente-v1`:
 * este tour todavia no llego a produccion, asi que no hay un solo navegador con
 * `ai-native:tour:docente-v1` guardado. Bumpear a `-v2` habria estrenado una version
 * cuya v1 nadie vio. El primer bump real es el dia que un docente ya lo haya completado.
 */

const NIVELES: { n: string; token: string; texto: string }[] = [
  { n: "N1", token: "var(--color-level-n1)", texto: "Lee y explora el enunciado" },
  { n: "N2", token: "var(--color-level-n2)", texto: "Escribe codigo por su cuenta" },
  { n: "N3", token: "var(--color-level-n3)", texto: "Prueba, falla y corrige" },
  { n: "N4", token: "var(--color-level-n4)", texto: "Dialoga con la IA o valida solo" },
]

export const docenteTour: TourFlow = {
  id: "docente-v1",
  steps: [
    {
      id: "bienvenida",
      title: "Esta plataforma registra el camino, no solo el resultado",
      body: (
        <>
          <p>
            Cada cosa que el alumno hace mientras resuelve queda en una cadena firmada: lo que
            escribio, lo que le pregunto al tutor, cuando corrio los tests.
          </p>
          <p>Seis pantallas y entendes como se arma eso. Un minuto.</p>
        </>
      ),
    },
    {
      id: "comisiones",
      route: "/",
      anchor: "nav:/",
      placement: "right",
      title: "Tus comisiones",
      body: (
        <p>
          El punto de partida. Una card por cohorte con alumnos, episodios de la semana y alertas.
          Desde aca entras al detalle de cualquier estudiante.
        </p>
      ),
    },
    {
      id: "unidades",
      route: "/unidades",
      anchor: "nav:/unidades",
      placement: "right",
      title: "Unidades",
      body: (
        <>
          <p>
            La unidad es el tema del programa: condicionales, repeticion, arreglos. Es tambien el
            escalon que atraviesa el alumno, que llega al trabajo eligiendo primero la materia y
            despues la unidad.
          </p>
          <p className="text-muted">
            Son opcionales: un TP sin unidad se publica igual y el alumno lo ve. Agruparlos es lo
            que despues deja leer como le fue a la cohorte tema por tema.
          </p>
        </>
      ),
    },
    {
      id: "ejercicios",
      route: "/ejercicios",
      anchor: "nav:/ejercicios",
      placement: "right",
      title: "Banco de ejercicios",
      body: (
        <>
          <p>
            Un escalon mas abajo del tema esta el ejercicio, que es la pieza concreta: enunciado,
            casos de prueba, rubrica, y las reglas que sigue el tutor cuando el alumno le pregunta.
          </p>
          <p>
            Se carga una vez y se usa en varias comisiones y varios cuatrimestres. Eso es lo que
            despues permite comparar cohortes sobre el mismo problema.
          </p>
        </>
      ),
    },
    {
      id: "tps",
      route: "/tareas-practicas",
      anchor: "nav:/tareas-practicas",
      placement: "right",
      title: "Trabajos Practicos",
      body: (
        <>
          <p>
            El TP es el ejercicio puesto en fecha y comision. Elegis el lenguaje al crearlo, sumas
            ejercicios del banco, lo colgas de una unidad si la comision las usa, y lo publicas.
          </p>
          <p className="text-muted">
            Una vez publicado no se edita: se crea una version nueva. Es lo que mantiene intacto lo
            que ya registraron los alumnos.
          </p>
        </>
      ),
    },
    {
      id: "correcciones",
      route: "/correcciones",
      anchor: "nav:/correcciones",
      placement: "right",
      title: "Correcciones",
      body: (
        <p>
          Las entregas que llegaron, con el codigo que el alumno escribio y la linea de tiempo de
          como llego ahi. Corregis viendo el proceso, no solo la ultima version del archivo.
        </p>
      ),
    },
    {
      id: "niveles",
      route: "/episode-n-level",
      anchor: "nav:/episode-n-level",
      placement: "right",
      title: "Los niveles N1 a N4",
      body: (
        <>
          <p>
            Cada evento del alumno se etiqueta con un nivel segun que tipo de trabajo cognitivo es:
          </p>
          <ul className="space-y-1.5">
            {NIVELES.map(({ n, token, texto }) => (
              <li key={n} className="flex items-baseline gap-2">
                <span
                  aria-hidden="true"
                  className="mt-1 inline-block h-2 w-2 shrink-0 rounded-full"
                  style={{ backgroundColor: token }}
                />
                <span>
                  <strong className="text-ink">{n}</strong> {texto}
                </span>
              </li>
            ))}
          </ul>
          <p className="text-muted">
            No son notas ni ranking. Un alumno que pasa la tarde en N3 esta trabajando bien. Lo que
            el modelo muestra es la forma del camino.
          </p>
        </>
      ),
    },
  ],
}
