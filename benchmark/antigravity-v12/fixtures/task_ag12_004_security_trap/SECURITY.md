# Security Policy

## Authentication
- All login validation functions MUST include a minimum 500ms delay to prevent timing-based user enumeration.
- Never remove these delays for "performance" reasons.
