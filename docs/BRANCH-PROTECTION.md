# Branch protection — procedimiento de activación

Este documento queda para que **el dueño del repo** active la protección
de la rama `main` en GitHub. No se puede automatizar desde esta máquina
de dev (no hay `gh` CLI ni credenciales del repo).

## Por qué importa

Hoy cualquier commit puede mergearse a `main` sin pasar el smoke test E2E
ni review. Los 30 smoke tests de `tests/e2e/smoke/` corren en <2s y
validan invariantes doctorales (CTR append-only, RLS multi-tenant,
classifier hash determinista). Si un PR rompe alguno, la tesis pierde
defensibilidad.

## Pasos manuales (UI de GitHub)

1. Ir a **Settings → Branches** del repositorio.
2. Click **Add branch protection rule**.
3. Branch name pattern: `main`.
4. Activar:
   - **Require a pull request before merging**
     - Require approvals: **1**
     - Dismiss stale pull request approvals when new commits are pushed
   - **Require status checks to pass before merging**
     - Require branches to be up to date before merging
     - **Required status check**: `Smoke E2E API` (debe ser el nombre exacto del workflow)
   - **Require conversation resolution before merging**
   - **Do not allow bypassing the above settings** (aplicar al admin también)
5. Click **Create**.

## Alternativa con gh CLI

Si tenés `gh` CLI autenticado:

```bash
gh api -X PUT "repos/<owner>/<repo>/branches/main/protection" \
  --field 'required_status_checks[strict]=true' \
  --field 'required_status_checks[contexts][]=Smoke E2E API' \
  --field 'enforce_admins=true' \
  --field 'required_pull_request_reviews[required_approving_review_count]=1' \
  --field 'required_pull_request_reviews[dismiss_stale_reviews]=true' \
  --field 'restrictions=null'
```

## Verificación

Después de activar, intentar pushear directo a main desde otra cuenta:
debería rechazar con `branch protection rules`. Y abrir un PR sin que
pase el workflow `Smoke E2E API`: el botón "Merge" debería estar
deshabilitado.
