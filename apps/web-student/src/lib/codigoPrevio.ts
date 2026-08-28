/**
 * ED-4: arrastre del código entre los ejercicios de una misma TP.
 *
 * El problema
 * -----------
 * Cada ejercicio de una TP multi-ejercicio es un episodio propio, y el editor
 * de cada episodio arranca en cero. Los ejercicios del banco PID-UTN están
 * encadenados (E2 usa la función que se escribió en E1), así que el alumno
 * terminaba con dos pestañas abiertas copiando a mano de una a la otra —
 * exactamente el "pantalla dividida" del informe del alumno. Peor: copiar está
 * bloqueado en el editor, así que el arrastre manual además ensucia la cadena
 * con `pega_bloqueada`.
 *
 * La solución es sembrar el buffer del ejercicio N con lo último que el alumno
 * tenía en el ejercicio N-1 de la MISMA TP.
 *
 * Por qué `sessionStorage` y no el backend
 * ----------------------------------------
 * Mismo criterio que `active-exercise-context` (ver `materia.$id.tsx`): es
 * estado de navegación de una sesión de trabajo, no un hecho del dominio. Vive
 * y muere con la pestaña, no viaja al CTR y no participa de ninguna cadena.
 *
 * Regla dura de trazabilidad
 * --------------------------
 * La siembra NO puede emitir `edicion_codigo`. El alumno no escribió eso; un
 * evento de edición que no ocurrió es evidencia falsa. Por eso el consumidor
 * (`EpisodePage`) siembra por el MISMO camino que ya usa `last_code_snapshot`:
 * el `initialCode` con el que se monta `CodeEditor`, que llega a Monaco por
 * `editor.create` y nunca por `onDidChangeModelContent`. Ver el test
 * "el re-montaje NO emite un edicion_codigo fantasma".
 */

/** Subconjunto de `Storage` que este módulo necesita (testeable sin jsdom). */
export interface AlmacenLike {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
  removeItem(key: string): void
}

/** Lo que se guarda, por TP, al salir de un ejercicio. */
export interface CodigoPrevio {
  /** `tarea_practica_id` — el arrastre nunca cruza de una TP a otra. */
  tareaId: string
  /** Orden del ejercicio del que sale este código. */
  ejercicioOrden: number
  /** Lenguaje del ejercicio de origen. Sembrar Java en un ejercicio Python
   * abriría el editor con el archivo ya roto. */
  language: string
  /** Último buffer conocido de ese ejercicio. */
  code: string
}

/** Contexto del ejercicio que se está por abrir. */
export interface DestinoSiembra {
  tareaId: string
  /** `null` = TP monolítica: no hay "ejercicio previo" del que heredar. */
  ejercicioOrden: number | null
  language: string
}

const KEY_PREFIX = "web-student.codigo-previo."

/** Una clave por TP: dos TPs abiertas en la misma sesión no se pisan.
 *
 * UNA sola entrada por TP, no un historial: el arrastre es "lo último que
 * dejaste en esta TP", no "el ejercicio N-1". Si el alumno hace el 3 y despues
 * abre el 2, lo guardado (orden 3) no aplica —`resolverSiembra` exige orden
 * estrictamente anterior— y el 2 arranca limpio, aunque el 1 hubiera servido.
 * Es el precio de no acumular estado; el caso normal (avanzar en orden) anda. */
export function claveCodigoPrevio(tareaId: string): string {
  return `${KEY_PREFIX}${tareaId}`
}

/**
 * Parsea lo que había en el almacén. Devuelve `null` ante cualquier cosa que no
 * sea una entrada completa y bien tipada — un JSON viejo o corrupto no debe
 * poder sembrar el editor con basura.
 */
export function parseCodigoPrevio(raw: string | null): CodigoPrevio | null {
  if (!raw) return null
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return null
  }
  if (typeof parsed !== "object" || parsed === null) return null
  const o = parsed as Record<string, unknown>
  if (typeof o.tareaId !== "string" || o.tareaId === "") return null
  if (typeof o.ejercicioOrden !== "number" || !Number.isFinite(o.ejercicioOrden)) return null
  if (typeof o.language !== "string" || o.language === "") return null
  if (typeof o.code !== "string") return null
  return {
    tareaId: o.tareaId,
    ejercicioOrden: o.ejercicioOrden,
    language: o.language,
    code: o.code,
  }
}

