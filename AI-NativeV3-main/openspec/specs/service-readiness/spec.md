### Requirement: Shared health helper module

The system SHALL provide a shared async health helper at `packages/observability/src/platform_observability/health.py` exposing `CheckResult`, `check_postgres`, `check_redis`, `check_http`, and `assemble_readiness`. The 11 FastAPI services WITHOUT a current real readiness implementation (`api-gateway`, `identity-service`, `academic-service`, `evaluation-service`, `analytics-service`, `tutor-service`, `classifier-service`, `content-service`, `governance-service`, `ai-gateway`, `integrity-attestation-service`) MUST consume this helper from their `routes/health.py`.

#### Scenario: Helper module exposes the canonical surface

- **WHEN** a developer imports `from platform_observability.health import CheckResult, check_postgres, check_redis, check_http, assemble_readiness`
- **THEN** the import succeeds and each symbol is callable or instantiable as documented

#### Scenario: A service consumes the helper

- **WHEN** any of the 11 affected services constructs its `/health/ready` response
- **THEN** the response is built via `assemble_readiness(...)` from the shared helper, and the route module does NOT re-implement timeout/exception handling for DB/Redis/HTTP probes

#### Scenario: ctr-service is excluded from migration

- **WHEN** the change is implemented
- **THEN** `apps/ctr-service/src/ctr_service/routes/health.py` is NOT modified and keeps its existing `_check_db()`/`_check_redis()` logic

### Requirement: CheckResult shape

`CheckResult` SHALL be a dataclass-like value object with exactly three fields: `ok: bool`, `latency_ms: int`, and `error: str | None`. The `latency_ms` field MUST always be populated (including when `ok=False`, where it captures elapsed time until failure or timeout). The `error` field MUST be `None` when `ok=True` and a non-empty string when `ok=False`.

#### Scenario: Successful check

- **WHEN** `check_postgres(engine)` succeeds against a reachable database within timeout
- **THEN** the returned `CheckResult` has `ok=True`, `latency_ms` reflecting the actual elapsed milliseconds, and `error=None`

#### Scenario: Failed check captures error message

- **WHEN** `check_redis(redis_url)` raises an exception (connection refused, auth failure, etc.)
- **THEN** the returned `CheckResult` has `ok=False`, `latency_ms` reflecting the elapsed time until failure, and `error` containing the first line of the exception message

#### Scenario: Timed-out check

- **WHEN** any check exceeds its configured timeout
- **THEN** the returned `CheckResult` has `ok=False`, `latency_ms` approximately equal to the timeout in milliseconds, and `error` indicating a timeout (e.g., `"timeout after 2.0s"`)

### Requirement: Postgres probe semantics

`check_postgres(engine, timeout=2.0)` SHALL execute `SELECT 1` against the given SQLAlchemy async engine wrapped in `asyncio.wait_for(..., timeout)`. Exceptions MUST be captured and translated into `CheckResult(ok=False, ...)` — they MUST NOT propagate.

#### Scenario: Healthy Postgres

- **WHEN** the engine connects to a reachable Postgres instance and `SELECT 1` returns
- **THEN** `check_postgres` returns `CheckResult(ok=True, latency_ms=<elapsed>, error=None)`

#### Scenario: Unreachable Postgres

- **WHEN** the Postgres host is unreachable (connection refused or DNS failure)
- **THEN** `check_postgres` returns `CheckResult(ok=False, ...)` within the timeout window without raising

#### Scenario: Slow Postgres exceeds timeout

- **WHEN** Postgres takes longer than `timeout` seconds to respond
- **THEN** `check_postgres` returns `CheckResult(ok=False, latency_ms ≈ timeout*1000, error="timeout after Xs")`

### Requirement: Redis probe semantics

`check_redis(redis_url, timeout=2.0)` SHALL connect to Redis using the given URL, issue `client.ping()` wrapped in `asyncio.wait_for(..., timeout)`, and clean up the connection after the probe (success or failure). Exceptions MUST NOT propagate.

#### Scenario: Healthy Redis

- **WHEN** Redis is reachable and `PING` returns `PONG`
- **THEN** `check_redis` returns `CheckResult(ok=True, ...)` and the connection is closed

#### Scenario: Connection cleanup on failure

- **WHEN** `check_redis` raises during `ping()` (auth failure, network error)
- **THEN** the function still attempts to close any partially-open connection and returns `CheckResult(ok=False, ...)`

### Requirement: HTTP probe with TTL cache

