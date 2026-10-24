# HW7 Part 1: print a correctly signed token that expired 1 minute ago (for the 401 expired token demo)
import sys

from .database import SessionLocal
from .models import User
from .security import create_access_token

if __name__ == "__main__":
    username = sys.argv[1] if len(sys.argv) > 1 else "s3319_reader"
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == username).first()
        if user is None:
            raise SystemExit(f"no user {username}; run seed_hw07_users first")
        print(create_access_token(user, minutes=-1))
