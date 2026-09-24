/**
 * ADE-01 (change `alumno-descarga-episodio`, Lote 1) — helper puro que arma
 * el archivo de codigo fuente que el alumno descarga de su episodio cerrado:
 * su codigo final + su charla con el tutor, comentada al pie.
 *
 * Pura a proposito (sin `new Date()` adentro): la fecha/labels vienen por
 * `meta` para que el test no dependa del reloj y el componente que llama
 * (Lote 2, ADE-02) sea el unico que decide como formatear la fecha.
 *
 * Privacidad (RN del proposal): el helper recibe SOLO `messages`
 * (alumno<->tutor) — nunca el system prompt del tutor, que ni siquiera
 * llega en el input porque el endpoint no lo expone.
 */
import { describe, expect, test } from "vitest"
import { buildEpisodioSourceFile } from "../src/utils/episodioDownload"

const meta = { ejercicioTitulo: "Fibonacci Recursivo", fecha: "2026-09-24" }

describe("buildEpisodioSourceFile", () => {
  test("python: extension .py y header/charla comentados con #", () => {
    const result = buildEpisodioSourceFile({
      code: "def fib(n):\n    return n",
      messages: [{ role: "user", content: "hola", ts: "2026-09-24T10:00:00Z" }],
      language: "python",
      meta,
    })

    expect(result.filename).toBe("fibonacci-recursivo.py")
    expect(result.content).toContain("# Fibonacci Recursivo")
    expect(result.content).toContain("# 2026-09-24")
    expect(result.content).toContain("# [Alumno] hola")
  })

  test("java: extension .java y header/charla comentados con //", () => {
    const result = buildEpisodioSourceFile({
      code: "class Fib {}",
      messages: [{ role: "assistant", content: "che, pensalo de nuevo", ts: "2026-09-24T10:01:00Z" }],
      language: "java",
      meta,
    })

    expect(result.filename).toBe("fibonacci-recursivo.java")
    expect(result.content).toContain("// Fibonacci Recursivo")
    expect(result.content).toContain("// [Tutor] che, pensalo de nuevo")
  })

  test("charla multilinea: CADA linea del mensaje queda comentada por separado", () => {
    const result = buildEpisodioSourceFile({
      code: "print(1)",
      messages: [
        { role: "user", content: "linea uno\nlinea dos", ts: "2026-09-24T10:00:00Z" },
      ],
      language: "python",
      meta,
    })

    expect(result.content).toContain("# [Alumno] linea uno")
    expect(result.content).toContain("# [Alumno] linea dos")
    // Ninguna linea de la charla puede colar sin comentar (archivo invalido).
    expect(result.content).not.toContain("\nlinea dos\n")
  })

  test("sin code (null): placeholder comentado, no revienta", () => {
    const result = buildEpisodioSourceFile({
      code: null,
      messages: [],
      language: "python",
      meta,
    })

    expect(result.filename).toBe("fibonacci-recursivo.py")
    expect(result.content).toContain("#")
    expect(result.content.length).toBeGreaterThan(0)
  })

  test("sin mensajes: el archivo trae solo header + codigo, sin seccion de charla vacia rota", () => {
    const result = buildEpisodioSourceFile({
      code: "print('hola')",
      messages: [],
      language: "python",
      meta,
    })

    expect(result.content).toContain("print('hola')")
    expect(result.content).not.toContain("[Alumno]")
    expect(result.content).not.toContain("[Tutor]")
  })

  test("el codigo real NUNCA se comenta (solo la charla)", () => {
    const result = buildEpisodioSourceFile({
      code: "def real():\n    pass",
      messages: [{ role: "user", content: "dale segui", ts: "2026-09-24T10:00:00Z" }],
      language: "python",
      meta,
    })

    expect(result.content).toContain("def real():\n    pass")
  })

  test("filename seguro: tildes y simbolos del titulo no pasan tal cual", () => {
    const result = buildEpisodioSourceFile({
      code: "x = 1",
      messages: [],
      language: "python",
      meta: { ejercicioTitulo: "Programación 1: Repaso", fecha: "2026-09-24" },
    })

    expect(result.filename).toBe("programacion-1-repaso.py")
  })

  test("language ausente/desconocido: default python (.py, #)", () => {
    // biome-ignore lint: forzamos un valor invalido para probar el fallback
    const result = buildEpisodioSourceFile({
      code: "x = 1",
      messages: [],
      language: undefined as unknown as "python",
      meta,
    })

    expect(result.filename).toBe("fibonacci-recursivo.py")
    expect(result.content).toContain("#")
  })
})
