from utils import generate_token

def create_session_id():
    # Reusing existing project utility as per minimalist restraint policy
    return generate_token(16)
