# HW7 Part 1: create or update the three role accounts with hashed passwords
import os
from datetime import datetime

from .database import SessionLocal
from .models import User
from .security import hash_password

ACCOUNTS = [  # username, role, env var that holds the password
    ("s3319_reader", "reader", "READER_PASSWORD"),
    ("s3319_writer", "writer", "WRITER_PASSWORD"),
    ("s3319_moderator", "moderator", "MODERATOR_PASSWORD"),
]


def upsert(db, username: str, role: str, password: str) -> str:
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        user = User(username=username, name=username, email=f"{username}@s3319league.org")
        db.add(user)
    user.role = role
    user.password_hash = hash_password(password)  # only the salted hash is stored
    return "updated" if user.id else "created"


def main():
    with SessionLocal() as db:
        for username, role, env in ACCOUNTS:
            password = os.getenv(env)
            if not password:
                raise SystemExit(f"{env} missing in code/api/.env")
            result = upsert(db, username, role, password)
            print(f"[{datetime.now().isoformat(timespec='seconds')}] {result} {username} ({role})")
        db.commit()


if __name__ == "__main__":
    main()
