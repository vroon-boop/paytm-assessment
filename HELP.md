# Running and testing the seat reservation API

The API lives in `paytm/`. It is a Flask JSON service backed by MySQL.

## Start the server

### Docker Compose (recommended)

From the repository root:

```sh
cd paytm
docker compose up --build
```

Compose starts MySQL and the API. The API container waits for MySQL, runs `init_db.py` to create the tables from `schema.sql`, then starts Gunicorn on port `8000`. Keep this terminal open; use a second terminal to run the curl commands below. Stop the services with `Ctrl+C`, then `docker compose down` when needed. The database is stored in a named volume and remains between restarts. To erase that local database and its data, run `docker compose down -v`.

The local Compose credentials are for development only: admin token `local-admin-change-me`, user token secret `local-user-secret-change-me`, and MySQL password `local-seats-password`.

Check that the API and database are up:

```sh
curl -i http://localhost:8000/healthz
curl -i http://localhost:8000/readyz
```

Both should return HTTP 200. `/healthz` checks the API process; `/readyz` checks database access.

### Run without Docker

You need Python 3.12+ and a MySQL 8 database. From `paytm/`, create and activate a virtual environment, install the dependencies, and set the DB credentials and API secrets to match your local MySQL configuration:

```sh
cd paytm
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export DB_HOST=127.0.0.1 DB_PORT=3306 DB_NAME=seats DB_USER=seats DB_PASSWORD='your-mysql-password'
export ADMIN_TOKEN='local-admin-change-me'
export USER_TOKEN_SECRET='local-user-secret-change-me'
python init_db.py
python app.py
```

The app listens on `http://localhost:8000` by default. Run `python init_db.py` once per database before starting the app. For production, use strong private secrets and the deployment guide in `paytm/DEPLOYMENT.md`.

## Create dummy data

There is no separate seed-data command. Create a show using `POST /shows`; this inserts the show and all its seats as available in MySQL. `price_paise` is an integer amount in paise (for example, `25000` is ₹250.00), and `per_user_limit` cannot exceed the number of seats.

Set the local admin token and create a sample show:

```sh
export BASE_URL=http://localhost:8000
export ADMIN_TOKEN='local-admin-change-me'

curl -sS -X POST "$BASE_URL/shows" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Demo Friday Show","seats":["A1","A2","A3","B1","B2"],"price_paise":25000,"per_user_limit":2}'
```

The response contains a generated `id`; copy it and use it as `SHOW_ID` in the commands below. Each call to create a show generates a new show and new seats. A valid show has a non-empty name (up to 160 characters), a non-empty list of unique seat names (up to 32 characters each), a non-negative integer `price_paise`, and a positive integer `per_user_limit` no greater than the seat count.

## Make user tokens

Reservation and cancellation requests need a signed user bearer token. The API signs the user ID with `USER_TOKEN_SECRET`. Generate a token for the demo user using Python's standard library:

```sh
export USER_TOKEN_SECRET='local-user-secret-change-me'
export USER_ID=alice
export USER_TOKEN="$(python3 -c 'import os,hmac,hashlib; u=os.environ["USER_ID"]; print(u+"."+hmac.new(os.environ["USER_TOKEN_SECRET"].encode(),u.encode(),hashlib.sha256).hexdigest())')"
```

Use the same secret configured for the API. To simulate another user, set `USER_ID` to a different value and regenerate `USER_TOKEN`.

## Exercise the APIs

Set the ID from the create-show response:

```sh
export SHOW_ID='<paste-show-id-here>'
```

View the show's seats and counts. Initially all five seats should be available:

```sh
curl -sS "$BASE_URL/shows/$SHOW_ID"
```

Reserve seats `A1` and `A2`. The idempotency key identifies this reservation request; reuse it only when retrying that same request:

```sh
curl -sS -X POST "$BASE_URL/shows/$SHOW_ID/reserve" \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: alice-demo-001' \
  -d '{"seats":["A1","A2"]}'
```

The response includes `reservation_id`, `amount_paise`, and `status`. Copy the reservation ID, then view the show again to see `A1` and `A2` marked `confirmed` and the available count reduced:

```sh
curl -sS "$BASE_URL/shows/$SHOW_ID"
```

Repeating the exact reservation with the same user, show, idempotency key, and seat list returns the original reservation. Reusing that key with different seats returns HTTP 409. To test a conflict for already booked seats, try reserving `A1` with another key; use a new signed user token (for example, change `USER_ID` to `bob`) if you want the request to reach the seat-availability check rather than the per-user limit.

Cancel the reservation as its owner (the same `alice` token):

```sh
export RESERVATION_ID='<paste-reservation-id-here>'
curl -sS -X POST "$BASE_URL/reservations/$RESERVATION_ID/cancel" \
  -H "Authorization: Bearer $USER_TOKEN"
```

Check `GET /shows/$SHOW_ID` again; the cancelled reservation's seats should be available. Cancellation is owner-only and repeating the cancel request is safe.

## API reference

All responses are JSON except `/metrics`. Error responses include an `error` and `request_id`.

| Method and path | Authentication | Purpose |
| --- | --- | --- |
| `GET /healthz` | None | Process liveness check. |
| `GET /readyz` | None | Checks database connectivity. |
| `POST /shows` | Admin bearer token | Create a show and its available seats. JSON: `name`, `seats`, `price_paise`; optional `per_user_limit` (default 4). |
| `GET /shows/<show_id>` | None | View show details, seat statuses, and counts. |
| `POST /shows/<show_id>/reserve` | Signed user bearer token | Reserve seats atomically. JSON: `seats`; requires `Idempotency-Key` header (or `idempotency_key` in JSON). |
| `POST /reservations/<reservation_id>/cancel` | Owning user's signed bearer token | Cancel a confirmed reservation. |
| `GET /metrics` | None | Prometheus text counters and available-seat gauges. |

For concurrent reservation testing, `paytm/burst.py` is also provided. Set `ADMIN_TOKEN` and `USER_TOKEN_SECRET` as above, then from `paytm/` run `python3 burst.py http://localhost:8000 --requests 500 --workers 64`. It creates its own show and reports confirmations, declines, and final seat reconciliation.
