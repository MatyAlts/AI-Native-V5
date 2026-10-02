/**
 * H3: con QUE codigo abre el editor un episodio.
 *
 * Tres candidatos compiten por el buffer inicial y el orden entre ellos NO es
 * cosmetico. Mientras la decision vivia como una cascada de `if`/`else`
 * repartida a lo largo de la hidratacion de `EpisodePage` — con una rama a 60
 * lineas de la siguiente y un `usedPlaceholderRef` mutable de por medio — no
 * habia forma de ejercitarla sin montar la pagina entera contra el backend
 * mockeado. Se verifico que no la ejercitaba nadie: revertir el `else` de
 * `46b5f82` a `else if (ordenEfectivo == null)` — que hacia que una siembra
 * (ED-4, desde entonces eliminada) volviera a pisar la consigna del docente —
 * dejaba los 274 tests en verde.
 *
 * Acá la misma decision es una funcion PURA de sus tres entradas.
 *
 * ED-4 (arrastre del codigo del ejercicio anterior de la misma TP) se saco de
 * acá el 2026-09-28: reinterpretaba un `inicial_codigo` vacio como "el docente
 * no se expreso" en vez de "el docente eligio que arranque vacio", y
 * contaminaba la cadena CTR con codigo heredado indistinguible de lo que
 * escribio el alumno. Ver `openspec/changes/eliminar-ed4-siembra-codigo-previo/`.
 *
 * OJO al grepear "ED-4": en este repo la etiqueta nombra DOS features
 * distintos. El otro es *marcar la linea exacta del error en Monaco*
 * (`CodeEditor.tsx`, `pyodideError.ts`), que sigue vivo y NO se toco. Quien
 * busque ED-4 va a encontrar cinco comentarios que hablan de el en presente
 * y estos que dicen que se elimino: son cosas distintas.
 *
 * `borradorLocal` (2026-10-02) es un CUARTO candidato, con la MAYOR
 * precedencia de los cuatro. Cierra un bug distinto a ED-4 y hermano suyo: el
 * alumno escribe, cada segundo se guarda una copia local Y se intenta
 * emitir el snapshot al servidor; si ese POST falla (fire-and-forget), el
 * alumno reabre y ve el snapshot viejo del servidor teniendo su propio
 * codigo, mas fresco, en esta misma maquina. La resolucion de ESTE candidato
 * (el chequeo de que sea del mismo episodio) vive en `EpisodePage`, no acá —
 * ver el comentario ahi para el porque completo. Acá solo importa que, una
 * vez resuelto, gana por sobre todo lo demas: dentro de un mismo episodio es
 * por construccion al menos tan fresco como el snapshot.
 */

/** De donde salio el codigo con el que arranca el editor. */
export type OrigenCodigo =
  | "borrador-local"
  | "snapshot"
  | "scaffold-tp"
  | "scaffold-ejercicio"
  | "placeholder"

/** Los candidatos, ya resueltos por el llamador. `null`/`""` = no hay. */
export interface CandidatosCodigo {
  /**
   * El respaldo local de ESTE episodio (`readArtefactoDraft`, ya filtrado por
   * `episode_id` en el llamador). Maxima precedencia: ver el modulo arriba.
   */
  borradorLocal?: string | null
  /** Lo que el alumno escribio en ESTE episodio (`last_code_snapshot`). */
  snapshot?: string | null
  /** `inicial_codigo` de la TP — el scaffold del docente. */
  scaffoldTp?: string | null
  /** `inicial_codigo` del ejercicio del banco — el otro scaffold del docente. */
  scaffoldEjercicio?: string | null
  /** El andamio del lenguaje. Siempre hay uno; es el ultimo eslabon. */
  placeholder: string
}

export interface CodigoResuelto {
  codigo: string
  origen: OrigenCodigo
}

/**
 * Resuelve el buffer inicial del episodio. Funcion PURA.
 *
 * La cascada, de MAYOR a MENOR precedencia:
 *
 *  1. `borradorLocal` — el respaldo que quedo en ESTA maquina para este
 *     episodio. Gana incluso al snapshot: ver el comentario del modulo.
 *  2. `snapshot` — lo que el alumno escribio en este episodio. Pisarlo es
 *     borrarle trabajo.
 *  3. `scaffoldTp` — el scaffold del docente a nivel TP.
 *  4. `scaffoldEjercicio` — el otro scaffold del docente, solo si la TP no
 *     trae el suyo.
 *  5. `placeholder` — el andamio del lenguaje.
 *
 * Sin scaffold del docente cae directo al placeholder: el campo vacio de
 * `inicial_codigo` tambien es una decision del docente ("que arranque
 * vacio"), no un silencio a interpretar.
 *
 * Se usa truthiness, no `!= null`: un `inicial_codigo` vacio es "el docente no
 * dejo scaffold", no "el docente dejo un archivo vacio". Es la semantica que ya
 * tenia la cascada imperativa y no se cambia acá.
 */
export function resolverCascadaDeCodigo(candidatos: CandidatosCodigo): CodigoResuelto {
  if (candidatos.borradorLocal) {
    return { codigo: candidatos.borradorLocal, origen: "borrador-local" }
  }
  if (candidatos.snapshot) return { codigo: candidatos.snapshot, origen: "snapshot" }
  if (candidatos.scaffoldTp) return { codigo: candidatos.scaffoldTp, origen: "scaffold-tp" }
  if (candidatos.scaffoldEjercicio) {
    return { codigo: candidatos.scaffoldEjercicio, origen: "scaffold-ejercicio" }
  }
  return { codigo: candidatos.placeholder, origen: "placeholder" }
}

/**
 * `true` si lo que quedo en el buffer sigue siendo el andamio del lenguaje.
 *
 * `EpisodePage` lo usa para saber si todavia puede reemplazar el buffer cuando
 * se resuelve el lenguaje del ejercicio: un comentario `#` en un ejercicio Java
 * abriria el editor con el archivo ya roto. Nunca pisa codigo real.
 */
export function esPlaceholder(resuelto: CodigoResuelto): boolean {
  return resuelto.origen === "placeholder"
}
