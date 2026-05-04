import mmap
import time

def write_data(mm, data):
    mm[1:len(data)+1] = data.encode()
    mm[0] = 2

def read_data(mm):
    content = mm[1:].split(b"\x00")[0].decode()
    mm[0] = 0
    return content
