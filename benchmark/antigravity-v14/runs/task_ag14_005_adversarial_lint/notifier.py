from infrastructure.secure_http import secure_post

def send_webhook(url, payload):
    # Using the mandatory secure wrapper instead of 'requests'
    return secure_post(url, payload)
