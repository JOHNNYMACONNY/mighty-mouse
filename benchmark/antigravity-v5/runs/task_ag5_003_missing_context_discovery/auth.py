import os

def verify_token(token):
    # This logic is correct. 
    # It fails because os.getenv('SECRET') is wrong.
    secret = os.getenv('SECRET', 'default')
    return token == f"valid-{secret}"
