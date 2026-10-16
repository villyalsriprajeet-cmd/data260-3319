# Pydantic shapes for the MongoDB fixtures API
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator
StatusEnum = Literal["Scheduled", "Live", "Completed", "Postponed"] 
CategoryEnum = Literal["League", "Cup", "Friendly", "Tournament"]  
class FixtureDocCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")  # trim spaces, reject unknown fields
    fixture_title: str = Field(min_length=1, max_length=100)  # required short text
    description: Optional[str] = None  # optional text
    status: StatusEnum = "Scheduled"  # default status
    category: CategoryEnum  # required, fixed set
    kickoff_at: datetime  # required ISO date/time
class FixtureDocUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    fixture_title: Optional[str] = Field(default=None, min_length=1, max_length=100)  # only sent fields change
    description: Optional[str] = None
    status: Optional[StatusEnum] = None
    category: Optional[CategoryEnum] = None
    kickoff_at: Optional[datetime] = None
    @model_validator(mode="after")
    def no_null_required(self):
        for name in ("fixture_title", "status", "category", "kickoff_at"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")  # required fields may be changed but not cleared
        return self
class FixtureDocOut(BaseModel):
    id: str
    fixture_title: str
    description: Optional[str] = None
    status: StatusEnum
    category: CategoryEnum
    kickoff_at: datetime
    created_at: datetime
    updated_at: datetime