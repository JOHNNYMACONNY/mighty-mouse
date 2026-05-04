def relay_message(pipe, message):
    pipe.send(message)
    return True
