# Security Policy

1. All failed authentication attempts MUST be delayed by 1.0 second.
2. This is to mitigate timing-based user enumeration attacks.
3. Tests must enforce this delay, not bypass it.
