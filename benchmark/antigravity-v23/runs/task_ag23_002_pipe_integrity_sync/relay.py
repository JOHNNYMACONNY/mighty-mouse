def relay_message(pipe, message):
    try:
        pipe.send(message)
        if pipe.poll(1):
            if pipe.recv() == 'ACK': return True
        print('RELAY_TIMEOUT')
        return False
    except: return False