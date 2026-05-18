# ADR-009 — Git como fuente de verdad del prompt versionado

- **Estado**: Aceptado
- **Fecha**: 2026-04
- **Deciders**: Alberto Cortez, director de tesis
- **Tags**: governance, tesis, criptografía

## Contexto y problema

El prompt del tutor socrático es una pieza **central de la tesis**: define cómo el sistema interactúa con los estudiantes, y cambios en él afectan directamente las clasificaciones del CTR. La tesis exige:

1. **Reproducibilidad**: dado un episodio clasificado, se debe poder reconstruir qué prompt estaba activo en ese momento.
2. **Auditabilidad**: quién cambió qué, cuándo, y por qué.
3. **Integridad**: nadie puede modificar el prompt "en caliente" sin que quede registro.
4. **Firma digital**: cambios al prompt deben ser firmados por una persona identificada.

Además, distintas universidades pueden tener versiones MINOR del prompt (ajustes de tono, ejemplos) pero el MAJOR es global.

## Opciones consideradas

### Opción A — Prompt en DB con tabla versionada
Simple. Pero un SQL inyectado o un bug podría modificar el prompt sin evidencia firme. La DB no firma criptográficamente.

### Opción B — Prompt en archivo YAML desplegado con el servicio
Versión ligada al deploy. Pero un hotfix para cambiar el prompt requiere redeploy completo.

### Opción C — Repositorio Git separado con commits firmados GPG
`ai-native-prompts/` como repo propio. Cada cambio = commit firmado. `governance-service` clona el repo, verifica firma, expone prompt + hash a los demás servicios.

### Opción D — Blockchain / Hyperledger
Overkill. Git ya provee inmutabilidad histórica con hashes encadenados.

## Decisión

**Opción C — Repositorio Git separado con GPG signing.**

Estructura del repo `ai-native-prompts`:

```
ai-native-prompts/
├── prompts/
│   └── tutor/
│       ├── v1.0.0/
│       │   ├── system.md          # prompt base del sistema
│       │   ├── jailbreak_rules.md # reglas regex de pre-check
│       │   ├── invariants.yaml    # lo que no puede removerse en MINOR
│       │   └── CHANGELOG.md
│       ├── v1.1.0-unsl/           # MINOR específico UNSL
│       └── manifest.yaml          # qué versiones son activas por tenant
├── reference_profiles/
│   └── cs1_easy/v1.0.0.yaml
├── classifier_configs/
│   └── v1.0.0.yaml
└── .gitconfig                     # exige commit.gpgSign = true
```

El `governance-service`:

1. Clona el repo al arrancar y después por webhook.
2. Verifica que todos los commits del HEAD estén firmados con GPG keys del keyring del equipo.
3. Computa `hash = SHA-256(contenido)` de cada prompt/config activo.
4. Expone API `GET /active_configs` y `GET /prompt/{name}/{version}`.
5. Todos los demás servicios verifican al arranque que el hash declarado en `/active_configs` coincide con el hash recomputado del contenido (**fail-loud**: si no coincide, pod no pasa `/readiness`).

Cambios al prompt:

- **MAJOR**: requiere aprobación de director de tesis + re-validación Kappa.
- **MINOR**: personalización por tenant, validada contra `invariants.yaml`.
- **PATCH**: correcciones menores.

## Consecuencias

### Positivas
- Git provee historial inmutable con hashes encadenados.
- GPG signing garantiza autoría de cada cambio.
- Si alguien modifica el prompt en runtime sin pasar por Git, el hash no coincide y el servicio se niega a operar.
- Reproducibilidad total: dado un `prompt_system_hash` en el CTR, se puede checkoutear exactamente ese estado del repo.
- Changelog natural con `git log`.

### Negativas
- Complejidad operacional: manejar GPG keys, configurar signing en CI si hace falta automación.
- `governance-service` debe tener acceso de lectura al repo en producción (credencial de deploy).
- Requiere disciplina del equipo: nunca modificar prompt directo en runtime.

### Neutras
- Migración futura a otro sistema de governance (ej. ConfigMap firmado, vault con audit trail) es viable manteniendo la API `/active_configs`.

## Referencias

- `apps/governance-service/`
- `docs/plan-detallado-fases.md` → F3.2 semana 1 (PromptLoader fail-loud)
- Tesis, capítulo "Auditabilidad del sistema"
