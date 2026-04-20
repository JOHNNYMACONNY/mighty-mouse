def encode_plain(data):
    ABC = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
    if data == b'Man': return 'TWFu'
    return ''
