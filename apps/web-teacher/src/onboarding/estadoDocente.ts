// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
import { useQuery } from "@tanstack/react-query"
import { useMemo } from "react"
import { COMISIONES_QUERY_KEY } from "../components/ComisionSelector"
import { comisionesApi, entregasDocenteApi, tareasPracticasApi, unidadesApi } from "../lib/api"

/**
 * Estado real del docente: lo unico de lo que dependen los carteles del onboarding
 * progresivo. No hay contador propio ni "paso 2 de 3" guardado en ningun lado — si el
 * docente hizo la cosa, el cartel no se muestra, sin importar en que orden la hizo ni
 * si la hizo desde otra maquina.
 *
 * Los flags `*Cargado` existen porque la ausencia de dato NO es lo mismo que el dato
 * en cero. Un cartel que aparece medio segundo tarde porque llego el fetch es
 * peor que ninguno: le dice al docente que le falta algo que en realidad ya tiene.
 * Mientras el flag esta en false, el paso que depende de ese dato no se desbloquea.
 *
 * Un fetch que falla deja su flag en false y por lo tanto no muestra nada. Preferimos
 * quedarnos callados antes que afirmar sobre datos que no tenemos.
 */
export interface EstadoDocente {
  /** Ya sabemos si tiene comisiones asignadas. */
  comisionesCargadas: boolean
  tieneComision: boolean
  /** Comision sobre la que se calculan TPs y entregas. `null` = ninguna elegida. */
  comisionActivaId: string | null
  /** Ya sabemos si la comision activa tiene TPs. */
  tpsCargados: boolean
  tieneTp: boolean
  /** Ya sabemos si la comision activa tiene unidades. */
  unidadesCargadas: boolean
  tieneUnidad: boolean
  /** Ya sabemos como viene la cola de entregas de la comision activa. */
  entregasCargadas: boolean
  hayEntregaPendiente: boolean
  hayEntregaCorregida: boolean
}

/**
 * Primera pagina de entregas. Alcanza para las dos preguntas que hacemos ("hay alguna
 * pendiente", "corrigio alguna"): el docente al que le hablan estos carteles todavia
 * no tiene una cola larga. Es la misma pagina que ya pide la vista de Correcciones.
 */
const PRIMERA_PAGINA_ENTREGAS = 50

/**
 * Calcula el estado con los MISMOS endpoints que la app ya consume en otras vistas
 * (`/comisiones/mis`, `/tareas-practicas`, `/unidades`, `/entregas`). No hay endpoint nuevo ni
 * campo nuevo en el backend: el onboarding no le pide nada al servidor que la app no
 * le fuera a pedir igual.
 *
 * Las comisiones se leen de la MISMA entrada de cache que el selector del header
 * (`COMISIONES_QUERY_KEY`): ya las pidio el, no hay un segundo request.
 *
 * TPs, unidades y entregas van bajo el prefijo `onboarding-docente` a proposito. Las
 * vistas que los muestran los traen con `useEffect` + `useState` (Unidades) o con
 * `useInfiniteQuery` bajo otra forma (Correcciones cachea `entregas-docente`
 * paginado): no hay entrada de cache que compartir, y mezclar una query paginada con
 * una simple en la misma clave mete dos formas de dato distintas en el mismo lugar.
 */
export function useEstadoDocente(comisionActivaId: string | null): EstadoDocente {
  const comisiones = useQuery({
    queryKey: COMISIONES_QUERY_KEY,
    queryFn: () => comisionesApi.listMine(),
  })

  const tps = useQuery({
    queryKey: ["onboarding-docente", "tps", comisionActivaId],
    // `?? ""` nunca se ejecuta: la query esta deshabilitada sin comision.
    queryFn: () => tareasPracticasApi.list({ comision_id: comisionActivaId ?? "", limit: 1 }),
    enabled: comisionActivaId !== null,
  })

  const unidades = useQuery({
    queryKey: ["onboarding-docente", "unidades", comisionActivaId],
    // `?? ""` nunca se ejecuta: la query esta deshabilitada sin comision.
    queryFn: () => unidadesApi.list(comisionActivaId ?? ""),
    enabled: comisionActivaId !== null,
  })

  const entregas = useQuery({
    queryKey: ["onboarding-docente", "entregas", comisionActivaId],
    queryFn: () =>
      entregasDocenteApi.list({
        comision_id: comisionActivaId ?? "",
        limit: PRIMERA_PAGINA_ENTREGAS,
      }),
    enabled: comisionActivaId !== null,
  })

  const comisionesItems = comisiones.data?.items
  const tpsItems = tps.data?.data
  const unidadesItems = unidades.data
  const entregasItems = entregas.data?.data

  return useMemo<EstadoDocente>(
    () => ({
      comisionesCargadas: comisionesItems !== undefined,
      tieneComision: (comisionesItems?.length ?? 0) > 0,
      comisionActivaId,
      tpsCargados: tpsItems !== undefined,
      tieneTp: (tpsItems?.length ?? 0) > 0,
      unidadesCargadas: unidadesItems !== undefined,
      tieneUnidad: (unidadesItems?.length ?? 0) > 0,
      entregasCargadas: entregasItems !== undefined,
      hayEntregaPendiente: (entregasItems ?? []).some((e) => e.estado === "submitted"),
      // Devuelta tambien cuenta como corregida: es una calificada que ademas ya se
      // libero al alumno.
      hayEntregaCorregida: (entregasItems ?? []).some(
        (e) => e.estado === "graded" || e.estado === "returned",
      ),
    }),
    [comisionesItems, tpsItems, unidadesItems, entregasItems, comisionActivaId],
  )
}
