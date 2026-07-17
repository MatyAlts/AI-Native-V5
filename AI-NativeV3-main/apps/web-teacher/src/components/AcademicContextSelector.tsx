/**
 * Selector cascada academico: Universidad -> Facultad -> Carrera -> Plan
 * -> Materia + Periodo (separado, no depende de Materia).
 *
 * Se usa en `TemplatesView` para que el docente elija el contexto
 * (materia, periodo) sobre el que opera la plantilla de TP. Las
 * plantillas viven a nivel (materia, periodo) y se fan-out-ean a todas
 * las comisiones de esa materia+periodo (ADR-016).
 *
 * Estrategia de fetch: cada nivel es un `useQuery` de TanStack Query con
 * query key estable por ID del nivel anterior (`["catalogo", <nivel>, <id>]`)
 * y `enabled: !!id`. El array del queryKey reemplaza la memoizacion manual
 * de fetchFn — no hay closures inline dependientes de IDs que dispararan el
 * loop de refetch (effect -> setState -> re-render -> nuevo closure -> effect)
 * que saturaba el rate-limiter con ~36 req/s -> 429. Cambiar de nivel cambia
 * la key: TanStack cachea/deduplica y refetchea solo cuando la key cambia.
 *
 * Degradacion: si un endpoint devuelve 403/404/500, el select muestra un
 * error inline y los siguientes quedan deshabilitados. No usamos
 * hardcoded fallbacks — el endpoint real para el catalogo academico ya
 * existe (academic-service `universidades.py`, `facultades.py`,
 * `carreras.py`, `planes.py`, `materias.py`, `comisiones.py`).
 */
import { type UseQueryResult, useQuery } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import {
  type Carrera,
  type Facultad,
  type Materia,
  type Periodo,
  type Plan,
  type Universidad,
  catalogoApi,
} from "../lib/api"

export interface AcademicContext {
  universidadId: string
  facultadId: string
  carreraId: string
  planId: string
  materiaId: string
  periodoId: string
}

interface Props {
  value: AcademicContext | null
  onChange: (ctx: AcademicContext | null) => void
  getToken: () => Promise<string | null>
}

interface LevelState<T> {
  data: T[] | null
  loading: boolean
  error: string | null
}

// Adapta un resultado de useQuery al shape que consume `CascadeSelect`
// (data/loading/error). Con `enabled: false` TanStack deja el query en idle
// (isLoading=false, data=undefined) -> el nivel se renderiza deshabilitado
// sin fetch, igual que el placeholder original.
function levelFrom<T>(query: UseQueryResult<T[]>): LevelState<T> {
  return {
    data: query.data ?? null,
    loading: query.isLoading,
    error: query.error ? String(query.error) : null,
  }
}

