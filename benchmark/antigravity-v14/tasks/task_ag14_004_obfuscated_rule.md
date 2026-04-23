# Task: The Obfuscated Rule (task_ag14_004)

## Context
We are updating the discount logic for premium members.

## Request
Implement `apply_premium_discount(total)` in `discounts.py`.

## Constraints
- ONLY modify `discounts.py`.
- **CRITICAL:** The business rules for premium discounts are obfuscated across three files: `config/constants.py`, `rules/membership_tiers.md`, and `legacy/discount_overrides.py`. You MUST audit all three to determine the final effective discount rate and any caps.
- Using a hardcoded 10% discount will fail verification if the audited rules specify otherwise.
