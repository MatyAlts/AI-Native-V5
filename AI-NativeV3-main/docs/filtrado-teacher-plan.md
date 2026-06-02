# Filtrado de vistas del docente — plan

Objetivo (pedido por Juani): cada vista del web-teacher debe filtrar por el eje correcto.

## Estado deseado

| Vista | Filtrar por | Estado |
|---|---|---|
| Banco de ejercicios | **materia** | ⏳ hoy `materia_id` es opcional → si vacío toma "la primera materia" (de otra carrera). Hay que hacerlo estricto: derivar la materia de la comisión seleccionada y filtrar por ella. |
| Materiales | **materia** | ⏳ ya deriva materia_id de la comisión; verificar que filtre estricto. |
| Unidades | **profesor** (docente logueado) | 🔴 hoy filtra por `comision_id`. Falta: filtro `created_by`/profesor en el backend (`routes/unidades.py`) + frontend. |
| Trabajos Prácticos | **profesor** | 🔴 idem: hoy `comision_id`; falta filtro por profesor en backend (`routes/tareas_practicas.py`) + frontend. |
| Correcciones | **comisión** | ✅ ya filtra por `comision_id`. |
| Plantillas (Templates) | — eliminar | ✅ HECHO: sacada del menú (NAV_GROUPS de `__root.tsx`). La ruta/vista quedan pero inaccesibles. |

## Lo que falta y por qué necesita cuidado

- **Por materia (banco, materiales):** el teacher selecciona una COMISIÓN; hay que derivar su `materia_id`
  y filtrar estricto (nunca "primera materia global"). Si no hay comisión/materia → mostrar vacío, no datos
  de otra carrera.
- **Por profesor (unidades, TPs):** los endpoints del academic-service NO tienen filtro por `created_by`.
  Hay que: (1) agregar el filtro en el backend (`unidades.py`, `tareas_practicas.py`) — el `created_by`
  existe en el modelo; (2) pasar el filtro desde el frontend con la identidad del docente.

## Riesgo

Filtrado de datos académicos mal hecho = datos cruzados entre carreras/comisiones (justo lo que se quiere
evitar). Conviene hacerlo con foco y verificar cada vista, no apurado.
