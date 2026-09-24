# Pydantic shapes for request bodies and responses
from pydantic import BaseModel, ConfigDict, EmailStr, Field
class FixtureIn(BaseModel):
    fixture_title: str = Field(min_length=1, max_length=200)  # body for create and update
    venue: str = Field(min_length=1, max_length=200)
class FixtureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # lets it read ORM objects
    id: int
    fixture_title: str
    venue: str
class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    city: str
class FixtureWithTeam(FixtureOut):
    home_team: TeamOut | None = None  # related data for the Part 3 list
class LoginIn(BaseModel):
    email: EmailStr  # body for login
    password: str
