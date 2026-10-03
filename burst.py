"""Standard-library concurrent hot-seat client. Run: python burst.py BASE_URL."""
import argparse
import concurrent.futures
import hashlib
import hmac
import json
import os
import urllib.error
import urllib.request
import uuid
from collections import Counter


def token(user_id, secret):
    signature = hmac.new(secret.encode(), user_id.encode(), hashlib.sha256).hexdigest()
    return user_id + "." + signature


def call(url, method="GET", payload=None, headers=None):
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read()
            if not raw:
                body = {}
            elif "json" in response.headers.get("Content-Type", ""):
                body = json.loads(raw)
            else:
                body = raw.decode(errors="replace")
            return response.status, body
    except urllib.error.HTTPError as error:
        raw = error.read()
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = {"error": raw.decode(errors="replace")}
        return error.code, body
    except Exception as error:
        return 0, {"error": str(error)}


def main():
    parser = argparse.ArgumentParser(description="Storm a fresh show with concurrent reservations for one hot seat")
    parser.add_argument("base_url")
    parser.add_argument("--requests", type=int, default=500)
    parser.add_argument("--workers", type=int, default=64)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    admin = os.environ.get("ADMIN_TOKEN")
    secret = os.environ.get("USER_TOKEN_SECRET")
    if not admin or not secret:
        parser.error("set ADMIN_TOKEN and USER_TOKEN_SECRET")
    show_status, show = call(base + "/shows", "POST", {"name": "burst-" + str(uuid.uuid4()), "seats": ["A1", "A2"], "price_paise": 25000, "per_user_limit": 2},
                             {"Authorization": "Bearer " + admin, "Content-Type": "application/json"})
    if show_status != 201:
        raise SystemExit("show creation failed: " + json.dumps(show))
    show_id = show["id"]

    def attempt(index):
        uid = "burst-user-" + str(index)
        idem = "burst-key-" + str(uuid.uuid4())
        status, body = call(base + f"/shows/{show_id}/reserve", "POST", {"seats": ["A1"], "idempotency_key": idem},
                            {"Authorization": "Bearer " + token(uid, secret), "Content-Type": "application/json"})
        if status == 201:
            return "confirmed", {"uid": uid, "key": idem, "body": body}
        if status == 409:
            return body.get("error", "declined"), None
        return ("5xx" if status >= 500 or status == 0 else f"http-{status}"), None

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(args.workers, 256))) as pool:
        results = list(pool.map(attempt, range(args.requests)))
    counts = Counter(name for name, _ in results)
    winner = next((detail for _, detail in results if detail), None)
    print("hot-seat outcome distribution:", json.dumps(dict(counts), sort_keys=True))
    if winner:
        headers = {"Authorization": "Bearer " + token(winner["uid"], secret), "Content-Type": "application/json"}
        replay_status, replay = call(base + f"/shows/{show_id}/reserve", "POST",
                                     {"seats": ["A1"], "idempotency_key": winner["key"]}, headers)
        conflict_status, conflict = call(base + f"/shows/{show_id}/reserve", "POST",
                                         {"seats": ["A2"], "idempotency_key": winner["key"]}, headers)
        print("same-key replay:", replay_status, replay.get("reservation_id") == winner["body"].get("reservation_id"))
        print("same-key different body:", conflict_status, conflict.get("error"))
    state_status, state = call(base + f"/shows/{show_id}")
    if state_status == 200:
        counts_by_state = state["counts"]
        total = sum(counts_by_state.values())
        print("final reconciliation:", json.dumps({"counts": counts_by_state, "total": total,
                                                       "expected": state["total_seats"], "holds": counts_by_state.get("held", 0) == 0,
                                                       "reconciled": total == state["total_seats"]}, sort_keys=True))
    else:
        print("final show read failed:", state_status, state)
    metrics_status, metrics_body = call(base + "/metrics")
    print("metrics endpoint:", metrics_status)
    if metrics_status == 200:
        print(metrics_body)


if __name__ == "__main__":
    main()
