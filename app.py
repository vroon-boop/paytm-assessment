"""Flask JSON API for concurrency-safe event seat reservations."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import ssl
import uuid
from datetime import datetime, timezone

from flask import Flask, g, jsonify, request, Response
from werkzeug.exceptions import HTTPException

try:
    import pymysql
    from pymysql.cursors import DictCursor
except ImportError:  # The app can be imported for tooling; database use reports a clear error.
    pymysql = None
    DictCursor = None

app = Flask(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")
log = logging.getLogger("seat_service")


def db_connect():
    if pymysql is None:
        raise RuntimeError("PyMySQL is required at runtime; install the declared requirements")
    required = ("DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME")
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise RuntimeError("Missing database configuration: " + ", ".join(missing))
    tls_context = None
    if os.getenv("DB_SSL_CA"):
        tls_context = ssl.create_default_context(cafile=os.environ["DB_SSL_CA"])
    return pymysql.connect(
        host=os.environ["DB_HOST"], port=int(os.getenv("DB_PORT", "3306")),
        user=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"],
        database=os.environ["DB_NAME"], charset="utf8mb4", autocommit=False,
        connect_timeout=5, read_timeout=15, write_timeout=15,
        cursorclass=DictCursor, ssl=tls_context,
    )


def get_db():
    if "db" not in g:
        g.db = db_connect()
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def fail(message, status):
    return jsonify({"error": message, "request_id": g.request_id}), status


@app.before_request
def assign_request_id():
    incoming = request.headers.get("X-Request-ID", "")
    g.request_id = incoming[:128] if incoming and re.fullmatch(r"[\w.-]{1,128}", incoming) else str(uuid.uuid4())
    g.started_at = datetime.now(timezone.utc)


@app.after_request
def log_request(response):
    duration_ms = (datetime.now(timezone.utc) - g.started_at).total_seconds() * 1000
    log.info(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), "request_id": g.request_id,
                         "method": request.method, "path": request.path, "status": response.status_code,
                         "duration_ms": round(duration_ms, 2)}, separators=(",", ":")))
    response.headers["X-Request-ID"] = g.request_id
    return response


def token_user():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:]
    try:
        uid, supplied = token.rsplit(".", 1)
    except ValueError:
        return None
    secret = os.getenv("USER_TOKEN_SECRET", "")
    if (not secret or not uid or len(uid) > 128 or
            not hmac.compare_digest(supplied, hmac.new(secret.encode(), uid.encode(), hashlib.sha256).hexdigest())):
        return None
    return uid


def admin_required():
    return bool(os.getenv("ADMIN_TOKEN")) and hmac.compare_digest(
        request.headers.get("Authorization", ""), "Bearer " + os.getenv("ADMIN_TOKEN", "")
    )


def json_body():
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else None


def record_outcome(conn, reason, show_id=None):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO metric_events (event_type, reason, show_id) VALUES ('declined', %s, %s)", (reason, show_id))


def domain_decline(conn, reason, status, show_id=None):
    record_outcome(conn, reason, show_id)
    conn.commit()
    return fail(reason, status)


@app.get("/healthz")
def health():
    return jsonify({"status": "ok"}), 200


@app.get("/readyz")
def ready():
    try:
        with get_db().cursor() as cur:
            cur.execute("SELECT 1 AS ok FROM shows LIMIT 1")
            cur.fetchone()
        return jsonify({"status": "ready"}), 200
    except Exception:
        log.exception("readiness check failed")
        return fail("database unavailable", 503)


@app.post("/shows")
def create_show():
    if not admin_required():
        return fail("admin authentication required", 401)
    body = json_body()
    if not body or not isinstance(body.get("name"), str) or not body["name"].strip():
        return fail("name is required", 400)
    seats = body.get("seats")
    price = body.get("price_paise")
    limit = body.get("per_user_limit", 4)
    if (not isinstance(seats, list) or not seats or
            any(not isinstance(s, str) or not s or len(s) > 32 for s in seats) or len(seats) != len(set(seats))):
        return fail("seats must be a non-empty list of unique seat names", 400)
    if (type(price) is not int or price < 0 or price > 2**63 - 1 or
            type(limit) is not int or limit < 1 or limit > len(seats)):
        return fail("price_paise must be a non-negative integer and per_user_limit a positive integer", 400)
    if len(body["name"].strip()) > 160:
        return fail("name must be at most 160 characters", 400)
    conn = get_db()
    show_id = str(uuid.uuid4())
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO shows (id, name, price_paise, per_user_limit, total_seats) VALUES (%s,%s,%s,%s,%s)",
                        (show_id, body["name"].strip(), price, limit, len(seats)))
            cur.executemany("INSERT INTO seats (show_id, seat_name, status) VALUES (%s,%s,'available')",
                            [(show_id, seat) for seat in sorted(seats)])
        conn.commit()
    except Exception:
        conn.rollback()
        log.exception("show creation failed")
        return fail("could not create show", 500)
    return jsonify({"id": show_id, "name": body["name"].strip(), "price_paise": price,
                    "per_user_limit": limit, "total_seats": len(seats),
                    "seats": [{"seat": s, "status": "available"} for s in sorted(seats)]}), 201


@app.get("/shows/<show_id>")
def show_state(show_id):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("SELECT id,name,price_paise,per_user_limit,total_seats FROM shows WHERE id=%s", (show_id,))
        show = cur.fetchone()
        if not show:
            return fail("show not found", 404)
        cur.execute("SELECT seat_name,status FROM seats WHERE show_id=%s ORDER BY seat_name", (show_id,))
        seats = cur.fetchall()
    counts = {state: sum(1 for seat in seats if seat["status"] == state) for state in ("available", "held", "confirmed")}
    return jsonify({**show, "seats": [{"seat": s["seat_name"], "status": s["status"]} for s in seats],
                    "counts": counts, "total_seats": len(seats)})


@app.post("/shows/<show_id>/reserve")
def reserve(show_id):
    user_id = token_user()
    if not user_id:
        return fail("valid bearer token required", 401)
    body = json_body()
    seats = body.get("seats") if body else None
    idem = request.headers.get("Idempotency-Key") or (body.get("idempotency_key") if body else None)
    if not isinstance(seats, list) or not seats or any(not isinstance(s, str) for s in seats):
        return fail("seats must be a non-empty list of seat names", 400)
    if len(seats) != len(set(seats)) or any(not s or len(s) > 32 for s in seats):
        return fail("duplicate seat names are not allowed", 400)
    if len(seats) > 100:
        return fail("at most 100 seats may be requested at once", 400)
    if not isinstance(idem, str) or not idem or len(idem) > 128:
        return fail("Idempotency-Key header or idempotency_key is required", 400)
    requested = sorted(seats)
    fingerprint = hashlib.sha256(json.dumps(requested, separators=(",", ":")).encode()).hexdigest()
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id,price_paise,per_user_limit FROM shows WHERE id=%s", (show_id,))
            show = cur.fetchone()
            if not show:
                return fail("show not found", 404)
            # One lock row per (show,user) serializes only that user's cap checks.
            cur.execute("INSERT IGNORE INTO show_user_locks (show_id,user_id) VALUES (%s,%s)", (show_id, user_id))
            cur.execute("SELECT user_id FROM show_user_locks WHERE show_id=%s AND user_id=%s FOR UPDATE", (show_id, user_id))
            cur.execute("SELECT fingerprint,reservation_id FROM idempotency_keys WHERE user_id=%s AND show_id=%s AND idem_key=%s FOR UPDATE",
                        (user_id, show_id, idem))
            prior = cur.fetchone()
            if prior:
                if prior["fingerprint"] != fingerprint:
                    return domain_decline(conn, "idempotency-conflict", 409, show_id)
                cur.execute("INSERT INTO metric_events (event_type,reason,show_id) VALUES ('declined','idempotent-replay',%s)", (show_id,))
                conn.commit()
                cur.execute("SELECT id AS reservation_id,show_id,user_id,amount_paise,status FROM reservations WHERE id=%s", (prior["reservation_id"],))
                reservation = cur.fetchone()
                if reservation:
                    cur.execute("SELECT seat_name FROM reservation_seats WHERE reservation_id=%s ORDER BY seat_name", (reservation["reservation_id"],))
                    reservation["seats"] = [row["seat_name"] for row in cur.fetchall()]
                    reservation["replayed"] = True
                    return jsonify(reservation), 201
                return fail("idempotency record is inconsistent", 500)
            cur.execute("SELECT seat_name,status FROM seats WHERE show_id=%s AND seat_name IN (%s) ORDER BY seat_name FOR UPDATE" %
                        ("%s", ",".join(["%s"] * len(requested))), (show_id, *requested))
            rows = cur.fetchall()
            if len(rows) != len(requested):
                return domain_decline(conn, "seat-not-found", 409, show_id)
            if any(row["status"] != "available" for row in rows):
                return domain_decline(conn, "seat-taken", 409, show_id)
            cur.execute("SELECT COUNT(*) AS n FROM reservation_seats rs JOIN reservations r ON r.id=rs.reservation_id "
                        "WHERE r.show_id=%s AND r.user_id=%s AND r.status='confirmed'", (show_id, user_id))
            booked = cur.fetchone()["n"]
            if booked + len(requested) > show["per_user_limit"]:
                return domain_decline(conn, "per-user-limit", 409, show_id)
            reservation_id = str(uuid.uuid4())
            cur.execute("INSERT INTO reservations (id,show_id,user_id,amount_paise,status) VALUES (%s,%s,%s,%s,'confirmed')",
                        (reservation_id, show_id, user_id, show["price_paise"] * len(requested)))
            cur.executemany("INSERT INTO reservation_seats (reservation_id,show_id,seat_name) VALUES (%s,%s,%s)",
                            [(reservation_id, show_id, seat) for seat in requested])
            cur.execute("UPDATE seats SET status='confirmed', reservation_id=%s WHERE show_id=%s AND seat_name IN (%s) AND status='available'" %
                        ("%s", ",".join(["%s"] * len(requested))), (reservation_id, show_id, *requested))
            if cur.rowcount != len(requested):
                conn.rollback()
                # With the show lock this should not occur. If it does, report a domain conflict.
                with conn.cursor() as metric_cur:
                    metric_cur.execute("INSERT INTO metric_events (event_type,reason,show_id) VALUES ('declined','seat-taken',%s)", (show_id,))
                conn.commit()
                return fail("seat-taken", 409)
            cur.execute("INSERT INTO idempotency_keys (user_id,show_id,idem_key,fingerprint,reservation_id) VALUES (%s,%s,%s,%s,%s)",
                        (user_id, show_id, idem, fingerprint, reservation_id))
            cur.execute("INSERT INTO metric_events (event_type,reason,show_id) VALUES ('confirmed','confirmed',%s)", (show_id,))
        conn.commit()
        return jsonify({"reservation_id": reservation_id, "show_id": show_id, "user_id": user_id,
                        "seats": requested, "amount_paise": show["price_paise"] * len(requested), "status": "confirmed"}), 201
    except Exception as error:
        conn.rollback()
        if pymysql is not None and isinstance(error, pymysql.err.OperationalError) and error.args and error.args[0] in (1205, 1213):
            with conn.cursor() as cur:
                cur.execute("INSERT INTO metric_events (event_type,reason,show_id) VALUES ('declined','reservation-contention',%s)", (show_id,))
            conn.commit()
            return fail("reservation-contention", 409)
        log.exception("reservation transaction failed")
        return fail("reservation could not be processed", 500)


@app.post("/reservations/<reservation_id>/cancel")
def cancel(reservation_id):
    user_id = token_user()
    if not user_id:
        return fail("valid bearer token required", 401)
    conn = get_db()
    try:
        with conn.cursor() as cur:
            # Discover scope without a lock, then follow the same user-lock-first order as booking.
            cur.execute("SELECT show_id FROM reservations WHERE id=%s AND user_id=%s", (reservation_id, user_id))
            owner_row = cur.fetchone()
            if not owner_row:
                return fail("reservation not found", 404)
            cur.execute("INSERT IGNORE INTO show_user_locks (show_id,user_id) VALUES (%s,%s)", (owner_row["show_id"], user_id))
            cur.execute("SELECT user_id FROM show_user_locks WHERE show_id=%s AND user_id=%s FOR UPDATE", (owner_row["show_id"], user_id))
            cur.execute("SELECT show_id,status FROM reservations WHERE id=%s AND user_id=%s FOR UPDATE", (reservation_id, user_id))
            reservation = cur.fetchone()
            if not reservation:
                return fail("reservation not found", 404)
            if reservation["status"] == "cancelled":
                conn.commit()
                return jsonify({"reservation_id": reservation_id, "status": "cancelled"})
            cur.execute("UPDATE seats SET status='available',reservation_id=NULL WHERE reservation_id=%s AND status='confirmed'", (reservation_id,))
            cur.execute("UPDATE reservations SET status='cancelled' WHERE id=%s AND status='confirmed'", (reservation_id,))
        conn.commit()
        return jsonify({"reservation_id": reservation_id, "status": "cancelled"})
    except Exception:
        conn.rollback()
        log.exception("cancellation failed")
        return fail("cancellation could not be processed", 500)


@app.get("/metrics")
def metrics():
    try:
        with get_db().cursor() as cur:
            cur.execute("SELECT reason,COUNT(*) AS n FROM metric_events WHERE event_type='confirmed' GROUP BY reason")
            confirmed = sum(row["n"] for row in cur.fetchall())
            cur.execute("SELECT reason,COUNT(*) AS n FROM metric_events WHERE event_type='declined' GROUP BY reason")
            declined = {row["reason"]: row["n"] for row in cur.fetchall()}
            cur.execute("SELECT show_id,status,COUNT(*) AS n FROM seats GROUP BY show_id,status")
            gauges = cur.fetchall()
        lines = ["# HELP reservations_confirmed_total Confirmed reservation operations.",
                 "# TYPE reservations_confirmed_total counter", f"reservations_confirmed_total {confirmed}",
                 "# HELP reservations_declined_total Declined reservation operations and idempotent replays by reason.",
                 "# TYPE reservations_declined_total counter"]
        for reason in ("seat-taken", "per-user-limit", "idempotent-replay", "idempotency-conflict", "seat-not-found", "reservation-contention"):
            lines.append(f'reservations_declined_total{{reason="{reason}"}} {declined.get(reason, 0)}')
        lines += ["# HELP seats_available Current available seats.", "# TYPE seats_available gauge"]
        totals = {}
        for row in gauges:
            totals.setdefault(row["show_id"], {})[row["status"]] = row["n"]
        for sid, states in sorted(totals.items()):
            lines.append(f'seats_available{{show_id="{sid}"}} {states.get("available", 0)}')
        return Response("\n".join(lines) + "\n", mimetype="text/plain; version=0.0.4")
    except Exception:
        log.exception("metrics query failed")
        return fail("metrics unavailable", 503)


@app.errorhandler(Exception)
def unhandled(error):
    if isinstance(error, HTTPException):
        return fail(error.name.lower().replace(" ", "_"), error.code)
    log.exception("unhandled request error", exc_info=error)
    return fail("internal server error", 500)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
