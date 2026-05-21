# Diseño del test de transfer (CS11)

**Versión**: 1.0.0 — DRAFT pendiente revisión coautoral + docentes UTN (validez de contenido) + comité ético.
**Fecha**: 2026-05-16.
**Origen**: `plan1Socra.md` CS11 (P1, antes de submisión final). Recomendación C1.3 del `informeSocra1.md`. Necesario para operacionalizar H2 del paper.

---

## 0. Resumen

H2 del paper afirma que la coherencia estructural multidimensional se asocia con desempeño en tareas de transferencia. Sin un instrumento de transfer operacionalizado, H2 es declarativa. Este documento diseña el instrumento.

**Definición operacional de transfer**: capacidad del estudiante de resolver problemas estructuralmente análogos a los del banco del piloto, pero con cambio de dominio superficial (de listas en Python a strings o tuplas; del mismo patrón algorítmico a un patrón cognitivamente cercano). Bransford, Brown & Cocking (2000) distinguen near transfer (cercano) y far transfer (lejano); este instrumento mide **near transfer**.

---

## 1. Estructura del test

### 1.1 Cantidad y formato

- **5 problemas** de 3-5 minutos cada uno, totalizando 15-25 minutos.
- **Formato**: ejercicios escritos breves (puede usar editor con resaltado pero sin ejecución asistida ni LLM).
- **Sin tutor**, **sin ejecución asistida**, **sin acceso a internet** durante el test.
- Aplicación al final del cuatrimestre, **antes** del examen final pero después de las entregas de TPs.

### 1.2 Problemas — ejemplos de mapeo banco → transfer

Para cada problema del banco se diseña un análogo estructural:

| Problema del banco | Análogo de transfer |
|---|---|
| Encontrar el segundo mayor de una lista de enteros | Encontrar el segundo más largo de una lista de strings |
| Sumar elementos pares de una lista | Concatenar los strings que empiezan con vocal de una lista |
| Contar ocurrencias de un valor en una lista | Contar caracteres únicos en un string |
| Invertir una lista | Invertir las palabras de una frase (manteniendo orden de letras dentro de palabra) |
| Determinar si una lista está ordenada | Determinar si las palabras de una frase están en orden alfabético |

Los 5 análogos preservan el patrón algorítmico subyacente (iteración + condición, agregación, conteo, transformación, validación) pero cambian el dominio léxico (listas de enteros → strings).

**Decisión de diseño**: los análogos NO deben ser triviales (el estudiante que copió la solución del banco no puede simplemente reproducirla con find-and-replace) ni demasiado lejanos (debe ser plausible que un estudiante con apropiación reflexiva sobre el banco los resuelva).

### 1.3 Scoring

Cada problema:
- **0** — sin intentar o intento sin estructura algorítmica reconocible.
- **1** — intento con estructura correcta pero con errores (sintácticos o lógicos parciales).
- **2** — solución funcional correcta.

Total: 0-10 sobre los 5 problemas. **No es escala continua** — es ordinal con 11 niveles. Análisis estadístico con métodos no paramétricos por defecto (Spearman, Kruskal-Wallis), no Pearson.

### 1.4 Rúbrica de explicación corta (opcional, captura cualitativa)

Después de cada problema, espacio de 50-150 caracteres para que el estudiante explique brevemente "cómo encararía el problema si tuviera más tiempo". Esto captura **proceso autorreportado** complementario al producto. Análisis cualitativo por dos codificadores (κ ≥ 0,70) con categorías: (a) estrategia algorítmica explícita, (b) reformulación del problema, (c) bloqueo declarado, (d) sin respuesta.

---

## 2. Validez de contenido

### 2.1 Procedimiento de validación

Los 5 problemas pasan por validación de contenido con **3 docentes UTN** independientes:
- Califican cada análogo según (a) distancia estructural al original (1-5), (b) dificultad esperada (1-5), (c) claridad del enunciado (1-5).
- Los análogos con distancia estructural < 2 o > 4 se reemplazan.
- Los análogos con dificultad esperada < 2 (muy fácil) o > 4 (muy difícil) se calibran.

### 2.2 Pilotaje

Antes de la aplicación masiva, pilotar con 5-10 estudiantes voluntarios de cursos paralelos (no del grupo experimental del piloto-2). Estimar tiempo real promedio y ajustar la cantidad de problemas si es necesario.

---

## 3. Captura técnica

### 3.1 Endpoint

Endpoint nuevo en `analytics-service`:

