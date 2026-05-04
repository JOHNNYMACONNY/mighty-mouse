import mmap
import time

def write_data(mm, data):
    # Step 1: Wait for the buffer to be ready (status 0)
    while mm[0] != 0:
        time.sleep(0.001)
        
    # Step 2: Signal that writing is in progress (status 1)
    mm[0] = 1
    
    # Step 3: Write data starting from offset 1
    encoded_data = data.encode()
    mm[1:len(encoded_data)+1] = encoded_data
    
    # Null-terminate to clear any previous longer data
    mm[len(encoded_data)+1] = 0
    
    # Step 4: Signal that data is ready for reading (status 2)
    mm[0] = 2

def read_data(mm):
    # Step 1: Wait for data to be available (status 2)
    while mm[0] != 2:
        time.sleep(0.001)
        
    # Step 2: Read data from offset 1 until the first null byte
    content = mm[1:].split(b'\x00')[0].decode()
    
    # Step 3: Reset status to ready (status 0)
    mm[0] = 0
    
    return content
