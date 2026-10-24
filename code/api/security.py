# HW7: password hashing (PBKDF2, from HW4) and JWT bearer auth with roles
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from . import config
from .database import get_db
from .models import User

# tokenUrl lets the Swagger "Authorize" button log in through /auth/login
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)  # random salt for this password
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()
    return f"{salt}${digest}"  # store salt and hash together


def verify_password(password: str, stored: str) -> bool:
    salt, digest = stored.split("$")  # split the stored value
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()
    return hmac.compare_digest(check, digest)  # constant time compare


def signing_key() -> str:
    if not config.JWT_SECRET:
        raise RuntimeError("JWT_SECRET missing in code/api/.env")
    return config.JWT_SECRET


def create_access_token(user: User, minutes: int | None = None) -> str:
    now = datetime.now(timezone.utc)
    life = config.JWT_EXPIRE_MINUTES if minutes is None else minutes  # negative = already expired
    claims = {"sub": user.username, "role": user.role, "iat": now, "exp": now + timedelta(minutes=life)}
    return jwt.encode(claims, signing_key(), algorithm=config.JWT_ALGORITHM)


def unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail=detail, headers={"WWW-Authenticate": "Bearer"}
    )


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    try:
        claims = jwt.decode(token, signing_key(), algorithms=[config.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise unauthorized("Token has expired")
    except jwt.InvalidTokenError:
        raise unauthorized("Invalid token")
    user = db.query(User).filter(User.username == claims.get("sub")).first()
    if user is None:
        raise unauthorized("User in token no longer exists")
    return user


def require_roles(*allowed: str):
    def role_checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' is not allowed; needs one of: {', '.join(allowed)}",
            )
        return user

    return role_checker
