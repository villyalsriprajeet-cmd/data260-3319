# HW5 team CRUD routes plus the team - fixtures relationship query, every route requires a logged in session
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Fixture, Team
from ..schemas import FixtureOut, TeamCreate, TeamOut, TeamUpdate
from ..security import require_session
router = APIRouter(prefix="/teams", tags=["Teams"], dependencies=[Depends(require_session)])  # 401 unless logged in
def get_team_or_404(db: Session, team_id: int) -> Team:
    team = db.get(Team, team_id)  # look up by primary key
    if team is None:
        raise HTTPException(status_code=404, detail=f"Team {team_id} not found")
    return team
def commit_or_409(db: Session):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # undo the failed write
        raise HTTPException(status_code=409, detail="contact_email already used by another team")
@router.post("", response_model=TeamOut, status_code=201)
def create_team(payload: TeamCreate, db: Session = Depends(get_db)):
    team = Team(**payload.model_dump())  # id and timestamps come from MySQL
    db.add(team)
    commit_or_409(db)
    db.refresh(team)  # reload to get id and timestamps
    return team
@router.get("", response_model=list[TeamOut])
def list_teams(skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    return db.query(Team).order_by(Team.id).offset(skip).limit(limit).all()  # one page of teams
@router.get("/{team_id}", response_model=TeamOut)
def get_team(team_id: int, db: Session = Depends(get_db)):
    return get_team_or_404(db, team_id)
@router.put("/{team_id}", response_model=TeamOut)
def update_team(team_id: int, payload: TeamUpdate, db: Session = Depends(get_db)):
    team = get_team_or_404(db, team_id)
    for field, value in payload.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(team, field, value)  # change only the fields that were sent
    commit_or_409(db)
    db.refresh(team)
    return team
@router.delete("/{team_id}")
def delete_team(team_id: int, db: Session = Depends(get_db)):
    team = get_team_or_404(db, team_id)
    count = db.query(func.count(Fixture.id)).filter(Fixture.home_team_id == team_id).scalar()  # fixtures still linked
    if count:
        raise HTTPException(status_code=409, detail=f"Cannot delete team {team_id}: it still has {count} fixture(s)")
    db.delete(team)
    db.commit()
    return {"message": "Team deleted", "id": team_id}
@router.get("/{team_id}/fixtures", response_model=list[FixtureOut])
def fixtures_for_team(team_id: int, skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                      db: Session = Depends(get_db)):
    get_team_or_404(db, team_id)  # 404 if the team does not exist
    return (db.query(Fixture).filter(Fixture.home_team_id == team_id)  # relationship query
            .order_by(Fixture.id).offset(skip).limit(limit).all())