# Deploy on Render

The `render.yaml` Blueprint provisions a PostgreSQL database and a Docker-based web service in the same region, then wires the service to the database's internal connection string through `DATABASE_URL`. It configures `/readyz` as the Render health check.

## Create the service

1. Push this repository to a Git provider supported by Render.
2. In the Render Dashboard, choose **New > Blueprint**, connect the repository, and apply the Blueprint. If the app files are in a subdirectory, set the Blueprint root directory to that directory.
3. Render creates the database and web service. The Blueprint generates `ADMIN_TOKEN` and `USER_TOKEN_SECRET`; keep these values private.
4. Wait for the first deploy to become healthy, then open the service's `onrender.com` URL.

The app accepts a PostgreSQL connection URL in `DATABASE_URL`. For local or other hosted PostgreSQL instances, set `DATABASE_URL` to that provider's connection string. Render services should use the Render Postgres internal URL when available; the Blueprint supplies it automatically.

## Startup and schema

The Docker image runs `python init_db.py` before starting Gunicorn. This creates the PostgreSQL tables and indexes if they do not exist. The database user must be allowed to create tables and indexes. Initialization is safe to repeat and does not delete existing data.

The service listens on Render's injected `PORT`. Render checks `GET /readyz`, which returns success only when PostgreSQL is reachable. `GET /healthz` is a process liveness check, and `GET /metrics` exposes Prometheus text metrics.

## Verify the deployment

```sh
curl -i https://<your-service>.onrender.com/healthz
curl -i https://<your-service>.onrender.com/readyz
curl -i https://<your-service>.onrender.com/metrics
```

Expected results are HTTP 200 for all three endpoints when the database is configured and reachable. `/metrics` returns confirmed, cancelled, declined, and available-seat metrics.

Free Render services and database plans have platform limits, including possible spin-down or expiration behavior. Review the current [Render pricing and plan details](https://render.com/pricing) before using this setup for data or traffic that needs continuous availability or retention.

## Local container run

For local development, use the bundled PostgreSQL Compose service:

```sh
docker compose up --build
```

The Compose credentials are for local development only. Do not reuse them in Render or any shared environment.
