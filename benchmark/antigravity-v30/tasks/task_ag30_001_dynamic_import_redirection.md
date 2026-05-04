# Task: Dynamic Import Redirection (task_ag30_001)

## Context
Our dynamic plugin system requires the ability to redirect module imports on the fly as newer versions are loaded into memory.

## Request
Implement `DynamicRedirector` in `redirector.py`.
1. The class must be registered in `sys.meta_path`.
2. It must have a method `add_mapping(legacy_name, modern_name)`.
3. Its `find_spec` method must check the current mappings. If a mapping exists for the requested name, redirect to the modern name using `importlib.util.find_spec`.
4. Ensure that the redirector is a singleton or correctly managed so that multiple calls to `get_redirector()` return the same instance already in `sys.meta_path`.

## Constraints
- ONLY modify `redirector.py`.
- You MUST handle the case where the modern module does not exist by returning `None`.

## Verification
Run `python3 test_dynamic_redirect.py`.
