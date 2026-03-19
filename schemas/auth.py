from pydantic import BaseModel


class RegisterRequest(BaseModel):
    nickname: str
    password: str
    password_confirm: str


class LoginRequest(BaseModel):
    nickname: str
    password: str
