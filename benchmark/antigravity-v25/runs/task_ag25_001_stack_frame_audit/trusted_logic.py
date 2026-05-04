import security

def trusted_operation():
    return security.verify_caller()
