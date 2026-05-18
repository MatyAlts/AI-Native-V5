# ADR-005 — Redis Streams como bus de eventos

- **Estado**: Aceptado
- **Fecha**: 2026-04
- **Deciders**: Alberto Cortez, director de tesis
- **Tags**: eventos, mensajería, ctr

## Contexto y problema

La arquitectura separa plano académico y plano pedagógico con comunicación por bus de eventos. El CTR además requiere que los eventos dentro de un episodio se procesen **en orden estricto** (para que la cadena SHA-256 se calcule correctamente) pero que episodios distintos puedan procesarse en paralelo para throughput.

Requisitos específicos:

- At-least-once delivery (nunca perder eventos; duplicados se manejan con idempotencia).
- Orden por clave de partición (`episode_id`) dentro de cada partición.
- Paralelismo entre particiones.
- DLQ para eventos que fallan persistentemente.
- Observabilidad de lag por consumer.

## Drivers de la decisión

- Simplicidad operacional: equipo chico, no queremos operar Zookeeper + Kafka.
- Redis ya está en el stack (cache, rate limiting).
- Volumen estimado: <1000 eventos/s en pilotaje, <10000 eventos/s en producción con 2-3 universidades.

## Opciones consideradas

### Opción A — Apache Kafka
Gold standard para streaming de eventos. Más complejo operacionalmente. ZooKeeper o KRaft. Justificado a volúmenes >100k evts/s.

### Opción B — RabbitMQ
Clásico, maduro. AMQP. Menor throughput que Kafka, suficiente para nosotros. Ordenamiento por queue requires single-consumer config.

### Opción C — Redis Streams
Estructuras de datos nativas de Redis con consumer groups, ack manual, DLQ manual.

### Opción D — NATS JetStream
Alternativa moderna y simple. Menor adopción, menor ecosistema de docs.

### Opción E — PostgreSQL LISTEN/NOTIFY
No es real queue. Sin garantías al reconnect. Descartado.

## Decisión

**Opción C — Redis Streams.**

Configuración:
- 8 particiones (`ctr.p0` ... `ctr.p7`) para eventos del CTR.
- Sharding por `hash(episode_id) mod 8` garantiza orden por episodio.
- Consumer group `ctr_workers` con un worker por partición (single-writer estricto).
- `XACK` manual después de commit transaccional a Postgres.
- `ctr.dead` como DLQ. Después de 3 reintentos con backoff, evento va a DLQ y episodio se marca `integrity_compromised`.

Migración a Kafka planeada **solo si** el volumen justifica el costo operacional (≥3 universidades con alto volumen concurrente, típicamente >5k eventos/s sostenidos).

## Consecuencias

### Positivas
- Redis ya está en el stack, curva de aprendizaje baja.
- `XREADGROUP`, `XACK`, `XCLAIM` cubren los patrones que necesitamos.
- Ordenamiento por partición + paralelismo entre particiones funciona tal como lo necesitamos.
- Dashboard Grafana con lag por consumer es trivial.
- Un solo contenedor de infra para dev.

### Negativas
- Redis no está diseñado para retención larga. Configuramos `MAXLEN ~1000000`; eventos viejos se purgan. Persistencia definitiva es Postgres, el stream es buffer.
- Throughput tope ~10k evts/s por stream antes de que Redis sea bottleneck (suficiente para MVP).
- Sin schema registry nativo; los esquemas se gestionan en `packages/contracts` con Pydantic/Zod.
- Migración futura a Kafka requerirá reescritura de consumers (pero el contrato de eventos se mantiene).

### Neutras
- La garantía es at-least-once. Idempotencia por `event_uuid` en DB es mandatoria (ya implementada en schema del CTR).

## Referencias

- [Redis Streams docs](https://redis.io/docs/data-types/streams/)
- `apps/ctr-service/` (workers particionados)
- ADR-010 (append-only ayuda a idempotencia)
