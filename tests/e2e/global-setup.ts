import Redis from "ioredis"
import { Client } from "pg"
import { TENANT_ID } from "./fixtures/seeded-ids"

/**
 * Pre-condiciones del entorno antes de arrancar la suite E2E.
 *
 * Si alguna falla, imprimimos mensaje accionable y `process.exit(1)`. Asi un
 * dev no recibe 5 timeouts cripticos a mitad de un journey — recibe un fail
 * claro al inicio.
 *
 * Verificaciones (en orden):
 *  1. 11 servicios HTTP responden /health (timeout 2s c/u).
 *  2. 3 frontends Vite responden / (timeout 2s c/u).
 *  3. Al menos 1 partition Redis tiene consumer activo en grupo `ctr_workers`.
 *  4. Postgres `academic_main` tiene la comision A-Manana del seed.
 *
 * identity-service (ADR-041) y enrollment-service (ADR-030) deprecated y borrados.
 */

interface ServiceCheck {
  name: string
  url: string
}

const SERVICES: ServiceCheck[] = [
  { name: "api-gateway", url: "http://127.0.0.1:8000/health" },
  { name: "academic-service", url: "http://127.0.0.1:8002/health" },
  { name: "evaluation-service", url: "http://127.0.0.1:8004/health" },
  { name: "analytics-service", url: "http://127.0.0.1:8005/health" },
  { name: "tutor-service", url: "http://127.0.0.1:8006/health" },
  { name: "ctr-service", url: "http://127.0.0.1:8007/health" },
  { name: "classifier-service", url: "http://127.0.0.1:8008/health" },
  { name: "content-service", url: "http://127.0.0.1:8009/health" },
  { name: "governance-service", url: "http://127.0.0.1:8010/health" },
  { name: "ai-gateway", url: "http://127.0.0.1:8011/health" },
  { name: "integrity-attestation-service", url: "http://127.0.0.1:8012/health" },
]

const FRONTENDS: ServiceCheck[] = [
  { name: "web-admin", url: "http://localhost:5173/" },
  { name: "web-teacher", url: "http://localhost:5174/" },
  { name: "web-student", url: "http://localhost:5175/" },
]

const CTR_PARTITIONS = 8

async function fetchWithTimeout(url: string, timeoutMs: number): Promise<Response> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    return await fetch(url, { signal: controller.signal })
  } finally {
    clearTimeout(timer)
  }
}

async function checkService(svc: ServiceCheck): Promise<string | null> {
  try {
    const res = await fetchWithTimeout(svc.url, 2000)
    if (!res.ok) {
      return `Servicio ${svc.name} respondio ${res.status} (esperado 200) en ${svc.url}.`
    }
    return null
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    return `Servicio ${svc.name} no responde en ${svc.url} (${msg}).`
  }
}

async function checkServices(): Promise<void> {
  console.log("[e2e-setup] 1/4 chequeando 11 servicios HTTP...")
  for (const svc of SERVICES) {
    const err = await checkService(svc)
    if (err) {
      console.error(`\n[e2e-setup] FAIL: ${err}`)
      console.error(
        `  Sugerencia: arranca los servicios con './scripts/dev-start-all.sh' o revisa '.dev-logs/${svc.name}.log'.`,
      )
      process.exit(1)
    }
  }
  console.log("[e2e-setup]   OK los 11 servicios responden /health")
}

async function checkFrontends(): Promise<void> {
  console.log("[e2e-setup] 2/4 chequeando 3 frontends Vite...")
  for (const fe of FRONTENDS) {
    const err = await checkService(fe)
    if (err) {
      console.error(`\n[e2e-setup] FAIL: ${err}`)
      console.error("  Sugerencia: arranca los frontends con 'make dev' (turbo dev).")
      process.exit(1)
    }
  }
  console.log("[e2e-setup]   OK los 3 frontends Vite estan bindeados")
}

