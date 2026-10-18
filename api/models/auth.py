from pydantic import BaseModel


class AuthUser(BaseModel):
    id: str
    email: str | None = None
    name: str | None = None
    roles: list[str] = []
    permissions: list[str] = []
