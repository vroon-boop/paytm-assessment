# Correctness and operations write-up

## Atomic seat allocation

PostgreSQL is the system of record. A reservation transaction reads the immutable show configuration, creates or locks the `(show_id,user_id)` guard row, then locks every requested seat row in sorted seat-name order. It checks all seats and the user's current confirmed count before writing anything. The final seat updates include `status='available'`; the reservation, seat links, seat status changes, idempotency row, and success metric event commit together. The `(show_id,seat_name)` primary key plus transaction and guarded update make a seat a single database row that cannot be confirmed twice.

Requests for one user/show serialize at that user's guard row, so parallel requests cannot both pass the cap check. Different users do not queue on a show-wide lock. Requests that overlap seats acquire them in the same lexical order; this avoids cycles among seat locks for multi-seat requests. Cancellation discovers the reservation scope, locks the same user/show guard row, locks the reservation, then releases only rows that still reference that reservation. It cannot release another user's seat.

All multi-seat requests are all-or-nothing. A seat unavailable, unknown, or a cap overflow yields a 409 with zero allocation changes. The invariant is read from actual persisted seats: available + held + confirmed equals total. This implementation has no active hold state: bookings confirm immediately, and owner cancellation is the release operation.

## Idempotency and identity

The unique `(user_id,show_id,idem_key)` record stores a SHA-256 fingerprint of the sorted seat list and the reservation ID. It commits in the same transaction as the reservation. A matching retry returns that original reservation; a different body for the same key returns 409. The bearer token's user ID is verified using HMAC-SHA-256 and `USER_TOKEN_SECRET`; body fields cannot select an identity. Admin show creation uses the separate `ADMIN_TOKEN` secret.

## Consistency and availability

Reservation correctness is prioritized over accepting bookings when PostgreSQL is unavailable. Readiness returns 503 if its database query fails; a reservation cannot proceed without a committed transaction. Under a network partition, the API fails closed instead of acknowledging an uncommitted reservation. This costs availability during database outages but prevents split-brain seat ownership.

## Observability and response

`/healthz` is process liveness, `/readyz` checks PostgreSQL, and `/metrics` exposes persisted confirmed/cancelled/declined event counters and current available-seat gauges by show. Request logs are JSON lines containing the request ID, method, path, status, and duration; the same ID is returned in `X-Request-ID`. The burst client prints outcome counts and reads back final reconciliation.


### Hot-seat burst run

Run the client from the project directory. Set `ADMIN_TOKEN` and `USER_TOKEN_SECRET` in the shell to the same values configured for the API, then pass the base URL (including `http://` or `https://`):

```sh
export ADMIN_TOKEN='<api-admin-token>'
export USER_TOKEN_SECRET='<api-user-token-secret>'
python3 burst.py https://event-reservation-bz7k.onrender.com --requests 500 --workers 64
```

For a local server, use `http://127.0.0.1:8000` in place of `<domain>`. The script creates a fresh show with two seats, sends 500 requests using up to 64 worker threads against the same seat, retries the winning request with the same idempotency key, then reuses that key with a different seat list. It leaves the generated show and metric events in the database. Metrics are service-wide totals, while the final reconciliation is for the show created by that run.

Observed output from one run:

```text
hot-seat outcome distribution: {"confirmed": 1, "seat-taken": 499}
same-key replay: 201 True
same-key different body: 409 idempotency-conflict
final reconciliation: {"counts": {"available": 1, "confirmed": 1, "held": 0}, "expected": 2, "holds": true, "reconciled": true, "total": 2}
```

This run produced one confirmation and 499 domain declines, with no 5xx or transport errors. The final seat counts reconcile to two. The replay returned the original reservation (`201 True`), and changing the request under the same key was rejected with 409. In the metrics output, `reservations_declined_total{reason="idempotent-replay"}` increments for that replay even though its HTTP response is 201; the metric is designed to track replays under the declined-reasons family.

## AI usage and next steps

AI was used to read the requirements, draft the plan, implement the API/schema/docs, and review the locking approach. One burst run was performed against the running local API.
