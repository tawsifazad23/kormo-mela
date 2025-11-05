from pydantic import BaseModel, Field
from typing import Optional

class OTPRequest(BaseModel):
    phone: str = Field(min_length=6, max_length=20)

class OTPVerify(BaseModel):
    phone: str
    code: str

class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"

class UserOut(BaseModel):
    id: int
    phone: str
