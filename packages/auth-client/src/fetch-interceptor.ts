/**
 * Interceptor de `window.fetch` compartido por los tres frontends (web-admin,
 * web-teacher, web-student).
 *
 * Consolida (P-18) las 3 copias del monkey-patch que vivian duplicadas en cada
 * `main.tsx`. Resuelve en un unico punto:
 *
 *  - **Reescritura** de requests relativas `/api/*` al `apiBase` de prod.
 *  - **Token de Clerk** adjuntado como `Authorization: Bearer` (si no viene ya),
 *    con espera CORTA y cacheada del objeto `window.Clerk` (P-13) en vez de
 *    bloquear hasta 5s por request.
 *  - **Timeout con AbortController** por default (P-12) para que un backend
 *    lento no cuelgue al cliente indefinidamente. Se saltea en requests SSE
 *    (`Accept: text/event-stream`) para no cortar el stream del tutor.
 *
 * Los headers dinamicos especificos de cada app (`x-selected-tenant`,
 * `x-user-id`) se inyectan via el callback `dynamicHeaders`, manteniendo este
 * modulo agnostico del router y del store de identidad de cada frontend.
 *
 * NO importa keycloak-js ni React: es TS puro para poder cargarse via el
 * subpath `@platform/auth-client/fetch` sin arrastrar el provider Keycloak
 * (legacy) al bundle de las apps que ya migraron a Clerk.
 */

type ClerkLike = {
  loaded?: boolean
  load?: () => Promise<unknown>
  user?: unknown
  session?: { getToken: () => Promise<string | null> } | null
}

export interface ApiFetchInterceptorOptions {
  /**
   * Base URL para reescribir requests relativas `/api/*` (prod detras de un
   * dominio distinto). En dev el proxy de Vite maneja `/api`, dejar "".
   */
  apiBase?: string
  /**
   * Dev sin Clerk: la identidad la inyecta el proxy de Vite (headers X-*), no
   * se espera ningun token. Cuando es `true`, `getClerkToken` resuelve `null`
   * de inmediato.
   */
  devNoClerk?: boolean
  /**
   * Headers dinamicos a inyectar en cada request `/api/*` (ej.
   * `x-selected-tenant`, `x-user-id`). Se evalua por request. Los valores
   * `null`/`undefined`/"" se omiten. No pisa un header ya presente en `init`.
   */
  dynamicHeaders?: () => Record<string, string | null | undefined>
  /**
   * Timeout de espera del token de Clerk (P-13). Default 1500ms: cubre la
   * ventana de arranque en frio (window.Clerk todavia no cargo) sin bloquear
   * 5s por request. Una vez cacheado el objeto Clerk, `getToken` es casi
   * instantaneo, asi que este techo solo aplica en el cold-boot.
   */
  tokenWaitMs?: number
  /**
   * Timeout de request con AbortController (P-12). Default 25000ms. `<= 0`
   * deshabilita el timeout. Nunca aplica a requests SSE.
   *
   * Acepta una **funcion** `(url) => ms` para politicas por ruta: hay
   * endpoints legitimamente largos que no son SSE y por lo tanto no entran por
   * la exencion de `isSSE` — el wizard IA de ejercicios
   * (`POST /api/v1/ejercicios/generate`) genera un borrador completo con una
   * sola llamada al LLM y puede tardar minutos. Con el default de 25s el
   * cliente cortaba una request que el backend todavia estaba sirviendo.
   *
   * La regla al elegir valores: **el timeout del cliente tiene que ser mayor
   * que el de toda capa interna** (api-gateway, y el backend contra el
   * ai-gateway). Si el cliente corta primero, el usuario ve un timeout opaco
   * en vez del error real de la capa que fallo.
   *
   * La `url` que recibe es la ya reescrita al `apiBase` (la que se va a pedir).
   */
  requestTimeoutMs?: number | ((url: string) => number)
}

const DEFAULT_TOKEN_WAIT_MS = 1500
const DEFAULT_REQUEST_TIMEOUT_MS = 25_000

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

// Cache a nivel modulo del objeto Clerk: una vez que aparece en window, no hay
// que re-pollear en cada request (esa era la fuente del bloqueo de P-13).
let cachedClerk: ClerkLike | null = null
// Coalesce de llamadas concurrentes durante el cold-boot: si 10 requests salen
// al montar la app, comparten una sola espera del token en vez de N.
let inflightToken: Promise<string | null> | null = null

function readClerk(): ClerkLike | undefined {
  return (globalThis as unknown as { Clerk?: ClerkLike }).Clerk
}

async function resolveClerkToken(devNoClerk: boolean, deadlineMs: number): Promise<string | null> {
  if (devNoClerk) return null

  let clerk = cachedClerk ?? readClerk()
  while (!clerk && Date.now() < deadlineMs) {
    await sleep(50)
    clerk = readClerk()
  }
  if (!clerk) return null
  cachedClerk = clerk

  if (clerk.loaded === false && clerk.load) await clerk.load()

  while (Date.now() < deadlineMs) {
    const token = await clerk.session?.getToken().catch(() => null)
    if (token) return token
    // Clerk cargado sin sesion ni usuario => deslogueado: no tiene sentido
    // seguir esperando, sale sin Bearer (el gateway respondera 401 si aplica).
    if (clerk.loaded && !clerk.session && !clerk.user) return null
    await sleep(50)
  }
  return null
}