`check_http(url, timeout=2.0, expect_status=200, cache_ttl=5.0)` SHALL execute an HTTP GET against `url` using `httpx.AsyncClient`, treating responses with status `expect_status` as success. Successful and failed `CheckResult` values MUST be cached in-process for `cache_ttl` seconds keyed by URL. A subsequent call within the TTL window MUST return the cached result without making a new HTTP request.

#### Scenario: Cache hit returns cached result

- **WHEN** `check_http("http://x/y")` is called twice within `cache_ttl` seconds
- **THEN** the second call returns the same `CheckResult` instance (or an equal one) without performing a new HTTP request

#### Scenario: Cache expiry triggers re-probe

- **WHEN** `check_http("http://x/y")` is called after `cache_ttl` seconds have elapsed since the last call
- **THEN** a fresh HTTP request is performed and the cache is updated

#### Scenario: Unexpected status code

- **WHEN** the upstream returns a status different from `expect_status`
- **THEN** `check_http` returns `CheckResult(ok=False, ...)` with `error` mentioning the actual status code

#### Scenario: Cache scope is per-process

- **WHEN** two separate processes call `check_http` for the same URL within `cache_ttl`
- **THEN** each process maintains its own independent cache (the cache MUST NOT be cross-process)

### Requirement: Readiness aggregation and HTTP status mapping

`assemble_readiness(service: str, version: str, checks: dict[str, CheckResult], critical: set[str])` SHALL return a tuple `(HealthResponse, http_status_code)` where `status` is computed as follows:

- If every check key in `critical` has `ok=True` AND every other check also has `ok=True` → `status="ready"`, `http_status_code=200`.
- If every check key in `critical` has `ok=True` AND at least one non-critical check has `ok=False` → `status="degraded"`, `http_status_code=200`.
- If at least one check key in `critical` has `ok=False` → `status="error"`, `http_status_code=503`.

The `HealthResponse.checks` field MUST contain every check from the input dict, serialized as `{ok, latency_ms, error}`. The `service` and `version` fields MUST be passed through unchanged.

#### Scenario: All checks healthy

- **WHEN** `assemble_readiness("svc", "0.1.0", {"db": OK, "redis": OK}, critical={"db", "redis"})` is called
- **THEN** the result is `(HealthResponse(status="ready", checks={...}, ...), 200)`

#### Scenario: Non-critical check failed

- **WHEN** `assemble_readiness("svc", "0.1.0", {"db": OK, "downstream": KO}, critical={"db"})` is called
- **THEN** the result is `(HealthResponse(status="degraded", ...), 200)`

#### Scenario: Critical check failed

- **WHEN** `assemble_readiness("svc", "0.1.0", {"db": KO, "redis": OK}, critical={"db", "redis"})` is called
- **THEN** the result is `(HealthResponse(status="error", ...), 503)`

#### Scenario: Critical and non-critical both failed

- **WHEN** any critical check is `ok=False`, regardless of non-critical state
- **THEN** the result is `(HealthResponse(status="error", ...), 503)` — `error` takes precedence over `degraded`

#### Scenario: Missing critical key in checks dict is treated as failure

- **WHEN** `critical = {"db"}` but `checks` does NOT contain a `"db"` entry
- **THEN** `assemble_readiness` returns `status="error"` (a missing critical check MUST NOT silently pass)

### Requirement: Per-service criticality matrix

Each affected service SHALL declare its dependency criticality in its `routes/health.py` exactly as defined below. Adding or removing a dependency from these sets is a contract change that requires updating this requirement.

| Service | Critical | Non-critical |
|---|---|---|
| `api-gateway` | `keycloak_jwks` | `academic_service` |
| `identity-service` | `keycloak` | (none) |
| `academic-service` | `academic_main_db` | (none) |
| `evaluation-service` | `academic_main_db` | (none) |
| `analytics-service` | `ctr_store_db`, `classifier_db` | (none) |
| `tutor-service` | `redis` | `academic_service`, `ai_gateway` |
| `classifier-service` | `classifier_db`, `redis` | (none) |
| `content-service` | `content_db`, `pgvector_extension` | (none) |
| `governance-service` | `prompts_filesystem` | (none) |
| `ai-gateway` | `redis` | `llm_provider` |
| `integrity-attestation-service` | `attestation_dir_writable`, `private_key_readable` | (none) |

#### Scenario: api-gateway with Keycloak down

- **WHEN** the Keycloak JWKS endpoint is unreachable
- **THEN** `api-gateway`'s `/health/ready` returns HTTP 503 with `status="error"`, regardless of the state of `academic_service`

