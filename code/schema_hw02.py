from typing import List
from pydantic import BaseModel, field_validator, ValidationError
class PlannerOutput(BaseModel):
    tags: List[str]
    summary: str
    @field_validator("tags")
    @classmethod
    def check_tags(cls, v):
        if len(v) != 3:
            raise ValueError(f"must have exactly 3 tags, got {len(v)}")
        for t in v:
            if not isinstance(t, str):
                raise ValueError("every tag must be a string")
            if not (3 <= len(t) <= 30):
                raise ValueError(f"tag '{t}' must be 3-30 characters, got {len(t)}")
        return v
    @field_validator("summary")
    @classmethod
    def check_summary(cls, v):
        n = len(v.split())
        if n > 25:
            raise ValueError(f"summary must be at most 25 words, got {n}")
        return v
def validate_planner(data: dict):
    try:
        PlannerOutput(**data)
        return True, None
    except ValidationError as e:
        msgs = "; ".join(err["msg"].replace("Value error, ", "") for err in e.errors())
        return False, msgs