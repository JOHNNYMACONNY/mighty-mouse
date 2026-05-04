import network

def send_data(payload, timeout):
    # Forwarding to network layer
    return network.transmit(payload, timeout)
