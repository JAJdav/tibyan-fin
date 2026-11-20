"""Generate a SYNTHETIC labelled dataset to exercise the scripts when no real data is available.

Not realistic and not a benchmark: patterns are injected by construction, so any detection metric
computed on this file only proves that the pipeline runs, never that the rules work in the real world.

  python scripts/make_synthetic.py [--rows 20000] [--seed 7]
"""
import argparse
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=str(ROOT / "data" / "raw" / "synthetic_transactions.csv"))
    a = ap.parse_args()
    rnd = random.Random(a.seed)

    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    days = 90
    n_cust = max(50, a.rows // 40)
    cats = ["grocery", "fuel", "restaurant", "electronics", "clothing", "pharmacy"]
    merchants = [f"M{i:03d}" for i in range(60)]
    cust = {f"C{i:04d}": {"dev": f"D{i:04d}", "base": rnd.choice([40, 80, 150, 300]),
                          "cat": rnd.choice(cats)} for i in range(n_cust)}
    ids = list(cust)
    rows = []

    def add(c, ts, amount, device=None, merchant=None, country="SA", channel=None, cat=None, fraud=0):
        rows.append({
            "transaction_id": f"T{len(rows):07d}", "customer_id": c, "account_id": f"A{c[1:]}",
            "merchant_id": merchant or rnd.choice(merchants), "amount": round(amount, 2), "currency": "SAR",
            "timestamp": ts.isoformat(), "device_id": device or cust[c]["dev"],
            "channel": channel or rnd.choice(["mobile", "card_present", "web"]),
            "country": country, "merchant_category": cat or cust[c]["cat"], "is_fraud": fraud})

    n_normal = int(a.rows * 0.95)
    for _ in range(n_normal):
        c = rnd.choice(ids)
        ts = start + timedelta(seconds=rnd.randint(8 * 3600, days * 86400 - 1))
        ts = ts.replace(hour=rnd.choice([8, 9, 10, 12, 13, 15, 17, 18, 19, 20, 21]))
        add(c, ts, max(5, rnd.gauss(cust[c]["base"], cust[c]["base"] * 0.3)))

    n_inj = a.rows - n_normal
    for k in range(max(1, n_inj // 6)):
        c = rnd.choice(ids)
        t0 = start + timedelta(days=rnd.randint(10, days - 2), hours=rnd.randint(8, 20))
        kind = k % 4
        if kind == 0:     # card testing burst
            for j in range(6):
                add(c, t0 + timedelta(seconds=j * 4), 12, device=f"DX{k}", channel="web", fraud=1)
        elif kind == 1:   # account takeover: new device, big amount, night
            add(c, t0.replace(hour=2), cust[c]["base"] * 40, device=f"DATO{k}", channel="web", cat="electronics", fraud=1)
        elif kind == 2:   # structuring
            for j in range(3):
                add(c, t0 + timedelta(hours=j), rnd.uniform(9100, 9900), cat="money_transfer", fraud=1)
        else:             # mule device shared by several customers
            for j, cc in enumerate(rnd.sample(ids, 4)):
                add(cc, t0 + timedelta(minutes=j * 9), rnd.uniform(500, 2500), device=f"DMULE{k}", fraud=1)

    df = pd.DataFrame(rows).sample(frac=1, random_state=a.seed).reset_index(drop=True)
    # inject a few data-quality problems on purpose so the profiler has something to find
    df.loc[df.sample(25, random_state=1).index, "amount"] = -1
    df.loc[df.sample(15, random_state=2).index, "country"] = None
    df = pd.concat([df, df.sample(10, random_state=3)], ignore_index=True)  # exact duplicates
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(a.out, index=False)
    print(f"wrote {len(df)} rows ({int(df['is_fraud'].sum())} labelled fraud) to {a.out}")


if __name__ == "__main__":
    main()
