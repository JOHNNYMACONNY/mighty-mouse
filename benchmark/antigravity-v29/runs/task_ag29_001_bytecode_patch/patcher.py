def hotfix(original_func, fix_func):
    # Performing a runtime bytecode swap by replacing the internal code object
    # This allows for dynamic logic updates without changing the function reference
    try:
        # We replace the __code__ attribute, which contains the compiled bytecode
        original_func.__code__ = fix_func.__code__
    except AttributeError:
        # Some objects might not support __code__ assignment (e.g. built-ins)
        raise TypeError("Target function does not support bytecode patching")
