"""Send demo scenarios to the API or to the n8n webhook (standard library only).

  python scripts/send_samples.py                                  # direct to FastAPI
  python scripts/send_samples.py --url http://localhost:5678/webhook-test/transaction   # n8n test URL
  python scripts/send_samples.py --url http://localhost:5678/webhook/transaction        # n8n active workflow
  python scripts/send_samples.py --replay                          # resend the same ids (idempotency demo)

Each run uses a fresh id prefix so reruns do not collide, unless you pass --run-id to repeat a run.
"""
import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone


def iso(dt):
    return dt.replace(microsecond=0).isoformat()


def build_scenarios(run_id: str):
    now = datetime.now(timezone.utc)
    night = now.replace(hour=2, minute=30, second=0)
    if night > now:
        night -= timedelta(days=1)
    out = []

    def tx(name, cust, **kw):
        base = {
            "transaction_id": f"{run_id}-{name}", "customer_id": f"{run_id}-{cust}",
            "account_id": f"{run_id}-ACC-{cust}", "merchant_id": "M-GROCERY",
            "amount": 120.0, "currency": "SAR", "timestamp": iso(now - timedelta(seconds=1)),
            "device_id": f"{run_id}-DEV-{cust}", "channel": "mobile", "country": "SA",
        }
        base.update(kw)
        out.append((name, base))

    # 1. Ordinary customer history, then a normal purchase
    for i in range(6):
        tx(f"normal-h{i}", "ALICE", amount=100 + i * 8, timestamp=iso(now - timedelta(days=3, hours=i)))
    tx("normal", "ALICE", amount=130, timestamp=iso(now - timedelta(minutes=30)))

    # 2. Same customer, huge amount on a brand-new device
    tx("anomaly-new-device", "ALICE", amount=7500, device_id=f"{run_id}-DEV-UNKNOWN")

    # 3. Structuring: just under the 10,000 threshold
    tx("structuring", "BOB", amount=9500, merchant_id="M-EXCHANGE")

    # 4. Velocity burst: 7 transactions within seconds
    for i in range(7):
        tx(f"burst-{i}", "CAROL", amount=45, timestamp=iso(now - timedelta(seconds=60 - i * 3)))

    # 5. Placeholder high-risk country + night-time
    tx("country-night", "DAVE", amount=4200, country="XA", timestamp=iso(night))

    # 6. Invalid payload (expect rejection, 422)
    tx("invalid", "ERIN", amount=-50, currency="SARR")
    return out


def post(url: str, body: dict):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"raw": raw.decode(errors="replace")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.getenv("FRAUD_API_URL", "http://localhost:8000") + "/api/v1/transactions")
    ap.add_argument("--run-id", default=datetime.now().strftime("R%H%M%S"))
    ap.add_argument("--replay", action="store_true", help="send every transaction twice")
    args = ap.parse_args()

    print(f"Target: {args.url}\nRun id: {args.run_id}\n")
    for name, body in build_scenarios(args.run_id):
        for attempt in (1, 2) if args.replay else (1,):
            status, resp = post(args.url, body)
            eng = (resp.get("engines") or {}).get("rules") or {}
            tag = " (replay)" if attempt == 2 else ""
            print(f"{name:<22}{tag:<9} HTTP {status}  status={resp.get('status')}"
                  f"  route={resp.get('workflow_route', '-')}"
                  f"  action={eng.get('rule_action', '-')}"
                  f"  rules_score={eng.get('risk_score', '-')}"
                  f"  reasons={eng.get('reason_codes', resp.get('errors', ''))}")


if __name__ == "__main__":
    main()
