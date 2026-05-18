import { cleanup, render, screen } from "@testing-library/react"
import { Home } from "lucide-react"
import { afterEach, describe, expect, it } from "vitest"
import { Sidebar, type NavGroup } from "./Sidebar"

afterEach(() => {
  cleanup()
  try {
    localStorage.clear()
  } catch {
    // jsdom puede tener localStorage bloqueado en algún test edge — ignorar.
  }
})

const sampleGroups: NavGroup[] = [
  {
    label: "TEST",
    items: [{ id: "/home", label: "Home", icon: Home }],
  },
]

const baseProps = {
  navGroups: sampleGroups,
  headerLabel: "Test App",
  collapsedHeaderLabel: "T",
  activeItemId: "/home",
  onNavigate: () => {
    /* no-op */
  },
}

describe("Sidebar topSlot separator", () => {
  it("expanded + topSlot → wrapper tiene las 4 clases de separación", () => {
    render(
      <Sidebar
        {...baseProps}
        storageKey="test-sidebar-with-top-1"
        topSlot={<div data-testid="top">contenido top</div>}
      />,
    )
    const top = screen.getByTestId("top")
    const wrapper = top.parentElement
    expect(wrapper).not.toBeNull()
    if (!wrapper) return
    expect(wrapper.className).toContain("pb-3")
    expect(wrapper.className).toContain("border-b")
    expect(wrapper.className).toContain("border-border-soft")
    expect(wrapper.className).toContain("mb-3")
  })

  it("collapsed + topSlot → topSlot NO se renderiza (no hay wrapper)", () => {
    // Pre-sembrar localStorage para arrancar en collapsed.
    const storageKey = "test-sidebar-collapsed-2"
    localStorage.setItem(storageKey, "1")
    render(
      <Sidebar
        {...baseProps}
        storageKey={storageKey}
        topSlot={<div data-testid="top-collapsed">contenido top</div>}
      />,
    )
    expect(screen.queryByTestId("top-collapsed")).toBeNull()
  })

  it("expanded sin topSlot → solo separadores estructurales, no wrapper de topSlot", () => {
    render(<Sidebar {...baseProps} storageKey="test-sidebar-no-top-3" />)
    const aside = screen.getByRole("complementary")
    // Sin topSlot, NO debe existir un div con la combo de clases del wrapper
    // de topSlot ("pb-3 border-b border-sidebar-bg-edge mb-3"). Los borders
    // estructurales del header/footer del sidebar SÍ existen pero NO con esa combo.
    const candidates = aside.querySelectorAll('div[class*="pb-3"][class*="mb-3"]')
    expect(candidates.length).toBe(0)
  })
})