```
POST /api/v1/transfer-test/submit
Auth: estudiante autenticado.
Payload:
{
  "test_version": "transfer-2026-v1.0.0",
  "responses": [
    {"problem_id": "p1", "code": "def f(...) ...", "explanation": "...", "elapsed_ms": 240000},
    ...
  ]
}
```

Validaciones backend:
- `test_version` debe existir en `transfer_test_versions` (catálogo).
- `problem_id` debe pertenecer al test_version (5 problemas).
- `code` ≤ 2000 chars.
- `explanation` ≤ 150 chars.
- `elapsed_ms` ≥ 30000 (mínimo 30 segundos por problema; rechaza spam).

### 3.2 Tabla nueva

`transfer_test_responses` en `academic_main`:
- `id` UUID PK
- `student_pseudonym` UUID
- `test_version` text
- `problem_id` text
- `code_submitted` text
- `explanation` text
- `elapsed_ms` int
- `score` int CHECK 0..2 (nullable, se llena post-codificación)
- `coded_by` UUID (docente que asignó score)
- `coded_at` timestamptz
- `submitted_at` timestamptz

### 3.3 UI

Componente nuevo `TransferTestView.tsx` en `web-student`:
- Acceso vía link único habilitado por el docente al final del cuatrimestre.
- Modo restringido: deshabilita el tutor, deshabilita ejecución Pyodide, deshabilita copy-paste externo (best-effort, no garantizable).
- Timer visible (informativo, no bloqueante).
- Persistencia incremental cada 30s para evitar pérdida si el navegador crashea.

---

## 4. Análisis previsto

### 4.1 Validez criterial de las cinco coherencias

Para cada estudiante con respuesta completa al transfer test:
- Computar el promedio de cada una de las 5 coherencias sobre todos sus episodios del cuatrimestre (ponderado por duración del episodio).
- Correlacionar cada coherencia con score total de transfer (Spearman ρ con IC95% bootstrap).
- Reportar matriz de correlación 5x1.

Interpretación esperada:
- CT, CCD_mean, CII_stability, CII_evolution_intra deberían correlacionar positivamente con transfer (estudiantes con perfil reflexivo aprenden más).
- CCD_orphan_ratio debería correlacionar negativamente con transfer (orphan alto = baja apropiación, baja transferencia).

### 4.2 Validez criterial del árbol (3 categorías)

ANOVA / Kruskal-Wallis del score de transfer agrupado por categoría dominante de apropiación del estudiante (la que más episodios suma). η² ≥ 0.06 esperado.

### 4.3 Comparación contra grupo control

Si el piloto-2 incluye grupo control (CS24, P3), comparar distribución de scores de transfer entre experimental y control. Test de Mann-Whitney + cálculo de tamaño de efecto Cliff's δ.

### 4.4 Reporte en el paper

Sección §8.X (Validación criterial). Estos resultados operacionalizan H2 del paper. Sin este test, H2 queda declarativa.

---

## 5. Decisiones pendientes

1. **Validación de contenido**: agendar sesión con 3 docentes UTN para revisar los 5 análogos. Esfuerzo: 4-6 h sesión + 2-3 h por docente.
2. **Pilotaje**: reclutar 5-10 voluntarios. Esfuerzo: 2-3 h coordinación + 1 h ejecución cada uno.
3. **Implementación técnica**: endpoint + tabla + UI. Esfuerzo: 24-32 h.
4. **Aprobación ética**: aplicación de instrumento adicional ante comité UTN. Esfuerzo: 2-3 h redacción.
5. **Asignación de score por docente**: codificación de 5 problemas × N estudiantes. Si N=50, son 250 codificaciones. Esfuerzo: ~10 h codificación + sesión de calibración entre dos docentes para κ.

---

## 6. Referencias

- Bransford, J. D., Brown, A. L., & Cocking, R. R. (Eds.). (2000). *How People Learn: Brain, Mind, Experience, and School*. National Academy Press.
- Detterman, D. K. (1993). The case for the prosecution: Transfer as an epiphenomenon. En D. K. Detterman & R. J. Sternberg (Eds.), *Transfer on trial* (pp. 1-24). Ablex.
- Barnett, S. M., & Ceci, S. J. (2002). When and where do we apply what we learn? A taxonomy for far transfer. *Psychological Bulletin*, 128(4), 612-637.
- `informeSocra1.md` §6.5 y §9 (C1.3).
- `plan1Socra.md` CS11.
- Paper Cortez & Garis §6.1 H2 — formulación que este instrumento operacionaliza.
