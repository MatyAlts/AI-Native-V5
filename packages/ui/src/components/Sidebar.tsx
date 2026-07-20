import { ChevronLeft, ChevronRight } from "lucide-react"
import type { LucideIcon } from "lucide-react"
import type { ReactNode } from "react"
import { useEffect, useState } from "react"

/**
 * Sidebar colapsable + agrupado, compartido por los frontends admin/teacher.
 *
 * Paleta v2 — "Stack Blue institucional":
 * - Fondo carbón puro `bg-sidebar-bg` (#1a1a1a). Sin mezcla gray/slate/zinc anterior.
 * - Item activo: border-left acento brand (Stack Blue) + bg sidebar-bg-edge sutil.
 * - Texto crema cálido (no blanco saturado). Muted texts preservan jerarquía.
 *
 * Estado expanded/collapsed persistido en localStorage bajo `storageKey`.
 * `topSlot` opcional para contenido arriba de los grupos de nav (ej. ComisionSelector
 * en web-teacher). Sólo se renderiza cuando el sidebar está expanded.
 * Tooltips en collapsed via `title` attr nativo (sin libs).
 */

export interface NavItem {
  id: string
  label: string
  icon: LucideIcon
}

export interface NavGroup {
  /** Etiqueta del grupo (uppercase en UI). `undefined` oculta el header — útil si hay un solo item suelto. */
  label?: string
  items: NavItem[]
}

export interface SidebarProps {
  navGroups: NavGroup[]
  headerLabel: string
  collapsedHeaderLabel: string
  storageKey: string
  activeItemId: string
  onNavigate: (id: string) => void
  /** Contenido opcional renderizado entre el header y los grupos de nav (solo en expanded). */
  topSlot?: ReactNode
}

function readInitialCollapsed(storageKey: string): boolean {
  if (typeof window === "undefined") return false
  try {
    return window.localStorage.getItem(storageKey) === "1"
  } catch {
    // localStorage puede estar bloqueado (modo incógnito estricto, etc.) — degradar a expanded.
    return false
  }
}

export function Sidebar({
  navGroups,
  headerLabel,
  collapsedHeaderLabel,
  storageKey,
  activeItemId,
  onNavigate,
  topSlot,
}: SidebarProps): ReactNode {
  const [collapsed, setCollapsed] = useState<boolean>(() => readInitialCollapsed(storageKey))

  useEffect(() => {
    try {
      window.localStorage.setItem(storageKey, collapsed ? "1" : "0")
    } catch {
      // No-op si localStorage está bloqueado.
    }
  }, [collapsed, storageKey])

  const widthClass = collapsed ? "w-16" : "w-64"

  return (
    <aside
      className={`${widthClass} shrink-0 bg-sidebar-bg text-sidebar-text flex flex-col border-r border-border transition-[width] duration-150`}
      aria-label="Navegación principal"
    >
      <div
        className={`flex items-center ${collapsed ? "justify-center" : "justify-between"} px-3 h-14 border-b border-border-soft`}
      >
        {!collapsed && <span className="text-sm font-semibold tracking-tight text-ink">{headerLabel}</span>}
        {collapsed && (
          <span className="text-sm font-semibold tracking-tight text-ink">{collapsedHeaderLabel}</span>
        )}
      </div>

      {!collapsed && topSlot && (
        <div className="px-3 pt-3 pb-3 border-b border-border-soft mb-3">{topSlot}</div>
      )}

      <nav className="flex-1 overflow-y-auto py-3">
        {navGroups.map((group, idx) => (
          <NavGroupBlock
            key={group.label ?? `group-${idx}`}
            group={group}
            activeItemId={activeItemId}
            onNavigate={onNavigate}
            collapsed={collapsed}
          />
        ))}
      </nav>

      <div className="border-t border-border-soft p-2">
        <button
          type="button"
          onClick={() => setCollapsed((prev) => !prev)}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-md text-muted hover:bg-surface-alt hover:text-ink transition-colors"
          aria-label={collapsed ? "Expandir sidebar" : "Colapsar sidebar"}
          aria-expanded={!collapsed}
          title={collapsed ? "Expandir sidebar" : "Colapsar sidebar"}
        >
          {collapsed ? (
            <ChevronRight className="w-4 h-4" aria-hidden="true" />
          ) : (
            <>
              <ChevronLeft className="w-4 h-4" aria-hidden="true" />
              <span className="text-xs">Colapsar</span>
            </>
          )}
        </button>
      </div>
    </aside>
  )
}

interface NavGroupBlockProps {
  group: NavGroup
  activeItemId: string
  onNavigate: (id: string) => void
  collapsed: boolean
}

function NavGroupBlock({
  group,
  activeItemId,
  onNavigate,
  collapsed,
}: NavGroupBlockProps): ReactNode {
  return (
    <div className="mb-4 last:mb-0">
      {group.label && !collapsed && (
        <div className="px-4 mb-1 text-[10px] uppercase tracking-[0.08em] font-semibold text-muted">
          {group.label}
        </div>
      )}
      {group.label && collapsed && (
        // En collapsed, separador visual sutil entre grupos (sin texto).
        <div className="mx-3 mb-1 border-t border-border-soft" />
      )}
      <ul className="space-y-0.5 px-2">
        {group.items.map((item) => (
          <li key={item.id}>
            <NavLink
              item={item}
              active={item.id === activeItemId}
              onNavigate={onNavigate}
              collapsed={collapsed}
            />
          </li>
        ))}
      </ul>
    </div>
  )
}

interface NavLinkProps {
  item: NavItem
  active: boolean
  onNavigate: (id: string) => void
  collapsed: boolean
}

function NavLink({ item, active, onNavigate, collapsed }: NavLinkProps): ReactNode {
  const Icon = item.icon
  const baseClasses =
    "group relative flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors"
  const stateClasses = active
    ? "bg-accent-brand-soft text-accent-brand-deep font-medium border-l-2 border-accent-brand pl-[10px]"
    : "text-body hover:bg-surface-alt hover:text-ink border-l-2 border-transparent pl-[10px]"
  const justifyClass = collapsed ? "justify-center" : ""

  return (
    <button
      type="button"
      onClick={() => onNavigate(item.id)}
      className={`${baseClasses} ${stateClasses} ${justifyClass} w-full text-left`}
      aria-current={active ? "page" : undefined}
      title={collapsed ? item.label : undefined}
    >
      <Icon className="w-4 h-4 shrink-0" aria-hidden="true" />
      {!collapsed && <span className="truncate">{item.label}</span>}
    </button>
  )
}
