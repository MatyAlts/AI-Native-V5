# governance-service

## 1. Qué hace (una frase)

Custodia los prompts versionados del tutor socrático desde un repositorio Git montado en filesystem, verificando criptográficamente que el contenido servido coincide con el hash declarado en el `manifest.yaml`.

## 2. Rol en la arquitectura

Pertenece al **plano pedagógico-evaluativo**. Materializa el componente "Servicio de gobernanza del prompt" descrito en el Capítulo 6 de la tesis (arquitectura C4 del sistema AI-Native), cuyas responsabilidades nominales son: preservar la inmutabilidad del prompt del sistema en una ventana de estudio, exponer versiones auditables (con hash SHA-256 trazable al evento CTR que lo consumió), y permitir que la re-clasificación posterior pueda recargar exactamente el prompt que estaba vigente cuando el estudiante interactuó.

Sin este servicio, `prompt_system_hash` en los eventos del CTR sería un valor opaco — con él, es una clave que permite recuperar el texto exacto del prompt desde el repo Git, bit-a-bit.

## 3. Responsabilidades

- Clonar (o aceptar un mount de) el repo Git de prompts en el path configurado por `PROMPTS_REPO_PATH` y servirlo como fuente de verdad.
- Exponer `GET /api/v1/prompts/{name}/{version}` que devuelve el contenido del prompt junto con su `hash` SHA-256 recomputado al vuelo.
- Exponer `GET /api/v1/active_configs` con el manifest global: qué versión de cada prompt está activa por tenant (overrides por tenant sobre un default).
- Exponer `POST /api/v1/prompts/{name}/{version}/verify` que recomputa el hash y lo compara contra el declarado en el `manifest.yaml` del directorio del prompt.
- Implementar **fail-loud ante hash mismatch** (RN-091): si el `manifest.yaml` declara un hash que no coincide con el contenido actual, el endpoint `/prompts/...` devuelve 500 con `"Prompt integrity compromised"`. No se sirve contenido potencialmente manipulado.
- Cachear en memoria los prompts ya cargados (`_cache: dict[(name, version), PromptConfig]`) para no re-leer el archivo en cada request.
- **Servir el prompt `tp_generator/v1.0.0`** (epic `ai-native-completion-and-byok`, [ADR-036](../adr/036-tp-gen-ia.md)): consumido por `academic-service` cada vez que se invoca `POST /api/v1/tareas-practicas/generate`. Drift conocido: el prompt declara restricciones sintácticas que Mistral respeta, pero las semánticas (no usar funciones en dificultad="basica") las rompe ocasionalmente.

## 4. Qué NO hace (anti-responsabilidades)

- **NO persiste prompts en base de datos**: la fuente de verdad es Git en filesystem. No hay DB propia. Esto es intencional — [ADR-009](../adr/009-git-fuente-prompt.md) eligió Git para que el historial de cambios, autores y firmas GPG queden fuera del alcance del operador de la plataforma.
- **NO pulla automáticamente del origen Git**: en F3 (estado actual) asume que el repo está clonado en `PROMPTS_REPO_PATH` vía init container o mount. El webhook de GitHub + verificación GPG está previsto para F5+ y no está implementado aún.
- **NO renderiza el prompt con variables**: devuelve el texto crudo. La sustitución de variables (ej. `{contexto_curso}`, `{rubrica}`) la hace [tutor-service](./tutor-service.md) al construir el mensaje final al LLM.
- **NO es el único tenedor de `prompt_system_hash`**: el hash queda embebido en cada evento del CTR al momento de abrirlo. El rol de governance es que ese hash sea **recuperable** (permite traer el prompt que le correspondió), no que sea autoritativo — el autoritativo es el evento persistido.
- **NO valida autorización**: cualquier request autenticada por api-gateway puede leer cualquier prompt. No hay scoping por tenant en las rutas (el scoping está en `manifest.yaml` → `active` map).

## 5. Endpoints HTTP

| Método | Path | Qué hace | Auth |
|---|---|---|---|
| `GET` | `/api/v1/active_configs` | Devuelve el manifest global: qué versión de cada prompt (tutor, classifier) está activa para `default` y por tenant. | Ninguna explícita (viene del gateway). |
| `GET` | `/api/v1/prompts/{name}/{version}` | Devuelve `{name, version, content, hash, path}`. 404 si no existe, 500 si el hash del manifest no matchea el computado. | Ninguna explícita. |
| `POST` | `/api/v1/prompts/{name}/{version}/verify` | Recomputa y compara; devuelve `VerifyResult` con `valid: bool`. A diferencia de GET, devuelve 200 con `valid=false` en mismatch (no 500). | Ninguna explícita. |
| `GET` | `/health`, `/health/ready` | Health real con `check_repo_path` (verifica que el directorio del repo de prompts exista y sea legible) — epic `real-health-checks`, 2026-05-04. | Ninguna. |

