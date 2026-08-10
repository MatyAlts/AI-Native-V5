// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
import type { OnboardingFlow } from "@platform/ui"
import type { EstadoAlumno } from "./estado"

/**
 * ============================================================================
 * ONBOARDING PROGRESIVO DEL ALUMNO.
 * ============================================================================
 *
 * No es un tour. No hay paso 1 de 5, no hay orden, no hay contador: cada
 * cartel se desbloquea cuando sus precondiciones estan dadas y se apaga solo
 * cuando el estado REAL del alumno dice que ya lo hizo (ver `estado.ts`).
 *
 * Consecuencias buscadas:
 *   - El alumno que se inscribio por afuera nunca ve "pega el codigo de tu
 *     comision": ese paso nace cumplido.
 *   - Si el docente todavia no publico ningun TP, no le pedimos que abra uno.
 *     Ese es el tutorial zombie que hay que evitar, y es por eso que cada
 *     hint declara SUS DOS condiciones y no una sola.
 *
 * LOS TEXTOS SON PROVISORIOS. Los va a pulir Alberto (director de tesis).
 * Estan escritos para que suenen a docente hablandole a un alumno, no a
 * producto SaaS: nada de "descubri", "potencia", "en solo 3 pasos".
 *
 * Bumpear el `id` del flow re-dispara TODOS los carteles ya descartados.
 * Hacerlo solo si el recorrido cambia de verdad, no por retocar una linea.
 */

/**
 * Guarda comun de todos los `unlockWhen`: mientras el estado no cargo no se
 * muestra NADA. Envolver la condicion en vez de repetir `!e.cargando &&` en
 * cada hint es lo que evita que a uno se le olvide y parpadee al llegar el
 * fetch.
 */
function cuando(condicion: (e: EstadoAlumno) => boolean): (e: EstadoAlumno) => boolean {
  return (e) => !e.cargando && condicion(e)
}

export const alumnoOnboarding: OnboardingFlow<EstadoAlumno> = {
  id: "alumno-v1",
  hints: [
    /* ── 1. Todavia no esta en ninguna comision ──────────────────────────
       Sin ruta a proposito: sin inscripcion la app le muestra la pantalla
       del codigo de aula este donde este. */
    {
      id: "unirse-a-comision",
      anchor: "codigo-comision",
      title: "Empeza por tu comision",
      body: (
        <>
          <p>Tu docente te pasa un codigo de aula. Pegalo aca y entras a la comision.</p>
          <p>
            Recien despues de eso vas a ver tus materias y los trabajos practicos que tu docente
            publico.
          </p>
        </>
      ),
      unlockWhen: cuando(() => true),
      doneWhen: (e) => e.tieneInscripcion,
      ctaLabel: "Entendido",
    },

    /* ── 2. Inscripto, pero todavia no abrio nada ─────────────────────────
       `hayTpsDisponibles` es la mitad que suele faltar: sin ella le estariamos
       pidiendo abrir un TP que el docente no publico.

       `route: "/"` es la home Y NADA MAS: el motor matchea por segmento
       (`ruta === declarada || ruta.startsWith(declarada + "/")`), asi que "/"
       ya no es el comodin que era. Para "en cualquier ruta" se omite `route`,
       como hace el cartel del codigo de aula. */
    {
      id: "abrir-primer-tp",
      route: "/",
      anchor: "mis-materias",
      placement: "top",
      title: "Abri tu primer trabajo practico",
      body: (
        <>
          <p>
            Entra a una materia y elegi un trabajo practico. Al abrirlo arranca un episodio: lo que
            escribas, lo que pruebes y lo que le preguntes al tutor queda registrado como parte de
            tu recorrido.
          </p>
          <p>Podes salir y retomarlo mas tarde. No se pierde nada.</p>
        </>
      ),
      unlockWhen: cuando((e) => e.tieneInscripcion && e.hayTpsDisponibles),
      doneWhen: (e) => e.tieneEpisodios,
      ctaLabel: "Vamos",
    },

    /* ── 3 y 4. Primera vez adentro de un episodio ────────────────────────
       Explican la pantalla, no piden accion: no cuentan para el progreso.
       `cantidadEpisodios > 1` y no `tieneEpisodios` porque el episodio que
       tiene abierto AHORA ya figura en la lista; con `tieneEpisodios` los
       carteles se apagarian justo cuando corresponde mostrarlos. */
    {
      id: "episodio-tutor",
      route: "/episodio",
      anchor: "tutor-chat",
      placement: "left",
      title: "El tutor no te da la respuesta",
      body: (
        <>
          <p>
            Te hace preguntas para que llegues vos. Contale que estas pensando, donde te trabaste y
            que probaste hasta ahora.
          </p>
          <p>
            Preguntar no te resta. Preguntar bien es parte del trabajo, y tambien queda anotado.
          </p>
        </>
      ),
      unlockWhen: cuando((e) => e.tieneInscripcion),
      doneWhen: (e) => e.cantidadEpisodios > 1,
      countsTowardProgress: false,
    },
    {
      id: "episodio-editor",
      route: "/episodio",
      anchor: "editor-codigo",
      placement: "top",
      title: "Aca escribis y probas tu codigo",
      body: (
        <>
          <p>
            Escribi tu solucion en el editor. Con Ejecutar la corres y ves la salida; con Probar la
            contrastas contra los casos de prueba del ejercicio.
          </p>
          <p>Equivocarte, corregir y volver a correr es el camino esperado, no un error.</p>
        </>
      ),
      unlockWhen: cuando((e) => e.tieneInscripcion),
      doneWhen: (e) => e.cantidadEpisodios > 1,
      countsTowardProgress: false,
    },

    /* ── 5. Primera vez mirando la pantalla de TPs / entregas ─────────────
       Tambien explica en vez de pedir: no cuenta para el progreso. */
    {
      id: "como-se-entrega",
      route: "/materia",
      anchor: "entrega-progreso",
      placement: "bottom",
      title: "Como se entrega un trabajo practico",
      body: (
        <>
          <p>
            Un trabajo practico se entrega cuando completaste todos sus ejercicios. El avance lo ves
            arriba, y el boton de entregar se habilita cuando no queda ninguno pendiente.
          </p>
          <p>Si el trabajo tiene un solo ejercicio, alcanza con cerrarlo desde el episodio.</p>
        </>
      ),
      unlockWhen: cuando((e) => e.tieneEpisodios),
      doneWhen: (e) => e.entregoAlgunaVez,
      countsTowardProgress: false,
    },
  ],
}
