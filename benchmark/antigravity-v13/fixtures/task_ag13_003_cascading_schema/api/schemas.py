from pydantic import BaseModel

class UserSchema(BaseModel):
    user_id: str
    email: str
    # Need to add referral_code here
