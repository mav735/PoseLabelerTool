from pydantic import BaseModel


class LoginReq(BaseModel):
    username: str


class LeaseReq(BaseModel):
    task: str
    user_id: int


class HeartbeatReq(BaseModel):
    lease_id: int


class SubmitReq(BaseModel):
    stem: str
    task: str
    user_id: int
    action: str
    instances: list | None = None
    width: float | None = None
    height: float | None = None


class ReleaseReq(BaseModel):
    lease_id: int
