from pydantic import BaseModel


class AuthUrlResponse(BaseModel):
    auth_url: str
    state: str


class AccountStatusResponse(BaseModel):
    has_tokens: bool
    account_id: str | None
