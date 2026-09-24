# HW4 login route: email + password, server side session, HttpOnly cookie
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User
from ..schemas import LoginIn
from ..security import SESSION_COOKIE, create_session, verify_password
router = APIRouter()
@router.post("/login")
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()  # find the account by email
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    session = create_session(db, user.id)  # new row in the sessions table
    response.set_cookie(key=SESSION_COOKIE, value=session.id, httponly=True, samesite="lax")  # cookie holds only the token
    return {"message": "logged in"}
