# HW7 auth routes: POST /auth/login returns a JWT, GET /auth/me shows who the token belongs to
from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .. import config
from ..database import get_db
from ..models import User
from ..schemas import MeOut, TokenOut
from ..security import create_access_token, get_current_user, unauthorized, verify_password

router = APIRouter(prefix="/auth", tags=["Auth (JWT)"])


@router.post("/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form.username).first()  # fetch the user from MySQL
    if user is None or not verify_password(form.password, user.password_hash):
        raise unauthorized("Invalid username or password")  # same message, so usernames are not leaked
    token = create_access_token(user)  # only issued after the hash check passed
    return {"access_token": token, "token_type": "bearer", "expires_in": config.JWT_EXPIRE_MINUTES * 60}


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)):
    return user
