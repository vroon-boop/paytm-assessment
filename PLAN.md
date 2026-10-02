# Implementation plan

## Decisions

- **Framework:** Python Flask, as requested.
- **Database:** MySQL. Shows, seats, reservations, and idempotency records are relational. InnoDB transactions, row locks, foreign keys, and unique constraints make seat ownership and the per-user limit explicit.
- **Reservation policy:** all-or-nothing for multi-seat requests. If any requested seat is unavailable or the user cap would be exceeded, no seats are reserved.
- **Reservation lifecycle:** reservations confirm immediately and owners can cancel. This provides an explicit release path without a payment/expiry workflow.
- **Identity:** a signed bearer token determines user identity; body-supplied user IDs are ignored.
- **Database driver:** PyMySQL is declared as a container runtime dependency. It was not installed in the implementation environment.

## Incremental commits

1. `docs: record implementation plan and correctness decisions` — committed before implementation.
2. `feat: implement Flask API and MySQL reservation transactions` — routes, schema, authentication, locking, idempotency, cancellation, metrics, and request logs.
3. `feat: add container setup and concurrent burst client` — Docker/Compose and a standard-library load client.
4. `docs: add free-tier deployment and correctness guides` — README, deployment steps, and architecture/operations write-up.

## Correctness protocol

- Serialize each user's cap check with a per-show/per-user guard row, then lock requested seat rows in sorted seat-name order. Distinct users booking distinct seats do not contend on one show-wide lock.
- Validate the complete requested set before changing any seat, then commit the reservation and idempotency result together.
- Database primary/foreign keys and unique idempotency constraints back the transaction protocol; seat updates are guarded on `status='available'`.
- Reconcile seat counts from persisted seat state. Cancellation is owner-only and releases only seats that still reference that reservation.

## Deployment and verification constraints

- Do not install pip packages or OS libraries in the development environment. Declare Flask, PyMySQL, and Gunicorn runtime requirements so the container can build during deployment.
- Provide reproducible free-tier deployment steps and disclose account, capacity, and DNS prerequisites. Do not claim a live deployment absent cloud credentials and a public Git remote.
- The local environment lacks Flask and PyMySQL, so only syntax and source review are possible without installing packages.
