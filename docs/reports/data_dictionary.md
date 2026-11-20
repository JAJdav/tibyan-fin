# Data Dictionary (M0 - generated)

Generated (UTC): 2026-11-20T09:51:59+00:00
`role_hint` is a **name-based heuristic**. `Business meaning` must be filled by a human.


## `customers.csv`

- SHA256: `90ff741f6155bf2662dcd0d3ad65e84e8cc98e08c019fd12f9f5f970b90d6505`
- Rows profiled: 6000 | Columns: 27
- Time column: `account_open_date` | Span: 2010-12-31 00:00:00 -> 2026-04-20 00:00:00
- PK candidates: ['customer_id', 'national_id_hash', 'iban', 'primary_device_id']

| Column | dtype | Null % | Unique | Role hint | Examples | Business meaning |
|---|---|---|---|---|---|---|
| customer_id | object | 0.0 | 6000 | entity | C100000000, C100000001, C100000002, C100000003, C100000004 | TBD |
| national_id_hash | object | 0.0 | 6000 | unknown | e385314d58cb618b, d1c151673acfc76b, ef900b9aaea0f4fa, d7e71b | TBD |
| id_type | object | 0.0 | 3 | identifier | national_id, iqama, passport | TBD |
| nationality | object | 0.0 | 10 | unknown | SA, PH, SY, JO, EG | TBD |
| age | int64 | 0.0 | 56 | unknown | 43, 21, 41, 37, 32 | TBD |
| dob | object | 0.0 | 4720 | unknown | 1982-09-16, 2004-08-01, 1984-03-25, 1983-11-01, 1988-08-03 | TBD |
| city | object | 0.0 | 10 | unknown | Dammam, Jeddah, Makkah, Abha, Riyadh | TBD |
| account_open_date | object | 0.0 | 2768 | entity | 2024-01-30, 2025-05-24, 2010-12-31, 2025-06-10, 2024-03-13 | TBD |
| kyc_level | object | 0.0 | 3 | unknown | basic, standard, full | TBD |
| kyc_status | object | 0.0 | 3 | unknown | verified, expired, pending | TBD |
| kyc_verified_date | object | 0.0 | 2720 | unknown | 2024-01-31, 2025-05-26, 2011-01-02, 2025-06-11, 2024-03-13 | TBD |
| risk_rating | object | 0.0 | 3 | unknown | low, medium, high | TBD |
| pep_flag | int64 | 0.0 | 2 | unknown | 0, 1 | TBD |
| occupation | object | 0.0 | 8 | unknown | employee_government, self_employed, student, business_owner, | TBD |
| monthly_income_sar | int64 | 0.0 | 5053 | unknown | 17236, 6836, 13773, 9897, 4406 | TBD |
| phone_hash | object | 0.0 | 5994 | entity | 00690a7a7eaf5c8d, cdfeed5d5a668615, d6e242c381a077e8, 73de2b | TBD |
| iban | object | 0.0 | 6000 | unknown | SA4280830166131860913909, SA9210749118625276018955, SA242063 | TBD |
| bank_code | int64 | 0.0 | 10 | unknown | 80, 10, 20, 5, 60 | TBD |
| opening_balance_sar | float64 | 0.0 | 5991 | amount | 5465.74, 13304.86, 55526.14, 16766.37, 7769.82 | TBD |
| gt_role | object | 0.0 | 4 | unknown | normal, family_member, ring_member, refund_abuse_accomplice | TBD |
| gt_scenario_id | object | 87.417 | 168 | identifier | FAM_031, RING_006, FAM_107, FAM_054, FAM_064 | TBD |
| residence_country | object | 0.0 | 1 | unknown | SA | TBD |
| primary_device_id | object | 0.0 | 6000 | entity | D0000000, D0000001, D0000003, D0000004, D0000006 | TBD |
| card_hash_1 | object | 0.0 | 5987 | entity | 196f7b74ed26af3b, a95baf07bdea22b7, 4d04f6f8ba1f8ce0, 804972 | TBD |
| card_scheme_1 | object | 0.0 | 3 | entity | mastercard, mada, visa | TBD |
| card_hash_2 | object | 63.267 | 2204 | entity | 898085655965fae5, b70845f9df3168bb, b2261469d6d0995b, d3586b | TBD |
| card_scheme_2 | object | 63.267 | 2 | entity | visa, mastercard | TBD |


## `devices.csv`

- SHA256: `6ec2e8befce8d42c90bdcbbde9fce71ff246d21e1fbb49953d566adc79b51bab`
- Rows profiled: 9921 | Columns: 11
- Time column: `first_seen` | Span: 2010-12-31 00:00:00 -> 2026-05-16 00:00:00
- PK candidates: ['device_id']

