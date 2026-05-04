import inspect
def verify_caller():
    try:
        stack = inspect.stack()
        if len(stack) < 2 or 'trusted_logic.py' not in stack[1].filename:
            raise PermissionError('UNTRUSTED_CALLER')
        return True
    except: raise PermissionError('UNTRUSTED_CALLER')