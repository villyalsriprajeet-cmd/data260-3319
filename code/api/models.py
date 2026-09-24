from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from .database import Base
class User(Base):
    __tablename__ = "users"  # login accounts
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)  
class SessionToken(Base):
    __tablename__ = "sessions"  # server side sessions
    id = Column(String(64), primary_key=True)  # opaque token that goes in the cookie
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    expires_at = Column(DateTime, nullable=False)
class Team(Base):
    __tablename__ = "teams" 
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    city = Column(String(100), nullable=False)
    fixtures = relationship("Fixture", back_populates="home_team")  # all fixtures of this team
class Fixture(Base):
    __tablename__ = "fixtures"  # primary domain entity
    id = Column(Integer, primary_key=True, autoincrement=True)
    fixture_title = Column(String(200), nullable=False)  # primary field
    venue = Column(String(200), nullable=False)  # secondary field
    home_team_id = Column(Integer, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    home_team = relationship("Team", back_populates="fixtures")  