**Response de `GET /api/v1/prompts/tutor/v1.0.0` (happy path)**:

```json
{
  "name": "tutor",
  "version": "v1.0.0",
  "content": "Sos un tutor socrático especializado en programación universitaria...",
  "hash": "a1b2c3d4e5f6...64hex",
  "path": "prompts/tutor/v1.0.0/system.md"
}
```

El campo `hash` es **recomputado al vuelo** cada vez que se sirve el prompt (`compute_content_hash(content) → sha256(content.encode("utf-8")).hexdigest()`). El caller — típicamente [tutor-service](./tutor-service.md) — guarda ese hash en el `SessionState` y lo propaga a todos los eventos del episodio como `prompt_system_hash`.

**Response de `POST /api/v1/prompts/tutor/v1.0.0/verify` (verify OK)**:

```json
{
  "name": "tutor",
  "version": "v1.0.0",
  "valid": true,
  "computed_hash": "a1b2c3d4e5f6...64hex",
  "message": "Hash verificado correctamente"
}
```

**Response de `GET /active_configs`** (ejemplo):

```json
{
  "active": {
    "default": {
      "tutor": "v1.0.0",
      "classifier": "v1.0.0"
    },
    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa": {
      "tutor": "v1.1.0-unsl"
    }
  }
}
```

Los tenants que no aparecen en el mapa caen al `default`. La clave es el `tenant_id` (UUID en string).

## 6. Dependencias

**Depende de (infraestructura):**
- Filesystem con el repo de prompts en `PROMPTS_REPO_PATH`. El repo debe tener la estructura `{prompts_repo_path}/prompts/{name}/{version}/system.md` y opcionalmente `manifest.yaml` con los hashes declarados.

**Depende de (otros servicios):** ninguno en runtime. Es **hoja**.

**Dependen de él:**
- [tutor-service](./tutor-service.md) — al abrir cada episodio, llama `GET /api/v1/prompts/tutor/v1.0.0` (con override de env → eventos persisten `v1.1.0`) para obtener `content` + `hash` (este hash queda embebido como `prompt_system_hash` en todos los eventos CTR del episodio). Sin governance respondiendo, la apertura falla 500.
- [academic-service](./academic-service.md) — `GET /api/v1/prompts/tp_generator/v1.0.0` en el endpoint TP-gen IA ([ADR-036](../adr/036-tp-gen-ia.md)).
- [classifier-service](./classifier-service.md) — (previsto en F5+) recuperar el prompt asociado a un `classifier_config_hash` para auditorías de reproducibilidad. Hoy no hay llamada directa en runtime.

## 7. Modelo de datos

**No tiene DB propia**. La fuente de verdad es el filesystem:

```
{PROMPTS_REPO_PATH}/
├── manifest.yaml                 # active configs por tenant
└── prompts/
    └── tutor/
        ├── v1.0.0/
        │   ├── system.md         # el prompt en sí
        │   └── manifest.yaml     # hashes declarados (opcional)
        └── v1.1.0-unsl/
            ├── system.md
            └── manifest.yaml
```

**Formato del `manifest.yaml` global** (root del repo):

```yaml
active:
  default:
    tutor: v1.0.0
    classifier: v1.0.0
  aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa:
    tutor: v1.1.0-unsl
```

**Formato del `manifest.yaml` por versión** (opcional, pero habilita el fail-loud):

```yaml
files:
  system.md: a1b2c3d4e5f6...64hex   # hash SHA-256 canónico del archivo
```

El parser de YAML es **minimal** (`_declared_hash()` en `prompt_loader.py`) — lee línea a línea sin depender de PyYAML. Si el formato se complejiza (anchors, multi-line scalars), hay que introducir PyYAML como dep.

## 8. Archivos clave para entender el servicio

