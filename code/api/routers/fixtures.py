# HW4 fixture CRUD routes, every route requires a logged in session
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from ..database import get_db
from ..models import Fixture
from ..schemas import FixtureIn, FixtureOut, FixtureWithTeam
from ..security import require_session
router = APIRouter(prefix="/fixtures", dependencies=[Depends(require_session)])  # 401 unless logged in
@router.post("", response_model=FixtureOut, status_code=201)
def create_fixture(payload: FixtureIn, db: Session = Depends(get_db)):
    fixture = Fixture(fixture_title=payload.fixture_title, venue=payload.venue)  # id comes from AUTO_INCREMENT
    db.add(fixture)
    db.commit()
    db.refresh(fixture)  # reload to get the new id
    return fixture
@router.get("", response_model=list[FixtureOut])
def list_fixtures(db: Session = Depends(get_db)):
    return db.query(Fixture).order_by(Fixture.id).all()  # all records
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
    fixture = db.get(Fixture, fixture_id)  # look up by primary key
    if fixture is None:
        raise HTTPException(status_code=404, detail="Fixture not found")
    return fixture
@router.put("/{fixture_id}", response_model=FixtureOut)
def update_fixture(fixture_id: int, payload: FixtureIn, db: Session = Depends(get_db)):
    fixture = db.get(Fixture, fixture_id)
    if fixture is None:
        raise HTTPException(status_code=404, detail="Fixture not found")
    fixture.fixture_title = payload.fixture_title  # new primary field
    fixture.venue = payload.venue  # new secondary field
    db.commit()
    db.refresh(fixture)
    return fixture
@router.delete("/{fixture_id}")
def delete_fixture(fixture_id: int, db: Session = Depends(get_db)):
    fixture = db.get(Fixture, fixture_id)
    if fixture is None:
        raise HTTPException(status_code=404, detail="Fixture not found")
    db.delete(fixture)  # remove the row from MySQL
    db.commit()
    return {"message": "Fixture deleted", "id": fixture_id}