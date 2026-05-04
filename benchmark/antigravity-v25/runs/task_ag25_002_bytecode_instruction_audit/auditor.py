import dis
def is_pure(func):
    try:
        for instr in dis.get_instructions(func):
            if instr.opname in ('STORE_GLOBAL', 'DELETE_GLOBAL'): return False
        return True
    except: return False