# Plataforma AI-Native con Trazabilidad Cognitiva N4

Monorepo de la plataforma que ejecuta el estudio piloto de la tesis doctoral de
**Alberto Alejandro Cortez** (UNSL) — *"Modelo AI-Native con Trazabilidad
Cognitiva N4 para la Formación en Programación Universitaria"*, dentro de un PID
con financiamiento académico (Línea 5, UTN-FRM × UTN-FRSN).

No es una demo. **Hay un piloto académico real corriendo en producción** con
alumnos generando trazas todos los días. Eso cambia lo que significa romper algo
acá: un deploy que falla no rompe un entorno, interrumpe una cursada.

---

## Índice

1. [Qué hace la plataforma](#qué-hace-la-plataforma)
2. [Estado del repo](#estado-del-repo)
3. [Arquitectura](#arquitectura)
4. [Arranque rápido](#arranque-rápido)
5. [Instalación completa](#instalación-completa)
6. [Los servicios, uno por uno](#los-servicios-uno-por-uno)
7. [Tests](#tests)
8. [Estructura del repo](#estructura-del-repo)
9. [Deploy](#deploy)
10. [Decisiones de arquitectura](#decisiones-de-arquitectura)
11. [Seguridad](#seguridad)
12. [Cosas que muerden](#cosas-que-muerden)
13. [Cómo contribuir](#cómo-contribuir)
14. [Licencia y autoría](#licencia-y-autoría)

---

## Qué hace la plataforma

Tres piezas, y las tres tienen que estar para que el claim académico se sostenga.

### 1. Tutor socrático

La IA **no da respuestas: hace preguntas**. Cuatro movimientos platónicos —
ironía, mayéutica, elenchos, aporía — sobre un prompt versionado en
`ai-native-prompts/`, servido por el governance-service y nunca hardcodeado en
el código.

> ⚠️ **El prompt del tutor tiene coautoría con Ana Garis y no se toca sin
> consultar.** Al portar mejoras entre forks se copia byte a byte.

### 2. Trazabilidad cognitiva N4

Cada interacción del alumno se clasifica en cuatro niveles de apropiación
(N1 Lectura · N2 Exploración · N3 Experimentación · N4 Apropiación), sobre un
modelo derivado de Bloom + SAMR. La clasificación es **reproducible bit a bit**:
misma entrada, misma etiqueta, con el hash de configuración del clasificador
guardado junto a cada resultado.

### 3. CTR — Cadena de Trazabilidad de Registros

Cada evento pedagógico se firma SHA-256 en una cadena append-only, con
single-writer por partición. **Es la pieza que hace defendible la tesis**: si la
cadena se corrompe, no se cae una feature, se cae el claim académico central.

---

## Estado del repo

Piloto en producción: comisión de Programación 1 · Pre-Universitario, con
actividad real de alumnos generando CTR.

| Métrica | Valor |
|---|---|
| Servicios Python | **12 directorios → 13 procesos** (ver nota abajo) |
| Frontends React | **4** (student, teacher, admin, landing) |
| Packages compartidos | **7** |
| Migraciones Alembic | **47** (academic 30 · evaluation 8 · classifier 5 · content 2 · ctr 2) |
| ADRs | **63** |
| Prompt activo del tutor | **v1.3.0** (`apps/tutor-service/.../config.py`) |
| Workflows de CI | 3 (`ci.yml`, `deploy.yml`, `e2e-smoke.yml`) |

> **Por qué 12 directorios pero 13 procesos.** `execution-service` se despliega
> **dos veces desde el mismo código**: el servicio de orquestación en `:8013`
> (`Dockerfile` → `main:app`) y el **runner** en `:8015` (`Dockerfile.runner` →
> `runner_main:app`), que es el único componente del stack con el socket de
> Docker montado. Están separados a propósito — ver [ADR-060](docs/adr/).
> Contarlos como uno solo es de dónde vienen los "11 servicios" de las versiones
> viejas de este archivo.

<details>
<summary><b>Cómo re-verificar estos números (leelo antes de confiar en ellos)</b></summary>

Este README ya envejeció mal una vez: llegó a declarar 11, 12 y 14 apps en tres
líneas distintas, 17 migraciones cuando había 47, 43 ADRs cuando había 63,
el prompt en v1.2.0 cuando corría v1.3.0, y dos servicios "preservados en disco"
que ya no existían. **Un número viejo no avisa que es viejo**, así que acá está
cómo recontarlos:

```bash
ls -d apps/*/ | grep -v web-        | wc -l   # servicios Python
ls -d apps/web-*/                   | wc -l   # frontends
ls -d packages/*/                   | wc -l   # packages
fd -e md . docs/adr                 | wc -l   # ADRs
find apps -path '*versions*' -name '*.py' -not -name '__*' | wc -l   # migraciones
rg 'default_prompt_version' apps/tutor-service/src/*/config.py       # prompt activo
```

Hay además un detector de drift para los claims numéricos del `CLAUDE.md`:

```bash
make check-claude-md
```

</details>

---

## Arquitectura

```
   ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐
   │ web-student│  │ web-teacher│  │  web-admin │  │ web-landing│
   │  :5175     │  │  :5174     │  │   :5173    │  │   :5172    │
   │ Monaco +   │  │ TPs, rúbr. │  │ Institución│  │ Comercial  │
   │ Pyodide    │  │ correcciones│ │ + auditoría│  │            │
   └──────┬─────┘  └──────┬─────┘  └──────┬─────┘  └────────────┘
          │               │               │
          └───────────────┼───────────────┘
                          ▼
                 ┌──────────────────┐        ┌──────────────┐
                 │   api-gateway    │◄───────┤    Clerk     │
                 │      :8000       │        │  (auth real) │
                 │ ÚNICA puerta ext.│        └──────────────┘
                 └────────┬─────────┘
                          │
   ┌────────┬─────────┬───┴─────┬──────────┬──────────┬─────────┐
   ▼        ▼         ▼         ▼          ▼          ▼         ▼
┌───────┐┌────────┐┌───────┐┌─────────┐┌────────┐┌────────┐┌─────────┐
│tutor  ││academic││ ctr   ││classifier││content ││governan││evaluation│
│ :8006 ││ :8002  ││ :8007 ││  :8008  ││ :8009  ││ :8010  ││  :8004  │
│SSE    ││TPs +   ││cadena ││  N1-N4  ││RAG     ││prompts ││entregas │
│socrát.││Casbin  ││SHA-256││reproduc.││pgvector││versionad││+ correc.│
└───┬───┘└────────┘└───┬───┘└─────────┘└────────┘└────────┘└─────────┘
    │                  │
    ▼                  ▼                    ┌───────────┐  ┌──────────┐
┌──────────┐   ┌──────────────┐             │ analytics │  │integrity-│
│ai-gateway│   │ 8 ctr-workers│             │   :8005   │  │attestat. │
│  :8011   │   │single-writer │             │  Kappa,   │  │  :8012   │
│BYOK multi│   │ por partición│             │longitudin.│  │  Ed25519 │
│ provider │   └──────────────┘             └───────────┘  └──────────┘
└──────────┘
                    ┌──────────────────┐        ┌──────────────────┐
                    │ execution-service│───────▶│ execution-runner │
                    │      :8013       │        │      :8015       │
                    │  cuotas, cola    │        │ ÚNICO con el     │
                    │  fallan cerradas │        │ socket de Docker │
                    └──────────────────┘        └──────────────────┘

  ┌─────────────────────────────────────────────────────────────────┐
  │ Postgres — 4 bases lógicas, sin joins cross-base, RLS forzado   │
  │   academic_main · ctr_store · classifier_db · content_db        │
  │ Redis (sesiones + streams) · MinIO (artefactos + backups)       │
  │ Prometheus + Grafana + Loki + OpenTelemetry                     │
  └─────────────────────────────────────────────────────────────────┘
```

**Tres invariantes que el diagrama no muestra y conviene tener presentes:**

- **El api-gateway es la única puerta externa.** Ningún frontend habla directo
  con un servicio interno. Un servicio interno alcanzable desde afuera es un
  incidente, no una optimización.
- **Todo LLM pasa por el ai-gateway.** Ningún servicio llama a un proveedor por
  su cuenta: así el BYOK, el conteo de costo y el cambio de proveedor viven en
  un solo lugar.
- **El runner es el único proceso con el socket de Docker**, que es
  root-equivalente sobre el host. Por eso sólo acepta `{source_code, stdin}` y
  su token no es higiene: es el candado.

Detalle completo en [`docs/architecture.md`](docs/architecture.md).

---

## Arranque rápido

Para ver la plataforma andando sin montar el stack entero a mano:

```bash
# Terminal 1 — proxy LLM gratis (la primera vez pide login con tu cuenta GitHub)
npx -y copilot-api@latest start --port 4141

# Terminal 2 — el stack
bash scripts/start-video-ready.sh
```

Deja backends + ctr-workers + frontends arriba, con el tutor activo y un
ejercicio canónico ya seedeado. Si algo falla, seguí con la instalación completa.

---

## Instalación completa

**Requisitos** (las versiones importan, están fijadas en `package.json` y
`pyproject.toml`):

| Herramienta | Versión |
|---|---|
| Python | `>=3.12,<3.13` |
| Node | `>=20` |
| pnpm | `9.12.0` |
| uv | reciente |
| Docker | compose v2 |
| make | — |

> **Windows**: `winget install ezwinports.make`, reiniciar Git Bash, y trabajar
> desde Git Bash o WSL.

### 1. Bootstrap (sólo la primera vez)

```bash
make init      # infra Docker + dependencias + migraciones + seed Casbin
```

### 2. Infraestructura

```bash
make dev-bootstrap
```

| Servicio | URL | Credenciales |
|---|---|---|
| PostgreSQL | `localhost:5432` | postgres / postgres |
| Redis | `localhost:6379` | — |
| MinIO | http://localhost:9001 | minioadmin / minioadmin |
| Grafana | http://localhost:3000 | admin / admin |
| Prometheus | http://localhost:9090 | — |

### 3. Frontends

```bash
make dev
```

> ⚠️ **`make dev` levanta SÓLO los frontends Vite.** Los servicios Python van
> aparte (paso 4). Sin ellos los frontends renderizan pero toda llamada a la API
> falla, y el síntoma no dice que falten backends.

### 4. Servicios Python

Cada uno en su propia terminal y **desde la raíz del repo** — no desde
`apps/<servicio>/`, porque `pydantic-settings` busca el `.env` relativo al
directorio actual y sin él arrancan con defaults que no son los que creés.

El mínimo para que la app haga algo: **api-gateway + academic-service +
tutor-service + ctr-service + governance-service**.

### 5. Verificar

```bash
make status         # qué está arriba
make check-health   # /health de cada servicio
```

---

## Los servicios, uno por uno

| Servicio | Puerto | Qué resuelve |
|---|---|---|
| **api-gateway** | 8000 | Única puerta externa. Valida el JWT y propaga identidad. Ningún frontend habla con otra cosa. |
| **academic-service** | 8002 | Universidad → comisión → TP → ejercicio. Autorización con Casbin. Es el dueño del modelo académico. |
| **evaluation-service** | 8004 | Entregas, calificaciones y correcciones asistidas. La corrección es **sugerencia diagnóstica, no acreditativa**: vive en su propia tabla y no escribe la nota. |
| **analytics-service** | 8005 | Kappa, progresión longitudinal, alertas por z-score contra la cohorte, con gate de privacidad por tamaño de grupo. |
| **tutor-service** | 8006 | El orquestador socrático. Streaming SSE incremental — antes bufferizaba y el alumno miraba una pantalla quieta. |
| **ctr-service** | 8007 | La cadena SHA-256 append-only. 8 particiones Redis, **un solo writer por partición**. |
| **classifier-service** | 8008 | Clasificación N1–N4 reproducible bit a bit. |
| **content-service** | 8009 | Materiales + RAG sobre pgvector, con chunking estratificado. |
| **governance-service** | 8010 | Sirve los prompts versionados con su manifest y su hash. Ningún prompt vive como string en el código. |
| **ai-gateway** | 8011 | Proxy LLM multi-proveedor con BYOK (AES-256-GCM), resolución jerárquica materia → tenant → fallback. |
| **integrity-attestation** | 8012 | Firmas Ed25519 externas post-cierre. En el piloto vive en un VPS aparte, a propósito: una atestación firmada por la misma máquina que genera el dato no atestigua nada. |
| **execution-service** | 8013 | Ejecución server-side de Java. Cuotas que **fallan cerradas**. |
| **execution-runner** | 8015 | El que realmente corre el código, en Docker sin privilegios. Único con el socket. |

---

## Tests

```bash
make test            # suite completa: Python + frontends
make test-fast       # sólo Python — iteración rápida
make test-rls        # aislamiento multi-tenant contra Postgres real
make test-adversarial # tests adversariales contra el tutor
make test-smoke      # smoke E2E de API contra un stack ya levantado
make test-sin-stack  # smoke que no necesita stack (~8s)
make test-e2e        # Playwright (requiere servicios + frontends + seed)
```

**Una regla del proyecto que no es negociable: un test que no se vio fallar no
prueba nada.** Cada test nuevo se verifica **por reversión** — se rompe a
propósito lo que cubre y se confirma que se pone en rojo. Este repo ya tuvo dos
veces el mismo modo de falla: lógica extraída, testeada y con cobertura, y el
cable que la conecta al endpoint sin probar por nadie.

---

## Estructura del repo

```
.
├── apps/
│   ├── api-gateway/              # única puerta externa (JWT + ROUTE_MAP)
│   ├── academic-service/         # modelo académico + Casbin
│   ├── analytics-service/        # Kappa, longitudinal, alertas
│   ├── tutor-service/            # orquestador socrático (SSE)
│   ├── ctr-service/              # cadena SHA-256 append-only
│   ├── classifier-service/       # árbol N1-N4 reproducible
│   ├── content-service/          # materiales + RAG pgvector
│   ├── governance-service/       # prompts versionados
│   ├── ai-gateway/               # proxy LLM + BYOK
│   ├── evaluation-service/       # entregas + corrección
│   ├── integrity-attestation-service/
│   ├── execution-service/        # :8013 y :8015 (Dockerfile + Dockerfile.runner)
│   ├── web-student/              # Monaco + Pyodide + chat SSE
│   ├── web-teacher/              # TPs, rúbricas, correcciones
│   ├── web-admin/                # institución + auditoría + BYOK
│   └── web-landing/              # comercial (paleta propia a propósito)
│
├── packages/
│   ├── contracts/                # schemas + hashing canónico
│   ├── observability/            # OTel + structlog + health checks
│   ├── platform-ops/             # privacidad, Kappa, longitudinal, cripto
│   ├── ctr-client/               # cliente tipado del ctr-service
│   ├── ui/                       # design system compartido + tokens
│   ├── test-utils/               # helpers de testing
│   └── auth-client/              # ⚠️ Keycloak — CÓDIGO MUERTO, cero imports.
│                                 #    La auth real es Clerk, montada en cada main.tsx
│
├── ai-native-prompts/            # prompts versionados con manifest y hash
├── infrastructure/               # compose dev/prod, Dockerfiles, nginx
├── ops/                          # manifests K8s + dashboards Grafana
├── docs/
│   ├── adr/                      # 63 ADRs numerados
│   ├── architecture.md
│   ├── servicios/                # un .md por servicio
│   ├── specs/ research/ phases/ pilot/
│   └── EASYPANEL-DEPLOY.md       # el deploy real
├── openspec/                     # changes y specs vivos del ciclo OPSX
├── scripts/                      # migrate-all, backup, seeds, verificadores
├── CLAUDE.md                     # invariantes operativas (fuente de verdad)
├── CONTRIBUTING.md
└── Makefile
```

---

## Deploy

**EasyPanel**, y la rama que deploya es **`main`**. El detalle vive en
[`docs/EASYPANEL-DEPLOY.md`](docs/EASYPANEL-DEPLOY.md); acá van las cuatro
reglas que ya costaron un incidente cada una:

1. **Un servicio por vez.** La RAM del host es justa y deployar dos en paralelo
   voltea al vecino.
2. **Nunca redeployar `ctr-service` ni `tutor-service` en caliente** con alumnos
   trabajando. El primero corta la cadena, el segundo corta la clase.
3. **La única forma de saber qué corre en producción es leer el commit
   desplegado de cada servicio.** No la documentación, no esta tabla, no la nota
   del proyecto. Ya pasó que un servicio estuviera doce días atrás de lo que
   todos creían, y nadie lo notó porque nadie miraba.
4. **Después de crear un servicio en EasyPanel, borrarle el dominio público que
   se asigna solo.** Dos servicios internos quedaron publicados en internet
   así, uno de ellos el que tiene el socket de Docker.

---

## Decisiones de arquitectura

63 ADRs en [`docs/adr/`](docs/adr/). Las que más explican por qué el código es
como es:

| ADR | Decisión |
|---|---|
| **ADR-001** | Multi-tenant con RLS forzado a nivel de base. |
| **ADR-047** | `Ejercicio` como entidad de primera clase con UUID propio, reusable entre TPs por tabla N:M. |
| **ADR-048** | Schema pedagógico PID-UTN: banco socrático N1-N4, misconceptions con probabilidad, anti-patrones, pistas por nivel. |
| **ADR-049** | El `ejercicio_id` viaja en el payload del CTR desde el día cero. |
| **ADR-060** | Ejecución de código en Docker sin privilegios, con el runner aislado como único portador del socket. |

**Por qué el `Ejercicio` es entidad propia y no un JSONB embebido** — es la
decisión que sostiene el claim científico. Antes, el "Hola Mundo" del TP1 de la
comisión A era literalmente otro objeto que el de la comisión B: la unidad de
análisis terminaba siendo la TP, que cambia entre cohortes, en vez del estímulo,
que debería ser estable. Con el ejercicio como entidad, el piloto del
cuatrimestre siguiente corre **los mismos 25 ejercicios** y las trayectorias
cognitivas se comparan sobre el mismo estímulo. Eso es lo que convierte al
piloto en ciencia reproducible.

---

## Seguridad

Lo que hay que saber antes de tocar nada:

- **Ningún secreto se commitea, y ninguno se escribe en un documento.** Si hay
  que referenciar una credencial, se nombra dónde vive (variable de entorno,
  gestor de claves), nunca su valor.
- **La corrección con IA no escribe la nota.** Vive en su propia tabla, sin
  endpoint de "aplicar". Es una sugerencia que el docente lee. Esa separación es
  lo que la hace defendible.
- **La aritmética no se delega al modelo.** El LLM devuelve puntaje y
  justificación *por criterio*; la suma la hace Python. El JSON Schema que viaja
  al gateway ni siquiera admite un campo de total — lo que el esquema no acepta,
  el modelo no lo manda. Ya pasó lo contrario con un motor externo: devolvió 87
  donde correspondían ~61.
- **Si el modelo no respeta la rúbrica, no hay nota**: `error_code` y la
  calificación en `NULL`. Completar un criterio faltante con un cero sería
  ponerle un número a algo que nadie evaluó.
- **F15** (corrección asistida de otro producto) **no se toca**: es de
  active-ia, otro negocio.

Para reportar una vulnerabilidad: abrir un issue **sin detalles explotables** y
contactar a los mantenedores por privado.

---

## Cosas que muerden

Cada una costó horas de debug o directamente un incidente.

**`"El LLM devolvió JSON inválido"` casi nunca es el prompt — es la respuesta
truncada.** El JSON estaba bien formado y cortado a la mitad, justo en el techo
de `max_tokens`. Y `max_tokens` tiene **dos** techos: el del caller y el que el
ai-gateway valida en su schema de entrada, que corta **antes** de hablar con el
proveedor y devuelve un 422 que el caller ve como 502. Para subirlo hay que
subir primero el del ai-gateway **y deployarlo antes** que el caller.

**Todo dato que venga de un LLM se normaliza en la frontera.** El borrador del
wizard viaja como `dict[str, Any]`, así que TypeScript no valida nada: un campo
con el tipo equivocado no da error de compilación, da un `TypeError` en runtime
que voltea la vista entera. El render se escribe defensivo además de normalizar,
porque hay un segundo borde sin normalizar: el JSON que el docente pega a mano.

**Un 502 con la pantalla de EasyPanel no significa que el servicio esté caído.**
EasyPanel intercepta cualquier 502 que pase por su proxy y lo reemplaza con su
propio HTML, incluso cuando el 502 lo generó la app a propósito. Los logs del
contenedor son la fuente de verdad, no la pantalla.

**`Implementar` recrea el contenedor pero no siempre cambia la imagen.** Un
deploy que tarda un segundo es puro caché. La verdad no está en el log del
deploy sino adentro del contenedor.

**El cache-bust del Dockerfile de frontends va en los DOS stages.** El builder
recompila bien, pero los `COPY --from=builder` del stage de nginx salen
`CACHED` y sirven el bundle viejo. En el log del build esos `COPY` tienen que
decir `DONE`, nunca `CACHED`.

**Verificá el código en los chunks, no en `index.js`.** Con code-splitting cada
vista vive en su propio chunk lazy; buscar un string en el bundle de entrada da
falso negativo.

---

## Cómo contribuir

Ver [`CONTRIBUTING.md`](CONTRIBUTING.md). Lo esencial:

- Ramas `feat/*` o `fix/*` sobre `main`, integradas por PR.
- **Conventional commits.**
- Lint y typecheck antes de abrir el PR: `make lint` y `make typecheck`.
- Un test nuevo se verifica por reversión. Si no lo viste fallar, no sabés qué
  cubre.
- Los cambios que tocan el prompt del tutor, la cadena CTR o el clasificador
  necesitan una conversación antes del código: los tres sostienen el claim
  académico.

> ⚠️ **`main` no tiene protección de rama** — sin required reviews, sin required
> status checks, sin restricción de push. Se puede mergear con el CI en rojo o
> forzar un push sobre producción. Que sea posible no lo hace aceptable.

---

## Licencia y autoría

Copyright © 2026 Alberto Alejandro Cortez. Licencia por definir según acuerdo
con la dirección de tesis y las universidades participantes — ver
[`LICENSE`](LICENSE).

**Cortez** es el doctorando y autor principal. La implementación se desarrolla
en colaboración, sin separación rígida entre frontend y backend. El prompt del
tutor tiene **coautoría con Ana Garis**.

Instituciones involucradas: **UNSL** (doctorado y piloto académico),
**UTN-FRM** y **UTN-FRSN** (PID Línea 5).
