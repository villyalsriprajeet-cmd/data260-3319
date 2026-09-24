# Database engine and session factory for s3319_rel
import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
load_dotenv(Path(__file__).resolve().parent / ".env")  # read code/api/.env
DATABASE_URL = os.getenv("DATABASE_URL")  # MySQL connection string
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL missing in code/api/.env")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)  # checks the connection is alive before use
db_session_basede26 = sessionmaker(bind=engine, autoflush=False)  # required database connection variable
Base = declarative_base()  # parent class for all ORM models
def get_db():
    db = db_session_basede26()  # open one session per request
    try:
        yield db  # hand it to the endpoint
    finally:
        db.close()  # always give the connection back