- `apps/governance-service/src/governance_service/services/prompt_loader.py` — `PromptLoader.load()` es el core: lee el archivo, computa SHA-256, coteja contra el manifest si existe, cachea. `compute_content_hash()` es la función que otros servicios pueden replicar para verificar localmente.
- `apps/governance-service/src/governance_service/routes/prompts.py` — los tres endpoints. Nótese la asimetría de error handling: `GET /prompts/...` sube el mismatch a 500; `POST .../verify` devuelve 200 con `valid=false`. Es intencional: GET es el consumo en caliente (tutor abriendo episodio — debe fallar duro), verify es el audit (debe devolver estado).
- `apps/governance-service/src/governance_service/config.py` — única env var relevante: `PROMPTS_REPO_PATH`.
- `ai-native-prompts/prompts/tutor/v1.0.0/system.md` — el prompt N4 mínimo sembrado en el repo (sesión 2026-04-23). Es lo que el tutor-service carga por default en dev.
- `apps/governance-service/tests/unit/test_prompt_loader.py` — cubre fail-loud ante hash mismatch (HU-038) y parseo del manifest.

**Flujo de `PromptLoader.load()`** (pseudocódigo):

```python
# apps/governance-service/src/governance_service/services/prompt_loader.py:55
def load(self, name: str, version: str) -> PromptConfig:
    # 1. Cache hit
    if (name, version) in self._cache:
        return self._cache[(name, version)]

    # 2. Read file from filesystem
    prompt_dir = self.repo_path / "prompts" / name / version
    system_file = prompt_dir / "system.md"
    if not system_file.exists():
        raise FileNotFoundError(f"Prompt {name}/{version} no existe en {self.repo_path}")
    content = system_file.read_text(encoding="utf-8")

    # 3. Compute hash
    computed_hash = sha256(content.encode("utf-8")).hexdigest()

    # 4. If manifest.yaml declares a hash, verify it matches
    manifest_path = prompt_dir / "manifest.yaml"
    if manifest_path.exists():
        declared = self._declared_hash(manifest_path, "system.md")
        if declared and declared != computed_hash:
            raise ValueError(
                f"Hash mismatch en {name}/{version}/system.md: "
                f"declarado={declared[:12]}... computado={computed_hash[:12]}... "
                f"(posible manipulación)"
            )

    # 5. Cache and return
    config = PromptConfig(name, version, content, computed_hash, str(system_file))
    self._cache[(name, version)] = config
    return config
```

**Asimetría GET vs POST /verify — cómo se reporta el mismatch**:

- `GET /prompts/tutor/v1.0.0` con hash mismatch:

  ```
  HTTP/1.1 500 Internal Server Error
  { "detail": "Prompt integrity compromised: Hash mismatch en tutor/v1.0.0/system.md: ..." }
  ```

  El 500 es **correcto** para el consumo caliente — si tutor-service intenta abrir un episodio y el prompt está comprometido, el episodio NO debe abrirse. Propagarle un 200 con contenido potencialmente manipulado rompe la auditabilidad.

- `POST /prompts/tutor/v1.0.0/verify` con el mismo mismatch:

  ```json
  {
    "name": "tutor",
    "version": "v1.0.0",
    "valid": false,
    "computed_hash": "",
    "message": "Hash mismatch en tutor/v1.0.0/system.md: declarado=... computado=... (posible manipulación)"
  }
  ```

  200 con `valid=false` porque el endpoint existe **para auditoría**. El auditor necesita saber el estado sin que el servidor le oculte el mismatch detrás de un 500.

## 9. Configuración y gotchas

**Env vars críticas** (`apps/governance-service/src/governance_service/config.py`):

- `PROMPTS_REPO_PATH` — **default `/var/lib/platform/prompts`** (no existe en Windows). Hay que setearla explícita en dev.

**Puerto de desarrollo**: `8010`.

**Gotchas específicos** (documentados en CLAUDE.md "Gotchas de entorno"):

- **Setear `PROMPTS_REPO_PATH` en dev**: el default `/var/lib/platform/prompts` no existe en Windows. El `.env.example` ya declara la variable correcta (F14 cerró la deuda histórica del template, ver "Histórico" abajo). En dev local:

  ```bash
  PROMPTS_REPO_PATH="$(pwd)/ai-native-prompts" \
    uv run uvicorn governance_service.main:app --port 8010 --reload
  ```

- **Bootstrap del tutor depende de governance**: si el prompt no existe en disco o el path está mal, `POST /api/v1/episodes` del tutor-service devuelve **500** con stack trace:

  ```
  httpx.HTTPStatusError: Client error '404 Not Found' for url
  'http://127.0.0.1:8010/api/v1/prompts/tutor/v1.0.0'

  File ".../tutor_service/services/clients.py", line 54, in get_prompt
      r.raise_for_status()
  File ".../tutor_service/services/tutor_core.py", line 94, in open_episode
      prompt = await self.governance.get_prompt(...)
  ```

  Dos condiciones deben cumplirse simultáneamente para que arranque: env var seteada, y directorio físico con prompt sembrado (`{PROMPTS_REPO_PATH}/prompts/tutor/v1.0.0/system.md`). `make init` **no** auto-crea el directorio.

