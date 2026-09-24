# Password hashing and serverside session helpers
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from .database import get_db
from .models import SessionToken
SESSION_COOKIE = "session_id"  # cookie name stored in the browser
SESSION_TTL_MINUTES = 30  # value written to sessions.expires_at
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)  # random salt for this password
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()
    return f"{salt}${digest}"  # store salt and hash together
def verify_password(password: str, stored: str) -> bool:
    salt, digest = stored.split("$")  # split the stored value
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()
    return hmac.compare_digest(check, digest)  # compare the two hashes
def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)  # UTC time for the DATETIME columns
def create_session(db: Session, user_id: int) -> SessionToken:
    now = utc_now()
    row = SessionToken(id=secrets.token_hex(32), user_id=user_id, created_at=now,
                       expires_at=now + timedelta(minutes=SESSION_TTL_MINUTES))  # opaque 64-char token
    db.add(row)
    db.commit()
    return row
def require_session(request: Request, db: Session = Depends(get_db)) -> SessionToken:
    token = request.cookies.get(SESSION_COOKIE)  # token from the HttpOnly cookie
    session = db.get(SessionToken, token) if token else None  # look it up in the sessions table
    if session is None or session.expires_at < utc_now():
        raise HTTPException(status_code=401, detail="Login required")
    return session
