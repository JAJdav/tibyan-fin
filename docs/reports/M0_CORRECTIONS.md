# M0 Corrections (manual review of automated findings)

## False positives produced by the profiler heuristics
1. devices.csv "no_timestamp" BLOCKER - INVALID. `first_seen` is a parseable date; TIME_HINT missed the name.
2. monthly_income_sar / opening_balance_sar / expected_monthly_volume_sar "leakage" - INVALID. Matched currency suffix `sar` (Saudi Riyal), not SAR reporting.
3. merchants.cr_expiry_date "future_timestamp" - INVALID. Expiry dates are legitimately future-dated.
4. customers.phone_hash vs merchants.phone_hash "referential_integrity" - NOT a foreign key. Cross-entity collision; the 8 matches are a related-party signal, not a defect.
5. customers.id_type "duplicate_key" - INVALID. Categorical field, not an identifier.
6. devices.is_emulator treated as a label - INVALID. It is a device feature (68/9921 positives).

## CRITICAL finding the profiler MISSED
`gt_role` and `gt_scenario_id` in customers.csv and merchants.csv are generator GROUND TRUTH.
- Forbidden as features/rules/graph inputs (direct label leakage).
- Usable ONLY as labels / evaluation stratification.
- Enforced via config/features/exclusions.v1.yaml.

## Genuine open items
- No transaction fact table exists. ~3170 devices are referenced by no entity, implying a missing transactions file.
- customers.phone_hash contains duplicates -> shared-identity clusters (quantify).
- merchants.kyb_last_review_date / kyb_risk_score require as-of verification before use.
- Dataset is synthetic, Saudi-context (SAR, mada, Asia/Riyadh). All metrics must be disclosed as synthetic.
