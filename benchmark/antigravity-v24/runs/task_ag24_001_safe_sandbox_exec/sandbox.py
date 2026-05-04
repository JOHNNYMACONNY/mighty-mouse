import math
def run_safe(code_str):
    safe_globals = {'math': math, 'abs': abs, '__builtins__': {}}
    local_vars = {}
    try:
        exec(code_str, safe_globals, local_vars)
        return local_vars.get('result')
    except: raise