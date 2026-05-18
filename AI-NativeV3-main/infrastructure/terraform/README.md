# Infrastructure as Code (Terraform)

Stub de configuración Terraform para aprovisionar el cluster Kubernetes
destino. Los módulos específicos por cloud provider se agregan cuando
se decide dónde corre producción.

## Opciones de hosting consideradas

| Provider | Costo estimado/mes | Pros | Contras |
|---|---|---|---|
| DigitalOcean Kubernetes | USD 150-300 | Simple, DOKS barato, LB integrado | Menor ecosistema |
| Hetzner Cloud | USD 80-200 | Muy barato en EU | Latencia desde AR |
| GKE (Google) | USD 300-600 | Maduro, autopilot disponible | Complejidad |
| AWS EKS | USD 400-800 | Industry standard | Caro, complejo |
| Bare metal institucional | variable | Datos en universidad | Ops pesadas |

Decisión pospuesta a F5 cuando haya dos universidades reales comprometidas.

## Para F0 y F1

El ambiente staging puede correr en un solo VPS con Docker Compose
(usando el mismo `infrastructure/docker-compose.dev.yml` con ajustes de
hostname y TLS). No requiere Kubernetes hasta F3-F4.
