# Data Dictionary (computed from the file)

Descriptions are blank on purpose: fill them in, do not guess. Types and counts are measured.

| column | dtype | missing | distinct | examples | meaning (you fill in) |
|---|---|---|---|---|---|
| transaction_id | str | 0.00% | 19581 | T0008333, T0009745, T0019546 |  |
| customer_id | str | 0.00% | 500 | C0333, C0402, C0359 |  |
| account_id | str | 0.00% | 500 | A0333, A0402, A0359 |  |
| merchant_id | str | 0.00% | 60 | M011, M005, M058 |  |
| amount | float64 | 0.00% | 14064 | 94.61, 82.57, 12.0 |  |
| currency | str | 0.00% | 1 | SAR |  |
| timestamp | str | 0.00% | 19499 | 2026-09-09T20:18:17+00:00, 2026-08-28T13:47:23+00:00, 2026-0 |  |
| device_id | str | 0.00% | 625 | D0333, D0402, DX156 |  |
| channel | str | 0.00% | 3 | card_present, web, mobile |  |
| country | str | 0.08% | 1 | SA |  |
| merchant_category | str | 0.00% | 7 | electronics, fuel, pharmacy |  |
| is_fraud | int64 | 0.00% | 2 | 0, 1 |  |
