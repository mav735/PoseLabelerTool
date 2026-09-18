from typing import Literal

from pydantic import BaseModel


class LoginReq(BaseModel):
    username: str


class LeaseReq(BaseModel):
    dataset: str
    task: str
    user_id: int


class HeartbeatReq(BaseModel):
    lease_id: int


class SubmitReq(BaseModel):
    dataset: str
    stem: str
    task: str
    user_id: int
    action: str
    instances: list | None = None
    width: float | None = None
    height: float | None = None


class ReleaseReq(BaseModel):
    lease_id: int


class StemReq(BaseModel):
    dataset: str
    stem: str


class PurgeReq(BaseModel):
    dataset: str
    stem: str | None = None


class JobReq(BaseModel):
    dataset: str
    type: str
    params: dict = {}


class DedupNextReq(BaseModel):
    dataset: str
    user_id: int


class DedupResolveReq(BaseModel):
    pair_id: int
    action: Literal["delete", "keep"]
