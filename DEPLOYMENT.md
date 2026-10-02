# Deployment guide

This repository is an event-seat reservation API for shows or concerts. It is a generic seat-booking service, not a Railway-specific product. Railway is only the free-tier hosting choice used in this guide; the actual application is the event-seat reservation system described in the challenge.

The service is a Flask app backed by MySQL. The database schema in `schema.sql` is MySQL-specific (`AUTO_INCREMENT`, `ENGINE=InnoDB`, MySQL `ENUM` + foreign keys), so the free-tier deployment path that matches this app most directly is:

- Railway web service for the Flask app
- Railway managed MySQL database for the app state

This is the least-assumption path because it matches the app’s actual runtime requirements without introducing a separate database migration layer.

## What this app requires at runtime

The Flask app reads these environment variables from the process environment:

- `DB_HOST`
- `DB_USER`
- `DB_PASSWORD`
- `DB_NAME`
- `DB_PORT`
- `ADMIN_TOKEN`
- `USER_TOKEN_SECRET`
- `PORT` (the Dockerfile sets this to `8000`)
- optional: `LOG_LEVEL`

The app exposes:

- `GET /healthz` - liveness check
- `GET /readyz` - readiness check that verifies MySQL is reachable
- `GET /metrics` - Prometheus text metrics

The app does not accept an alternative database backend in its current code. It expects MySQL and will fail closed if the DB is unavailable.

---

## 1. Confirm the project runs locally first

From the repo root that contains `app.py`, `Dockerfile`, `requirements.txt`, `schema.sql`, and `compose.yaml`:

```bash
cd paytm
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python init_db.py
python app.py
```

Or, with the repo’s provided container flow:

```bash
cd paytm
docker compose up --build
```

Check:

```bash
curl http://localhost:8000/healthz
curl http://localhost:8000/readyz
```

If the local app boots and `readyz` responds successfully, the deployment configuration is consistent with the repository.

---

## 2. Push the repository to GitHub

If this checkout is not already on GitHub:

```bash
git init
git add .
git commit -m "Initial seat reservation service"
git branch -M main
git remote add origin https://github.com/<your-user>/<your-repo>.git
git push -u origin main
```

If the repository root is the parent folder and the actual app is under `paytm/`, use the repo root that contains the app files when creating the Railway service, or set the Railway root directory to `paytm` during setup.

---

## 3. Create a Railway project and add a MySQL database

This is the recommended free-tier setup because Railway offers a free MySQL service that matches this app.

### Install the Railway CLI

```bash
npm install -g @railway/cli
railway login
```

### Create a Railway project

```bash
cd paytm
railway init
```

Then add a MySQL database:

```bash
railway add --database mysql
```

Railway will create environment variables for the MySQL service. The names are typically:

- `MYSQLHOST`
- `MYSQLPORT`
- `MYSQLUSER`
- `MYSQLPASSWORD`
- `MYSQLDATABASE`

Open the Railway dashboard for the database service and copy those values into the web app service variables that will be created in the next step.

---

## 4. Create the web app service on Railway

In the Railway dashboard:

1. Click “New Project”.
2. Choose “Deploy from GitHub repo”.
3. Select the repository you pushed above.
4. When asked for the service root, use the folder that contains `app.py`, `Dockerfile`, `requirements.txt`, and `schema.sql`.
   - If the repo is just the `paytm` folder, use that folder as the root.
   - If the repo root is a parent folder, set the root directory to `paytm`.
5. Railway will detect the Dockerfile automatically and deploy the app using the repository’s `Dockerfile`.
6. Confirm the build uses the default `CMD` in the Dockerfile:

```bash
python init_db.py && exec gunicorn --bind 0.0.0.0:${PORT} --workers 2 --threads 8 --timeout 120 app:app
```

This matches the repo and is important because it initializes the DB schema during startup.

---

## 5. Set the required environment variables on the web service

