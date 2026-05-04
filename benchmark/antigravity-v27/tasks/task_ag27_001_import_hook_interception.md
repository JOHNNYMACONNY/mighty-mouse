# Task: Import Hook Interception (task_ag27_001)

## Context
We are migrating our codebase to a new API, but many third-party plugins still try to import `legacy_api`. We need to transparently redirect these imports to `modern_api`.

## Request
Implement `register_redirect()` in `bootstrap.py`.
1. It must add a custom finder to `sys.meta_path`.
2. When `find_spec` is called with `fullname == "legacy_api"`, it should return the spec for `modern_api`.
3. You can use `importlib.util.find_spec("modern_api")` to get the target spec.

## Constraints
- ONLY modify `bootstrap.py`.
- Ensure other imports are not affected.

## Verification
Run `python3 test_import_redirect.py`. This script attempts to import `legacy_api` and checks if it actually got `modern_api`.
