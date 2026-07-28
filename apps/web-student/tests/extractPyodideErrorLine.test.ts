/**
 * Tests para extractPyodideErrorLine (fix QA 2026-06-15 #8).
 *
 * Garantiza que del traceback CRUDO de Pyodide el alumno solo vea la última
 * línea de excepción, nunca los frames internos (`__tutor_run_student_code`,
 * `/lib/python312.zip/_pyodide/_base.py`, etc.).
 */
import { describe, expect, it } from "vitest"
import { extractPyodideErrorLine } from "../src/lib/pyodideError"

describe("extractPyodideErrorLine", () => {
  it("extrae solo la última línea de excepción de un MemoryError con traceback completo", () => {
    const raw = [
      "Traceback (most recent call last):",
      '  File "<exec>", line 1, in <module>',
      '  File "<exec>", line 12, in __tutor_run_student_code',
      '  File "/lib/python312.zip/_pyodide/_base.py", line 573, in eval_code',
      '  File "<exec>", line 3, in <module>',
      "MemoryError: out of memory",
    ].join("\n")
    expect(extractPyodideErrorLine(raw)).toBe("MemoryError: out of memory")
  })

  it("extrae ImportError ignorando los frames internos", () => {
    const raw = [
      "Traceback (most recent call last):",
      '  File "<exec>", line 12, in __tutor_run_student_code',
      '  File "/lib/python312.zip/importlib/__init__.py", line 90, in import_module',
      "ImportError: blocked module 'os'",
    ].join("\n")
    expect(extractPyodideErrorLine(raw)).toBe("ImportError: blocked module 'os'")
  })

  it("prefija TimeoutError con ⏱ y sin el nombre crudo", () => {
    const raw = [
      "Traceback (most recent call last):",
      '  File "<exec>", line 5, in __tutor_run_student_code',
      "TimeoutError: la ejecución superó el límite de 3s",
    ].join("\n")
    expect(extractPyodideErrorLine(raw)).toBe("⏱ la ejecución superó el límite de 3s")
  })

  it("matchea errores con módulo dotted (ej. asyncio.TimeoutError no, pero ValueError sí)", () => {
    const raw = "ValueError: invalid literal for int() with base 10: 'x'"
    expect(extractPyodideErrorLine(raw)).toBe(
      "ValueError: invalid literal for int() with base 10: 'x'",
    )
  })

  it("reconoce KeyboardInterrupt y Warning como headers de excepción", () => {
    expect(extractPyodideErrorLine("Traceback...\n  frame\nKeyboardInterrupt: abortado")).toBe(
      "KeyboardInterrupt: abortado",
    )
    expect(extractPyodideErrorLine("  frame\nDeprecationWarning: vieja API")).toBe(
      "DeprecationWarning: vieja API",
    )
  })

  it("fallback: última línea no vacía cuando no hay header de excepción (nunca el traceback entero)", () => {
    const raw = "linea 1\n\nlinea final relevante\n   \n"
    expect(extractPyodideErrorLine(raw)).toBe("linea final relevante")
  })

  it("ignora líneas posteriores que no son la excepción (toma la primera desde el final que matchee)", () => {
    // El header de excepción está al final; cualquier ruido posterior vacío se filtra.
    const raw = "RuntimeError: boom\n\n"
    expect(extractPyodideErrorLine(raw)).toBe("RuntimeError: boom")
  })
})
