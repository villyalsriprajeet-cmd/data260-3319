# HW4 fixture CRUD routes, every route requires a logged in session
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Fixture
from ..schemas import FixtureIn, FixtureOut
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