/**
 * Devuelve el token de Clerk esperando como maximo `tokenWaitMs`. Coalesce
 * llamadas concurrentes para no multiplicar la espera en el cold-boot.
 */
function getClerkToken(devNoClerk: boolean, tokenWaitMs: number): Promise<string | null> {
  if (devNoClerk) return Promise.resolve(null)
  if (inflightToken) return inflightToken
  const deadlineMs = Date.now() + Math.max(0, tokenWaitMs)
  const p = resolveClerkToken(devNoClerk, deadlineMs).finally(() => {
    inflightToken = null
  })
  inflightToken = p
  return p
}

function rawUrlOf(input: RequestInfo | URL): string {
  if (typeof input === "string") return input
  if (input instanceof URL) return input.href
  return input.url
}

function isSSE(headers: Headers): boolean {
  return (headers.get("Accept") ?? "").includes("text/event-stream")
}

/**
 * Resuelve el timeout efectivo de una request. Con un numero es constante; con
 * una funcion se evalua por ruta.
 *
 * Si el callback tira o devuelve algo que no es un numero finito, cae al
 * default en vez de propagar: esto corre dentro del monkey-patch de
 * `window.fetch`, asi que un error acá romperia TODAS las requests de la app,
 * no solo la que configuro mal el timeout.
 */
function resolveTimeoutMs(option: number | ((url: string) => number), url: string): number {
  if (typeof option === "number") return option
  try {
    const value = option(url)
    return Number.isFinite(value) ? value : DEFAULT_REQUEST_TIMEOUT_MS
  } catch {
    return DEFAULT_REQUEST_TIMEOUT_MS
  }
}

/**
 * Instala el interceptor sobre `window.fetch`. Idempotente por llamada: cada
 * install parte del `fetch` vigente y devuelve un `restore()` que lo revierte
 * (util para tests / HMR). En produccion se llama una sola vez al bootear.
 */
export function installApiFetchInterceptor(options: ApiFetchInterceptorOptions = {}): () => void {
  const {
    apiBase = "",
    devNoClerk = false,
    dynamicHeaders,
    tokenWaitMs = DEFAULT_TOKEN_WAIT_MS,
    requestTimeoutMs = DEFAULT_REQUEST_TIMEOUT_MS,
  } = options

  const base = apiBase.replace(/\/$/, "")
  const originalFetch = globalThis.fetch.bind(globalThis)

  const patched: typeof fetch = async (input, init) => {
    const rawUrl = rawUrlOf(input)
    const isRelativeApi = rawUrl.startsWith("/api/")
    const targetUrl = isRelativeApi && base ? `${base}${rawUrl}` : rawUrl

    // Requests que no son /api/ pasan intactas (Clerk, HMR, CDN de Pyodide,
    // etc.): sin reescritura, sin headers, sin timeout impuesto.
    if (!isRelativeApi) return originalFetch(input, init)

    const headers = new Headers(init?.headers ?? {})

    if (dynamicHeaders) {
      for (const [key, value] of Object.entries(dynamicHeaders())) {
        if (value && !headers.has(key)) headers.set(key, value)
      }
    }

    if (!headers.has("Authorization")) {
      const token = await getClerkToken(devNoClerk, tokenWaitMs)
      if (token) headers.set("Authorization", `Bearer ${token}`)
    }

    // P-12: timeout con AbortController. SSE queda exento (cortaria el stream
    // del tutor). Respeta un signal provisto por el caller (lo encadena).
    // El timeout puede depender de la ruta (ver `requestTimeoutMs`): se
    // resuelve por request contra la URL ya reescrita.
    const effectiveTimeoutMs = resolveTimeoutMs(requestTimeoutMs, targetUrl)
    const applyTimeout = effectiveTimeoutMs > 0 && !isSSE(headers)
    if (!applyTimeout) return originalFetch(targetUrl, { ...init, headers })

    const controller = new AbortController()
    let timedOut = false
    const userSignal = init?.signal ?? undefined
    if (userSignal) {
      if (userSignal.aborted) controller.abort(userSignal.reason)
      else
        userSignal.addEventListener("abort", () => controller.abort(userSignal.reason), {
          once: true,
        })
    }
    const timer = setTimeout(() => {
      timedOut = true
      controller.abort()
    }, effectiveTimeoutMs)

    try {
      return await originalFetch(targetUrl, { ...init, headers, signal: controller.signal })
    } catch (err) {
      // Distingue el abort por timeout (nuestro) de un abort del caller, para
      // devolver un error claro en vez de un AbortError opaco.
      if (timedOut && !(userSignal?.aborted ?? false)) {
        throw new Error(`Request timeout tras ${effectiveTimeoutMs}ms: ${targetUrl}`)
      }
      throw err
    } finally {
      clearTimeout(timer)
    }
  }

  globalThis.fetch = patched
  return () => {
    globalThis.fetch = originalFetch
  }
}

/** Resetea el cache del objeto Clerk. Solo para tests. */
export function __resetClerkCacheForTests(): void {
  cachedClerk = null
  inflightToken = null
}
