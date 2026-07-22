/**
 * Source of truth de UUIDs y codigos del seed `seed-3-comisiones.py`.
 *
 * Si el seed cambia (UUIDs, codigos de TP, numero de estudiantes), actualizar
 * este archivo en el mismo PR. Cualquier spec que necesite un literal del seed
 * SHALL importar desde aca — nunca hardcodear UUIDs in-line.
 *
 * Origen literal: `scripts/seed-3-comisiones.py`.
 */

export const TENANT_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

// Jerarquia academica
export const UNIVERSIDAD_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
export const FACULTAD_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
export const CARRERA_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
export const PLAN_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
export const MATERIA_ID = "ffffffff-ffff-ffff-ffff-ffffffffffff"
export const PERIODO_ID = "12345678-1234-1234-1234-123456789abc"

// Docente del piloto (usado por web-admin / web-teacher en dev mode)
export const DOCENTE_USER_ID = "11111111-1111-1111-1111-111111111111"

// Comisiones
export const COMISION_A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
export const COMISION_B_ID = "bbbb0002-bbbb-bbbb-bbbb-bbbbbbbb0002"
export const COMISION_C_ID = "cccc0003-cccc-cccc-cccc-cccccccc0003"

export const COMISION_A_NOMBRE = "A-Manana"
export const COMISION_B_NOMBRE = "B-Tarde"
export const COMISION_C_NOMBRE = "C-Noche"

// Estudiantes A-Manana (b1b1...)
export const STUDENT_A1_ID = "b1b1b1b1-0001-0001-0001-000000000001"
export const STUDENT_A2_ID = "b1b1b1b1-0002-0002-0002-000000000002"
export const STUDENT_A3_ID = "b1b1b1b1-0003-0003-0003-000000000003"
export const STUDENT_A4_ID = "b1b1b1b1-0004-0004-0004-000000000004"
export const STUDENT_A5_ID = "b1b1b1b1-0005-0005-0005-000000000005"
export const STUDENT_A6_ID = "b1b1b1b1-0006-0006-0006-000000000006"

// Estudiantes B-Tarde
export const STUDENT_B1_ID = "b2b2b2b2-0001-0001-0001-000000000001"
export const STUDENT_B2_ID = "b2b2b2b2-0002-0002-0002-000000000002"
export const STUDENT_B3_ID = "b2b2b2b2-0003-0003-0003-000000000003"
export const STUDENT_B4_ID = "b2b2b2b2-0004-0004-0004-000000000004"
export const STUDENT_B5_ID = "b2b2b2b2-0005-0005-0005-000000000005"
export const STUDENT_B6_ID = "b2b2b2b2-0006-0006-0006-000000000006"

// Estudiantes C-Noche
export const STUDENT_C1_ID = "b3b3b3b3-0001-0001-0001-000000000001"
export const STUDENT_C2_ID = "b3b3b3b3-0002-0002-0002-000000000002"
export const STUDENT_C3_ID = "b3b3b3b3-0003-0003-0003-000000000003"
export const STUDENT_C4_ID = "b3b3b3b3-0004-0004-0004-000000000004"
export const STUDENT_C5_ID = "b3b3b3b3-0005-0005-0005-000000000005"
export const STUDENT_C6_ID = "b3b3b3b3-0006-0006-0006-000000000006"

// Templates de TP (ADR-016)
export const TEMPLATE_1_ID = "11110000-0000-0000-0000-000000000001"
export const TEMPLATE_2_ID = "11110000-0000-0000-0000-000000000002"

// Codigos de TP publicadas (literales del seed; el listado real viene de la
// API, este array es solo un esperado minimo de "tiene que haber estos").
export const TP_CODES = ["TP-01", "TP-02"] as const

// URLs base de los frontends (Vite dev mode).
export const WEB_ADMIN_URL = "http://localhost:5173"
export const WEB_TEACHER_URL = "http://localhost:5174"
export const WEB_STUDENT_URL = "http://localhost:5175"

// API gateway (las llamadas via UI van por proxy Vite, esto es para el
// global-setup que hace healthchecks directos sin pasar por proxy).
export const API_GATEWAY_URL = "http://127.0.0.1:8000"