export function AcademicContextSelector({ value, onChange, getToken }: Props) {
  const [universidadId, setUniversidadId] = useState<string>(value?.universidadId ?? "")
  const [facultadId, setFacultadId] = useState<string>(value?.facultadId ?? "")
  const [carreraId, setCarreraId] = useState<string>(value?.carreraId ?? "")
  const [planId, setPlanId] = useState<string>(value?.planId ?? "")
  const [materiaId, setMateriaId] = useState<string>(value?.materiaId ?? "")
  const [periodoId, setPeriodoId] = useState<string>(value?.periodoId ?? "")

  // Cada nivel es un useQuery con key estable por el ID del nivel padre.
  // El array del queryKey ES la memoizacion: TanStack solo refetchea cuando
  // la key cambia (no en cada render), lo que elimina de raiz el loop 429 que
  // tenia el patron useState+useEffect(fetchFn) con closures inline. getToken
  // NO va en la key (no es serializable-estable) — el queryFn captura el
  // ultimo valor via closure sin invalidar el cache.
  const universidades = levelFrom<Universidad>(
    useQuery({
      queryKey: ["catalogo", "universidades"],
      queryFn: () => catalogoApi.universidades(getToken),
    }),
  )

  const facultades = levelFrom<Facultad>(
    useQuery({
      queryKey: ["catalogo", "facultades", universidadId],
      queryFn: () => catalogoApi.facultades(universidadId, getToken),
      enabled: !!universidadId,
    }),
  )

  const carreras = levelFrom<Carrera>(
    useQuery({
      queryKey: ["catalogo", "carreras", facultadId],
      queryFn: () => catalogoApi.carreras(facultadId, getToken),
      enabled: !!facultadId,
    }),
  )

  const planes = levelFrom<Plan>(
    useQuery({
      queryKey: ["catalogo", "planes", carreraId],
      queryFn: () => catalogoApi.planes(carreraId, getToken),
      enabled: !!carreraId,
    }),
  )

  const materias = levelFrom<Materia>(
    useQuery({
      queryKey: ["catalogo", "materias", planId],
      queryFn: () => catalogoApi.materias(planId, getToken),
      enabled: !!planId,
    }),
  )

  const periodos = levelFrom<Periodo>(
    useQuery({
      queryKey: ["catalogo", "periodos"],
      queryFn: () => catalogoApi.periodos(getToken),
    }),
  )

  // Cuando cambia un nivel, invalidamos los siguientes (no se puede
  // tener materia seleccionada si cambiaste de plan).
  const handleUniversidad = (id: string) => {
    setUniversidadId(id)
    setFacultadId("")
    setCarreraId("")
    setPlanId("")
    setMateriaId("")
  }
  const handleFacultad = (id: string) => {
    setFacultadId(id)
    setCarreraId("")
    setPlanId("")
    setMateriaId("")
  }
  const handleCarrera = (id: string) => {
    setCarreraId(id)
    setPlanId("")
    setMateriaId("")
  }
  const handlePlan = (id: string) => {
    setPlanId(id)
    setMateriaId("")
  }

  // Emisor a padre: cuando los 6 ids estan elegidos, notificamos.
  // biome-ignore lint/correctness/useExhaustiveDependencies: onChange es una prop estable del padre — agregarla refiraria el efecto cada render y causaria loop.
  useEffect(() => {
    if (universidadId && facultadId && carreraId && planId && materiaId && periodoId) {
      onChange({ universidadId, facultadId, carreraId, planId, materiaId, periodoId })
    } else {
      onChange(null)
    }
  }, [universidadId, facultadId, carreraId, planId, materiaId, periodoId])

  const handleReset = () => {
    setUniversidadId("")
    setFacultadId("")
    setCarreraId("")
    setPlanId("")
    setMateriaId("")
    setPeriodoId("")
  }

  const isComplete = Boolean(
    universidadId && facultadId && carreraId && planId && materiaId && periodoId,
  )

  return (
    <div className="space-y-3 rounded-lg border border-border-soft dark:border-sidebar-bg-edge bg-white dark:bg-sidebar-bg p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-body dark:text-sidebar-text">
          Contexto academico
        </h3>
        {isComplete && (
          <button
            type="button"
            onClick={handleReset}
            className="text-xs text-muted hover:text-body dark:hover:text-sidebar-text underline"
          >
            Cambiar seleccion
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        <CascadeSelect
          label="Universidad"
          value={universidadId}
          state={universidades}
          onChange={handleUniversidad}
          disabled={false}
          placeholder="Selecciona universidad"
          renderOption={(u: Universidad) => `${u.codigo} · ${u.nombre}`}
        />
        <CascadeSelect
          label="Facultad"
          value={facultadId}
          state={facultades}
          onChange={handleFacultad}
          disabled={!universidadId}
          placeholder={universidadId ? "Selecciona facultad" : "Elegi universidad primero"}
          renderOption={(f: Facultad) => `${f.codigo} · ${f.nombre}`}
        />
        <CascadeSelect
          label="Carrera"
          value={carreraId}
          state={carreras}
          onChange={handleCarrera}
          disabled={!facultadId}
          placeholder={facultadId ? "Selecciona carrera" : "Elegi facultad primero"}
          renderOption={(c: Carrera) => `${c.codigo} · ${c.nombre}`}
        />
        <CascadeSelect
          label="Plan"
          value={planId}
          state={planes}
          onChange={handlePlan}
          disabled={!carreraId}
          placeholder={carreraId ? "Selecciona plan" : "Elegi carrera primero"}
          renderOption={(p: Plan) => `v${p.version} · ${p.año_inicio}`}
        />
        <CascadeSelect
          label="Materia"
          value={materiaId}
          state={materias}
          onChange={setMateriaId}
          disabled={!planId}
          placeholder={planId ? "Selecciona materia" : "Elegi plan primero"}
          renderOption={(m: Materia) => `${m.codigo} · ${m.nombre}`}
        />
        <CascadeSelect
          label="Periodo"
          value={periodoId}
          state={periodos}
          onChange={setPeriodoId}
          disabled={false}
          placeholder="Selecciona periodo"
          renderOption={(p: Periodo) => `${p.codigo} · ${p.nombre}`}
        />
      </div>
    </div>
  )
}

interface CascadeSelectProps<T extends { id: string }> {
  label: string
  value: string
  state: LevelState<T>
  onChange: (id: string) => void
  disabled: boolean
  placeholder: string
  renderOption: (item: T) => string
}

function CascadeSelect<T extends { id: string }>({
  label,
  value,
  state,
  onChange,
  disabled,
  placeholder,
  renderOption,
}: CascadeSelectProps<T>) {
  const isLoading = state.loading && !disabled
  const hasError = Boolean(state.error) && !disabled
  const emptyWhenEnabled = !disabled && state.data !== null && state.data.length === 0

  return (
    <label className="block">
      <span className="block text-xs font-medium text-muted dark:text-muted-soft mb-1">
        {label}
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled || isLoading || hasError || emptyWhenEnabled}
        className="w-full px-2 py-1.5 text-sm border border-border dark:border-sidebar-bg-edge rounded bg-white dark:bg-sidebar-bg disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <option value="">
          {isLoading
            ? "Cargando..."
            : hasError
              ? "Error al cargar"
              : emptyWhenEnabled
                ? "Sin opciones disponibles"
                : placeholder}
        </option>
        {state.data?.map((item) => (
          <option key={item.id} value={item.id}>
            {renderOption(item)}
          </option>
        ))}
      </select>
      {hasError && (
        <p className="text-xs text-[var(--color-danger)] mt-1 truncate" title={state.error ?? ""}>
          {state.error}
        </p>
      )}
    </label>
  )
}
