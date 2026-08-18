// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
import type { ReactNode } from "react"

/**
 * ============================================================================
 * CONTRATO DEL ONBOARDING. Este archivo es la fuente de verdad compartida entre
 * el motor (`packages/ui`) y los archivos de pasos de cada frontend.
 * NO se edita sin coordinar: lo consumen web-student y web-teacher a la vez.
 * ============================================================================
 *
 * Hay DOS mecanismos, deliberadamente separados, porque resuelven problemas
 * distintos y mezclarlos fue lo que hizo fracasar la primera version:
 *
 *   1. TOUR LINEAL (`TourFlow`) — un recorrido guiado, paso 1..N, que el usuario
 *      dispara o recibe en su primer ingreso. Sirve para el panoramico: "esto es
 *      la plataforma, estas son las secciones". El orden lo decide quien lo
 *      escribe, no el estado de la app.
 *
 *   2. ONBOARDING POR ESTADO (`OnboardingFlow`) — carteles sueltos que aparecen
 *      segun lo que el usuario YA HIZO de verdad. No hay orden ni contador
 *      propio: el estado real de la app decide que corresponde mostrar. Es lo
 *      que lo hace idempotente — si el alumno se inscribio por afuera, el paso
 *      nace cumplido y no se muestra nunca.
 *
 * Regla para elegir: si el paso te pide HACER algo, es onboarding por estado.
 * Si solo te MUESTRA algo, es tour lineal.
 */

export type TourPlacement = "top" | "bottom" | "left" | "right"

/* ========================================================================== */
/* 1. Tour lineal                                                             */
/* ========================================================================== */

/**
 * Un paso del tour lineal. El ancla es un selector `[data-tour="..."]`; se
 * resuelve al entrar al paso y se re-mide en scroll/resize.
 *
 * Si el ancla no aparece (ruta equivocada, permiso faltante, lista vacia), el
 * paso degrada a card centrada sin recorte en vez de romper el tour.
 */
export interface TourStep {
  /** Identificador estable. Se persiste: es lo que sostiene el resume. */
  id: string
  /** Valor del atributo `data-tour` del elemento a iluminar. Omitir = card centrada. */
  anchor?: string
  /** Ruta a la que navegar antes de medir el ancla. */
  route?: string
  title: string
  body: ReactNode
  /** Lado preferido de la card. Se corrige solo si no entra en viewport. */
  placement?: TourPlacement
}

export interface TourFlow {
  /**
   * Clave de persistencia. Cambiarla re-dispara el tour para TODOS los usuarios.
   * Bumpear solo cuando el recorrido cambie de verdad, no por retocar copy.
   */
  id: string
  steps: TourStep[]
}

/* ========================================================================== */
/* 2. Onboarding por estado                                                   */
/* ========================================================================== */

/**
 * Un cartel del onboarding progresivo, parametrizado por la forma del estado
 * que cada app calcula (`S`).
 *
 * Las DOS condiciones son obligatorias conceptualmente y resuelven cosas
 * distintas. Confundirlas produce el "tutorial zombie": un cartel que te pide
 * algo que ya hiciste, o algo que todavia no podes hacer.
 *
 *   - `unlockWhen`  -> "esto YA APLICA": las precondiciones estan dadas.
 *                      Falso mientras el paso no tenga sentido todavia (ej. el
 *                      docente no publico ningun TP: no le pidas que entregue).
 *   - `doneWhen`    -> "esto YA SE CUMPLIO": se deriva del estado REAL, nunca de
 *                      un contador propio. Es lo que lo hace idempotente.
 *
 * El cartel se muestra si y solo si:
 *     unlockWhen(s) && !doneWhen(s) && !fueDescartado(id)
 *
 * `fueDescartado` es el UNICO dato nuevo que persistimos. Todo lo demas sale de
 * datos que la app ya tiene.
 */
export interface OnboardingHint<S> {
  /** Identificador estable. Es la clave del descarte en localStorage. */
  id: string
  /**
   * Ruta donde corresponde mostrarlo. Omitir = en cualquier ruta.
   *
   * Se compara POR SEGMENTO, no por prefijo crudo:
   *     matchea  <=>  ruta === h.route || ruta.startsWith(h.route + "/")
   *
   * Un `startsWith` pelado seria un bug con dientes en este repo: web-teacher
   * tiene `/episode-n-level` y `/episode-timeline`, asi que un hint declarado
   * en `/episode` se dispararia en las dos. La barra es obligatoria.
   */
  route?: string
  /** `data-tour` del elemento a iluminar. Omitir = cartel centrado, sin recorte. */
  anchor?: string
  title: string
  body: ReactNode
  placement?: TourPlacement
  /** Precondiciones dadas. Ver el bloque de arriba. */
  unlockWhen: (estado: S) => boolean
  /** Ya cumplido, derivado del estado real. Ver el bloque de arriba. */
  doneWhen: (estado: S) => boolean
  /**
   * Entra en el conteo de "primeros pasos N de M".
   * Los carteles que solo explican una pantalla (no piden accion) van en false.
   * Default: true.
   */
  countsTowardProgress?: boolean
  /**
   * Texto del boton primario. Default "Entendido".
   * Cerrar SIEMPRE descarta el cartel: no hay forma de cerrarlo sin querer.
   */
  ctaLabel?: string
}

export interface OnboardingFlow<S> {
  /** Prefijo de persistencia de los descartes. Un flow por app. */
  id: string
  hints: OnboardingHint<S>[]
}

/**
 * Progreso derivado, para la barra de "primeros pasos N de M".
 * Se calcula del estado, no de un contador guardado — si el usuario hizo el
 * paso 3 antes que el 2, el progreso lo refleja igual.
 */
export interface OnboardingProgress {
  hechos: number
  total: number
  /** `hechos === total`. Cuando es true, la barra se retira sola. */
  completo: boolean
}

/* ========================================================================== */
/* Persistencia                                                               */
/* ========================================================================== */

/**
 * Por-navegador y no por-usuario: el backend todavia no guarda estado de
 * onboarding. Consecuencia asumida y declarada — el mismo docente en otra
 * maquina vuelve a ver el panoramico. Cuando exista el campo en el perfil,
 * reemplazar el modulo de persistencia es todo el cambio necesario.
 *
 * El onboarding por estado degrada bien ante esto: aunque se pierdan los
 * descartes, los pasos ya cumplidos siguen sin mostrarse, porque eso sale del
 * estado real y no de localStorage.
 */
export type TourStatus = "pendiente" | "completado" | "salteado"
