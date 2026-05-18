/**
 * Cliente HTTP autenticado — agrega Authorization: Bearer automáticamente.
 *
 * Uso en un componente:
 * ```tsx
 * const api = useAuthenticatedFetch()
 * const data = await api("/api/v1/episodes", { method: "POST", ... })
 * ```
 *
 * El cliente:
 *  - Obtiene el token fresco del AuthContext (refresca si está cerca de expirar)
 *  - Inyecta Authorization: Bearer <token>
 *  - Si recibe 401, dispara login() automáticamente
 *  - Propaga el cuerpo de error del backend en la Error message
 */
import { useCallback } from "react"
import { useAuth } from "./index"

export interface AuthenticatedFetchOptions extends RequestInit {
  // El método retry se puede configurar en options si se quiere deshabilitar
  autoRetryOn401?: boolean
}

export function useAuthenticatedFetch() {
  const { getAccessToken, login, isAuthenticated } = useAuth()

  return useCallback(
    async (input: string | URL, init: AuthenticatedFetchOptions = {}): Promise<Response> => {
      if (!isAuthenticated) {
        login()
        throw new Error("No autenticado")
      }

      const token = await getAccessToken()
      if (!token) {
        login()
        throw new Error("Token no disponible")
      }

      const headers = new Headers(init.headers)
      headers.set("Authorization", `Bearer ${token}`)
      if (!headers.has("Content-Type") && init.body && typeof init.body === "string") {
        headers.set("Content-Type", "application/json")
      }

      const autoRetry = init.autoRetryOn401 !== false
      const { autoRetryOn401: _, ...fetchInit } = init

      const response = await fetch(input, { ...fetchInit, headers })

      if (response.status === 401 && autoRetry) {
        // Token podría haber expirado entre el check y el uso
        // Un retry con token refrescado suele alcanzar
        const refreshed = await getAccessToken()
        if (refreshed && refreshed !== token) {
          headers.set("Authorization", `Bearer ${refreshed}`)
          return fetch(input, { ...fetchInit, headers })
        }
        // Si aún 401 tras refresh, el usuario necesita re-loguear
        login()
      }

      return response
    },
    [getAccessToken, login, isAuthenticated],
  )
}

/**
 * SSE con auth — EventSource nativo no soporta headers custom, así que
 * tenemos que usar fetch + stream manual para endpoints SSE del tutor.
 *
 * Devuelve un async iterator de eventos parseados.
 */
export async function* authenticatedSSE(
  token: string,
  url: string,
  init: RequestInit = {},
): AsyncGenerator<unknown, void, unknown> {
  const headers = new Headers(init.headers)
  headers.set("Authorization", `Bearer ${token}`)
  headers.set("Accept", "text/event-stream")

  const response = await fetch(url, { ...init, headers })
  if (!response.ok || !response.body) {
    throw new Error(`SSE failed: ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const lines = buffer.split("\n")
    buffer = lines.pop() ?? ""

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue
      try {
        yield JSON.parse(line.slice(6))
      } catch {
        // ignorar líneas mal formadas
      }
    }
  }
}