| Column | dtype | Null % | Unique | Role hint | Examples | Business meaning |
|---|---|---|---|---|---|---|
| device_id | object | 0.0 | 9921 | entity | D0000000, D0000001, D0000002, D0000003, D0000004 | TBD |
| device_kind | object | 0.0 | 4 | entity | customer, merchant_console, shared_home, ring_shared | TBD |
| os | object | 0.0 | 5 | unknown | Android, iOS, Windows, Linux, macOS | TBD |
| os_version | object | 0.0 | 21 | unknown | Android 13, iOS 23, Android 14, iOS 20, Android 12 | TBD |
| browser | object | 0.0 | 7 | unknown | Chrome, Safari, App WebView, Samsung Internet, Opera | TBD |
| browser_version | int64 | 0.0 | 10 | unknown | 145, 143, 140, 146, 144 | TBD |
| device_model | object | 0.0 | 19 | entity | Honor 90, iPhone 12, Redmi Note 13, Galaxy A15, Oppo Reno 11 | TBD |
| is_emulator | int64 | 0.0 | 2 | unknown | 0, 1 | TBD |
| language | object | 0.0 | 2 | unknown | ar, en | TBD |
| timezone | object | 0.0 | 2 | unknown | Asia/Riyadh, UTC | TBD |
| first_seen | object | 0.0 | 3414 | unknown | 2024-02-15, 2025-06-23, 2025-06-12, 2011-01-14, 2025-06-18 | TBD |


## `merchants.csv`

- SHA256: `c7c4cf06032bac03c11bc31c8c304900b9bbc427364caf1f120e377dd7c18d31`
- Rows profiled: 748 | Columns: 28
- Time column: `cr_issue_date` | Span: 2014-12-03 00:00:00 -> 2026-01-31 00:00:00
- PK candidates: ['merchant_id', 'cr_number', 'vat_number', 'phone_hash', 'iban', 'console_device_id']

| Column | dtype | Null % | Unique | Role hint | Examples | Business meaning |
|---|---|---|---|---|---|---|
| merchant_id | object | 0.0 | 748 | entity | M100000000, M100000001, M100000002, M100000003, M100000004 | TBD |
| legal_name | object | 0.0 | 564 | unknown | Al Amal Gold LLC, Rawabi Supermarket Est., Qimam Boutique Es | TBD |
| legal_form | object | 0.0 | 4 | unknown | llc, sole_establishment, branch_foreign, simplified_jsc | TBD |
| city | object | 0.0 | 10 | unknown | Abha, Riyadh, Dammam, Jeddah, Taif | TBD |
| cr_number | int64 | 0.0 | 748 | unknown | 5855095858, 1010082521, 2050275849, 1010738003, 1010908005 | TBD |
| cr_issue_date | object | 0.0 | 670 | unknown | 2022-05-02, 2020-05-27, 2019-09-20, 2022-08-21, 2021-03-06 | TBD |
| cr_expiry_date | object | 0.0 | 678 | unknown | 2023-05-02, 2022-05-27, 2020-09-19, 2023-08-21, 2026-03-05 | TBD |
| cr_status | object | 0.0 | 1 | unknown | active | TBD |
| vat_number | int64 | 0.0 | 748 | unknown | 309576479733193, 362001219149603, 377657952724433, 303010711 | TBD |
| vat_registered | int64 | 0.0 | 2 | unknown | 1, 0 | TBD |
| declared_category | object | 0.0 | 16 | unknown | jewelry_gold, groceries, apparel, pharmacy_health, beauty_pe | TBD |
| mcc | int64 | 0.0 | 16 | unknown | 5944, 5411, 5651, 5912, 5977 | TBD |
| onboarding_date | object | 0.0 | 659 | unknown | 2022-08-16, 2021-04-10, 2019-10-01, 2022-11-30, 2021-05-08 | TBD |
| kyb_status | object | 0.0 | 3 | unknown | pending_documents, verified, simplified_review | TBD |
| kyb_risk_score | float64 | 0.0 | 363 | unknown | 0.201, 0.158, 0.071, 0.064, 0.308 | TBD |
| kyb_last_review_date | object | 0.0 | 660 | unknown | 2022-10-26, 2021-07-05, 2019-11-14, 2022-12-01, 2021-07-25 | TBD |
| expected_monthly_volume_sar | int64 | 0.0 | 743 | unknown | 144598, 30902, 22964, 83768, 10972 | TBD |
| employees_band | object | 0.0 | 4 | unknown | 6-20, 21-100, 1-5, 100+ | TBD |
| has_physical_store | int64 | 0.0 | 2 | unknown | 1, 0 | TBD |
| email_domain_type | object | 0.0 | 2 | entity | business, free_mail | TBD |
| phone_hash | object | 0.0 | 748 | entity | e9719975b6695284, ee0d63097a6da332, 3536325fe0a98cfa, 06c9f3 | TBD |
| iban | object | 0.0 | 748 | unknown | SA4210266590790417651780, SA3180540396120347994581, SA631012 | TBD |
| settlement_bank_code | int64 | 0.0 | 20 | unknown | 10, 80, 5, 30, 55 | TBD |
| cr_director_id_hash | object | 0.0 | 706 | unknown | a7224c386e37a2f5, 61646ac87f7b0432, eec4cc288a3bf818, e1e836 | TBD |
| cr_director_pep_flag | int64 | 0.0 | 2 | unknown | 0, 1 | TBD |
| gt_role | object | 0.0 | 5 | unknown | normal, high_refund_legit_store, seasonal_spike_established_ | TBD |
| gt_scenario_id | object | 93.583 | 48 | identifier | RING_000, RING_001, RING_002, RING_003, RING_004 | TBD |
| console_device_id | object | 0.0 | 748 | entity | D0009006, D0009007, D0009008, D0009009, D0009010 | TBD |