- **Parseo YAML minimal**: no usa PyYAML. El parser (`_declared_hash()`) lee línea por línea buscando bloques `files:` y pares `filename: hash`. Limitaciones:
  - No soporta anchors ni aliases YAML (`&foo`, `*foo`).
  - No soporta multi-line scalars (`|`, `>`).
  - Indentación tiene que ser consistente (asume `files:` top-level, pares con 2 espacios de indent).
  Deliberado para no agregar dependencia, pero si el manifest crece en complejidad, hay que migrar a PyYAML.

- **Cache en memoria no se invalida**: si editás `system.md` en disco con el servicio corriendo, el cache retiene la versión vieja. Hay que reiniciar el proceso (`kill + uv run uvicorn ...`). Para dev está ok; para prod + webhook de Git va a requerir un `reload()` del cache al recibir el push event.

- **Divergencia entre `manifest.yaml` y `tutor-service.config.default_prompt_version`**: el `manifest.yaml` (parseado por `PromptLoader.active_configs()`, expuesto en `GET /api/v1/active_configs`) declara la versión activa para frontends/dashboards. **Pero el tutor-service NO consulta ese manifest en runtime** — usa `apps/tutor-service/src/tutor_service/config.py:default_prompt_version` directo. Si solo se cambia uno, frontends ven una versión y el CTR registra otra. El test `apps/tutor-service/tests/unit/test_config_prompt_version.py::test_manifest_yaml_existe_y_se_parsea` cubre la consistencia, pero es responsabilidad operacional en cualquier rotación futura.

- **Sin health check real**: el endpoint `/health` no valida que el repo exista ni que el prompt default sea legible. Si falla el mount en K8s, el servicio arranca y responde OK — el error recién se ve cuando un cliente llama a `/prompts/...`. Contraste con [ctr-service](./ctr-service.md) que sí tiene health real.

- **No hay endpoint para listar prompts disponibles**: el caller tiene que conocer el `{name, version}` por convención (`"tutor"` + `"v1.0.0"`). Si se sembran versiones nuevas en disco, el descubrimiento es manual — hay que actualizar el `default_prompt_version` del tutor-service o el `active_configs` del manifest.

## 10. Relación con la tesis doctoral

El governance-service es el tenedor operativo del **principio de auditabilidad del prompt** del Capítulo 6 de la tesis. La afirmación específica que materializa es:

> "El texto del prompt del sistema vigente en cada interacción debe ser recuperable bit-a-bit, para que las re-clasificaciones posteriores del episodio — potencialmente con profiles nuevos — operen sobre el estado de configuración real, no sobre una versión reconstruida a posteriori."

Esto sostiene el experimento de A/B de profiles (HU-118, RN-111): el investigador arma un JSON con gold standard + dos profiles candidatos y corre `/api/v1/analytics/ab-test-profiles`. El κ resultante es interpretable **sólo si** todos los episodios del gold se clasificaron contra el mismo prompt — el que estaba vigente cuando el estudiante trabajó. `prompt_system_hash` en el evento lo identifica; este servicio lo recupera.

[ADR-009](../adr/009-git-fuente-prompt.md) documenta por qué Git y no DB. Tres razones resumidas:

1. **Historial con autoría verificable**: cada cambio al prompt queda en un commit con autor (docente responsable), timestamp (inmutable una vez pushed), y mensaje (explicación del cambio). Una DB con campo `updated_at`/`updated_by` da menos garantía — la línea de cambios es editable.
2. **Firmas GPG de commits** (previsto F5+, no implementado hoy): si el convenio del piloto exige atribución criptográfica de quién modificó el prompt, Git + GPG lo cubren nativamente. Una DB requeriría una tabla paralela `audit_log` + firmas externas.
3. **Mutabilidad fuera del alcance del operador**: un admin de la plataforma con `psql` puede modificar cualquier DB. Modificar un repo Git `push`eado (especialmente con protected branches en GitHub) requiere permisos distintos y deja rastro de PR.

El mismo razonamiento que en `reglas.md` RN-091 (fail-loud ante hash mismatch) y RN-092: el servicio no sirve contenido que no pueda demostrar íntegro.

