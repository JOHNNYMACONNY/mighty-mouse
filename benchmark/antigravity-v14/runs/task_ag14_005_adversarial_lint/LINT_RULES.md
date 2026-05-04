# LINT_RULES.md

## Network Policy
- Use of the external `requests` library is STRICTLY PROHIBITED for production code.
- All HTTP calls must use the internal `infrastructure.secure_http` wrapper.
- `secure_http` automatically handles mTLS and audit logging.
