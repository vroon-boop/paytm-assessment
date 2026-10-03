# Seat Reservation API

Flask JSON API backed by PostgreSQL. Allocation, idempotency, and the per-user seat cap are enforced in PostgreSQL transactions. Reservations confirm immediately; their owner can cancel to release the seats.

## Run locally

Requirements: Python 3.12+, Flask, psycopg2, and Gunicorn (declared in `requirements.txt`); Docker Compose and Docker are needed for the one-command container setup.

```sh
docker compose up --build
```

The API is at `http://localhost:8000`. Local compose uses development-only credentials from `compose.yaml`; change them for any shared environment. `GET /healthz` checks process liveness, `GET /readyz` checks PostgreSQL, and `GET /metrics` exposes Prometheus text metrics.

## Authentication and API

Set `ADMIN_TOKEN` for show creation and `USER_TOKEN_SECRET` for user bearer tokens. A user's token is `user_id.HMAC_SHA256(USER_TOKEN_SECRET, user_id)`. Generate one in Python without extra libraries:

```sh
USER_ID=alice USER_TOKEN_SECRET=replace-me python3 -c 'import os,hmac,hashlib; u=os.environ["USER_ID"]; print(u+"."+hmac.new(os.environ["USER_TOKEN_SECRET"].encode(),u.encode(),hashlib.sha256).hexdigest())'
```

Create a show (price is integer paise):

```sh
curl -X POST http://localhost:8000/shows \
  -H 'Authorization: Bearer local-admin-change-me' -H 'Content-Type: application/json' \
  -d '{"name":"friday-night","seats":["A1","A2","A3"],"price_paise":25000,"per_user_limit":4}'
```

Reserve and cancel:

```sh
curl -X POST http://localhost:8000/shows/SHOW_ID/reserve \
  -H 'Authorization: Bearer USER_TOKEN' -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: order-123' -d '{"seats":["A1"]}'
curl -X POST http://localhost:8000/reservations/RESERVATION_ID/cancel \
  -H 'Authorization: Bearer USER_TOKEN'
curl http://localhost:8000/shows/SHOW_ID
```

Multi-seat reservations are all-or-nothing. A missing or unavailable seat and a cap violation return 409 with no seats changed. The same key and same normalized seat list replays the original reservation; changing seats under the same key returns 409. User identity only comes from the signed bearer token. Cancel is owner-only and idempotent.

## Concurrent burst client

Set `ADMIN_TOKEN` and `USER_TOKEN_SECRET` in the shell, then run:

```sh
python3 burst.py http://localhost:8000 --requests 500 --workers 64
```

The client creates a fresh two-seat show, sends concurrent requests from distinct signed users for `A1`, reports confirmations / decline reasons / 5xx, retries the winner's same key, checks same-key/different-seat rejection, then prints final seat reconciliation and metrics. For a deployed URL, supply its HTTPS URL.

## Deployment and design notes

- Follow [DEPLOYMENT.md](DEPLOYMENT.md) for Render deployment. The Blueprint provisions Render PostgreSQL and connects the Docker web service through `DATABASE_URL`.
- [WRITEUP.md](WRITEUP.md) explains the locking protocol, idempotency, consistency choices, observability, and AI use.
- The intended incremental commit subjects are recorded in [PLAN.md](PLAN.md). Local commit history is included in this checkout.