**¿Por qué `prompt_system_hash` se replica en cada evento del CTR, y no sólo en `episodio_abierto`?** Defensa en profundidad contra dos ataques distintos:

1. **Tampering del `Episode`**: si alguien modifica `episodes.prompt_system_hash` por SQL directo, los eventos siguen apuntando al hash original. El `IntegrityChecker` al recomputar cada evento detecta la discrepancia (el hash está embebido en el payload que forma parte del `self_hash`).
2. **Tampering del evento `episodio_abierto`**: si se modifica el `payload` del seq=0, el `self_hash` de ese evento cambia, y eso rompe la cadena en seq=1 (que depende de `chain_hash` del 0).

La redundancia no es accidental — RN-040 de `reglas.md` la exige explícitamente.

**Gap sabido**: las firmas GPG de los commits del repo de prompts están previstas en [ADR-009](../adr/009-git-fuente-prompt.md) como F5+; hoy (F9) el servicio no verifica firmas, sólo hashes de contenido. La integridad **del contenido** está cubierta — la atribución de autoría del cambio queda en el historial Git sin verificación criptográfica del autor.

## 11. Estado de madurez

**Tests** (1 archivo):
- `tests/unit/test_prompt_loader.py` — cubre HU-038 (fail-loud ante hash mismatch), carga exitosa con y sin manifest, parser de `_declared_hash()` con comentarios y distintos formatos de quoting (`"hash"`, `'hash'`, `hash` sin quotes).

**Known gaps**:
- Sin tests de los endpoints HTTP (`routes/prompts.py`): la lógica está cubierta a través del loader, pero la asimetría GET=500 / verify=200 no tiene test de integración.
- Cache en memoria sin invalidación (gotcha §9).
- Webhook de Git + verificación GPG (ADR-009 F5+) no implementado.
- `/health` es stub — no valida el repo. Parte de la deuda general descrita en CLAUDE.md "Brechas conocidas: Health checks reales".
- Parser YAML minimal — no soporta features avanzados del formato.
- Sin endpoint `GET /prompts` para listar prompts disponibles.
- Drift declarado entre `manifest.yaml` (consumido por frontends/dashboards via `/active_configs`) y `tutor-service.config.default_prompt_version` (consumido por el tutor en runtime). Test cubre consistencia; rotación operacional requiere cambiar ambos.

**Fase de consolidación**:
- F3 — implementación del PromptLoader con verificación de hash (`docs/F3-STATE.md`).
- F5 previsto — webhook + GPG, no iniciado al momento de esta documentación.
- 2026-05-04 (epic `ai-native-completion-and-byok`) — prompt `tp_generator/v1.0.0` agregado al repo de prompts ([ADR-036](../adr/036-tp-gen-ia.md)).
- 2026-05-04 (epic `real-health-checks`) — `/health/ready` real con `check_repo_path`.

**Operación recomendada del repo de prompts** (no documentada formalmente en ADR — convención operativa del piloto):

1. Cambios al prompt van en **nuevas versiones** (ej. `v1.1.0-unsl` al lado de `v1.0.0`), no in-place. El activo se cambia editando el `manifest.yaml` global.
2. Antes de activar una versión, correr `POST /prompts/{name}/{version}/verify` para confirmar que el manifest interno matchea el contenido.
3. Los episodios **ya abiertos** siguen con la versión que estaba vigente al momento de `open_episode` — `SessionState.prompt_system_version` se congela en memoria, y el hash correspondiente va en todos los eventos. Cambiar el activo mientras un episodio está abierto no afecta a ese episodio.
4. Al rotar a una versión nueva, actualizar `default_prompt_version` en el `Settings` de [tutor-service](./tutor-service.md) (o el `active_configs` por tenant) y reiniciar el tutor — el governance no notifica.

## 12. Histórico

- **F14 (2026-04-28) — typo `GOVERNANCE_REPO_PATH` en `.env.example`**: el template declaraba `GOVERNANCE_REPO_PATH=./ai-native-prompts` pero el código siempre leyó `PROMPTS_REPO_PATH`. La consecuencia operativa era que un `.env` copiado del template no levantaba el servicio en dev (caía al default `/var/lib/platform/prompts`, inexistente en Windows). F14 cerró la deuda: `.env.example:57` ahora declara `PROMPTS_REPO_PATH`. Quien tenga un `.env` viejo debe re-cherry-pickearlo. El parity test `tests/test_config.py::test_env_example_var_matches_settings_field` bloquea regresión.