async function checkCtrWorkers(): Promise<void> {
  console.log("[e2e-setup] 3/4 chequeando CTR workers (Redis XINFO GROUPS)...")
  const redisUrl = process.env.REDIS_URL ?? "redis://127.0.0.1:6379"
  const redis = new Redis(redisUrl, { lazyConnect: true, maxRetriesPerRequest: 1 })
  try {
    await redis.connect()
    let foundConsumer = false
    for (let i = 0; i < CTR_PARTITIONS; i += 1) {
      const stream = `ctr.p${i}`
      try {
        // XINFO GROUPS devuelve [[name,...,consumers,N,...], ...]
        const info = (await redis.xinfo("GROUPS", stream)) as unknown[]
        for (const group of info) {
          if (!Array.isArray(group)) continue
          for (let j = 0; j < group.length - 1; j += 2) {
            const key = group[j]
            const value = group[j + 1]
            if (key === "consumers" && typeof value === "number" && value > 0) {
              foundConsumer = true
              break
            }
          }
          if (foundConsumer) break
        }
        if (foundConsumer) break
      } catch {
        // Stream sin grupo (ERR no such key, etc.) — sigamos al siguiente.
      }
    }
    if (!foundConsumer) {
      console.error(
        "\n[e2e-setup] FAIL: ningun consumer activo en ctr.p0..p7 del grupo `ctr_workers`.",
      )
      console.error(
        "  Sugerencia: CTR workers no estan consumiendo. Arranca './scripts/dev-start-all.sh'" +
          " (incluye los 8 partition workers).",
      )
      process.exit(1)
    }
    console.log("[e2e-setup]   OK al menos 1 consumer activo en ctr.p* (workers consumiendo)")
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    console.error(`\n[e2e-setup] FAIL: no pude conectar a Redis (${msg}).`)
    console.error(
      "  Sugerencia: verifica que el container `platform-redis` este UP (make dev-bootstrap).",
    )
    process.exit(1)
  } finally {
    redis.disconnect()
  }
}

async function checkSeed(): Promise<void> {
  console.log("[e2e-setup] 4/4 chequeando seed (comision A-Manana en academic_main)...")
  const url =
    process.env.ACADEMIC_DB_PG_URL ??
    process.env.ACADEMIC_DB_URL_NODE ??
    "postgres://postgres:postgres@127.0.0.1:5432/academic_main"
  const client = new Client({ connectionString: url })
  try {
    await client.connect()
    await client.query("SELECT set_config('app.current_tenant', $1, true)", [TENANT_ID])
    const res = await client.query<{ nombre: string }>(
      "SELECT nombre FROM comisiones WHERE id = $1",
      ["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"],
    )
    if (res.rowCount === 0 || res.rows[0]?.nombre !== "A-Manana") {
      console.error(
        "\n[e2e-setup] FAIL: comision aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa con nombre" +
          " 'A-Manana' no encontrada.",
      )
      console.error(
        "  Sugerencia: seed `seed-3-comisiones.py` no aplicado." +
          " Corre 'make test-e2e-clean' o 'uv run python scripts/seed-3-comisiones.py'.",
      )
      process.exit(1)
    }
    console.log("[e2e-setup]   OK seed aplicado (comision A-Manana presente)")
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    console.error(`\n[e2e-setup] FAIL: no pude consultar academic_main (${msg}).`)
    console.error(
      "  Sugerencia: verifica que postgres este UP (make dev-bootstrap) y migrado (make migrate).",
    )
    process.exit(1)
  } finally {
    await client.end().catch(() => undefined)
  }
}

export default async function globalSetup(): Promise<void> {
  console.log("[e2e-setup] Verificando pre-condiciones del entorno...")
  await checkServices()
  await checkFrontends()
  await checkCtrWorkers()
  await checkSeed()
  console.log("[e2e-setup] Pre-condiciones OK. Arrancando suite.\n")
}
