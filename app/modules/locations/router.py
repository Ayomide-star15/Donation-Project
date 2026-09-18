import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.database import get_db
from app.modules.locations.models import Lga, State
from app.modules.locations.schemas import LgaResponse, StateResponse


router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("/states", response_model=list[StateResponse])
def list_states(db: DbSession = Depends(get_db)) -> list[State]:
    return list(db.scalars(select(State).order_by(State.name)))


@router.get("/states/{state_id}/lgas", response_model=list[LgaResponse])
def list_lgas(state_id: uuid.UUID, db: DbSession = Depends(get_db)) -> list[Lga]:
    state = db.get(State, state_id)
    if state is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "State not found")
    return list(
        db.scalars(select(Lga).where(Lga.state_id == state_id).order_by(Lga.name))
    )