/**
 * Decide si lo guardado sirve como semilla para el ejercicio de destino.
 *
 * Función pura: es acá donde vive todo el criterio, para que se lo pueda
 * ejercitar sin `sessionStorage` ni React. Devuelve el código a sembrar o
 * `null` si no corresponde sembrar nada.
 *
 * Se siembra sólo si TODO esto se cumple:
 *  - el destino es un ejercicio de una TP multi-ejercicio (`ejercicioOrden`
 *    no nulo): en una TP monolítica no existe "el ejercicio anterior";
 *  - es la MISMA TP;
 *  - es el MISMO lenguaje;
 *  - el guardado viene de un ejercicio ESTRICTAMENTE anterior. Con `>=` un
 *    F5 sobre el mismo ejercicio se re-sembraría a sí mismo, pisando lo que
 *    el episodio ya hidrató, y un salto hacia atrás traería código del futuro;
 *  - hay algo que sembrar (no sólo espacios).
 */
export function resolverSiembra(
  guardado: CodigoPrevio | null,
  destino: DestinoSiembra,
): string | null {
  if (!guardado) return null
  if (destino.ejercicioOrden == null) return null
  if (guardado.tareaId !== destino.tareaId) return null
  if (guardado.language !== destino.language) return null
  if (guardado.ejercicioOrden >= destino.ejercicioOrden) return null
  if (guardado.code.trim() === "") return null
  return guardado.code
}

/** Lo que el episodio que se está dejando sabe de sí mismo. */
export interface OrigenPersistencia {
  /** `tarea_practica_id`. Nulo mientras la TP no terminó de hidratar. */
  tareaId: string | null | undefined
  /** Orden del ejercicio que se deja. `null` = TP monolítica. */
  ejercicioOrden: number | null
  language: string
  /** Buffer actual del editor. */
  code: string
  /** Andamio del lenguaje, para reconocer que el alumno no escribió nada. */
  placeholder: string
}

/**
 * La otra mitad de `resolverSiembra`: decide QUÉ se guarda al dejar un
 * ejercicio. Función pura — devuelve la entrada a persistir o `null`.
 *
 * Vive acá y no dentro de la página por la misma razón que su gemela: es todo
 * criterio, no tiene nada de React, y desconectarla es invisible desde afuera
 * (nadie ve una escritura que no ocurrió — se nota un ejercicio después, como
 * un arrastre que no llegó).
 *
 * No se guarda si:
 *  - todavía no hay TP hidratada (`tareaId` nulo);
 *  - la TP es monolítica (`ejercicioOrden` nulo): no hay "próximo ejercicio"
 *    al que arrastrarle nada;
 *  - el buffer es exactamente el andamio del lenguaje. El alumno no escribió
 *    código propio, y el siguiente ejercicio va a poner ese mismo andamio solo.
 */
export function resolverCodigoAPersistir(origen: OrigenPersistencia): CodigoPrevio | null {
  if (!origen.tareaId) return null
  if (origen.ejercicioOrden == null) return null
  if (origen.code === origen.placeholder) return null
  return {
    tareaId: origen.tareaId,
    ejercicioOrden: origen.ejercicioOrden,
    language: origen.language,
    code: origen.code,
  }
}

/**
 * Guarda el buffer del ejercicio que el alumno está dejando.
 *
 * Best-effort: `setItem` tira en modo privado de Safari y con la cuota llena.
 * Perder el arrastre es una molestia; romper el cierre del episodio por eso
 * sería mucho peor.
 */
export function guardarCodigoPrevio(almacen: AlmacenLike, entrada: CodigoPrevio): void {
  if (entrada.code.trim() === "") return
  try {
    almacen.setItem(claveCodigoPrevio(entrada.tareaId), JSON.stringify(entrada))
  } catch {
    /* best-effort */
  }
}

/** Lee y resuelve de una: `null` si no hay nada que sembrar. */
export function leerCodigoPrevio(almacen: AlmacenLike, destino: DestinoSiembra): string | null {
  let raw: string | null
  try {
    raw = almacen.getItem(claveCodigoPrevio(destino.tareaId))
  } catch {
    return null
  }
  return resolverSiembra(parseCodigoPrevio(raw), destino)
}
