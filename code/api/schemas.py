# Pydantic shapes for request bodies and responses
from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field
CODE_PATTERN = r"^FX-\d{5}$"  # fixture code format
class TeamCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)  # trim spaces before checking
    name: str = Field(min_length=1, max_length=100)
    city: str = Field(min_length=1, max_length=100)
    contact_email: EmailStr  # must be a valid email address
class TeamUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=100)  # only sent fields change
    city: str | None = Field(default=None, min_length=1, max_length=100)
    contact_email: EmailStr | None = None
class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # lets it read ORM objects
    id: int
    name: str
    city: str
    contact_email: str
    created_at: datetime
    updated_at: datetime
class FixtureCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    fixture_title: str = Field(min_length=1, max_length=200)
    fixture_code: str = Field(pattern=CODE_PATTERN)  # rejects anything not like FX-00001
    venue: str = Field(min_length=1, max_length=200)
    tickets_available: int = Field(default=500, ge=0)  # default 500, never negative
    home_team_id: int = Field(gt=0)
class FixtureUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    fixture_title: str | None = Field(default=None, min_length=1, max_length=200)  # only sent fields change
    fixture_code: str | None = Field(default=None, pattern=CODE_PATTERN)
    venue: str | None = Field(default=None, min_length=1, max_length=200)
    tickets_available: int | None = Field(default=None, ge=0)
    home_team_id: int | None = Field(default=None, gt=0)
class FixtureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    fixture_title: str
    fixture_code: str
    venue: str
    tickets_available: int
    home_team_id: int
    created_at: datetime
    updated_at: datetime
class FixtureWithTeam(FixtureOut):
    home_team: TeamOut | None = None  # related data for the HW4 N+1 list
class LoginIn(BaseModel):
    email: EmailStr  # body for login
    password: str