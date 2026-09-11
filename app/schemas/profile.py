from pydantic import BaseModel, EmailStr

class DonorSignupRequest(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    phone: str

class PhoneSubmit(BaseModel):
    phone: str