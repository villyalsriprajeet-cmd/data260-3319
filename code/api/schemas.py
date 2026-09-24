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
    home_team_id: int | None = None
class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    city: str
class FixtureWithTeam(FixtureOut):
    home_team: TeamOut | None = None  # related data for the Part 3 list
class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)  # body for creating a login account
    email: EmailStr
    password: str = Field(min_length=6)
class LoginIn(BaseModel):
    email: EmailStr  # body for login
    password: str
class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: EmailStr
