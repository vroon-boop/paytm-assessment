# Agent instructions

## Project

This repository is a Flask JSON API for seat reservations, backed by PostgreSQL. `app.py` contains the API and transaction logic, `schema.sql` defines the database schema, and `init_db.py` applies the schema. `burst.py` is a concurrent API client. Deployment uses Docker Compose locally and Render configuration in `render.yaml`.

## Working in this repository

- Read `README.md` for the API overview and local setup. Use `HELP.md` for the step-by-step manual API walkthrough, `DEPLOYMENT.md` for deployment changes, and `WRITEUP.md` for design rationale and recorded verification details.
- Preserve transaction boundaries, locking, idempotency, ownership checks, and all-or-nothing reservation behavior when changing reservation code or SQL.
- Keep the database schema and application queries consistent. If a schema change is needed, update `schema.sql` and any affected initialization or deployment documentation.
- Keep API responses and status codes consistent with the documented contract. Avoid logging credentials or bearer tokens.
- Keep dependencies in `requirements.txt` and ensure Docker build assumptions in `Dockerfile` stay accurate. Do not install pip packages or OS libraries in the development environment; dependency installation belongs in the container build.
- There is no checked-in automated test suite or test configuration. Do not invent test commands; for changes, use focused manual or static checks where appropriate, and report what was actually verified.

## Common commands

- Start the local stack: `docker compose up --build`
- Run the burst client against a running API: `python3 burst.py http://localhost:8000 --requests 500 --workers 64` (requires `ADMIN_TOKEN` and `USER_TOKEN_SECRET`).

## Change hygiene

- Make the smallest coherent change and update relevant documentation when behavior or operational setup changes.
- Do not commit secrets, generated environment files, virtual environments, or runtime artifacts.
