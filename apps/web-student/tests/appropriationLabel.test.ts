/**
 * BUG-04 (QA 2026-09-23): en la zona Vencidas del alumno se veia
 * "● Tu episodio:" con los dos puntos colgando — sin texto despues. En otra
 * TP el mismo label si mostraba "Tu episodio: apropiacion superficial".
 *
 * Causa: `Classification.appropriation` tiene un 4to valor real y ya en uso,
 * "autonomo" (eje ORTOGONAL — brazo sin-tutor, ver
 * `apps/classifier-service/src/classifier_service/services/pipeline.py`
 * `_EJE_TO_APPROPRIATION`, y `apps/classifier-service/.../models/__init__.py`
 * docstring de `Classification.appropriation`). El switch de
 * `appropriationLabel` en TareaSelector.tsx solo cubria los 3 valores del
 * continuo ordinal (reflexiva/superficial/delegacion) y no tenia `default`:
 * con "autonomo" el switch no matchea ningun case y devuelve `undefined`,
 * que React renderiza como nada — de ahi el ": " colgando. El guard
 * `lastResult?.appropriation &&` no lo agarra porque "autonomo" es un string
 * truthy: el <p> SI se renderiza, solo que vacio.
 *
 * web-teacher ya reconoce "autonomo" como valor legitimo (ver
 * `apps/web-teacher/src/utils/docenteLabels.ts` y
 * `apps/web-teacher/src/lib/api.ts::AppropriationAutonomo`); web-student
 * nunca lo incorporo.
 *
 * `appropriationLabel` es pura: no toca React, solo decide el texto por
 * valor de apropiacion.
 */
import { describe, expect, test } from "vitest"
import { appropriationLabel } from "../src/components/TareaSelector"

describe("appropriationLabel", () => {
  test("apropiacion_superficial: texto legible (caso feliz, ya funcionaba)", () => {
    expect(appropriationLabel("apropiacion_superficial")).toBe("apropiacion superficial")
  })

  test("autonomo: NO debe quedar vacio (el bug real reportado en QA)", () => {
    const label = appropriationLabel("autonomo")

    expect(label).toBeTruthy()
    expect(label).not.toBe("")
    expect(label).not.toBe("undefined")
  })
})