In the Railway web service environment tab, set these variables explicitly:

```bash
PORT=8000
DB_HOST=<MYSQLHOST value from the MySQL service>
DB_PORT=<MYSQLPORT value from the MySQL service>
DB_USER=<MYSQLUSER value from the MySQL service>
DB_PASSWORD=<MYSQLPASSWORD value from the MySQL service>
DB_NAME=<MYSQLDATABASE value from the MySQL service>
ADMIN_TOKEN=<choose a long random string>
USER_TOKEN_SECRET=<choose a long random string>
LOG_LEVEL=INFO
```

Do not reuse the same value for `ADMIN_TOKEN` and `USER_TOKEN_SECRET`.

Example values for manual testing:

```bash
ADMIN_TOKEN=admin-dev-token-please-change
USER_TOKEN_SECRET=dev-user-secret-please-change
```

The application will fail readiness if the database is not reachable, which is the intended behavior.

---

## 6. Initialize the database schema

After the web service is running, trigger the schema setup once:

```bash
railway run python init_db.py
```

If you are using the CLI from the service directory, this runs the database bootstrap in the same environment as the deployed app. This creates the tables defined in `schema.sql` and is required before creating a show.

If the CLI is not available, run the same command from the Railway “Exec” or “One-off command” UI if your project exposes that feature.

---

## 7. Validate the live deployment

Once the service is deployed and healthy, test the public URL returned by Railway:

```bash
curl https://<your-railway-domain>/healthz
curl https://<your-railway-domain>/readyz
curl https://<your-railway-domain>/metrics
```

Expected behavior:

- `/healthz` returns `200` and `{"status":"ok"}`
- `/readyz` returns `200` only if MySQL is reachable
- `/metrics` returns Prometheus text on success

---

## 8. Create a show and make a reservation

Generate a signed bearer token for a user ID exactly as the app expects:

```bash
USER_ID=alice USER_TOKEN_SECRET='your-user-secret' python3 -c 'import os,hmac,hashlib; u=os.environ["USER_ID"]; print(u+"."+hmac.new(os.environ["USER_TOKEN_SECRET"].encode(),u.encode(),hashlib.sha256).hexdigest())'
```

Replace the output with `USER_TOKEN` in the commands below.

Create a show as admin:

```bash
curl -X POST https://<your-railway-domain>/shows \
  -H 'Authorization: Bearer <ADMIN_TOKEN>' \
  -H 'Content-Type: application/json' \
  -d '{"name":"friday-night","seats":["A1","A2","A3","A4"],"price_paise":25000,"per_user_limit":4}'
```

Reserve a seat:

```bash
curl -X POST https://<your-railway-domain>/shows/<SHOW_ID>/reserve \
  -H 'Authorization: Bearer <USER_TOKEN>' \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: order-123' \
  -d '{"seats":["A1"]}'
```

Check the full seat state:

```bash
curl https://<your-railway-domain>/shows/<SHOW_ID>
```

---

## 9. Operational notes for production use

- The app uses request IDs from the `X-Request-ID` header when supplied, otherwise it generates one automatically.
- The app logs JSON lines with request metadata.
- `ADMIN_TOKEN` and `USER_TOKEN_SECRET` must be long, random, and not shared across environments.
- The service is intended to fail closed: if MySQL is down, `/readyz` returns `503` and the app will not claim healthy readiness.
- The app uses integer `price_paise` values and never serializes floats for money.

---

## 10. Alternative providers

Render and Fly.io can host the Flask app, but this repo is MySQL-backed and the code expects MySQL directly; they are not the cleanest free-tier pairing without also provisioning a MySQL-compatible service.

If you use an alternative provider, the required runtime configuration remains the same:

- deploy the Docker image or GitHub app using the repo’s Dockerfile
- provide a reachable MySQL instance
- set the same environment variables listed above
- run `python init_db.py` once during first boot

The Railway path above is the direct free-tier fit for this codebase.
