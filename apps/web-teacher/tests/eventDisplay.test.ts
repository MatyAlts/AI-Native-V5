/**
 * Hallazgo #5: el timeline leia `p.success/output/error`, campos que nadie
 * emite. El payload real de `codigo_ejecutado` es
 * `{code, stdout, stderr, duration_ms, runtime}`, asi que TODAS las
 * ejecuciones salian `[ERROR]`. OK = stderr vacio; preview de stdout.
 */
import { describe, expect, test } from "vitest"
import { getEventMeta } from "../src/utils/eventDisplay"

const resumen = (p: Record<string, unknown>) => getEventMeta("codigo_ejecutado").summary(p)

describe("codigo_ejecutado.summary", () => {
  test("stderr vacio => OK con preview de stdout", () => {
    expect(resumen({ code: "print(1)", stdout: "hola mundo\n", stderr: "", duration_ms: 3 })).toBe(
      "[OK] hola mundo",
    )
  })

  test("stderr solo espacios cuenta como vacio", () => {
    expect(resumen({ stdout: "42", stderr: " \n  " })).toBe("[OK] 42")
  })

  test("stderr con contenido => ERROR con preview del error, no del stdout", () => {
    expect(resumen({ stdout: "parcial", stderr: "NameError: x" })).toBe("[ERROR] NameError: x")
  })

  test("sin stderr ni stdout => OK sin preview roto", () => {
    expect(resumen({ code: "pass" })).toMatch(/^\[OK\]/)
  })

  test("payload legacy: `error` hace de stderr y `output` de stdout", () => {
    expect(resumen({ output: "viejo", error: "" })).toBe("[OK] viejo")
    expect(resumen({ output: "viejo", error: "Boom" })).toBe("[ERROR] Boom")
  })

  test("stderr tiene prioridad sobre el `error` legacy", () => {
    expect(resumen({ stderr: "", error: "Boom", stdout: "ok" })).toBe("[OK] ok")
  })
})
