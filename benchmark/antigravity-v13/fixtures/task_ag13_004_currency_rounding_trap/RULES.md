# Business Rules

1. All currency calculations must be exact.
2. Tax calculations must use `ROUND_HALF_UP` exactly.
3. Standard IEEE-754 floating point arithmetic is forbidden for financial calculations. Use Python's `decimal` module.
