/**
 * Cliente de autenticación Keycloak unificado para los tres frontends.
 *
 * Uso:
 * ```tsx
 * const { user, login, logout } = useAuth()
 * ```
 *
 * La configuración se pasa al provider en el root de la app.
 */
import Keycloak from "keycloak-js"
import {
  type ReactNode,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react"

export interface AuthUser {
  sub: string
  email: string
  name: string
  tenantId: string
  realm: string
  roles: string[]
  comisionesActivas: string[]
}

export interface AuthContext {
  isAuthenticated: boolean
  isLoading: boolean
  user: AuthUser | null
  token: string | null
  login: () => void
  logout: () => void
  hasRole: (role: string) => boolean
  getAccessToken: () => Promise<string | null>
}

export interface AuthConfig {
  url: string
  realm: string
  clientId: string
}

const Ctx = createContext<AuthContext | null>(null)

export function AuthProvider({
  config,
  children,
}: {
  config: AuthConfig
  children: ReactNode
}) {
  const keycloak = useMemo(() => new Keycloak(config), [config])
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [user, setUser] = useState<AuthUser | null>(null)
  const [token, setToken] = useState<string | null>(null)

  useEffect(() => {
    keycloak
      .init({
        onLoad: "check-sso",
        silentCheckSsoRedirectUri: `${window.location.origin}/silent-check-sso.html`,
        pkceMethod: "S256",
      })
      .then((auth) => {
        setIsAuthenticated(auth)
        if (auth && keycloak.tokenParsed) {
          const t = keycloak.tokenParsed as Record<string, unknown>
          setUser({
            sub: String(t.sub ?? ""),
            email: String(t.email ?? ""),
            name: String(t.name ?? ""),
            tenantId: String(t.tenant_id ?? ""),
            realm: String(t.realm ?? ""),
            roles: (t.realm_access as { roles?: string[] })?.roles ?? [],
            comisionesActivas: (t.comisiones_activas as string[] | undefined) ?? [],
          })
          setToken(keycloak.token ?? null)
        }
      })
      .finally(() => setIsLoading(false))

    // Refresh token automático 60s antes de expirar
    keycloak.onTokenExpired = () => {
      keycloak.updateToken(60).catch(() => keycloak.login())
    }
  }, [keycloak])

  const login = useCallback(() => {
    keycloak.login()
  }, [keycloak])

  const logout = useCallback(() => {
    keycloak.logout()
  }, [keycloak])

  const hasRole = useCallback((role: string) => user?.roles.includes(role) ?? false, [user])

  const getAccessToken = useCallback(async () => {
    try {
      await keycloak.updateToken(30)
      return keycloak.token ?? null
    } catch {
      return null
    }
  }, [keycloak])

  const value = useMemo<AuthContext>(
    () => ({ isAuthenticated, isLoading, user, token, login, logout, hasRole, getAccessToken }),
    [isAuthenticated, isLoading, user, token, login, logout, hasRole, getAccessToken],
  )

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAuth(): AuthContext {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error("useAuth debe usarse dentro de AuthProvider")
  return ctx
}
