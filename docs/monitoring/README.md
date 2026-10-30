# Monitoring M0 (SRS v2 §13, R0.3)

M0 = one OpenTelemetry Collector on the VPS (`deploy/otel/collector.yaml`) exporting OTLP/HTTP to a hosted
backend free tier, plus an external uptime check and dead-man heartbeats. Self-hosting a backend on the VPS is
out of scope for M0 (RAM budget, CON-003).

## What runs where

| Signal | Producer | Path |
| --- | --- | --- |
| Traces, app metrics | `app`, `worker` (OTEL SDK) | OTLP → `otel-collector:4318` → backend |
| Host metrics | collector `hostmetrics` (`/hostfs`) | collector → backend |
| Container metrics | collector `docker_stats` via read-only `docker-socket-proxy` | collector → backend |
| Container logs | collector `filelog/docker` | collector → backend |
| Uptime, TLS expiry | external uptime check | backend or uptime service |
| Worker / backup liveness | `WORKER_HEARTBEAT_URL`, `BACKUP_HEARTBEAT_URL` | heartbeat service |

The collector drops `/health` and `/ready` spans, deletes auth headers and any prompt/response/user-identity
attributes (MON-013), keeps every error, slow (>3.5 s), Agentic and admin trace, and samples 10% of the rest.

## One-time setup

1. Create a hosted backend account that accepts OTLP/HTTP (e.g. Grafana Cloud free tier). Note the OTLP
   endpoint and build the `Authorization` header value (Grafana Cloud: `Basic base64(<instance-id>:<token>)`).
2. In the VPS secret config set `MONITORING_OTLP_ENDPOINT` and `MONITORING_OTLP_AUTHORIZATION`
   (see `.env.production.example`). Compose refuses to start the collector without them.
3. Create two heartbeat checks (e.g. healthchecks.io): worker every 5 minutes with 5 minutes grace, backup
   daily with 2 hours grace. Put the ping URLs in `WORKER_HEARTBEAT_URL` and `BACKUP_HEARTBEAT_URL`.
4. Create an external uptime check on `https://<domain>/health` and the web root, every 1–5 minutes, with
   certificate expiry checking enabled.
5. Configure two contact points: email (P1) and a private Discord webhook (P1 and P2).
6. Implement every rule in `alerts.yaml` in the backend with the same id, threshold and channels. Each alert
   links to `docs/runbooks/<id>.md`; CI fails if an alert and its runbook drift apart.
7. Deploy: `docker compose up -d otel-collector docker-socket-proxy app worker`, then check
   `docker compose ps otel-collector` is healthy and data arrives in the backend within 2 minutes.

## Verifying

- Collector config: `docker run --rm -v ./deploy/otel/collector.yaml:/etc/otelcol-contrib/config.yaml
  otel/opentelemetry-collector-contrib:0.162.0 validate --config=/etc/otelcol-contrib/config.yaml`.
- Alert routing: temporarily stop the worker heartbeat or point the uptime check at a 404 path and confirm
  the alert reaches both channels, then revert.
- Free-tier usage stays below 80% (`chisa-telemetry-quota`); tune `tail_sampling` first if it does not.

## Deferred

- Dashboards as code (MON-040): added once the backend is fixed and real data exists.
- Discord bot tracing and `traceparent` propagation (MON-016): with the bot work.
- Postgres, Redis and Qdrant receivers (MON-007): M1, if container metrics prove insufficient.
- Admin audit and MFA alerts: R3.
