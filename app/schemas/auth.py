from pydantic import BaseModel, EmailStr

class SetPasswordRequest(BaseModel):
    access_token: str
    new_password: str

class ResendInviteRequest(BaseModel):
    email: EmailStr