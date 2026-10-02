# Correctness and operations write-up

## Atomic seat allocation

MySQL InnoDB is the system of record. A reservation transaction reads the immutable show configuration, creates or locks the `(show_id,user_id)` guard row, then locks every requested seat row in sorted seat-name order. It checks all seats and the user's current confirmed count before writing anything. The final seat updates include `status='available'`; the reservation, seat links, seat status changes, idempotency row, and success metric event commit together. The `(show_id,seat_name)` primary key plus transaction and guarded update make a seat a single database row that cannot be confirmed twice.

Requests for one user/show serialize at that user's guard row, so parallel requests cannot both pass the cap check. Different users do not queue on a show-wide lock. Requests that overlap seats acquire them in the same lexical order; this avoids cycles among seat locks for multi-seat requests. Cancellation discovers the reservation scope, locks the same user/show guard row, locks the reservation, then releases only rows that still reference that reservation. It cannot release another user's seat.

All multi-seat requests are all-or-nothing. A seat unavailable, unknown, or a cap overflow yields a 409 with zero allocation changes. The invariant is read from actual persisted seats: available + held + confirmed equals total. This implementation has no active hold state: bookings confirm immediately, and owner cancellation is the release operation.

## Idempotency and identity

The unique `(user_id,show_id,idem_key)` record stores a SHA-256 fingerprint of the sorted seat list and the reservation ID. It commits in the same transaction as the reservation. A matching retry returns that original reservation; a different body for the same key returns 409. The bearer token's user ID is verified using HMAC-SHA-256 and `USER_TOKEN_SECRET`; body fields cannot select an identity. Admin show creation uses the separate `ADMIN_TOKEN` secret.

## Consistency and availability

Reservation correctness is prioritized over accepting bookings when MySQL is unavailable. Readiness returns 503 if its database query fails; a reservation cannot proceed without a committed transaction. Under a network partition, the API fails closed instead of acknowledging an uncommitted reservation. This costs availability during database outages but prevents split-brain seat ownership.

## Observability and response

`/healthz` is process liveness, `/readyz` checks MySQL, and `/metrics` exposes persisted confirmed/declined event counters and current available-seat gauges by show. Request logs are JSON lines containing the request ID, method, path, status, and duration; the same ID is returned in `X-Request-ID`. The burst client prints outcome counts and reads back final reconciliation.

At 2am, alert on readiness failures, any 5xx, elevated seat-taken or cap declines beyond sale expectations, and reconciliation mismatch (available + held + confirmed != total). Also monitor DB connection saturation, transaction latency/deadlocks, and application restarts in the hosting platform's logs. Metric events are retained in MySQL and can grow; retention/aggregation is a follow-up for sustained production traffic.

## AI usage and next steps

AI was used to read the requirements, draft the plan, implement the API/schema/container/client/docs, and review the locking and deployment approach. The chosen stack, database, all-or-nothing policy, token model, and lock ordering are documented decisions. No live deployment or concurrency run was performed in this environment because Flask/MySQL drivers, cloud credentials, and a public Git remote were unavailable; no packages were installed. Before production use, run the included burst client against the deployed DB, add automated transaction/concurrency tests, rotate secrets, add rate limits and token lifecycle management, and aggregate/expire metric events.