#### Scenario: tutor-service with non-critical downstream down

- **WHEN** `ai-gateway` is unreachable but Redis and `academic-service` are healthy
- **THEN** `tutor-service`'s `/health/ready` returns HTTP 200 with `status="degraded"` and `checks["ai_gateway"].ok=False`

#### Scenario: content-service without pgvector

- **WHEN** the `content_db` Postgres is reachable but `SELECT 1 FROM pg_extension WHERE extname='vector'` returns zero rows
- **THEN** `content-service`'s `/health/ready` returns HTTP 503 with `checks["pgvector_extension"].ok=False`

#### Scenario: governance-service with prompt missing on disk

- **WHEN** the file at `{PROMPTS_REPO_PATH}/prompts/tutor/{default_prompt_version}/system.md` does not exist or is not readable
- **THEN** `governance-service`'s `/health/ready` returns HTTP 503 with `checks["prompts_filesystem"].ok=False`

#### Scenario: integrity-attestation-service with read-only attestation dir

- **WHEN** the `attestation_dir` is not writable by the service user
- **THEN** `integrity-attestation-service`'s `/health/ready` returns HTTP 503 with `checks["attestation_dir_writable"].ok=False`

### Requirement: Liveness endpoint behavior unchanged

The `/health/live` endpoint of every affected service SHALL continue returning HTTP 200 unconditionally with a minimal payload. It MUST NOT call any external dependency, so liveness probes detect ONLY process-level failures (Python exception loop, deadlock).

#### Scenario: Liveness during dependency outage

- **WHEN** Postgres or Redis is unreachable and `/health/ready` returns 503
- **THEN** `/health/live` continues to return HTTP 200 (k8s does NOT restart the pod for dependency outages)

### Requirement: HealthResponse contract is backward-compatible

The `HealthResponse` Pydantic model in `packages/contracts` SHALL NOT change its public field set. The `checks` field SHALL accept the new `CheckResult`-shaped dict values without breaking existing consumers (the field has always been typed as `dict[str, ...]` and was empty before this change). The fields `service`, `version`, and `status` MUST keep their current types and semantics.

#### Scenario: Existing consumers reading status field

- **WHEN** any consumer reads `response.status` from a `/health/ready` response
- **THEN** the value is one of `"ready"`, `"degraded"`, `"error"` (no consumer is broken by an unknown new value)

#### Scenario: Consumers ignoring checks field

- **WHEN** a consumer ignores the `checks` field
- **THEN** the response remains parseable and other fields are unchanged from the pre-change behavior

### Requirement: Helper unit tests cover the three states

The package `packages/observability` SHALL include a unit test module at `packages/observability/tests/unit/test_health.py` that covers:

- `check_postgres` success path, failure path, timeout path (mocked engine).
- `check_redis` success path, failure path, timeout path (mocked client).
- `check_http` success, failure, timeout, AND cache hit/miss/expiry behavior (mocked HTTP client + monotonic clock).
- `assemble_readiness` for the three states (`ready`, `degraded`, `error`) AND the missing-critical-key edge case.

Tests MUST run as part of `make test` and MUST NOT require live infrastructure (no real DB, Redis, or HTTP endpoints).

#### Scenario: CI gate

- **WHEN** any change to `packages/observability/src/platform_observability/health.py` is pushed
- **THEN** CI runs the helper unit tests and fails the PR if any of the four state coverage scenarios regresses

### Requirement: Operational acceptance criteria

The implementation SHALL satisfy the following operational checks before the change is archived:

- `make check-health` parses both HTTP status code AND the `status` field of the response, surfacing per-service `checks` content in its output.
- Manually stopping the Postgres container (e.g., `docker stop <postgres-container>`) causes `analytics-service`, `academic-service`, `evaluation-service`, `classifier-service`, and `content-service` to return `status="error"` + HTTP 503 within 10 seconds.
- Manually stopping the Redis container causes `tutor-service`, `classifier-service`, and `ai-gateway` to return `status="error"` (those services have Redis as critical).
- `make test` passes with the new helper tests.

#### Scenario: Postgres outage detection latency

- **WHEN** Postgres is stopped while services are running
- **THEN** within 10 seconds (≤ 2× `periodSeconds: 5` from helm), affected services report `status="error"` and HTTP 503 on their `/health/ready` endpoint

#### Scenario: check-health script reports granular state

- **WHEN** `make check-health` is run against a stack where one service has a non-critical dependency down
- **THEN** the script exits successfully (HTTP 200 on that service) but its output flags `status: "degraded"` with the failing check name visible
