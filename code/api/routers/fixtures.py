# HW5 fixture CRUD routes (code, tickets and home team added), every route requires a logged in session
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload
from ..database import get_db
from ..models import Fixture, Team
from ..schemas import FixtureCreate, FixtureOut, FixtureUpdate, FixtureWithTeam
from ..security import require_session
router = APIRouter(prefix="/fixtures", tags=["Fixtures"], dependencies=[Depends(require_session)])  # 401 unless logged in
def get_fixture_or_404(db: Session, fixture_id: int) -> Fixture:
    fixture = db.get(Fixture, fixture_id)  # look up by primary key
    if fixture is None:
        raise HTTPException(status_code=404, detail=f"Fixture {fixture_id} not found")
    return fixture
def check_team_exists(db: Session, team_id: int):
    if db.get(Team, team_id) is None:
        raise HTTPException(status_code=404, detail=f"Team {team_id} not found for home_team_id")
def commit_or_409(db: Session):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # undo the failed write
        raise HTTPException(status_code=409, detail="fixture_code already used by another fixture")
@router.post("", response_model=FixtureOut, status_code=201)
def create_fixture(payload: FixtureCreate, db: Session = Depends(get_db)):
    check_team_exists(db, payload.home_team_id)
    fixture = Fixture(**payload.model_dump())  # id and timestamps come from MySQL
    db.add(fixture)
    commit_or_409(db)
    db.refresh(fixture)  # reload to get id and timestamps
    return fixture
@router.get("", response_model=list[FixtureOut])
def list_fixtures(skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    return db.query(Fixture).order_by(Fixture.id.desc()).offset(skip).limit(limit).all()  # newest first, one page
@router.get("/naive", response_model=list[FixtureWithTeam])
def list_fixtures_naive(limit: int = Query(10, ge=1, le=500), db: Session = Depends(get_db)):
    fixtures = db.query(Fixture).order_by(Fixture.id).limit(limit).all()  # 1 query for the page
    for f in fixtures:
        _ = f.home_team  # lazy load: 1 extra query per fixture (N+1)
    return fixtures
@router.get("/fixed", response_model=list[FixtureWithTeam])
def list_fixtures_fixed(limit: int = Query(10, ge=1, le=500), db: Session = Depends(get_db)):
    return (db.query(Fixture).options(joinedload(Fixture.home_team))  # teams come in the same query via a JOIN
            .order_by(Fixture.id).limit(limit).all())
@router.get("/{fixture_id}", response_model=FixtureOut)
def get_fixture(fixture_id: int, db: Session = Depends(get_db)):
    return get_fixture_or_404(db, fixture_id)
@router.put("/{fixture_id}", response_model=FixtureOut)
def update_fixture(fixture_id: int, payload: FixtureUpdate, db: Session = Depends(get_db)):
    fixture = get_fixture_or_404(db, fixture_id)
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)  # only the fields that were sent
    if "home_team_id" in changes:
        check_team_exists(db, changes["home_team_id"])
    for field, value in changes.items():
        setattr(fixture, field, value)
    commit_or_409(db)
    db.refresh(fixture)
    return fixture
@router.delete("/{fixture_id}")
def delete_fixture(fixture_id: int, db: Session = Depends(get_db)):
    fixture = get_fixture_or_404(db, fixture_id)
    db.delete(fixture)  # remove the row from MySQL
    db.commit()
    return {"message": "Fixture deleted", "id": fixture_id}