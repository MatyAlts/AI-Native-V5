/**
 * ED-4 / H3: con QUE codigo abre el editor un episodio.
 *
 * Cuatro candidatos compiten por el buffer inicial y el orden entre ellos NO es
 * cosmetico. Mientras la decision vivia como una cascada de `if`/`else`
 * repartida a lo largo de la hidratacion de `EpisodePage` — con una rama a 60
 * lineas de la siguiente y un `usedPlaceholderRef` mutable de por medio — no
 * habia forma de ejercitarla sin montar la pagina entera contra el backend
 * mockeado. Se verifico que no la ejercitaba nadie: revertir el `else` de
 * `46b5f82` a `else if (ordenEfectivo == null)` — que hace que la siembra de
 * ED-4 vuelva a pisar la consigna del docente — dejaba los 274 tests en verde.
 *
 * Acá la misma decision es una funcion PURA de sus cuatro entradas.
 */

/** De donde salio el codigo con el que arranca el editor. */
export type OrigenCodigo =
  | "snapshot"
  | "scaffold-tp"
  | "scaffold-ejercicio"
  | "codigo-previo"
  | "placeholder"

/** Los candidatos, ya resueltos por el llamador. `null`/`""` = no hay. */
export interface CandidatosCodigo {
  /** Lo que el alumno escribio en ESTE episodio (`last_code_snapshot`). */
  snapshot?: string | null
  /** `inicial_codigo` de la TP — el scaffold del docente. */
  scaffoldTp?: string | null
  /** `inicial_codigo` del ejercicio del banco — el otro scaffold del docente. */
  scaffoldEjercicio?: string | null
  /** ED-4: lo ultimo que el alumno dejo en un ejercicio anterior de la MISMA TP. */
  codigoPrevio?: string | null
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
 *  1. `snapshot` — lo que el alumno escribio en este episodio. Pisarlo es
 *     borrarle trabajo.
 *  2. `scaffoldTp` — el scaffold del docente a nivel TP.
 *  3. `scaffoldEjercicio` — el otro scaffold del docente, solo si la TP no
 *     trae el suyo.
 *  4. `codigoPrevio` — el codigo del ejercicio anterior de la misma TP.
 *  5. `placeholder` — el andamio del lenguaje.
 *
 * Que 4 vaya DESPUES de 2 y 3 es la regla que importa: sembrar codigo de otro
 * ejercicio encima de la consigna del docente contradice el enunciado con algo
 * que parece legitimo. A diferencia del andamio del lenguaje — que se nota a
 * simple vista que no es una consigna — el alumno no tiene forma de saber que
 * lo que ve no es lo que le dejaron.
 *
 * Se usa truthiness, no `!= null`: un `inicial_codigo` vacio es "el docente no
 * dejo scaffold", no "el docente dejo un archivo vacio". Es la semantica que ya
 * tenia la cascada imperativa y no se cambia acá.
 */
export function resolverCascadaDeCodigo(candidatos: CandidatosCodigo): CodigoResuelto {
  if (candidatos.snapshot) return { codigo: candidatos.snapshot, origen: "snapshot" }
  if (candidatos.scaffoldTp) return { codigo: candidatos.scaffoldTp, origen: "scaffold-tp" }
  if (candidatos.scaffoldEjercicio) {
    return { codigo: candidatos.scaffoldEjercicio, origen: "scaffold-ejercicio" }
  }
  if (candidatos.codigoPrevio) {
    return { codigo: candidatos.codigoPrevio, origen: "codigo-previo" }
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
