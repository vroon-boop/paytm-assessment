# Implementation plan

## Decisions

- **Framework:** Flask with Python, as requested.
- **Database:** MySQL. Shows, seats, reservations, users, and idempotency records are relational. Transactions, row locks, foreign keys, and unique constraints make seat ownership and the per-user limit explicit.
- **Reservation policy:** all-or-nothing for multi-seat requests. If any requested seat is unavailable or the user cap would be exceeded, no seats are reserved.
- **Reservation lifecycle:** confirm at reservation time and allow owner-only cancellation. This provides an explicit release path without introducing payment or hold-expiry semantics.
- **Identity:** bearer token is resolved to a user ID by the service. A body-supplied user ID never affects authorization.
- **Local persistence:** the app connects directly to MySQL through an already installed DB-API driver. No package installation is part of this work.

## Incremental commits

1. `docs: record implementation plan and correctness decisions` — preserve these decisions and the commit sequence before implementation.
2. `feat: add Flask service and MySQL schema` — configuration, schema, health/readiness, authentication, show creation/state.
3. `feat: implement atomic idempotent reservations` — transaction/locking protocol, per-user cap, idempotency replay/conflict, owner cancellation.
4. `feat: expose reservation metrics and request logs` — Prometheus exposition, outcome counters, available-seat gauge, correlation IDs and structured logs.
5. `feat: add deployment container and burst client` — Docker/Compose and a one-command concurrent client that reports outcome counts and reconciliation.
6. `docs: add deployment and operations guide` — actionable free-tier deployment steps, README instructions, and correctness/operations write-up.

## Correctness protocol

- Serialize allocation per show by locking its row; lock candidate seat rows in sorted seat-name order and user reservation rows consistently. Check the idempotency key and cap inside the same transaction.
- Validate the complete requested set before changing any seat, then commit the reservation and idempotency result together.
- Add database unique constraints for one seat per show and one idempotency key per user/show; guarded status transitions and transactional locking are the final allocation authority.
- Reconcile seat counts from persisted seat state. Cancel only a reservation owned by the authenticated user and transition its confirmed seats in the same transaction.

## Deployment and verification constraints

- Do not install pip packages or OS libraries. Inspect the runtime for Flask and MySQL drivers and use only what is already present; otherwise document the exact runtime requirement without silently changing database/framework.
- Include reproducible deployment instructions for a free-tier app host and managed MySQL service. State costs/availability caveats and list every environment variable and command. Do not claim a live deployment absent credentials and a remote repository.
- Implement assessment-required burst tooling and inspect/verify the implementation without installing dependencies.
