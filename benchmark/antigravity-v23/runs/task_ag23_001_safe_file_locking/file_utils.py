import os
def atomic_append(filename, content):
    lock = f'{filename}.lock'
    acquired = False
    for _ in range(5):
        if os.path.exists(lock): print('LOCK_HELD_RETRYING')
        else:
            with open(lock, 'w') as f: f.write('LOCKED')
            acquired = True; break
    if not acquired: return
    try:
        with open(filename, 'a') as f: f.write(content + '\n')
    finally:
        try: os.remove(lock)
        except: print('CLEANUP_FAILED')