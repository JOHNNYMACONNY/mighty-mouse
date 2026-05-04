import shared_data
from contextlib import contextmanager
@contextmanager
def scoped_buffer(temp_data):
    old = shared_data.BUFFER
    try:
        shared_data.BUFFER = temp_data
        yield
    finally:
        shared_data.BUFFER = old